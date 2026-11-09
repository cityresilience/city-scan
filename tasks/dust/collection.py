from core.py.log_module import setup_logger
logger = setup_logger(__name__)

import os
import datetime

import ee

from core.py import gee_fns as fns

# CAMS NRT dust AOD -> ONE multi-band raster, one band per year (server-side toBands, one export).
# Each band is a single-year mean of the analysis frames (model_forecast_hour == 0).
# The dust band only exists from ~2022.
#
# BAD_FRAMES: individual CAMS frames that are corrupt (invalid geometry) and make ANY mean
# containing them fail with "internal error". 20230512T00F000 is one such frame; dropping it
# alone recovers all of 2023 (no need to skip the year). Add ids here if new ones surface.
FIRST_YEAR = 2022
BAD_FRAMES = ['20230512T00F000']


def datacollection(aoi, city_name, output_dir, return_raster=False):
    """Multi-band dust AOD (CAMS NRT): one band per year, built server-side, single export."""

    logger.info("Starting dust data collection...")

    AOI, bounds = fns.aoi_to_ee_geometry(aoi)
    last_year = datetime.datetime.now().year - 1          # current year is incomplete
    years = list(range(FIRST_YEAR, last_year + 1))
    logger.info(f"Dust: yearly AOD bands {years} (single multi-band export)")

    base = (ee.ImageCollection('ECMWF/CAMS/NRT')
            .select('dust_aerosol_optical_depth_at_550nm_surface')
            .filter(ee.Filter.eq('model_forecast_hour', 0))          # analysis frames only
            .filter(ee.Filter.inList('system:index', BAD_FRAMES).Not())  # drop corrupt frames
            .filterBounds(AOI))

    def yearly(y):
        y = ee.Number(y)
        start = ee.Date.fromYMD(y, 1, 1)
        return base.filterDate(start, start.advance(1, 'year')).mean()

    dust = ee.ImageCollection(ee.List(years).map(yearly)).toBands() \
             .rename([f'dust_{y}' for y in years])            # one band per year

    spatial_dir = os.path.join(output_dir, "spatial")
    os.makedirs(spatial_dir, exist_ok=True)
    out_path = os.path.join(spatial_dir, f"{city_name}_dust.tif")
    fns.tiled_collection(dust, aoi, out_path, scale=44528,
                         dtype='float32', nodata=float('nan'), output_dir=output_dir)
    logger.info(f"Saved dust AOD ({len(years)}-band yearly): {out_path}")
    return {'dust': out_path}
