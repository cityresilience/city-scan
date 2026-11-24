"""
Unified OSM feature fetcher.

Routes by AOI bounding-box area:
  - area <= LARGE_AOI_THRESHOLD_KM2 → Overpass (Kumi primary, overpass-api.de fallback)
  - area > LARGE_AOI_THRESHOLD_KM2 → Geofabrik PBF extract (see osm_pbf)

Entry point: fetch_features(aoi, tags) -> GeoDataFrame or None
"""
import geopandas as gpd

from core.py.log_module import setup_logger

logger = setup_logger(__name__)

LARGE_AOI_THRESHOLD_KM2 = 5000

OVERPASS_ENDPOINTS = [
    "https://overpass.kumi.systems/api/interpreter",
    "https://overpass-api.de/api/interpreter",
]


def fetch_features(aoi, tags, cache_dir=None, buffer_m=0):
    """
    Fetch OSM features matching tags over an AOI.

    Parameters
    ----------
    aoi : GeoDataFrame
        AOI polygon(s) in any CRS (internally reprojected to EPSG:4326).
    tags : dict
        OSMnx-style tag selector, e.g. {"building": True} or
        {"amenity": ["school", "hospital"]}.
    cache_dir : str or Path, optional
        Override for the PBF cache directory. Default: mnt/.cache/osm-pbf.
    buffer_m : float, default 0
        Buffer the AOI by this many meters before querying (useful for
        accessibility so we capture features just outside the AOI).

    Returns
    -------
    GeoDataFrame in EPSG:4326 clipped to the AOI, or None on failure.
    """
    if aoi is None or aoi.empty:
        logger.error("AOI is empty.")
        return None

    aoi_4326 = aoi.to_crs(4326) if str(aoi.crs).upper() != "EPSG:4326" else aoi
    query_aoi = _buffer_aoi(aoi_4326, buffer_m) if buffer_m else aoi_4326
    area_km2 = _bbox_area_km2(query_aoi)
    logger.info(f"OSM fetch: AOI bbox {area_km2:,.0f} km²")

    if area_km2 > LARGE_AOI_THRESHOLD_KM2:
        logger.info(f"Routing to PBF backend (> {LARGE_AOI_THRESHOLD_KM2} km²)")
        from core.py import osm_pbf
        gdf = osm_pbf.fetch_features(query_aoi, tags, cache_dir=cache_dir)
    else:
        logger.info("Routing to Overpass backend")
        gdf = _overpass_features(query_aoi, tags)

    if gdf is None or len(gdf) == 0:
        return None

    try:
        gdf = gpd.clip(gdf, aoi_4326)
    except Exception as e:
        logger.warning(f"Clip to AOI failed: {e}")
    return gdf


def _bbox_area_km2(aoi_4326):
    """Equal-area bbox km² using EPSG:6933."""
    eq = aoi_4326.to_crs("EPSG:6933")
    b = eq.total_bounds
    return (b[2] - b[0]) * (b[3] - b[1]) / 1e6


def _buffer_aoi(aoi_4326, buffer_m):
    """Buffer AOI by meters using EPSG:3857 metric projection."""
    tmp = aoi_4326.to_crs("EPSG:3857")
    buffered = tmp.geometry.iloc[0].buffer(buffer_m)
    return gpd.GeoDataFrame(geometry=[buffered], crs="EPSG:3857").to_crs(4326)


def _overpass_features(aoi_4326, tags):
    """OSMnx features_from_polygon with Kumi primary, overpass-api.de fallback."""
    import osmnx as ox

    geom = aoi_4326.geometry.iloc[0]
    ox.settings.timeout = 600

    last_err = None
    for endpoint in OVERPASS_ENDPOINTS:
        try:
            if hasattr(ox.settings, "overpass_url"):
                ox.settings.overpass_url = endpoint
            if hasattr(ox.settings, "overpass_endpoint"):
                ox.settings.overpass_endpoint = endpoint
            logger.info(f"  Overpass endpoint: {endpoint}")
            gdf = ox.features_from_polygon(geom, tags)
            if gdf is not None and len(gdf) > 0:
                return gdf
            logger.info(f"  No features returned from {endpoint}")
            return gdf
        except Exception as e:
            logger.warning(f"  Endpoint failed: {endpoint} — {e}")
            last_err = e
            continue

    logger.error(f"All Overpass endpoints failed. Last error: {last_err}")
    return None
