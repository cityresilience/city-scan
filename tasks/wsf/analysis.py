# import
import os
import math
import numpy as np
import pandas as pd
import geopandas as gpd
import rasterio
from rasterio.io import MemoryFile
from rasterio.mask import mask
from rasterio.warp import reproject, Resampling, calculate_default_transform
from scipy.ndimage import distance_transform_edt
from core.py.log_module import setup_logger

logger = setup_logger(__name__)


def _cell_areas_km2(meta):
    """Compute per-pixel area in km2 for a geographic (EPSG:4326) raster.
    Returns 2D array of pixel areas matching raster height/width."""
    transform = meta["transform"]
    height = meta["height"]
    width = meta["width"]

    # Pixel size in degrees
    dx = abs(transform.a)
    dy = abs(transform.e)

    # Center latitude of each row
    top_y = transform.f
    row_centers = np.array([top_y - (i + 0.5) * dy for i in range(height)])

    # Length of 1 degree at each latitude (in km)
    lat_rad = np.radians(row_centers)
    km_per_deg_lat = 111.132  # roughly constant
    km_per_deg_lon = 111.320 * np.cos(lat_rad)

    # Area per pixel = (dx * km/deg_lon) * (dy * km/deg_lat) for each row
    pixel_area = (dx * km_per_deg_lon) * (dy * km_per_deg_lat)  # shape (height,)

    # Broadcast to (height, width)
    return np.broadcast_to(pixel_area[:, np.newaxis], (height, width))


# Equivalent of Caroline's clean.py — clean_uba()
def stats_wsf(
        city_name: str,
        output_dir: str,
        dataset: str = "tracker",
        return_df: bool = False
    ):
    """
    Compute cumulative built-up area by year from a WSF raster.

    Works for both Tracker (fractional years) and Evolution (integer years).
    Floors values to integer years, computes cumulative area.

    Output CSV columns: year, cumulative_sq_km

    Parameters
    ----------
    city_name : str
        City name for locating raster file.
    output_dir : str
        Base output directory.
    dataset : str
        "tracker" or "evolution".
    return_df : bool
        If True, return the DataFrame.

    Returns
    -------
    pd.DataFrame or None
    """
    raster_path = os.path.join(output_dir, "spatial", f"{city_name}_wsf_{dataset}.tif")
    output_path = os.path.join(output_dir, "tabular", f"{city_name}_wsf_{dataset}.csv")

    logger.info(f"Computing WSF stats from: {os.path.basename(raster_path)}")

    if not os.path.exists(raster_path):
        logger.error(f"WSF raster not found at: {raster_path}")
        return None

    # Accumulate built-up area per time-bin in ROW STRIPS — a full 10m national
    # tracker is ~18e9 px (66 GiB) if read whole. Windowing gives the EXACT same
    # per-bin area sums (it's a weighted histogram), bounded to one strip.
    from rasterio.windows import Window
    with rasterio.open(raster_path) as src:
        band = 2 if (dataset == "tracker" and src.count >= 2) else 1
        H, W = src.height, src.width
        base_meta = src.meta.copy()
        STRIP = 4096
        area_by_code = {}  # tracker: year*100+month -> km2 ; evolution: year -> km2
        for r in range(0, H, STRIP):
            h = min(STRIP, H - r)
            win = Window(0, r, W, h)
            vals = src.read(band, window=win).astype(float)
            sm = base_meta.copy()
            sm.update(height=h, width=W, transform=src.window_transform(win))
            areas = _cell_areas_km2(sm)
            valid = (vals > 0) & (~np.isnan(vals))
            if not valid.any():
                continue
            av = areas[valid]
            vv = vals[valid]
            if dataset == "tracker":
                yi = np.floor(vv).astype(int)
                mi = np.clip(np.round((vv - yi) * 12).astype(int), 1, 12)
                codes = yi * 100 + mi
            else:
                codes = np.floor(vv).astype(int)
            uc, inv = np.unique(codes, return_inverse=True)
            sums = np.bincount(inv, weights=av)
            for c, s in zip(uc.tolist(), sums.tolist()):
                area_by_code[c] = area_by_code.get(c, 0.0) + s

    if not area_by_code:
        logger.error("No valid WSF pixels found.")
        return None

    if dataset == "tracker":
        # Cumulative area over sorted (year, month): each pixel's value is the
        # time it became built, so cumulative-to-(yr,mo) = sum of all bins <= it.
        codes_sorted = sorted(area_by_code)
        running = 0.0
        cumulative = []
        for c in codes_sorted:
            running += area_by_code[c]
            cumulative.append({"year": c // 100, "month": c % 100,
                               "cumulative_sq_km": running})
        df = pd.DataFrame(cumulative)
    else:
        min_year, max_year = min(area_by_code), max(area_by_code)
        running = 0.0
        cumulative = []
        for yr in range(min_year, max_year + 1):
            running += area_by_code.get(yr, 0.0)
            cumulative.append({"year": yr, "cumulative_sq_km": running})
        df = pd.DataFrame(cumulative)

    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    df.to_csv(output_path, index=False)
    logger.info(f"WSF stats saved to: {output_path}")

    if return_df:
        return df
    return None


def _resample_to_target(data, src_meta, target_meta, method=Resampling.nearest):
    """Resample a raster array to match target raster's resolution and extent.
    Returns (resampled_array, resampled_meta)."""
    dst_crs = target_meta.get("crs", src_meta["crs"])
    dst_transform = target_meta["transform"]
    dst_width = target_meta["width"]
    dst_height = target_meta["height"]

    # Ensure 3D
    if data.ndim == 2:
        data = data[np.newaxis, :, :]

    destination = np.zeros((data.shape[0], dst_height, dst_width), dtype=data.dtype)

    reproject(
        source=data,
        destination=destination,
        src_transform=src_meta["transform"],
        src_crs=src_meta.get("crs", "EPSG:4326"),
        dst_transform=dst_transform,
        dst_crs=dst_crs,
        dst_width=dst_width,
        dst_height=dst_height,
        resampling=method,
    )

    out_meta = target_meta.copy()
    out_meta.update({"count": data.shape[0], "dtype": str(data.dtype)})

    return destination, out_meta


def harmonize_wsf(
        aoi: gpd.GeoDataFrame,
        city_name: str,
        output_dir: str,
        dist_thresh: int = 10,
        return_df: bool = False
    ):
    """
    Harmonize WSF Evolution (30m, 1985-2015) with WSF Tracker (10m, 2016+).
    Adapted from Nouakchott wsf_harmonize.py.

    Pipeline:
      1. Mode resample tracker 10m → 30m
      2. Create evo_c: evo clipped to confirmed 2016 tracker overlap
      3. EDT on raw evo (all evo pixels as anchors) with binary opening cleanup
      4. Backdate disputed pixels within threshold using nearest evo year
      5. Combine: evo_c + backdated + tracker remaining

    Output:
    - {city}_wsf_harmonized.tif (spatial)
    - processed/wsf_harmonized.csv (tabular) with columns:
      year, cumulative_sq_km, source, growth_percentage
    """
    import xarray as xr
    import rioxarray
    from scipy.ndimage import distance_transform_edt, binary_opening

    logger.info("Starting WSF harmonization...")

    spatial_dir = os.path.join(output_dir, "spatial")
    tabular_dir = os.path.join(output_dir, "tabular")
    tracker_path = os.path.join(spatial_dir, f"{city_name}_wsf_tracker.tif")
    evo_path = os.path.join(spatial_dir, f"{city_name}_wsf_evolution.tif")

    if not os.path.exists(tracker_path):
        logger.error(f"WSF Tracker not found: {tracker_path}")
        return None
    if not os.path.exists(evo_path):
        logger.error(f"WSF Evolution not found: {evo_path}")
        return None

    # Load evolution + tracker onto ONE shared grid, capping resolution at
    # national scale. The distance_transform_edt below is GLOBAL (can't be
    # windowed/chunked), so the whole array must fit in RAM. A 30m national grid
    # (~2e9 px) OOMs; ~100m (~1.8e8 px) fits. Corridors/cities (e.g. Lobito,
    # ~5e7 px) stay at native 30m — the cap doesn't trigger. Warp-reading also
    # avoids ever materializing the full 10m tracker.
    from rasterio.transform import from_origin
    NAT_CAP = 3e8  # px; above this, coarsen so EDT fits

    with rasterio.open(evo_path) as esrc:
        e_left, e_bottom, e_right, e_top = esrc.bounds
        native_res = abs(esrc.transform.a)
        target_res = native_res
        if esrc.width * esrc.height > NAT_CAP:
            target_res = max(native_res, 100 / 111320.0)  # ~100m in degrees
            logger.info(f"National scale: harmonizing at ~{round(target_res * 111320)}m "
                        f"(global EDT memory cap)")
        cw = int(round((e_right - e_left) / target_res))
        ch = int(round((e_top - e_bottom) / target_res))
        dst_transform = from_origin(e_left, e_top, target_res, target_res)
        evo_arr = np.empty((ch, cw), dtype=np.float32)
        reproject(source=rasterio.band(esrc, 1), destination=evo_arr,
                  src_transform=esrc.transform, src_crs=esrc.crs,
                  dst_transform=dst_transform, dst_crs=esrc.crs,
                  resampling=Resampling.mode)

    # Tracker 'era' band -> same shared grid (mode-resample, then floor to year).
    # Note: at native res this matches the old floor-then-mode; the mode is over
    # discrete half-year era values so flooring after is equivalent in practice.
    with rasterio.open(tracker_path) as tsrc:
        tband = 2 if tsrc.count >= 2 else 1
        trk_arr = np.empty((ch, cw), dtype=np.float32)
        reproject(source=rasterio.band(tsrc, tband), destination=trk_arr,
                  src_transform=tsrc.transform, src_crs=tsrc.crs,
                  dst_transform=dst_transform, dst_crs=esrc.crs,
                  resampling=Resampling.mode)

    ys = e_top - (np.arange(ch) + 0.5) * target_res
    xs = e_left + (np.arange(cw) + 0.5) * target_res

    def _da(arr):
        return (xr.DataArray(arr, dims=('y', 'x'), coords={'y': ys, 'x': xs})
                .rio.write_crs(4326).rio.write_transform(dst_transform))

    evo = _da(np.where(evo_arr > 0, evo_arr, np.nan))
    trk_mode = _da(np.floor(np.where(trk_arr >= 2016, trk_arr, np.nan)))
    trk_mode = trk_mode.where(trk_mode >= 2016)

    # Evo clipped to confirmed 2016 overlap
    evo_c = evo.where((trk_mode == 2016) & (evo > 0))

    # EDT on raw evo (all evo pixels as anchors) with binary opening cleanup
    evo_binary = (evo.values > 0).astype(bool)
    evo_cleaned = binary_opening(evo_binary, structure=np.ones((3, 3)))

    evo_clean_vals = evo.values.copy()
    evo_clean_vals[~evo_cleaned] = np.nan
    mask = ~(evo_clean_vals > 0)
    distances, nearest_idx = distance_transform_edt(
        mask, return_distances=True, return_indices=True
    )
    backdated = evo_clean_vals[nearest_idx[0], nearest_idx[1]]

    disputed = (trk_mode == 2016).values & ~(evo.values > 0)

    # Auto dist_thresh: 90th percentile of disputed-pixel distances. For dense
    # cities this stays small (~5-10px); for sparse corridors (e.g. Lobito) it
    # scales up automatically so distant rural dev gets backdated too instead
    # of piling into the tracker-2016 bucket and producing an artificial spike.
    disputed_dists = distances[disputed]
    if disputed_dists.size > 0:
        auto_thresh = int(np.ceil(np.percentile(disputed_dists, 90)))
        median_d = int(np.median(disputed_dists))
        logger.info(
            f"Auto dist_thresh: {auto_thresh} pixels "
            f"(~{auto_thresh * 30}m at 30m res) | "
            f"median disputed dist: {median_d}px, 90th: {auto_thresh}px, "
            f"manual default was {dist_thresh}"
        )
        dist_thresh = auto_thresh
    else:
        logger.info(f"Distance threshold: {dist_thresh} pixels (~{dist_thresh * 30}m at 30m res)")

    # Backdate disputed pixels within threshold
    needs_backdate = (trk_mode == 2016) & ~(evo > 0) & (distances <= dist_thresh)

    n_disputed = int(disputed.sum())
    n_backdated = int(needs_backdate.values.sum())
    logger.info(f"Disputed pixels: {n_disputed:,}")
    if n_disputed > 0:
        logger.info(f"Backdated:       {n_backdated:,} ({n_backdated / n_disputed * 100:.1f}%)")

    # Combine: evo_c + backdated + tracker remaining
    combined = evo_c.copy()
    combined.values[needs_backdate.values] = backdated[needs_backdate.values]
    trk_remaining = trk_mode.where(trk_mode >= 2016)
    combined = combined.where(combined > 0, trk_remaining)

    # Save raster
    output_tif = os.path.join(spatial_dir, f'{city_name}_wsf_harmonized.tif')
    combined.rio.to_raster(output_tif)
    logger.info(f"Saved raster: {output_tif}")

    # Clip to AOI for stats only
    evo_aoi = evo.rio.clip(aoi.geometry)
    evo_c_aoi = evo_c.rio.clip(aoi.geometry)
    trk_mode_aoi = trk_mode.rio.clip(aoi.geometry)
    combined_aoi = combined.rio.clip(aoi.geometry)

    # Compute pixel area in sq km
    res_x = abs(float(combined_aoi.x[1] - combined_aoi.x[0]))
    res_y = abs(float(combined_aoi.y[1] - combined_aoi.y[0]))
    lat_mid = float(combined_aoi.y.mean())
    m_per_deg_x = 111320 * np.cos(np.radians(lat_mid))
    m_per_deg_y = 110540
    pixel_area_km2 = (res_x * m_per_deg_x) * (res_y * m_per_deg_y) / 1e6

    # Compute cumulative stats per source (AOI only)
    def get_stats(da, source_name, min_val=0):
        vals = da.values[~np.isnan(da.values)]
        vals = vals[vals > min_val]
        if len(vals) == 0:
            return pd.DataFrame(columns=['year', 'cumulative_sq_km', 'source', 'growth_percentage'])
        years, counts = np.unique(vals.astype(int), return_counts=True)
        cum = np.cumsum(counts)
        cum_km2 = cum * pixel_area_km2
        growth = np.concatenate([[np.nan], np.diff(cum_km2) / cum_km2[:-1] * 100])
        return pd.DataFrame({
            'year': years,
            'cumulative_sq_km': np.round(cum_km2, 3),
            'source': source_name,
            'growth_percentage': np.round(growth, 3),
        })

    df = pd.concat([
        get_stats(evo_aoi, 'WSF Evolution'),
        get_stats(evo_c_aoi, 'WSF Evolution (masked)'),
        get_stats(trk_mode_aoi, 'WSF Tracker', min_val=2015),
        get_stats(combined_aoi, 'WSF Harmonized'),
    ], ignore_index=True)

    os.makedirs(tabular_dir, exist_ok=True)
    output_csv = os.path.join(tabular_dir, f'{city_name}_wsf_harmonized.csv')
    df.to_csv(output_csv, index=False)
    logger.info(f"Saved CSV: {output_csv}")

    if return_df:
        return combined, df
    return None


# From Caroline's clean.py — clean_uba_area()
def compute_histogram(
        city_name: str,
        output_dir: str,
        clipped_image=None,
        clipped_meta=None,
        return_df: bool = False
    ):
    """
    Bin WSF Evolution raster by decade of urban expansion.
    Produces uba_area.csv with columns: bin, year, count, percentage.
    """

    logger.info("Starting UBA area histogram analysis…")

    bins = [
        {"range": "Before 1985", "min_year": 0, "max_year": 1985},
        {"range": "1986-1995", "min_year": 1986, "max_year": 1995},
        {"range": "1996-2005", "min_year": 1996, "max_year": 2005},
        {"range": "2006-2015", "min_year": 2006, "max_year": 2015},
    ]

    def _bin_counts(valid):
        c = []
        for b in bins:
            if b["range"] == "Before 1985":
                c.append(int(np.sum(valid <= b["max_year"])))
            else:
                c.append(int(np.sum((valid >= b["min_year"]) & (valid <= b["max_year"]))))
        return np.array(c, dtype=np.int64)

    def _valid(arr, nd):
        v = arr[arr != nd] if nd is not None else arr[np.isfinite(arr)]
        return v[(v >= 1900) & (v <= 2030)]

    counts = np.zeros(len(bins), dtype=np.int64)
    total_pixels = 0

    if clipped_image is not None and clipped_meta is not None:
        v = _valid(clipped_image.squeeze().astype(float), clipped_meta.get("nodata"))
        counts += _bin_counts(v)
        total_pixels += int(v.size)
    else:
        # Accumulate bin counts in ROW STRIPS — a full national evolution raster
        # (~2e9 px) OOMs if read whole; a histogram is exact when windowed.
        from rasterio.windows import Window
        raster_path = os.path.join(output_dir, "spatial", f"{city_name}_wsf_evolution.tif")
        if not os.path.exists(raster_path):
            logger.error(f"WSF evolution raster not found at: {raster_path}")
            return None
        with rasterio.open(raster_path) as src:
            nd = src.nodata
            H, W = src.height, src.width
            STRIP = 4096
            for r in range(0, H, STRIP):
                h = min(STRIP, H - r)
                d = src.read(1, window=Window(0, r, W, h)).astype(float)
                v = _valid(d, nd)
                if v.size:
                    counts += _bin_counts(v)
                    total_pixels += int(v.size)

    if total_pixels == 0:
        logger.error("No valid UBA year values.")
        return None

    bin_data = []
    for b, count in zip(bins, counts.tolist()):
        representative_year = "≤1985" if b["range"] == "Before 1985" else f"{b['min_year']}-{b['max_year']}"
        bin_data.append({
            'bin': b["range"],
            'year': representative_year,
            'count': count,
            'percentage': round((count / total_pixels) * 100, 2) if total_pixels > 0 else 0
        })

    result_df = pd.DataFrame(bin_data)

    tabular_dir = os.path.join(output_dir, "tabular")
    os.makedirs(tabular_dir, exist_ok=True)
    output_path = os.path.join(tabular_dir, f"{city_name}_uba_area.csv")

    try:
        result_df.to_csv(output_path, index=False)
        logger.info(f"UBA area histogram saved to: {output_path}")
    except Exception as e:
        logger.error(f"Error saving histogram CSV: {e}")

    if return_df:
        return result_df
    return None
