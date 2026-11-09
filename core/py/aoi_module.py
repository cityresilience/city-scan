# Import
import warnings
import geopandas as gpd
from shapely.geometry import Point
from core.py.log_module import setup_logger
logger = setup_logger(__name__)

def find_country(aoi):
    """
    Find country name and country iso3 code based on intersecting aoi with global country database.

    Returns the primary country (largest intersection) plus a list of all
    intersecting ISO3 codes (for multi-country AOIs like corridors).

    Parameters
    ----------
    aoi : GeoDataFrame
        The AOI geodataframe.

    Returns
    -------
    country_iso3 : str
        ISO3 code of the primary (largest area) country, lowercase.
    country_name : str
        Name of the primary country, lowercase with underscores.
    country_iso3_list : list[str]
        All intersecting ISO3 codes, lowercase, sorted by intersection area (largest first).
    """

    # define global public bucket and relevant blobs
    global_bucket_dir = 'https://storage.googleapis.com/city-scan-global-public/'
    country_blob_dir = 'wb_countries/WB_countries_Admin0_10m.shp'
    # extract ISO3 from AOI
    countries = gpd.read_file(f'{global_bucket_dir}{country_blob_dir}').to_crs(epsg=4326)
    # Perform spatial join to find intersections
    # geometry-only AOI: its own attribute columns (e.g. an ISO_A3 in a WB
    # boundary extract) would collide with the countries layer and get suffixed
    intersection = gpd.overlay(aoi[[aoi.geometry.name]], countries, how='intersection')
    # Calculate the area of each intersection
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", UserWarning)
        intersection['area'] = intersection.geometry.area

    # Sort by area descending — primary country first
    intersection = intersection.sort_values('area', ascending=False)

    # Primary country (largest intersection)
    max_area_country = intersection.iloc[0]
    country_iso3 = max_area_country['ISO_A3'].lower()
    country_name = max_area_country['NAME_EN'].replace(' ', '_').replace("'", "").lower()

    # All intersecting countries, but DROP border slivers — where the AOI
    # boundary and the WB boundary don't perfectly align, tiny overlaps appear
    # (e.g. Uzbekistan AOI clips 87 km2 of Afghanistan). Downloading whole
    # neighbour datasets for <1% sliver area is wasteful, so keep only countries
    # contributing a meaningful share. Primary country is always kept.
    SLIVER_FRAC = 0.01  # 1% of total intersected area
    total_area = intersection['area'].sum()
    keep = intersection[intersection['area'] >= SLIVER_FRAC * total_area]
    dropped = intersection[intersection['area'] < SLIVER_FRAC * total_area]
    country_iso3_list = keep['ISO_A3'].str.lower().tolist()
    if country_iso3 not in country_iso3_list:  # safety: never drop the primary
        country_iso3_list.insert(0, country_iso3)

    logger.info(f'detect ISO3 from AOI: {country_iso3}')
    if not dropped.empty:
        slivers = [f"{r['ISO_A3'].lower()} ({100*r['area']/total_area:.1f}%)"
                   for _, r in dropped.iterrows()]
        logger.info(f'dropped border slivers: {", ".join(slivers)}')
    if len(country_iso3_list) > 1:
        logger.info(f'multi-country AOI: {country_iso3_list}')

    return country_iso3, country_name, country_iso3_list