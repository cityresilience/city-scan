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
    """Multi-year mean UV Aerosol Index from Sentinel-5P (TROPOMI).

    Source: COPERNICUS/S5P/OFFL/L3_AER_AI, band absorbing_aerosol_index.
    ~5 km, 2018+. The absorbing-aerosol index flags dust + smoke.
    """

    logger.info("Starting aerosol data collection...")

    AOI, bounds = fns.aoi_to_ee_geometry(aoi)

    s5p = (ee.ImageCollection('COPERNICUS/S5P/OFFL/L3_AER_AI')
           .select('absorbing_aerosol_index')
           .filterDate('2018-07-01', '2100-01-01')
           .filterBounds(AOI))
    aai_mean = s5p.mean()

    spatial_dir = os.path.join(output_dir, "spatial")
    os.makedirs(spatial_dir, exist_ok=True)

    out_path = os.path.join(spatial_dir, f"{city_name}_aerosol.tif")
    fns.tiled_collection(aai_mean, aoi, out_path, scale=1113.2,
                         dtype='float32', nodata=float('nan'), output_dir=output_dir)
    logger.info(f"Saved aerosol index mean: {out_path}")

    return {'aerosol': out_path}
