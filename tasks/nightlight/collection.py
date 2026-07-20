from core.py.log_module import setup_logger
logger = setup_logger(__name__)

import os

import ee

from core.py import gee_fns as fns


def datacollection(
    aoi,
    city_name,
    output_dir,
    return_raster=False
):

    logger.info("Starting nightlight data collection...")

    AOI, bounds = fns.aoi_to_ee_geometry(aoi)

    viirs = ee.ImageCollection('NOAA/VIIRS/DNB/MONTHLY_V1/VCMSLCFG')
    max_date = ee.Date(viirs.reduceColumns(ee.Reducer.max(), ['system:time_start']).get('max'))
    date_range = ee.DateRange(max_date.advance(-10, 'year'), max_date)

    def addTime(image):
        return image.addBands(image.metadata('system:time_start').divide(1000 * 60 * 60 * 24 * 365))

    viirs_filtered = viirs.filterDate(date_range).filterBounds(AOI).map(addTime)

    linear_fit = viirs_filtered.select(['system:time_start', 'avg_rad']).reduce(ee.Reducer.linearFit())
    sum_of_light = viirs_filtered.select('avg_rad').reduce(ee.Reducer.sum())

    spatial_dir = os.path.join(output_dir, "spatial")
    os.makedirs(spatial_dir, exist_ok=True)

    results = {}

    linfit_rio = fns.tiled_collection(linear_fit.select('scale'), aoi, scale=463.83)
    linfit_rio = linfit_rio.rio.clip(aoi.to_crs(linfit_rio.rio.crs).geometry, drop=True)
    linfit_path = os.path.join(spatial_dir, f"{city_name}_linfit.tif")
    linfit_rio.rio.to_raster(linfit_path)
    logger.info(f"Saved linear fit: {linfit_path}")
    results['linfit'] = linfit_rio if return_raster else linfit_path

    sum_rio = fns.tiled_collection(sum_of_light.select('avg_rad_sum'), aoi, scale=463.83)
    sum_rio = sum_rio.rio.clip(aoi.to_crs(sum_rio.rio.crs).geometry, drop=True)
    sum_path = os.path.join(spatial_dir, f"{city_name}_avg_rad_sum.tif")
    sum_rio.rio.to_raster(sum_path)
    logger.info(f"Saved sum of lights: {sum_path}")
    results['avg_rad_sum'] = sum_rio if return_raster else sum_path

    return results
