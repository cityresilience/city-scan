import os
import yaml
import pandas as pd
import geopandas as gpd
from core.py.log_module import setup_logger

logger = setup_logger(__name__)

KOEPPEN_BUCKET = "city-scan-global-data"
KOEPPEN_BLOB = "climate-classification/Koeppen-Geiger-ASCII.csv"


def calculate_aoi_area(aoi):
    """Calculate AOI area in km² using equal-area projection."""
    return float(aoi.to_crs(epsg=6933).area.sum() / 1e6)


def get_koeppen_classification(aoi):
    """Look up Köppen climate classification for AOI centroid."""
    centroid = aoi.geometry.centroid.iloc[0]
    lon, lat = centroid.x, centroid.y

    try:
        from google.cloud import storage
        import io

        client = storage.Client()
        bucket = client.bucket(KOEPPEN_BUCKET)
        blob = bucket.blob(KOEPPEN_BLOB)
        content = blob.download_as_text()
        koeppen = pd.read_csv(io.StringIO(content))
    except Exception as e:
        logger.error(f"Failed to download Köppen CSV from GCS: {e}")
        return ""

    lon_min, lon_max = lon - 0.5, lon + 0.5
    lat_min, lat_max = lat - 0.5, lat + 0.5
    koeppen_city = koeppen[
        (koeppen[' Lon'].between(lon_min, lon_max)) &
        (koeppen['Lat'].between(lat_min, lat_max))
    ][' Cls'].unique()

    koeppen_text = ', '.join(koeppen_city)
    logger.info(f"Köppen classification: {koeppen_text}")
    return koeppen_text


def datacollection(aoi, city_name, country_name, output_dir):
    """Create basic_info.yml with country, AOI area, and Köppen classification."""

    logger.info("Creating basic_info.yml...")

    aoi_area = calculate_aoi_area(aoi)
    logger.info(f"AOI area: {aoi_area:.2f} km²")

    koeppen = get_koeppen_classification(aoi)

    basic_info = {
        'country': country_name,
        'aoi_area': round(aoi_area, 2),
        'koeppen': koeppen,
    }

    tabular_dir = os.path.join(output_dir, "tabular")
    os.makedirs(tabular_dir, exist_ok=True)
    output_path = os.path.join(tabular_dir, f"{city_name}_basic_info.yml")

    with open(output_path, 'w') as f:
        yaml.dump(basic_info, f)

    logger.info(f"basic_info.yml saved to: {output_path}")

    return basic_info
