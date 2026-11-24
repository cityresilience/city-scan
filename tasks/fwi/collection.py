# import
import os
import glob
import numpy as np
import geopandas as gpd
import rasterio
from rasterio.mask import mask
from shapely.geometry import box
from rasterio.crs import CRS
from core.py.log_module import setup_logger
from datetime import datetime, timedelta

# Import raster processing module from backend
import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../../backend'))
from core.py import raster_module as raster_pro

logger = setup_logger(__name__)

def datacollection(
        aoi: gpd.GeoDataFrame,
        city_name: str,
        output_dir: str,
        fwi_first_year: int,
        fwi_last_year: int,
        return_raster: bool = True
    ):
    """
    Download FWI raster from public GCS bucket for the AOI and clip it.

    Parameters
    ----------
    aoi : GeoDataFrame
        AOI polygon(s).
    city_name : str
        City name for naming output files.
    output_dir : str
        Directory where clipped raster will be saved.
    fwi_first_year : int
        Year to start FWI analysis as indicated in city_inputs.yml
    fwi_last_year : int
        Year to finish FWI analysis as indicated in city_inputs.yml
    return_raster : bool, optional
        Whether to return raster data (default True, for consistency with other modules)

    Returns
    -------
    tuple
        (fwi_raster_dict, out_meta) where:
        - fwi_raster_dict: Dictionary {date_str → clipped_raster_array}
        - out_meta: Rasterio metadata for writing outputs
    """

    logger.info("Starting FWI data collection…")

    # Validate AOI
    if aoi is None or aoi.empty:
        logger.error("AOI is empty. Cannot continue.")
        return None, None

    # Ensure AOI is in correct CRS for raster operations
    if aoi.crs is None:
        logger.error("AOI has no CRS defined.")
        return None, None

    logger.info(f"AOI CRS: {aoi.crs}")

    # Create buffered bounding box around AOI
    aoi_buff = aoi.geometry.buffer(2).total_bounds
    features = gpd.GeoDataFrame(
        {'geometry': box(*aoi_buff)}, 
        index=[0], 
        crs=CRS.from_epsg(4326)
    ).geometry

    # Initialize raster dictionary
    fwi_raster_dict = {}
    out_meta = None

    logger.info(f"Retrieving FWI data for years {fwi_first_year}-{fwi_last_year}")

    # Generate date range - sample first day of each week (52 samples/year instead of 365)
    start_date = datetime(fwi_first_year, 1, 1)
    end_date = datetime(fwi_last_year, 12, 31)
    
    current_date = start_date
    file_count = 0
    success_count = 0

    while current_date <= end_date:
        date_str = current_date.strftime('%Y%m%d')
        gcs_url = f"/vsicurl/https://storage.googleapis.com/city-scan-global-public/nasa_fwi/FWI.GEOS-5.Daily.Default.{date_str}.tif"
        
        try:
            # Attempt to clip raster from GCS URL
            out_image, file_meta = raster_pro.raster_mask_file(gcs_url, features)
            
            # Filter out empty rasters
            if np.nansum(out_image) != 0:
                fwi_raster_dict[date_str] = out_image
                success_count += 1
                
                # Store metadata from first successful read
                if out_meta is None:
                    out_meta = file_meta
                
                logger.info(f"Successfully clipped FWI raster for {date_str}")
            
            file_count += 1
            
        except Exception as e:
            # Many dates may not have data available, so this is expected
            logger.warning(f"Skipping {date_str}: {str(e)[:100]}")
        
        current_date += timedelta(weeks=1)

    logger.info(f"FWI data collection complete. Processed {file_count} dates, successfully clipped {success_count} rasters.")
    
    if not fwi_raster_dict:
        logger.error("No valid FWI rasters were collected. Check data availability and AOI.")
        return None, None

    logger.info(f"Collected {len(fwi_raster_dict)} non-empty FWI rasters.")
    
    return fwi_raster_dict, out_meta
