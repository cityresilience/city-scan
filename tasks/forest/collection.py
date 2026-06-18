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

    # Forest cover 2023
    tif_fc23 = os.path.join(spatial_dir, f"{city_name}_forest_cover23.tif")
    fc23_rio = fns.tiled_collection(forestCover23, aoi, scale=30, resampling=Resampling.nearest)
    fc23_rio = fc23_rio.rio.clip(aoi.to_crs(fc23_rio.rio.crs).geometry, drop=True)
    fc23_rio = fc23_rio.fillna(0).round().astype(np.int8)
    fc23_rio.rio.write_nodata(0, inplace=True)
    fc23_rio.rio.to_raster(tif_fc23)
    logger.info(f"Forest cover raster saved to: {tif_fc23}")

    # Deforestation year
    tif_defor = os.path.join(spatial_dir, f"{city_name}_deforestation.tif")
    defor_rio = fns.tiled_collection(deforestation_year, aoi, scale=30, resampling=Resampling.nearest)
    defor_rio = defor_rio.rio.clip(aoi.to_crs(defor_rio.rio.crs).geometry, drop=True)
    defor_rio = defor_rio.fillna(0).round().astype(np.int16)
    defor_rio.rio.write_nodata(0, inplace=True)
    defor_rio.rio.to_raster(tif_defor)
    logger.info(f"Deforestation raster saved to: {tif_defor}")

    if return_raster:
        return fc23_rio, defor_rio

    return None
