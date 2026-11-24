# Download building footprints from OpenStreetMap.
# Routes to Geofabrik PBF for large AOIs, Overpass for typical cities — see core/py/osm_client.
import os
from core.py.log_module import setup_logger
from core.py import osm_client

logger = setup_logger(__name__)


def datacollection(aoi, city_name, output_dir):
    """
    Download building footprints from OSM, clip to AOI, save as FlatGeobuf.

    Parameters
    ----------
    aoi : GeoDataFrame
        AOI polygon(s).
    city_name : str
        City name for naming output files.
    output_dir : str
        Directory where output will be saved.
    """
    logger.info("Starting building footprint collection...")

    if aoi is None or aoi.empty:
        logger.error("AOI is empty.")
        return None

    spatial_dir = os.path.join(output_dir, "spatial")
    os.makedirs(spatial_dir, exist_ok=True)
    output_path = os.path.join(spatial_dir, f"{city_name}_building_footprints.fgb")

    if os.path.exists(output_path):
        logger.info(f"Building footprints already exist: {output_path}")
        return output_path

    buildings = osm_client.fetch_features(aoi, {"building": True})
    if buildings is None or len(buildings) == 0:
        logger.warning("No building data found for this area")
        return None

    buildings.to_file(output_path, driver="FlatGeobuf")
    file_size = os.path.getsize(output_path) / (1024 * 1024)
    logger.info(f"Saved {len(buildings)} buildings to: {output_path} ({file_size:.1f} MB)")

    return output_path
