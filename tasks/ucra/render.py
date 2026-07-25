"""UCRA render — per-city maps + peer-context plots.

Maps are drawn in the style of the CRP "Urban Climate Risk Analysis — Burundi"
report (see `style.py`): washed-out basemap, semi-transparent raster clipped to
the AOI, black dashed AOI outline, tick-marked scale bar, no axes.

Plots deliberately use the CROSS-CITY stats tables (exported as
`ucra_stats_*_ucra.csv`) and highlight this city against its peers — that is
what those tables are for, and it keeps UCRA's comparative meaning intact
instead of drawing a one-point "comparison".

Output: mnt/<id>/03-render-output/ucra/{maps,plots,cmip6}/  (separate from City
Scan and FCS renders). Every figure is isolated so one failure never aborts the
rest.
"""
import glob
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from core.py.log_module import setup_logger
from .style import (ucra_map, HILITE, PEER,
                    CRP_THERMAL, CRP_RED, CRP_URBAN, CRP_DROUGHT)

logger = setup_logger(__name__)

TAG = "_ucra"

# One dict per map. Keys beyond `pattern`/`stem` are passed straight to
# `ucra_map`, so a new layer is a new entry and nothing else.
#
# `basemap`: "satellite" for the surface-temperature style layers — the report
# puts those over imagery so the reader can see which land cover is hot — and
# "light" for everything else, matching its pale street-canvas choropleths.
#
# `keep_zero`: the urban-heat grids declare nodata=0, but zero IS a measurement
# there ("no projected increase"). Masking it blanks the whole layer.
#
# `mask_values`: the opposite case — a value that is stored but isn't a
# measurement. WSF evolution writes 0 for "never built up"; left in, the ramp
# runs 0-2015 instead of 1985-2015 and every real year collapses into one shade.
MAP_SPECS = [
    dict(pattern=f"*_lst_summer{TAG}.tif", stem="lst_summer",
         title="Land surface temperature — summer", label="°C",
         cmap=CRP_THERMAL, basemap="satellite"),
    dict(pattern=f"*_lst_winter{TAG}.tif", stem="lst_winter",
         title="Land surface temperature — winter", label="°C",
         cmap=CRP_THERMAL, basemap="satellite"),
    dict(pattern=f"*_WSFevolution_4326{TAG}.tif", stem="wsf_evolution",
         title="Built-up area evolution (WSF)", label="year of urbanisation",
         cmap=CRP_URBAN, basemap="satellite", mask_values=(0,), pct=(0, 100)),
    dict(pattern=f"*air_quality_2019{TAG}.tif", stem="air_quality_2019",
         title="Air quality (PM2.5) — 2019", label="µg/m³",
         cmap=CRP_RED, basemap="light"),
    dict(pattern=f"*bu_ssp2_2050{TAG}.tif", stem="builtup_ssp2_2050",
         title="Built-up projection — SSP2, 2050", label="built-up fraction",
         cmap=CRP_URBAN, basemap="light"),
    dict(pattern=f"*bu_ssp3_2080{TAG}.tif", stem="builtup_ssp3_2080",
         title="Built-up projection — SSP3, 2080", label="built-up fraction",
         cmap=CRP_URBAN, basemap="light"),
    dict(pattern=f"*_gdp{TAG}.tif", stem="gdp",
         title="Gridded GDP", label="USD", cmap="Greens", basemap="light"),
    dict(pattern=f"*urban-ssp2_day_sum{TAG}.tif", stem="urbanheat_ssp2_day_sum",
         title="Urban heat island — SSP2, daytime", label="°C increase",
         cmap=CRP_THERMAL, basemap="light", keep_zero=True),
    dict(pattern=f"*urban-ssp2_nig_sum{TAG}.tif", stem="urbanheat_ssp2_nig_sum",
         title="Urban heat island — SSP2, night-time", label="°C increase",
         cmap=CRP_THERMAL, basemap="light", keep_zero=True),
    dict(pattern=f"*urban-ssp5_day_sum{TAG}.tif", stem="urbanheat_ssp5_day_sum",
         title="Urban heat island — SSP5, daytime", label="°C increase",
         cmap=CRP_THERMAL, basemap="light", keep_zero=True),
    dict(pattern=f"*twsan*{TAG}.tif", stem="drought_twsan",
         title="Terrestrial water storage anomaly", label="anomaly",
         cmap=CRP_DROUGHT, basemap="light"),
]


def _render_maps(scan, spatial: Path, out_maps: Path) -> int:
    n = 0
    for spec in MAP_SPECS:
        spec = dict(spec)
        pattern, stem = spec.pop("pattern"), spec.pop("stem")
        hits = sorted(glob.glob(str(spatial / pattern)))
        if not hits:
            continue
        try:
            ucra_map(hits[0], scan.aoi, out_maps / f"{stem}{TAG}.png", **spec)
            n += 1
        except Exception as e:  # noqa
            logger.warning(f"  UCRA map skipped {stem}: {e}")
    return n


def _peer_bar(df, city, valcol, title, ylabel, out_png):
    """Bar across all cities with this city highlighted."""
    d = df.dropna(subset=[valcol]).copy()
    d = d.sort_values(valcol)
    colors = [HILITE if str(c).strip().lower() == city.strip().lower() else PEER
              for c in d["city"]]
    fig, ax = plt.subplots(figsize=(8, 4.2))
    ax.bar(d["city"].astype(str), d[valcol], color=colors)
    ax.set_title(title, loc="left", fontsize=11, fontweight="bold")
    ax.set_ylabel(ylabel)
    ax.tick_params(axis="x", rotation=60, labelsize=8)
    for lbl in ax.get_xticklabels():
        if lbl.get_text().strip().lower() == city.strip().lower():
            lbl.set_color(HILITE); lbl.set_fontweight("bold")
    ax.grid(alpha=0.3, axis="y")
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)
    fig.tight_layout(); fig.savefig(out_png, dpi=150); plt.close(fig)


def _render_plots(scan, tabular: Path, out_plots: Path, city: str) -> int:
    n = 0

    # 1. Mean summer LST vs peers
    f = tabular / f"ucra_stats_avg_temp{TAG}.csv"
    if f.exists():
        try:
            df = pd.read_csv(f)
            _peer_bar(df, city, "avg", "Mean land surface temperature vs peer cities",
                      "°C", out_plots / f"avg_temp_peers{TAG}.png")
            n += 1
        except Exception as e:  # noqa
            logger.warning(f"  UCRA plot skipped avg_temp_peers: {e}")

    # 2. This city's PM2.5 trend 1998-2019, against the peer mean
    f = tabular / f"ucra_stats_avg_air_1998_2019{TAG}.csv"
    if f.exists():
        try:
            df = pd.read_csv(f)
            mine = df[df["city"].astype(str).str.strip().str.lower() == city.strip().lower()]
            peers = df.groupby("year")["avg"].mean()
            if mine.empty:
                raise ValueError(f"city '{city}' not in avg_air table")
            fig, ax = plt.subplots(figsize=(7, 4.2))
            ax.plot(peers.index, peers.values, color=PEER, lw=2, label="Peer-city mean")
            ax.plot(mine["year"], mine["avg"], color=HILITE, marker="o", ms=3, lw=2, label=city)
            ax.set_title("Air quality (PM2.5), 1998-2019", loc="left",
                         fontsize=11, fontweight="bold")
            ax.set_xlabel("Year"); ax.set_ylabel("PM2.5 (µg/m³)")
            ax.legend(fontsize=8, frameon=False); ax.grid(alpha=0.3)
            for s in ("top", "right"):
                ax.spines[s].set_visible(False)
            fig.tight_layout(); fig.savefig(out_plots / f"air_quality_trend{TAG}.png", dpi=150)
            plt.close(fig)
            n += 1
        except Exception as e:  # noqa
            logger.warning(f"  UCRA plot skipped air_quality_trend: {e}")

    # 3. A CCKP anomaly vs peers (first available anomaly table)
    anoms = sorted(glob.glob(str(tabular / f"ucra_stats_anom_*{TAG}.csv")))
    if anoms:
        try:
            src = Path(anoms[0])
            df = pd.read_csv(src)
            valcol = [c for c in df.columns if c != "city"][0]
            var = src.stem.replace("ucra_stats_anom_", "").replace(TAG, "")
            _peer_bar(df, city, valcol, f"CCKP anomaly — {var} ({valcol}) vs peers",
                      "anomaly", out_plots / f"cckp_anomaly_peers{TAG}.png")
            n += 1
        except Exception as e:  # noqa
            logger.warning(f"  UCRA plot skipped cckp_anomaly_peers: {e}")

    return n


def render(scan):
    spatial = Path(scan.spatial_dir)
    tabular = Path(scan.tabular_dir)
    out_root = Path(scan.render_dir) / "ucra"
    out_maps, out_plots = out_root / "maps", out_root / "plots"
    out_maps.mkdir(parents=True, exist_ok=True)
    out_plots.mkdir(parents=True, exist_ok=True)

    city = str(scan.city_inputs.get("city_name", scan.city_name)).replace("_", " ")
    nm = _render_maps(scan, spatial, out_maps)
    npl = _render_plots(scan, tabular, out_plots, city)
    logger.info(f"UCRA render: {nm} maps + {npl} plots -> {out_root}")
    return nm, npl
