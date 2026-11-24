import os
import io
import zipfile
import requests
import geopandas as gpd
from shapely.geometry import shape, Point
from core.py.log_module import setup_logger

logger = setup_logger(__name__)

data_source = None

AQUIFERS_GEOJSON_URL = "https://gravis.gfz.de/basins/aquifers/aquifers.geojson"
CSV_ZIP_URL = "https://gravis.gfz.de/zipcsvdata/G3P/G3P/aquifers/{basin_name}"


def find_aquifer_basin(aoi):
    """
    Download aquifer basin boundaries and find which basin the AOI falls in.
    Returns the basin name or None if the AOI doesn't fall in any basin.
    """
    logger.info("Downloading aquifer basin boundaries...")
    resp = requests.get(AQUIFERS_GEOJSON_URL, timeout=30)
    resp.raise_for_status()
    basins = resp.json()

    # Use AOI centroid for point-in-polygon lookup
    aoi_4326 = aoi.to_crs(4326)
    centroid = aoi_4326.geometry.unary_union.centroid

    for feat in basins["features"]:
        polygon = shape(feat["geometry"])
        if polygon.contains(centroid):
            basin_name = feat["properties"]["Name"]
            logger.info(f"AOI falls in aquifer basin: {basin_name}")
            return basin_name

    # Fallback: check if any basin intersects the AOI
    aoi_shape = aoi_4326.geometry.unary_union
    for feat in basins["features"]:
        polygon = shape(feat["geometry"])
        if polygon.intersects(aoi_shape):
            basin_name = feat["properties"]["Name"]
            logger.info(f"AOI intersects aquifer basin: {basin_name}")
            return basin_name

    logger.warning("AOI does not fall within any known aquifer basin")
    return None


def datacollection(aoi, city_name, output_dir):
    """
    Download G3P groundwater storage data for the aquifer basin containing the AOI.
    Saves GWSA and SWS CSVs to tabular/.

    Source: https://gravis.gfz.de/gws (G3P v1.12, GRACE/GRACE-FO)
    """
    logger.info("Starting groundwater data collection...")

    global data_source
    basin_name = find_aquifer_basin(aoi)
    if basin_name is None:
        data_source = "No aquifer basin"
        return None
    data_source = f"G3P ({basin_name})"

    # Download CSV zip for this basin
    url = CSV_ZIP_URL.format(basin_name=requests.utils.quote(basin_name))
    logger.info(f"Downloading G3P data for {basin_name}...")
    resp = requests.get(url, timeout=60)
    resp.raise_for_status()

    # Extract CSVs
    tabular_dir = os.path.join(output_dir, "tabular")
    os.makedirs(tabular_dir, exist_ok=True)

    saved_files = []
    with zipfile.ZipFile(io.BytesIO(resp.content)) as zf:
        for name in zf.namelist():
            if name.endswith(".csv"):
                zf.extract(name, tabular_dir)
                saved_files.append(name)
                logger.info(f"Saved: {name}")

    logger.info(f"Groundwater data collection complete ({len(saved_files)} files)")
    return basin_name
