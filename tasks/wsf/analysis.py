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

    with rasterio.open(raster_path) as src:
        # Tracker TIF: band 2 ('era') has fractional years; Evolution TIF: band 1 has integer years
        if dataset == "tracker" and src.count >= 2:
            vals = src.read(2).astype(float)
        else:
            vals = src.read(1).astype(float)
        meta = src.meta.copy()

    # Cell areas in km2
    areas = _cell_areas_km2(meta)

    # Valid pixels: non-zero, non-nan
    valid_mask = (vals > 0) & (~np.isnan(vals))
    area_valid = areas[valid_mask]
    vals_valid = vals[valid_mask]

    if vals_valid.size == 0:
        logger.error("No valid WSF pixels found.")
        return None

    if dataset == "tracker":
        # Tracker: fractional years (e.g. 2016.5 = Jul 2016). Group by year+month.
        years_int = np.floor(vals_valid).astype(int)
        months_frac = vals_valid - years_int
        months_int = np.clip(np.round(months_frac * 12).astype(int), 1, 12)
        # Build unique (year, month) pairs sorted
        ym_pairs = sorted(set(zip(years_int, months_int)))
        cumulative = []
        for yr, mo in ym_pairs:
            mask = (years_int < yr) | ((years_int == yr) & (months_int <= mo))
            area = float(area_valid[mask].sum())
            cumulative.append({"year": yr, "month": mo, "cumulative_sq_km": area})
        df = pd.DataFrame(cumulative)
    else:
        # Evolution: integer year values in pixels
        vals_floored = np.floor(vals_valid).astype(int)
        min_year = int(vals_floored.min())
        max_year = int(vals_floored.max())
        years = list(range(min_year, max_year + 1))
        cumulative = []
        for yr in years:
            area = float(area_valid[vals_floored <= yr].sum())
            cumulative.append({"year": yr, "cumulative_sq_km": area})
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

    # Load data
    evolution = xr.open_dataset(evo_path)
    tracker = xr.open_dataset(tracker_path)

    # Process evolution (30m, 1985-2015)
    evo = evolution['band_data'].squeeze('band')
    evo = evo.where(evo > 0)
    evo = evo.rio.write_crs(4326)

    # Process tracker (10m, 2016-2025) — band index 1 = 'era' (fractional years)
    trk = tracker.isel(band=1 if tracker.sizes.get('band', 1) > 1 else 0)['band_data']
    trk = trk.rio.write_crs(4326)
    trk = np.floor(trk)

    # Mode resample tracker to 30m
    trk_mode = trk.rio.reproject_match(evo, resampling=Resampling.mode)
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

    # Load raster from disk if not provided
    if clipped_image is None or clipped_meta is None:
        raster_path = os.path.join(output_dir, "spatial", f"{city_name}_wsf_evolution.tif")

        if not os.path.exists(raster_path):
            logger.error(f"WSF evolution raster not found at: {raster_path}")
            return None

        try:
            with rasterio.open(raster_path) as src:
                clipped_image = src.read()
                clipped_meta = src.meta
        except Exception as e:
            logger.error(f"Failed to load raster: {e}")
            return None

    # Prepare valid data
    data = clipped_image.squeeze().astype(float)
    nodata_value = clipped_meta.get("nodata")
    if nodata_value is not None:
        valid_data = data[data != nodata_value]
    else:
        valid_data = data[~np.isnan(data)]
        valid_data = valid_data[np.isfinite(valid_data)]
    valid_data = valid_data[(valid_data >= 1900) & (valid_data <= 2030)]

    if valid_data.size == 0:
        logger.error("No valid UBA year values.")
        return None

    bins = [
        {"range": "Before 1985", "min_year": 0, "max_year": 1985},
        {"range": "1986-1995", "min_year": 1986, "max_year": 1995},
        {"range": "1996-2005", "min_year": 1996, "max_year": 2005},
        {"range": "2006-2015", "min_year": 2006, "max_year": 2015},
    ]

    total_pixels = len(valid_data)
    bin_data = []
    for b in bins:
        if b["range"] == "Before 1985":
            count = int(np.sum(valid_data <= b["max_year"]))
        else:
            count = int(np.sum((valid_data >= b["min_year"]) & (valid_data <= b["max_year"])))
        representative_year = f"≤1985" if b["range"] == "Before 1985" else f"{b['min_year']}-{b['max_year']}"
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
