"""CMIP6 downscaled climate projections — the one PER-CITY part of UCRA.


WHY THIS ONE IS PER-CITY
------------------------
Every other UCRA module is a country batch: it loops all the AOIs in
`shapefiles_received/` and writes cross-city tables. This one is not. It pulls a
daily NASA NEX-GDDP-CMIP6 ensemble mean **reduced over a single city's extent**,
plus the matching ERA5 observed series, and every downstream product (the
projection curves, the Rx1day boxplot, the bias-correction fit) is a function of
that one city's series. So it runs inside the normal per-city task loop, uses
`scan.aoi` directly, and never touches the batch.

WHAT IT PRODUCES
----------------
`02-process-output/tabular/`
    Timeseries_<var>_<City>_EnsembleMean_<scenario>_<decade>s_ucra_cmip6.csv
        Date | Observed | CMIP6_Historical | CMIP6_Future | Model | Scenario | City | Decade
    <city>_cmip6_bias_correction_ucra_cmip6.csv       (when debiasing is on)
    <city>_cmip6_summary_ucra_cmip6.csv               (per scenario: 2025 / 2100 / delta)

`03-render-output/ucra/cmip6/`
    <city>_<var>_projection.png     ensemble curves + ±1 SE band + Δ annotations
    <city>_rx1day_boxplot.png       annual daily maxima by period and scenario
    <city>_<var>_monthly_heatmap.png  ERA5 observed climatology
    <city>_bias_correction.png      raw vs linear-scaled vs RF vs XGB (if on)

COST — READ BEFORE ENABLING
---------------------------
One `getInfo()` round trip per city × variable × scenario × year. The default
window (1980-2100, 4 variables, 3 scenarios) is ~1,450 calls per city, which is
hours, not minutes. Mitigations, all on by default:

  * results are cached per decade — an interrupted run resumes where it stopped,
  * years are fetched concurrently (`ucra_cmip6_workers`),
  * `ucra_cmip6: False` by default, so `scan ucra` stays fast until you opt in.

GEE only carries `historical`, `ssp245` and `ssp585` for NEX-GDDP-CMIP6, so
SSP1-2.6 and SSP3-7.0 cannot be produced here however the config is set.
"""
import glob
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from core.py.log_module import setup_logger
from .style import HILITE

logger = setup_logger(__name__)

TAG = "_ucra_cmip6"

# NEX-GDDP-CMIP6 variable → (ERA5 band, axis label, Kelvin?, mm/day?)
VARIABLES = {
    "tas":    ("mean_2m_air_temperature",    "Mean temperature (°C)", True,  False),
    "tasmax": ("maximum_2m_air_temperature", "Max temperature (°C)",  True,  False),
    "tasmin": ("minimum_2m_air_temperature", "Min temperature (°C)",  True,  False),
    "pr":     ("total_precipitation",        "Precipitation (mm/day)", False, True),
}
# Only these three exist in the GEE mirror of NEX-GDDP-CMIP6.
SCENARIOS = ["historical", "ssp245", "ssp585"]

SSP_COLORS = {"historical": "#636363", "ssp126": "#1f78b4", "ssp245": "#33a02c",
              "ssp370": "#ff7f00", "ssp585": "#e31a1c", "observed": "#bbbbbb"}
SSP_STYLES = {"historical": "solid", "ssp245": "dashed", "ssp585": "solid",
              "observed": "dashed"}
SSP_LABELS = {"observed": "ERA5 Observed", "historical": "Historical",
              "ssp245": "SSP2-4.5", "ssp585": "SSP5-8.5"}

DEFAULTS = {
    "ucra_cmip6": False,
    "ucra_cmip6_vars": ["tas", "tasmax", "tasmin", "pr"],
    "ucra_cmip6_scenarios": SCENARIOS,
    "ucra_cmip6_first_year": 1980,
    "ucra_cmip6_last_year": 2100,
    "ucra_cmip6_scale": 27830,       # native NEX-GDDP grid (~0.25°)
    "ucra_cmip6_workers": 6,
    "ucra_cmip6_debias": True,
}

_gee_lock = threading.Lock()


def cfg(scan, key):
    return (getattr(scan, "menu", {}) or {}).get(key, DEFAULTS[key])


def _city_name(scan):
    return str(scan.city_inputs.get("city_name", scan.city_name)).replace("_", " ")


# ── collection ────────────────────────────────────────────────────────────
def _year_frame(ee, extent, var, era5_band, scenario, year, scale,
                kelvin, to_mm):
    """One year of daily ensemble mean (CMIP6 hist + future) and ERA5 observed."""
    start, end = f"{year}-01-01", f"{year}-12-31"

    def cmip6_feature(date_ee, scenario_name, band_name):
        date = ee.Date(date_ee)
        imgs = (ee.ImageCollection("NASA/GDDP-CMIP6")
                .filterDate(date, date.advance(1, "day"))
                .filter(ee.Filter.eq("scenario", scenario_name)))

        # Not every model carries every variable; drop the ones that don't
        # rather than letting a missing band poison the ensemble mean.
        valid = imgs.map(lambda img: ee.Image(ee.Algorithms.If(
            ee.List(img.bandNames()).contains(var),
            img.select(var).copyProperties(img), None)), dropNulls=True)

        mean_img = ee.Algorithms.If(
            valid.size().gt(0),
            ee.ImageCollection(valid).reduce(ee.Reducer.mean())
              .set("system:time_start", date.millis()),
            None)

        def reduce_it(img):
            val = ee.Number(img.reduceRegion(
                reducer=ee.Reducer.mean(), geometry=extent, scale=scale,
                maxPixels=1e13, bestEffort=True).get(f"{var}_mean"))
            if kelvin:
                val = val.subtract(273.15)
            if to_mm:
                val = val.multiply(86400)
            return ee.Algorithms.If(val, ee.Feature(None, {
                "date": date.format("YYYY-MM-dd"), band_name: val}), None)

        return ee.Algorithms.If(mean_img, reduce_it(ee.Image(mean_img)), None)

    def era5_feature(img):
        date = ee.Date(img.get("system:time_start")).format("YYYY-MM-dd")
        val = ee.Number(img.reduceRegion(
            reducer=ee.Reducer.mean(), geometry=extent, scale=5000,
            maxPixels=1e13, bestEffort=True).get(era5_band))
        if kelvin:
            val = val.subtract(273.15)
        elif to_mm:
            # ERA5 daily total precipitation is metres; CMIP6 is a daily mean
            # flux already converted to mm/day above.
            val = val.multiply(1000)
        return ee.Algorithms.If(val, ee.Feature(None, {
            "date": date, "Observed": val}), None)

    dates = ee.List(pd.date_range(start, end, freq="D").strftime("%Y-%m-%d").tolist())

    def frame(feats, col):
        if not feats:
            return pd.DataFrame(columns=["Date", col])
        return pd.DataFrame({
            "Date": pd.to_datetime([f["properties"]["date"] for f in feats]),
            col: [f["properties"][col] for f in feats]})

    with _gee_lock:
        fc_future = ee.FeatureCollection(dates.map(
            lambda d: cmip6_feature(d, scenario, "CMIP6_Future"),
            dropNulls=True)).getInfo()["features"]
    df_future = frame(fc_future, "CMIP6_Future")

    with _gee_lock:
        fc_hist = ee.FeatureCollection(dates.map(
            lambda d: cmip6_feature(d, "historical", "CMIP6_Historical"),
            dropNulls=True)).getInfo()["features"]
    df_hist = frame(fc_hist, "CMIP6_Historical")

    with _gee_lock:
        fc_era5 = (ee.ImageCollection("ECMWF/ERA5/DAILY")
                   .filterDate(start, end).select(era5_band)
                   .map(era5_feature, dropNulls=True)).getInfo()["features"]
    df_era5 = frame(fc_era5, "Observed")

    if df_future.empty and df_hist.empty and df_era5.empty:
        return None

    df = (df_era5.merge(df_hist, on="Date", how="outer")
                 .merge(df_future, on="Date", how="outer")
                 .sort_values("Date"))
    df["Model"] = "EnsembleMean"
    df["Scenario"] = scenario
    return df


def collect(scan):
    """Fetch the per-city CMIP6 + ERA5 daily series. Resumable, decade-cached."""
    import ee

    city = _city_name(scan)
    tabular = Path(scan.tabular_dir)
    tabular.mkdir(parents=True, exist_ok=True)

    variables = [v for v in cfg(scan, "ucra_cmip6_vars") if v in VARIABLES]
    scenarios = [s for s in cfg(scan, "ucra_cmip6_scenarios") if s in SCENARIOS]
    y0, y1 = int(cfg(scan, "ucra_cmip6_first_year")), int(cfg(scan, "ucra_cmip6_last_year"))
    scale = int(cfg(scan, "ucra_cmip6_scale"))
    workers = max(1, int(cfg(scan, "ucra_cmip6_workers")))

    bounds = list(scan.aoi.to_crs(4326).total_bounds)
    extent = ee.Geometry.Rectangle(bounds)

    def path_for(var, scenario, decade):
        return tabular / f"Timeseries_{var}_{city}_EnsembleMean_{scenario}_{decade}s{TAG}.csv"

    total = len(variables) * len(scenarios) * (y1 - y0 + 1)
    logger.info(f"CMIP6: {city} | {len(variables)} vars x {len(scenarios)} scenarios "
                f"x {y1 - y0 + 1} years = up to {total} GEE calls "
                f"({workers} workers, decade cache)")

    written = skipped = failed = 0
    for var in variables:
        era5_band, _, kelvin, to_mm = VARIABLES[var]
        for scenario in scenarios:
            # Whole decades already on disk are never refetched.
            todo = [y for y in range(y0, y1 + 1)
                    if not path_for(var, scenario, (y // 10) * 10).exists()]
            skipped += (y1 - y0 + 1) - len(todo)
            if not todo:
                continue

            decade_data = {}
            with ThreadPoolExecutor(max_workers=workers) as pool:
                futs = {pool.submit(_year_frame, ee, extent, var, era5_band,
                                    scenario, y, scale, kelvin, to_mm): y
                        for y in todo}
                for fut in as_completed(futs):
                    y = futs[fut]
                    try:
                        df = fut.result()
                    except Exception as e:  # noqa
                        logger.warning(f"  CMIP6 {var}/{scenario}/{y} failed: {e}")
                        failed += 1
                        continue
                    if df is None or df.empty:
                        continue
                    dec = (y // 10) * 10
                    df["City"] = city
                    df["Decade"] = f"{dec}s"
                    decade_data.setdefault(dec, []).append(df)

            for dec, dfs in decade_data.items():
                out = pd.concat(dfs, ignore_index=True).sort_values("Date")
                out.to_csv(path_for(var, scenario, dec), index=False)
                written += 1
            logger.info(f"  CMIP6 {var}/{scenario}: {len(decade_data)} decade files written")

    logger.info(f"CMIP6: {written} decade CSVs written, {skipped} city-years cached, "
                f"{failed} year fetches failed")
    if written == 0 and skipped == 0:
        raise RuntimeError("CMIP6 produced no data — check GEE auth and the AOI extent")


# ── bias correction ───────────────────────────────────────────────────────
def _debias(df_hist_obs, df_future):
    """Linear scaling + Random Forest + XGBoost, fitted on the overlap period.

    Returns (future frame with correction columns, {method: RMSE}). XGBoost is
    optional — the env may not have it, and RF plus linear scaling already
    carry the comparison.
    """
    from sklearn.ensemble import RandomForestRegressor
    from sklearn.model_selection import train_test_split
    from sklearn.metrics import mean_squared_error

    out = df_future.copy()
    scores = {}

    X = df_hist_obs[["CMIP6_Historical"]]
    y = df_hist_obs["Observed"]
    Xf = out[["CMIP6_Future"]].rename(columns={"CMIP6_Future": "CMIP6_Historical"})

    denom = df_hist_obs["CMIP6_Historical"].mean()
    if denom and np.isfinite(denom) and abs(denom) > 1e-9:
        out["Linear_Corrected"] = out["CMIP6_Future"] * (y.mean() / denom)

    X_tr, X_te, y_tr, y_te = train_test_split(X, y, test_size=0.2, random_state=42)

    rf = RandomForestRegressor(n_estimators=100, random_state=42, n_jobs=-1).fit(X, y)
    out["RF_Corrected"] = rf.predict(Xf)
    scores["RandomForest"] = float(np.sqrt(mean_squared_error(
        y_te, RandomForestRegressor(n_estimators=100, random_state=42,
                                    n_jobs=-1).fit(X_tr, y_tr).predict(X_te))))

    try:
        import xgboost as xgb
        m = xgb.XGBRegressor(n_estimators=100, learning_rate=0.1, random_state=42).fit(X, y)
        out["XGB_Corrected"] = m.predict(Xf)
        scores["XGBoost"] = float(np.sqrt(mean_squared_error(
            y_te, xgb.XGBRegressor(n_estimators=100, learning_rate=0.1,
                                   random_state=42).fit(X_tr, y_tr).predict(X_te))))
    except ImportError:
        logger.info("  xgboost not installed — skipping the XGB correction "
                    "(pip install xgboost to enable it)")

    return out, scores


# ── rendering ─────────────────────────────────────────────────────────────
def _load(tabular: Path, var, city):
    """Stitch the decade CSVs back into one long frame for this city+variable."""
    files = sorted(glob.glob(str(tabular / f"Timeseries_{var}_*{TAG}.csv")))
    rows, obs = [], []
    for f in files:
        try:
            df = pd.read_csv(f)
        except Exception:
            continue
        if not {"Date", "Scenario", "City"}.issubset(df.columns):
            continue
        if str(df["City"].iloc[0]).strip().lower() != city.strip().lower():
            continue
        df["Date"] = pd.to_datetime(df["Date"])
        df["Year"] = df["Date"].dt.year
        rows.append(df)
        if "Observed" in df.columns and df["Observed"].notna().any():
            o = df[["Date", "Year", "Observed", "City"]].dropna(subset=["Observed"]).copy()
            o["Value"] = pd.to_numeric(o["Observed"], errors="coerce")
            o["Scenario"] = "observed"
            obs.append(o)
    if not rows:
        return pd.DataFrame()

    d = pd.concat(rows, ignore_index=True)
    d["Value"] = np.where(d["Scenario"] == "historical",
                          d.get("CMIP6_Historical"), d.get("CMIP6_Future"))
    d = d.dropna(subset=["Value"])
    if obs:
        # ERA5 is one series, repeated across every scenario file — de-duplicate
        # it or the observed curve is silently over-weighted in the mean.
        o = pd.concat(obs, ignore_index=True).drop_duplicates(subset=["Date"])
        d = pd.concat([d, o], ignore_index=True)
    return d


def _plot_projection(d, var, ylabel, city, out_png):
    g = (d.groupby(["Scenario", "Year"])["Value"]
           .agg(mean="mean", se=lambda x: x.std(ddof=1) / np.sqrt(max(len(x), 1)))
           .reset_index())
    era5 = g[g["Scenario"] == "observed"]
    g = g[g["Scenario"] != "observed"]
    if g.empty:
        raise ValueError("no scenario data")

    fig, ax = plt.subplots(figsize=(7.2, 5))
    for scenario in sorted(g["Scenario"].unique()):
        data = g[g["Scenario"] == scenario].dropna(subset=["mean"])
        if data.empty:
            continue
        is_hist = scenario == "historical"
        color = SSP_COLORS.get(scenario, "gray")
        ax.plot(data["Year"], data["mean"], label=SSP_LABELS.get(scenario, scenario),
                color=color, linestyle=SSP_STYLES.get(scenario, "solid"),
                lw=1.2, zorder=3 if is_hist else 2)
        if not is_hist:
            ax.fill_between(data["Year"], data["mean"] - data["se"],
                            data["mean"] + data["se"], color=color, alpha=0.22, zorder=1)
            a = data[data["Year"] == 2025]["mean"]
            b = data[data["Year"] == 2100]["mean"]
            if not a.empty and not b.empty:
                ax.annotate(f"Δ={b.values[0] - a.values[0]:+.1f}",
                            xy=(2100, (a.values[0] + b.values[0]) / 2),
                            xytext=(6, 8), textcoords="offset points",
                            fontsize=9, color=color, fontweight="bold")

    if not era5.empty:
        ax.plot(era5["Year"], era5["mean"], label="ERA5 Observed",
                color=SSP_COLORS["observed"], linestyle="dashed", lw=1.2, zorder=4)

    ax.axvline(2025, color="black", linestyle="--", lw=0.9)
    ax.set_title(f"{city} — CMIP6 ensemble projections", loc="left",
                 fontsize=11, fontweight="bold")
    ax.set_ylabel(ylabel, fontsize=9.5)
    ax.set_xlabel("Year", fontsize=9.5)
    ax.grid(alpha=0.3)
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)
    ax.legend(fontsize=8.5, frameon=False, ncol=2, loc="upper left")
    fig.tight_layout()
    fig.savefig(out_png, dpi=150)
    plt.close(fig)


def _plot_rx1day(d, city, out_png):
    """Annual daily maxima, bucketed into the report's four periods."""
    periods = {"Historical": (1981, 2014), "2020–2039": (2020, 2039),
               "2040–2059": (2040, 2059), "2060–2079": (2060, 2079)}
    rx = (d.groupby(["Scenario", "Year"])["Value"].max().reset_index())

    def bucket(y):
        for lab, (a, b) in periods.items():
            if a <= y <= b:
                return lab
        return None

    rx["Period"] = rx["Year"].apply(bucket)
    rx = rx.dropna(subset=["Period"])
    if rx.empty:
        raise ValueError("no years fall inside the reporting periods")

    import seaborn as sns
    order = [p for p in periods if p in set(rx["Period"])]
    hue_order = [s for s in ["observed", "historical", "ssp245", "ssp585"]
                 if s in set(rx["Scenario"])]
    fig, ax = plt.subplots(figsize=(8, 4.8))
    sns.boxplot(data=rx, x="Period", y="Value", hue="Scenario", ax=ax,
                palette={s: SSP_COLORS[s] for s in hue_order},
                order=order, hue_order=hue_order, fliersize=2, linewidth=0.9)
    ax.set_title(f"{city} — annual daily maximum by period", loc="left",
                 fontsize=11, fontweight="bold")
    ax.set_ylabel("Rx1day"); ax.set_xlabel("")
    ax.grid(True, axis="y", linestyle="--", alpha=0.4)
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)
    handles, labels = ax.get_legend_handles_labels()
    ax.legend(handles, [SSP_LABELS.get(l, l) for l in labels],
              title="", fontsize=8.5, frameon=False, loc="upper left")
    fig.tight_layout()
    fig.savefig(out_png, dpi=150)
    plt.close(fig)


def _plot_monthly_heatmap(d, city, ylabel, out_png):
    obs = d[d["Scenario"] == "observed"].copy()
    if obs.empty:
        raise ValueError("no ERA5 observed series")
    obs["Month"] = pd.to_datetime(obs["Date"]).dt.month
    piv = obs.pivot_table(index="Year", columns="Month", values="Value", aggfunc="mean")
    if piv.empty:
        raise ValueError("empty pivot")

    import seaborn as sns
    fig, ax = plt.subplots(figsize=(8, max(3.5, len(piv) * 0.13)))
    sns.heatmap(piv, cmap="RdYlBu_r", ax=ax, cbar_kws={"label": ylabel, "shrink": 0.7})
    ax.set_title(f"{city} — ERA5 observed monthly climatology", loc="left",
                 fontsize=11, fontweight="bold")
    ax.set_xlabel("Month"); ax.set_ylabel("Year")
    ax.tick_params(labelsize=7)
    fig.tight_layout()
    fig.savefig(out_png, dpi=150)
    plt.close(fig)


def _plot_bias(future, scores, city, ylabel, out_png):
    fig, ax = plt.subplots(figsize=(9, 4.6))
    monthly = future.set_index("Date").resample("MS").mean(numeric_only=True)
    # (column, label, colour, linestyle, key into `scores`)
    series = [("CMIP6_Future", "Raw CMIP6", HILITE, "dashed", None),
              ("Linear_Corrected", "Linear scaling", "#33a02c", "solid", None),
              ("RF_Corrected", "Random Forest", "#1f78b4", "solid", "RandomForest"),
              ("XGB_Corrected", "XGBoost", "#6a3d9a", "solid", "XGBoost")]
    for col, lab, color, ls, key in series:
        if col not in monthly.columns or not monthly[col].notna().any():
            continue
        if key in scores:
            lab = f"{lab}  (RMSE {scores[key]:.2f})"
        ax.plot(monthly.index, monthly[col], label=lab,
                color=color, linestyle=ls, lw=1.1)
    ax.set_title(f"{city} — CMIP6 bias correction", loc="left",
                 fontsize=11, fontweight="bold")
    ax.set_ylabel(ylabel); ax.set_xlabel("")
    ax.grid(alpha=0.3)
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)
    ax.legend(fontsize=8.5, frameon=False)
    fig.tight_layout()
    fig.savefig(out_png, dpi=150)
    plt.close(fig)


def render(scan):
    """Plots + summary tables from whatever CMIP6 CSVs exist. Never fatal."""
    city = _city_name(scan)
    tabular = Path(scan.tabular_dir)
    out = Path(scan.render_dir) / "ucra" / "cmip6"
    out.mkdir(parents=True, exist_ok=True)

    variables = [v for v in cfg(scan, "ucra_cmip6_vars") if v in VARIABLES]
    n = 0
    summaries = []

    for var in variables:
        _, ylabel, _, _ = VARIABLES[var]
        d = _load(tabular, var, city)
        if d.empty:
            logger.info(f"  CMIP6 render: no data for {var} — skipping")
            continue

        try:
            _plot_projection(d, var, ylabel, city, out / f"{scan.city_name}_{var}_projection.png")
            n += 1
        except Exception as e:  # noqa
            logger.warning(f"  CMIP6 plot skipped {var} projection: {e}")

        # Scenario summary: 2025 baseline, 2100 endpoint, delta.
        try:
            g = d[d["Scenario"] != "observed"].groupby(["Scenario", "Year"])["Value"].mean()
            for scenario in d["Scenario"].unique():
                if scenario == "observed":
                    continue
                try:
                    a, b = g.loc[(scenario, 2025)], g.loc[(scenario, 2100)]
                except KeyError:
                    continue
                summaries.append({"city": city, "variable": var, "scenario": scenario,
                                  "value_2025": a, "value_2100": b, "delta": b - a})
        except Exception as e:  # noqa
            logger.warning(f"  CMIP6 summary skipped {var}: {e}")

        if var == "pr":
            try:
                _plot_rx1day(d, city, out / f"{scan.city_name}_rx1day_boxplot.png")
                n += 1
            except Exception as e:  # noqa
                logger.warning(f"  CMIP6 plot skipped rx1day: {e}")

        if var == "tas":
            try:
                _plot_monthly_heatmap(d, city, ylabel,
                                      out / f"{scan.city_name}_{var}_monthly_heatmap.png")
                n += 1
            except Exception as e:  # noqa
                logger.warning(f"  CMIP6 plot skipped monthly heatmap: {e}")

            if cfg(scan, "ucra_cmip6_debias"):
                try:
                    hist = d[(d["Scenario"] == "historical")][["Date", "Value"]].rename(
                        columns={"Value": "CMIP6_Historical"})
                    obs = d[d["Scenario"] == "observed"][["Date", "Value"]].rename(
                        columns={"Value": "Observed"})
                    overlap = hist.merge(obs, on="Date", how="inner").dropna()
                    fut = d[d["Scenario"].str.startswith("ssp")][["Date", "Value"]].rename(
                        columns={"Value": "CMIP6_Future"}).dropna()
                    if len(overlap) < 100 or fut.empty:
                        raise ValueError(f"overlap too short ({len(overlap)} days)")
                    corrected, scores = _debias(overlap, fut)
                    corrected.to_csv(
                        tabular / f"{scan.city_name}_cmip6_bias_correction{TAG}.csv",
                        index=False)
                    _plot_bias(corrected, scores, city, ylabel,
                               out / f"{scan.city_name}_bias_correction.png")
                    n += 1
                    logger.info("  CMIP6 bias correction RMSE: " +
                                ", ".join(f"{k}={v:.2f}" for k, v in scores.items()))
                except Exception as e:  # noqa
                    logger.warning(f"  CMIP6 bias correction skipped: {e}")

    if summaries:
        pd.DataFrame(summaries).to_csv(
            tabular / f"{scan.city_name}_cmip6_summary{TAG}.csv", index=False)

    logger.info(f"CMIP6 render: {n} figures -> {out}")
    return n
