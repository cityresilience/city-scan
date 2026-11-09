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

    logger.info("Starting Forest data collection...")

    fc = ee.Image("UMD/hansen/global_forest_change_2024_v1_12")

    deforestation0023 = fc.select('loss').eq(1).rename('fcloss0023')
    forestCover00 = fc.select('treecover2000').gte(20)
    forestCoverGain0012 = fc.select('gain').eq(1)
    forestCover23 = forestCover00.subtract(deforestation0023) \
        .add(forestCoverGain0012).gte(1).rename('fc23')
    deforestation_year = fc.select('lossyear').rename('lossyear')

    spatial_dir = os.path.join(output_dir, "spatial")
    os.makedirs(spatial_dir, exist_ok=True)

    from rasterio.enums import Resampling

    # Forest cover 2023 — streamed windowed (clip+fillna+cast per strip); never
    # holds the national array in RAM.
    tif_fc23 = os.path.join(spatial_dir, f"{city_name}_forest_cover23.tif")
    fns.tiled_collection(forestCover23, aoi, tif_fc23, scale=30, dtype='int8',
                          nodata=0, fillna=0, round_vals=True, resampling=Resampling.nearest, output_dir=output_dir)
    logger.info(f"Forest cover raster saved to: {tif_fc23}")

    # Deforestation year
    tif_defor = os.path.join(spatial_dir, f"{city_name}_deforestation.tif")
    fns.tiled_collection(deforestation_year, aoi, tif_defor, scale=30, dtype='int16',
                          nodata=0, fillna=0, round_vals=True, resampling=Resampling.nearest, output_dir=output_dir)
    logger.info(f"Deforestation raster saved to: {tif_defor}")

    if return_raster:
        return tif_fc23, tif_defor

    return None
