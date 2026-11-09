# import
import os
import math
import numpy as np
import geopandas as gpd
import rasterio
from rasterio.merge import merge
from core.py.log_module import setup_logger

logger = setup_logger(__name__)

# GCS bucket path for WSF Tracker (private bucket, needs credentials)
GCS_TRACKER_BASE = "/vsigs/city-scan-global-private/wsf_tracker"

# DLR download URL template for WSF Evolution
DLR_EVO_URL = "https://download.geoservice.dlr.de/WSF_EVO/files/WSFevolution_v1_{x}_{y}/WSFevolution_v1_{x}_{y}.tif"


def _tile_grid(aoi_bounds):
    """Compute 2-degree tile grid coordinates covering the AOI extent.
    Returns list of (x, y) tuples matching DLR/WSF tile naming convention."""
    minx, miny, maxx, maxy = aoi_bounds

    # WSF Tracker: floor to nearest even number, step by 2
    x_seq = list(range(math.floor(minx - minx % 2), math.ceil(maxx) + 1, 2))
    # WSF Evolution uses floor(val/2)*2 rounding
    y_seq = list(range(math.floor(miny - miny % 2), math.ceil(maxy) + 1, 2))

    return [(x, y) for x in x_seq for y in y_seq]


def _windowed_mosaic(tile_datasets, aoi, out_path, indexes=None, out_dtype=None,
                     transform_fn=None, band_desc=None, strip_rows=2048):
    """
    Mosaic tiles into out_path clipped to the AOI, processed in row strips so
    the full mosaic is NEVER held in memory (national AOIs OOM otherwise:
    a whole-country 10m grid is tens of GB uncompressed).

    Per strip: merge(bounds=strip) -> mask outside-AOI to nodata ->
    optional transform_fn(array) -> write. Peak memory = one strip.

    Parameters
    ----------
    indexes : list[int] or None — source bands to read (None = all)
    out_dtype : str or None — output dtype (None = source dtype)
    transform_fn : callable or None — applied to each strip array before write
    band_desc : str or None — band description for single-band outputs
    """
    from rasterio.features import geometry_mask
    from rasterio.windows import Window
    from rasterio.transform import from_origin

    ref = tile_datasets[0]
    resx, resy = ref.res
    n_bands = len(indexes) if indexes else ref.count
    aoi_shapes = [geom.__geo_interface__ for geom in aoi.geometry]

    # Output grid: AOI bounds snapped outward to the tiles' pixel grid
    minx, miny, maxx, maxy = aoi.total_bounds
    ox, oy = ref.transform.c, ref.transform.f  # tile grid origin
    col0 = math.floor((minx - ox) / resx)
    row0 = math.floor((oy - maxy) / resy)
    col1 = math.ceil((maxx - ox) / resx)
    row1 = math.ceil((oy - miny) / resy)
    width, height = col1 - col0, row1 - row0
    out_transform = from_origin(ox + col0 * resx, oy - row0 * resy, resx, resy)

    profile = {
        "driver": "GTiff", "width": width, "height": height, "count": n_bands,
        "dtype": out_dtype or ref.dtypes[0], "crs": ref.crs,
        "transform": out_transform, "nodata": 0,
        "tiled": True, "compress": "deflate", "BIGTIFF": "IF_SAFER",
    }

    with rasterio.open(out_path, "w", **profile) as dst:
        if band_desc and n_bands == 1:
            dst.set_band_description(1, band_desc)
        for r in range(0, height, strip_rows):
            h = min(strip_rows, height - r)
            strip_bounds = rasterio.windows.bounds(Window(0, r, width, h), out_transform)
            strip, _ = merge(tile_datasets, bounds=strip_bounds, indexes=indexes, nodata=0)
            strip = strip[:, :h, :width]  # guard against merge edge rounding
            strip_transform = rasterio.windows.transform(Window(0, r, width, h), out_transform)
            inside = geometry_mask(aoi_shapes, out_shape=(h, width),
                                   transform=strip_transform, invert=True)
            strip[:, ~inside] = 0
            if transform_fn is not None:
                strip = transform_fn(strip)
            dst.write(strip.astype(profile["dtype"]), window=Window(0, r, width, h))

    return profile


def datacollection(
        aoi: gpd.GeoDataFrame,
        city_name: str,
        output_dir: str,
        return_raster: bool = False
    ):
    """
    Download WSF Tracker and WSF Evolution, merge tiles, crop to AOI, save TIFs.

    WSF Tracker: Sentinel-2 (10m), 2016-2025, from GCS (2-degree tiles)
    WSF Evolution: Landsat (30m), 1985-2015, from DLR (2-degree tiles)

    Parameters
    ----------
    aoi : GeoDataFrame
        AOI polygon(s) in EPSG:4326.
    city_name : str
        City name for naming output files.
    output_dir : str
        Directory where clipped rasters will be saved.
    return_raster : bool
        If True, return dict of (array, meta) tuples.

    Returns
    -------
    dict or None
        Keys: 'tracker', 'evolution'. Values: (array, meta) tuples.
    """

    logger.info("Starting WSF data collection...")

    if aoi is None or aoi.empty:
        logger.error("AOI is empty. Cannot continue.")
        return None

    spatial_dir = os.path.join(output_dir, "spatial")
    os.makedirs(spatial_dir, exist_ok=True)

    aoi_bounds = aoi.total_bounds  # (minx, miny, maxx, maxy)
    aoi_shapes = [geom.__geo_interface__ for geom in aoi.geometry]
    tiles = _tile_grid(aoi_bounds)

    arrays = {}
    metas = {}

    # ==================================================================
    # WSF Tracker — Sentinel-2 (10m), 2016-2025, from GCS
    # 2-degree tiles: WSFtracker_20160701-20250701_{x}_{y}.tif
    # ==================================================================
    logger.info("Collecting WSF Tracker...")

    tracker_datasets = []
    for x, y in tiles:
        fname = f"WSFtracker_20160701-20250701_{x}_{y}.tif"
        gcs_path = f"{GCS_TRACKER_BASE}/{fname}"
        try:
            src = rasterio.open(gcs_path)
            tracker_datasets.append(src)
            logger.info(f"  Opened tile: {fname}")
        except Exception:
            logger.info(f"  Tile not found (ocean/missing): {fname}")

    if len(tracker_datasets) == 0:
        logger.error("No WSF Tracker tiles found for this area")
    else:
        # Convert mode values to fractional years (2016.5, 2017.0, ...) per strip.
        # Band 1 = mode (settlement class), values 1..N map to years starting at
        # 2016.5 with 0.5 step; 0 stays 0 (nodata).
        def _mode_to_era(strip):
            era = 2016.0 + strip.astype(np.float32) * 0.5
            era[strip <= 0] = 0
            return era

        tracker_path = os.path.join(spatial_dir, f"{city_name}_wsf_tracker.tif")
        tracker_out_meta = _windowed_mosaic(
            tracker_datasets, aoi, tracker_path,
            indexes=[1], out_dtype="float32",
            transform_fn=_mode_to_era, band_desc="era")

        for src in tracker_datasets:
            src.close()
        logger.info(f"WSF Tracker saved to: {tracker_path}")

        if return_raster:
            with rasterio.open(tracker_path) as src:
                arrays['tracker'] = src.read()
            metas['tracker'] = tracker_out_meta

    # ==================================================================
    # WSF Evolution — Landsat (30m), 1985-2015, from DLR
    # 2-degree tiles: WSFevolution_v1_{x}_{y}.tif
    # Direct download (tiles are small enough)
    # ==================================================================
    logger.info("Collecting WSF Evolution...")

    evo_datasets = []
    for x, y in tiles:
        tile_name = f"WSFevolution_v1_{x}_{y}"
        url = f"/vsicurl/https://download.geoservice.dlr.de/WSF_EVO/files/{tile_name}/{tile_name}.tif"
        try:
            src = rasterio.open(url)
            evo_datasets.append(src)
            logger.info(f"  Opened tile: {tile_name}")
        except Exception:
            logger.info(f"  Tile not found (ocean/missing): {tile_name}")

    if len(evo_datasets) == 0:
        logger.error("No WSF Evolution tiles found for this area")
    else:
        evo_path = os.path.join(spatial_dir, f"{city_name}_wsf_evolution.tif")
        evo_meta = _windowed_mosaic(evo_datasets, aoi, evo_path)

        for src in evo_datasets:
            src.close()
        logger.info(f"WSF Evolution saved to: {evo_path}")

        if return_raster:
            with rasterio.open(evo_path) as src:
                arrays['evolution'] = src.read()
            metas['evolution'] = evo_meta

    logger.info("WSF data collection complete.")

    if return_raster:
        return arrays, metas

    return None
