"""Shared plumbing for the Python-side static maps (UCRA and FCS).

Only the mechanical parts live here — reading and reprojecting a raster, adding
basemap tiles, and drawing a scale bar / north arrow. The *look* stays in each
task's own `style.py`, because the two deliberately differ:

  tasks/ucra/style.py   the CRP "Urban Climate Risk Analysis - Burundi" report
                        cartography — clipped raster, dashed AOI, colourbar below
  tasks/fcs/style.py    City Scan's own R map look (core/R/fns-maps-static.R) —
                        unclipped raster, solid grey AOI, legend panel on the
                        right, north arrow

Keeping the primitives in one place means a fix to the reprojection or the
scale-bar maths lands in both.
"""
import numpy as np

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

from core.py.log_module import setup_logger

logger = setup_logger(__name__)

WEB_MERCATOR = "EPSG:3857"


def provider(name):
    """Resolve a dotted contextily provider path, e.g. 'CartoDB.Positron'."""
    import contextily as cx
    src = cx.providers
    for part in name.split("."):
        src = getattr(src, part)
    return src


def read_reproject(tif, aoi=None, *, clip=False, keep_zero=False, mask_values=()):
    """Read `tif` as float32 in Web Mercator; return (array, (l, r, b, t)).

    clip         restrict to the AOI geometry (UCRA) rather than showing the
                 raster's full footprint (City Scan / FCS).
    keep_zero    honour 0 as a real measurement even when declared as nodata.
                 The FCS urban-heat grids set nodata=0 although zero means "no
                 projected increase" — masking it blanks the entire layer.
    mask_values  the converse: values that are stored but are not measurements.
                 WSF evolution writes 0 for "never built up", which otherwise
                 drags the colour ramp from 1985-2015 down to 0-2015.

    Web Mercator because that is what the basemap tiles are served in; warping
    here is what makes the overlay land on the imagery instead of beside it.
    """
    import rasterio
    from rasterio.mask import raster_geometry_mask
    from rasterio.warp import calculate_default_transform, reproject, Resampling

    with rasterio.open(tif) as ds:
        src_crs = ds.crs
        geom = None
        if clip and src_crs is not None and aoi is not None:
            try:
                geom = list(aoi.to_crs(src_crs).geometry)
            except Exception:
                geom = None

        # raster_geometry_mask rather than mask(): it returns the geometry mask
        # separately from the pixels, so the AOI crop and the nodata rule stay
        # independent (which `keep_zero` depends on). It also sidesteps rasterio
        # trying to put a NaN fill into an integer band — WSF evolution is int32
        # and failed on exactly that.
        if geom:
            outside, transform, window = raster_geometry_mask(ds, geom, crop=True)
            arr = ds.read(1, window=window).astype("float32")
            arr[outside] = np.nan
        else:
            arr = ds.read(1).astype("float32")
            transform = ds.transform
        nodata = ds.nodata

    if nodata is not None and not (keep_zero and nodata == 0):
        arr = np.where(arr == nodata, np.nan, arr)
    for v in mask_values:
        arr = np.where(arr == v, np.nan, arr)
    arr = np.where(np.isfinite(arr), arr, np.nan)

    h, w = arr.shape
    if src_crs is None:
        left, top = transform.c, transform.f
        return arr, (left, left + transform.a * w, top + transform.e * h, top)

    dst_transform, dw, dh = calculate_default_transform(
        src_crs, WEB_MERCATOR, w, h,
        left=transform.c, top=transform.f,
        right=transform.c + transform.a * w,
        bottom=transform.f + transform.e * h,
    )
    dst = np.full((dh, dw), np.nan, dtype="float32")
    reproject(source=arr, destination=dst,
              src_transform=transform, src_crs=src_crs,
              dst_transform=dst_transform, dst_crs=WEB_MERCATOR,
              src_nodata=np.nan, dst_nodata=np.nan,
              resampling=Resampling.nearest)
    left, top = dst_transform.c, dst_transform.f
    return dst, (left, left + dst_transform.a * dw, top + dst_transform.e * dh, top)


def aoi_bounds_3857(aoi, aspect_ratio, buffer_percent=0.05):
    """AOI bounds in Web Mercator, padded and forced to `aspect_ratio`.

    Mirrors core/R/fns-geometry.R::aspect_buffer, which is how every City Scan
    map picks its extent — pad by a fraction, then grow the short side so the
    map fills its panel without distorting.
    """
    minx, miny, maxx, maxy = aoi.to_crs(WEB_MERCATOR).total_bounds
    cx_, cy_ = (minx + maxx) / 2, (miny + maxy) / 2
    w = (maxx - minx) * (1 + buffer_percent)
    h = (maxy - miny) * (1 + buffer_percent)
    if w / h < aspect_ratio:
        w = h * aspect_ratio
    else:
        h = w / aspect_ratio
    return cx_ - w / 2, cx_ + w / 2, cy_ - h / 2, cy_ + h / 2


def add_basemap(ax, name="CartoDB.Positron", wash=0.0, zorder=0):
    """Add tiles, optionally washed out with a translucent white overlay.

    Never fatal: with no network the map still draws on a plain background.
    """
    try:
        import contextily as cx
        cx.add_basemap(ax, source=provider(name), crs=WEB_MERCATOR,
                       attribution=False, zorder=zorder)
        if wash > 0:
            x0, x1 = ax.get_xlim()
            y0, y1 = ax.get_ylim()
            ax.add_patch(plt.Rectangle((x0, y0), x1 - x0, y1 - y0, facecolor="white",
                                       alpha=wash, edgecolor="none", zorder=zorder + 1))
        return True
    except Exception as e:  # noqa — offline, tile server unhappy, bad zoom
        logger.warning(f"  basemap unavailable ({type(e).__name__}: {e}); plain background")
        return False


def nice_scale_km(span_m, frac=0.33):
    """A round scale-bar length ~ `frac` of the map width, in km.

    frac=0.33 matches ggspatial's `width_hint = 0.33` used across City Scan.
    """
    target = span_m * frac / 1000.0
    for v in (0.1, 0.25, 0.5, 1, 2, 2.5, 5, 10, 20, 25, 50, 100, 200, 250, 500):
        if target <= v:
            return v
    return 1000


def draw_scalebar(ax, *, label_at="end", n_ticks=4, frac=0.33,
                  pad_x=0.03, pad_y=0.04, fontsize=8, color="black"):
    """ggspatial `style = "ticks"` scale bar, bottom-left.

    label_at="end"  one label after the bar ("3 km") — the City Scan look.
    label_at="all"  0 / half / full labelled — the Burundi report look.
    Uses the axes' current limits, so call it after the extent is final.
    """
    x0lim, x1lim = ax.get_xlim()
    y0lim, y1lim = ax.get_ylim()
    span = x1lim - x0lim
    km = nice_scale_km(span, frac=frac)
    length = km * 1000.0
    if length > span * 0.9:          # degenerate / very small AOI
        return

    x0 = x0lim + span * pad_x
    y0 = y0lim + (y1lim - y0lim) * pad_y
    tick = (y1lim - y0lim) * 0.012

    ax.plot([x0, x0 + length], [y0, y0], color=color, lw=1.0,
            solid_capstyle="butt", zorder=6)
    for i in range(n_ticks + 1):
        x = x0 + length * i / n_ticks
        ax.plot([x, x], [y0, y0 - tick], color=color, lw=1.0, zorder=6)

    if label_at == "end":
        ax.text(x0 + length * 1.04, y0 - tick, f"{km:g} km", ha="left", va="bottom",
                fontsize=fontsize, color=color, zorder=6, clip_on=False)
    else:
        ty = y0 + tick * 0.8
        for f_, lab, ha in ((0.0, "0", "left"), (0.5, f"{km / 2:g}", "center")):
            ax.text(x0 + length * f_, ty, lab, ha=ha, va="bottom",
                    fontsize=fontsize, color=color, zorder=6)
        ax.text(x0 + length * 1.03, ty, f"{km:g} Kilometers", ha="left", va="bottom",
                fontsize=fontsize, color=color, zorder=6, clip_on=False)


def draw_north_arrow(ax, pad_x=0.965, pad_y=0.045, size=0.042, color="black"):
    """ggspatial `north_arrow_minimal`, bottom-right: a slim filled triangle
    over a small 'N'. Kept narrow (aspect ~1:5) to match the R original, which
    is a thin spike rather than a wedge."""
    x0lim, x1lim = ax.get_xlim()
    y0lim, y1lim = ax.get_ylim()
    w, h = x1lim - x0lim, y1lim - y0lim
    x = x0lim + w * pad_x
    y = y0lim + h * pad_y
    a = h * size
    # Half-width in *data* units must be derived from the x-span, not the
    # y-span: the axes are not square, so using `a` both ways skews the arrow.
    half = (w / h) * a * 0.10

    ax.fill([x - half, x, x + half], [y, y + a, y],
            color=color, zorder=6, clip_on=False)
    ax.text(x, y - a * 0.22, "N", ha="center", va="top",
            fontsize=7.5, color=color, zorder=6, clip_on=False)


def strip_axes(ax):
    """theme_custom(): no ticks, no labels, no frame."""
    ax.set_xticks([])
    ax.set_yticks([])
    for s in ax.spines.values():
        s.set_visible(False)


def stretch(finite, vmin=None, vmax=None, pct=(2, 98)):
    """Percentile stretch with a guard for constant / degenerate rasters."""
    if vmin is None or vmax is None:
        lo, hi = np.nanpercentile(finite, list(pct))
        vmin = lo if vmin is None else vmin
        vmax = hi if vmax is None else vmax
    if not np.isfinite(vmin) or not np.isfinite(vmax) or vmax <= vmin:
        vmin = float(np.nanmin(finite))
        vmax = vmin + (abs(vmin) * 1e-3 or 1e-6)
    return vmin, vmax
