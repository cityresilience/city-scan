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

    # Snap any residual fractional/nodata values to the nearest valid ESA
    # WorldCover class, applied per strip INSIDE the windowed writer (the
    # [..., None] broadcast expands each strip 12x — never the national grid).
    valid_codes = np.array([0, 10, 20, 30, 40, 50, 60, 70, 80, 90, 95, 100], dtype=np.uint8)

    def _snap(arr):  # arr: (bands, h, w) float; NaN already -> 0 by fillna=0
        return valid_codes[np.argmin(np.abs(arr[..., None] - valid_codes), axis=-1)]

    fns.tiled_collection(lc, aoi, tif_path, scale=10, dtype='uint8', nodata=0,
                          fillna=0, resampling=Resampling.nearest, transform_fn=_snap, output_dir=output_dir)

    logger.info(f"Land cover raster saved to: {tif_path}")

    if return_raster:
        return tif_path

    return None
