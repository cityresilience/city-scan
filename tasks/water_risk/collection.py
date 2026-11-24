import os
import ee
import geopandas as gpd
from core.py.log_module import setup_logger
from core.py.gee_fns import aoi_to_ee_geometry

logger = setup_logger(__name__)


def datacollection(aoi, city_name, output_dir):
    """
    Download WRI Aqueduct v4 water risk data from GEE.
    Clips the global FeatureCollection to the AOI and saves as GeoJSON.

    Source: WRI/GppWater/aqueduct_water_risk_v4
    """

    logger.info("Starting WRI Aqueduct water risk data collection...")

    AOI, bounds = aoi_to_ee_geometry(aoi)

    # Load WRI Aqueduct v4 FeatureCollection
    # fc = ee.FeatureCollection('WRI/GppWater/aqueduct_water_risk_v4')
    fc = ee.FeatureCollection('WRI/Aqueduct_Water_Risk/V4/baseline_annual')

    # Filter to AOI
    fc_clipped = fc.filterBounds(AOI)

    # Get feature count
    count = fc_clipped.size().getInfo()
    logger.info(f"Found {count} water risk features intersecting AOI")

    if count == 0:
        logger.warning("No WRI Aqueduct features found for this AOI")
        return None

    # Convert to GeoDataFrame
    features = fc_clipped.getInfo()['features']
    gdf = gpd.GeoDataFrame.from_features(features, crs="EPSG:4326")

    # Clip to AOI boundary
    aoi_4326 = aoi.to_crs(4326)
    gdf = gpd.clip(gdf, aoi_4326)

    if gdf.empty:
        logger.warning("No water risk data after clipping to AOI")
        return None

    # WRI encodes NODATA as -9999 in raw score columns — replace with NaN so
    # downstream binning/quantile logic ignores them instead of poisoning the scale.
    import numpy as np
    numeric_cols = gdf.select_dtypes(include="number").columns
    gdf[numeric_cols] = gdf[numeric_cols].replace(-9999, np.nan)

    # Save
    spatial_dir = os.path.join(output_dir, "spatial")
    os.makedirs(spatial_dir, exist_ok=True)
    output_path = os.path.join(spatial_dir, f"{city_name}_water_risk.geojson")
    gdf.to_file(output_path, driver="GeoJSON")
    logger.info(f"Water risk data saved to: {output_path}")

    return gdf
