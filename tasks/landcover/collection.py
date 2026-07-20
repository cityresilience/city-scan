from core.py.log_module import setup_logger
logger = setup_logger(__name__)

import os

import ee
import numpy as np

from core.py import gee_fns as fns


def datacollection(
    aoi,
    city_name,
    output_dir,
    return_raster=False
    ):

    logger.info("Starting Land Cover data collection...")

    # ------------------------------------------------------------------
    # 1. Load AOI as EE Geometry and Image Source
    # ------------------------------------------------------------------

    lc = ee.ImageCollection('ESA/WorldCover/v200').first().select('Map')
    # Pin server-side grid to match xee's extraction (EPSG:3857, 10m). Without this,
    # GEE resamples categorical class codes and emits fractional values that break
    # the factor palette in layers.yml (renders white).
    lc = lc.reproject(crs='EPSG:3857', scale=10)

    spatial_dir = os.path.join(output_dir, "spatial")
    os.makedirs(spatial_dir, exist_ok=True)
    tif_path = os.path.join(spatial_dir, f"{city_name}_lc.tif")

    from rasterio.enums import Resampling
    lc_rio = fns.tiled_collection(lc, aoi, scale=10, resampling=Resampling.nearest)
    lc_rio = lc_rio.rio.clip(aoi.to_crs(lc_rio.rio.crs).geometry, drop=True)

    # Guard: snap any residual fractional values to nearest valid ESA WorldCover class.
    valid_codes = np.array([0, 10, 20, 30, 40, 50, 60, 70, 80, 90, 95, 100], dtype=np.uint8)
    arr = np.asarray(lc_rio.values)
    arr = np.where(np.isnan(arr), 0, arr)
    snapped = valid_codes[np.argmin(np.abs(arr[..., None] - valid_codes), axis=-1)]
    lc_rio = lc_rio.copy(data=snapped.astype(np.uint8))

    lc_rio.rio.to_raster(tif_path, dtype='uint8')

    logger.info(f"Land cover raster saved to: {tif_path}")

    if return_raster:
        return lc_rio

    return None
