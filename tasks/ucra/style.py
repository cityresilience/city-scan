"""Burundi-style cartography for UCRA figures.

The look is taken from the CRP "Urban Climate Risk Analysis — Burundi" report:

  * a **desaturated basemap** underneath (satellite imagery for surface-temperature
    style layers, a pale grey street canvas for everything else),
  * the data raster laid over it **semi-transparent and clipped to the AOI**,
  * the AOI drawn as a **black dashed outline** — no fill, no halo,
  * **no axes, no frame, no gridlines**; the map is a picture, not a plot,
  * a **tick-marked scale bar** bottom-left labelled in kilometres,
  * the value range shown by a slim **horizontal colourbar under the map**
    (the report puts the range in the page caption instead; a report-embedded
    figure needs it attached).

Everything degrades gracefully: if the basemap tiles can't be fetched (offline,
rate-limited) the map still renders on a plain background.
"""
import numpy as np

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.colors import LinearSegmentedColormap

from core.py.log_module import setup_logger
from core.py.map_base import (read_reproject, add_basemap, draw_scalebar,
                              strip_axes, stretch, WEB_MERCATOR)

logger = setup_logger(__name__)

# ── palette ───────────────────────────────────────────────────────────────
# The report's ramps, in the order they read on the page.
AOI_EDGE = "#000000"
HILITE, PEER = "#c1272d", "#b0b0b0"

# Blue → cyan → yellow → orange → red. This is the ramp on the Burundi LST and
# heat pages; RdYlBu_r is the closest matplotlib built-in but runs too pale
# through the middle, so it's defined explicitly.
CRP_THERMAL = LinearSegmentedColormap.from_list("crp_thermal", [
    "#2c7bb6", "#00a6ca", "#00ccbc", "#90eb9d", "#ffff8c",
    "#f9d057", "#f29e2e", "#e76818", "#d7191c",
])
# Single-hue muted red used for the air-quality / exposure choropleths.
CRP_RED = LinearSegmentedColormap.from_list("crp_red", [
    "#f7e4e6", "#e9b3b9", "#d98089", "#c25664", "#a83246",
])
# Built-up / urbanisation ramp (report uses a warm ochre progression).
CRP_URBAN = LinearSegmentedColormap.from_list("crp_urban", [
    "#fff7e0", "#fee0a6", "#fdb863", "#e08214", "#b35806",
])
# Drought / SPEI: brown (dry) → white → blue-green (wet).
CRP_DROUGHT = LinearSegmentedColormap.from_list("crp_drought", [
    "#8c510a", "#d8b365", "#f6e8c3", "#f5f5f5", "#c7eae5", "#5ab4ac", "#01665e",
])

BASEMAPS = {
    # (provider path, how much white to lay over it)
    # Imagery needs a heavy wash to stop it competing with the data; Positron is
    # already near-white, so washing it hard erases the roads entirely.
    "satellite": ("Esri.WorldImagery", 0.45),
    "light": ("CartoDB.PositronNoLabels", 0.25),
}


def ucra_map(tif, aoi, out_png, *, title, label, cmap,
             basemap="light", alpha=0.78, keep_zero=False, mask_values=(),
             vmin=None, vmax=None, pct=(2, 98)):
    """Render one Burundi-styled map. Raises on an empty/unusable raster."""
    # clip=True is the Burundi look: the report shows the data only inside the
    # AOI. City Scan (and therefore tasks/fcs) leaves the raster unclipped.
    arr, extent = read_reproject(tif, aoi, clip=True, keep_zero=keep_zero,
                                 mask_values=mask_values)
    finite = arr[np.isfinite(arr)]
    if finite.size == 0:
        raise ValueError("raster is entirely nodata inside the AOI")
    vmin, vmax = stretch(finite, vmin, vmax, pct)

    left, right, bottom, top = extent
    padx, pady = (right - left) * 0.10, (top - bottom) * 0.10
    xlim = (left - padx, right + padx)
    ylim = (bottom - pady, top + pady)

    fig, ax = plt.subplots(figsize=(6.4, 6.4))
    ax.set_xlim(*xlim)
    ax.set_ylim(*ylim)

    # Basemap first, washed out so the data reads on top of it.
    if basemap in BASEMAPS:
        name, wash = BASEMAPS[basemap]
        add_basemap(ax, name, wash=wash)

    cm = plt.get_cmap(cmap).copy() if isinstance(cmap, str) else cmap.copy()
    cm.set_bad(alpha=0)
    im = ax.imshow(np.ma.masked_invalid(arr), extent=(left, right, bottom, top),
                   cmap=cm, vmin=vmin, vmax=vmax, origin="upper",
                   alpha=alpha, interpolation="nearest", zorder=2)

    try:
        aoi.to_crs(WEB_MERCATOR).boundary.plot(
            ax=ax, color=AOI_EDGE, linewidth=1.3, linestyle=(0, (3, 2)), zorder=5)
    except Exception:
        pass

    # geopandas' plot() refits the axes to the geometry — restore the extent.
    ax.set_xlim(*xlim)
    ax.set_ylim(*ylim)
    draw_scalebar(ax, label_at="all", n_ticks=8, frac=0.25)
    strip_axes(ax)
    ax.set_title(title, fontsize=11, loc="left", fontweight="bold", pad=8)

    cb = fig.colorbar(im, ax=ax, orientation="horizontal",
                      fraction=0.040, pad=0.02, shrink=0.72)
    cb.set_label(label, fontsize=8.5)
    cb.ax.tick_params(labelsize=7.5, length=2)
    cb.outline.set_visible(False)

    fig.savefig(out_png, dpi=150, bbox_inches="tight", facecolor="white")
    plt.close(fig)
