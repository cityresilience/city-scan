"""FCS render phase — curated maps + plots from a city's _fsca outputs.

Reads mnt/<id>/02-process-output/{spatial,tabular}/*_fsca.* and writes styled
PNGs to mnt/<id>/03-render-output/fcs/{maps,plots}/ (kept separate from the City
Scan render so the two don't get confused). Runs in the cityscan env (matplotlib
+ rasterio + geopandas). Every map/plot is wrapped so one failure never aborts
the rest — matching how City Scan treats task steps.
"""
import glob
import os
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from core.py.log_module import setup_logger
from core.py.map_base import read_reproject
from .style import cityscan_map, cityscan_map_array

logger = setup_logger(__name__)

TAG = "_fsca"


# ----------------------------------------------------------------------------- maps
def _find(spatial, stem):
    p = spatial / f"{stem}{TAG}.tif"
    return p if p.exists() else None


# Drawn in City Scan's own cartography (tasks/fcs/style.py) so FCS and City Scan
# maps are indistinguishable in the report. `title` is the legend heading and
# `subtitle` the italic unit line beneath it, matching format_title() in R.
MAP_SPECS = [
    dict(stem="processed_popdynamics_SSP2_2020",
         title="Projected population", subtitle="People per cell — SSP2, 2020",
         cmap="viridis"),
    dict(stem="processed_urbanland_ssp2_2020",
         title="Urban land", subtitle="Fraction of cell — SSP2, 2020", cmap="YlOrBr"),
    dict(stem="processed_urbanland_ssp2_2050",
         title="Projected urban land", subtitle="Fraction of cell — SSP2, 2050", cmap="YlOrBr"),
    dict(stem="processed_urbanland_ssp2_2100",
         title="Projected urban land", subtitle="Fraction of cell — SSP2, 2100", cmap="YlOrBr"),
    # UHI grids declare nodata=0, but 0 means "no increase" — keep it, else the
    # map is a single stray pixel (or empty) over these small inland AOIs.
    dict(stem="processed_urbanheatisland_urban-ssp2_day_sum",
         title="Urban heat island, daytime",
         subtitle="Temperature increase (°C) — SSP2, summer",
         cmap="coolwarm", keep_zero=True),
    dict(stem="processed_urbanheatisland_urban-ssp2_nig_sum",
         title="Urban heat island, night-time",
         subtitle="Temperature increase (°C) — SSP2, summer",
         cmap="coolwarm", keep_zero=True),
]


def _render_maps(scan, spatial: Path, out_maps: Path) -> int:
    aoi = scan.aoi
    n = 0
    for spec in MAP_SPECS:
        spec = dict(spec)
        stem = spec.pop("stem")
        tif = _find(spatial, stem)
        if not tif:
            continue
        try:
            cityscan_map(tif, aoi, out_maps / f"{stem}{TAG}.png", **spec)
            n += 1
        except Exception as e:  # noqa
            logger.warning(f"  FCS map skipped {stem}: {e}")

    # Anthropogenic heat flux: annual mean of the 12 monthly 2050 rasters.
    months = sorted(glob.glob(str(spatial / f"processed_heatflux_AHE_2050_*_average{TAG}.tif")))
    if months:
        try:
            stack, extent = [], None
            for m in months:
                a, extent = read_reproject(m, aoi, clip=False)
                stack.append(a)
            shape = stack[0].shape
            stack = [a for a in stack if a.shape == shape]
            # Cells outside the data footprint are NaN in every month, and
            # nanmean warns on those all-NaN slices. The result (NaN -> drawn
            # transparent) is what we want, so silence just this call.
            with np.errstate(invalid="ignore"):
                import warnings
                with warnings.catch_warnings():
                    warnings.simplefilter("ignore", category=RuntimeWarning)
                    mean = np.nanmean(np.stack(stack), axis=0)
            cityscan_map_array(
                mean, extent, aoi,
                out_maps / f"heatflux_AHE_2050_annual_mean{TAG}.png",
                title="Anthropogenic heat flux",
                subtitle="Annual mean (W/m²) — 2050", cmap="magma")
            n += 1
        except Exception as e:  # noqa
            logger.warning(f"  FCS map skipped heatflux annual mean: {e}")
    return n


# ---------------------------------------------------------------------------- plots
def _scenario_line(csv, title, ylabel, out_png, scale=1.0):
    """Line chart from a Scenario x year wide table (urbanland, etc.)."""
    df = pd.read_csv(csv)
    scen_col = df.columns[0]
    years = [c for c in df.columns[1:] if str(c).strip().isdigit()]
    if not years:
        raise ValueError("no year columns")
    fig, ax = plt.subplots(figsize=(7, 4.2))
    for _, row in df.iterrows():
        ax.plot([int(y) for y in years], [row[y] * scale for y in years],
                marker="o", ms=3, label=str(row[scen_col]))
    ax.set_title(title); ax.set_xlabel("Year"); ax.set_ylabel(ylabel)
    ax.legend(title="Scenario", fontsize=8); ax.grid(alpha=0.3)
    fig.tight_layout(); fig.savefig(out_png, dpi=140); plt.close(fig)


def _scenario_bar(csv, title, ylabel, out_png):
    """Bar chart from a Scenario x (few years) table (popdynamics 2020)."""
    df = pd.read_csv(csv)
    scen_col = df.columns[0]
    ycol = df.columns[1]
    fig, ax = plt.subplots(figsize=(6, 4))
    ax.bar(df[scen_col].astype(str), df[ycol])
    ax.set_title(title); ax.set_ylabel(ylabel); ax.grid(alpha=0.3, axis="y")
    fig.tight_layout(); fig.savefig(out_png, dpi=140); plt.close(fig)


def _cckp_line(csv, kind, out_png):
    """Line of the headline anomaly variable over time, one line per SSP."""
    df = pd.read_csv(csv)
    valcol = kind  # column name equals 'Precipitation' or 'Temperature'
    if valcol not in df.columns or "Variable" not in df.columns:
        raise ValueError("unexpected CCKP panel schema")
    var = next((v for v in df["Variable"].unique()
                if isinstance(v, str) and "Anomaly" in v and kind.lower()[:4] in v.lower()),
               df["Variable"].iloc[0])
    sub = df[df["Variable"] == var].copy()
    sub["year"] = pd.to_datetime(sub["time"], errors="coerce").dt.year
    piv = sub.groupby(["year", "SSP"])[valcol].mean().unstack("SSP")
    fig, ax = plt.subplots(figsize=(7, 4.2))
    for ssp in piv.columns:
        ax.plot(piv.index, piv[ssp], marker="o", ms=3, label=str(ssp))
    ax.set_title(f"CCKP {kind.lower()} — {var[:60]}")
    ax.set_xlabel("Year"); ax.set_ylabel(kind)
    ax.legend(title="SSP", fontsize=8); ax.grid(alpha=0.3)
    fig.tight_layout(); fig.savefig(out_png, dpi=140); plt.close(fig)


def _render_plots(scan, tabular: Path, out_plots: Path, city_tag: str) -> int:
    n = 0
    jobs = [
        (tabular / f"{city_tag}_urbanland{TAG}.csv",
         lambda p: _scenario_line(p, "Urban land fraction by SSP", "Urban land (%)",
                                  out_plots / f"urbanland_trend{TAG}.png", scale=100.0)),
        (tabular / f"{city_tag}_popdynamics{TAG}.csv",
         lambda p: _scenario_bar(p, "Population by SSP (2020)", "Population",
                                 out_plots / f"population_by_ssp{TAG}.png")),
        (tabular / f"{city_tag}_Precipitation_panel{TAG}.csv",
         lambda p: _cckp_line(p, "Precipitation", out_plots / f"cckp_precipitation{TAG}.png")),
        (tabular / f"{city_tag}_Temperature_panel{TAG}.csv",
         lambda p: _cckp_line(p, "Temperature", out_plots / f"cckp_temperature{TAG}.png")),
    ]
    for path, fn in jobs:
        if not path.exists():
            continue
        try:
            fn(path)
            n += 1
        except Exception as e:  # noqa
            logger.warning(f"  FCS plot skipped {path.name}: {e}")
    return n


def render(scan):
    """Entry point: build FCS maps + plots for this city under 03-render-output/fcs/."""
    # Rasters live in spatial/fcs/ — see the note in tasks/fcs/__init__.py on why
    # they are not flat beside City Scan's. Fall back to the flat layout so city
    # folders exported before that change still render.
    spatial = Path(scan.spatial_dir) / "fcs"
    if not spatial.is_dir():
        spatial = Path(scan.spatial_dir)
    tabular = Path(scan.tabular_dir)
    out_root = Path(scan.render_dir) / "fcs"
    out_maps = out_root / "maps"
    out_plots = out_root / "plots"
    out_maps.mkdir(parents=True, exist_ok=True)
    out_plots.mkdir(parents=True, exist_ok=True)

    city_disp = scan.city_inputs.get("city_name", scan.city_name)
    country = (scan.country_name or "pakistan").title()
    city_tag = f"{country}_{city_disp}"   # matches FCS filename prefix

    nm = _render_maps(scan, spatial, out_maps)
    npl = _render_plots(scan, tabular, out_plots, city_tag)
    logger.info(f"FCS render: {nm} maps + {npl} plots -> {out_root}")
