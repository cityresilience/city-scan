"""City Scan cartography for FCS maps.

Deliberately mirrors what `core/R/fns-maps-static.R` produces, so an FCS map and
a City Scan map sit side by side in the same report without looking like they
came from different projects:

  * `cartolight` (CartoDB Positron, **with** labels) basemap at full opacity,
  * raster laid over it semi-transparent and **not clipped** to the AOI — City
    Scan shows the data's real footprint and draws the boundary on top,
  * AOI as a **solid grey30 line** (`aoi_stroke`, linewidth 0.6),
  * extent = AOI + 5% buffer forced to the 8.77 x 7.55 map aspect,
  * ggspatial `style = "ticks"` scale bar bottom-left, `north_arrow_minimal`
    bottom-right,
  * **legend in its own panel on the right** at a 7:2 width split
    (`map_portions`), left/bottom justified, titled with a plain title over an
    italic subtitle (`format_title`),
  * no axes, no frame, white background, 200 dpi (`save_plot`).

The numbers here are read from the R source rather than eyeballed; see
`maps-static.R` (map_width/map_height/map_portions) and `fns-maps-aes.R`
(theme_custom/save_plot).
"""
import numpy as np

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.gridspec import GridSpec

from core.py.log_module import setup_logger
from core.py.map_base import (read_reproject, aoi_bounds_3857, add_basemap,
                              draw_scalebar, draw_north_arrow, strip_axes,
                              stretch, WEB_MERCATOR)

logger = setup_logger(__name__)

# core/R/maps-static.R
MAP_W, MAP_H = 8.77, 7.55
ASPECT = MAP_W / MAP_H
MAP_PORTIONS = (7, 2)          # map : legend
DPI = 200

# core/R/fns-maps-static.R :: aoi_stroke
AOI_COLOR = "grey"
AOI_LW = 1.2                   # ggplot linewidth 0.6 ~ 1.2 pt in matplotlib
BASEMAP = "CartoDB.Positron"   # ggspatial 'cartolight'
RASTER_ALPHA = 0.8


def cityscan_map(tif, aoi, out_png, *, keep_zero=False, mask_values=(), **kw):
    """Render one City-Scan-styled map from a raster path."""
    arr, extent = read_reproject(tif, aoi, clip=False, keep_zero=keep_zero,
                                 mask_values=mask_values)
    return cityscan_map_array(arr, extent, aoi, out_png, **kw)


def cityscan_map_array(arr, extent, aoi, out_png, *, title, subtitle, cmap,
                       vmin=None, vmax=None, pct=(2, 98), alpha=RASTER_ALPHA,
                       basemap=BASEMAP, discrete_labels=None):
    """Same, from an array already in Web Mercator — used where a map is derived
    from several rasters (the heat-flux annual mean). Raises if it carries no data."""
    finite = arr[np.isfinite(arr)]
    if finite.size == 0:
        raise ValueError("raster is entirely nodata")
    vmin, vmax = stretch(finite, vmin, vmax, pct)

    fig = plt.figure(figsize=(MAP_W + MAP_W * MAP_PORTIONS[1] / MAP_PORTIONS[0], MAP_H))
    gs = GridSpec(1, 2, width_ratios=MAP_PORTIONS, wspace=0.02,
                  left=0, right=1, top=1, bottom=0)
    ax = fig.add_subplot(gs[0, 0])
    lax = fig.add_subplot(gs[0, 1])
    lax.axis("off")

    # Extent first — add_basemap picks its zoom from the axes limits.
    x0, x1, y0, y1 = aoi_bounds_3857(aoi, ASPECT, buffer_percent=0.05)
    ax.set_xlim(x0, x1)
    ax.set_ylim(y0, y1)
    add_basemap(ax, basemap, wash=0.0)

    cm = plt.get_cmap(cmap).copy() if isinstance(cmap, str) else cmap.copy()
    cm.set_bad(alpha=0)
    im = ax.imshow(np.ma.masked_invalid(arr), extent=extent, cmap=cm,
                   vmin=vmin, vmax=vmax, origin="upper", alpha=alpha,
                   interpolation="nearest", zorder=2)

    try:
        aoi.to_crs(WEB_MERCATOR).boundary.plot(
            ax=ax, color=AOI_COLOR, linewidth=AOI_LW, linestyle="solid", zorder=5)
    except Exception:
        pass

    # set_xlim/ylim again: geopandas' plot() re-fits the axes to the geometry.
    ax.set_xlim(x0, x1)
    ax.set_ylim(y0, y1)
    draw_scalebar(ax, label_at="end")
    draw_north_arrow(ax)
    strip_axes(ax)

    # --- legend panel -------------------------------------------------------
    # legend.justification = c("left", "bottom"): the block hugs the lower-left
    # of its panel, which is why City Scan legends sit low rather than centred.
    cax = lax.inset_axes([0.06, 0.06, 0.16, 0.34])
    cb = fig.colorbar(im, cax=cax, orientation="vertical")
    cb.ax.tick_params(labelsize=9, length=2, pad=4)
    cb.outline.set_visible(False)
    if discrete_labels:
        cb.set_ticks(list(discrete_labels))
        cb.set_ticklabels([discrete_labels[k] for k in discrete_labels])

    # format_title(): title, then the subtitle in italics beneath it.
    lax.text(0.06, 0.50, _wrap(title, 20), transform=lax.transAxes,
             ha="left", va="bottom", fontsize=11, color="black")
    if subtitle:
        lax.text(0.06, 0.43, _wrap(subtitle, 22), transform=lax.transAxes,
                 ha="left", va="bottom", fontsize=10, style="italic", color="black")

    fig.savefig(out_png, dpi=DPI, facecolor="white", bbox_inches="tight",
                pad_inches=0.08)
    plt.close(fig)


def _wrap(text, width):
    """break_lines() equivalent — wrap on spaces at roughly `width` chars."""
    import textwrap
    return "\n".join(textwrap.wrap(str(text), width=width)) or str(text)
