"""
Geofabrik PBF backend for large-AOI OSM extraction.

Flow:
  1. Resolve intersecting country ISO3s via find_country.
  2. For each ISO3, download the Geofabrik country PBF (cached, refresh every 30 days).
  3. pyrosm loads each PBF with a bounding-box filter applied at parse time.
  4. Multi-country AOIs: concat per-country GeoDataFrames.

Requires only: pyrosm (pip install pyrosm). No system binaries.
"""
import json
from datetime import datetime, timedelta
from pathlib import Path

import geopandas as gpd
import pandas as pd
import requests

from core.py.aoi_module import find_country
from core.py.cache import get_cache_namespace_dir
from core.py.log_module import setup_logger

logger = setup_logger(__name__)

GEOFABRIK_BASE = "https://download.geofabrik.de"
MAX_AGE_DAYS = 30
USER_AGENT = "city-scan-automation/1.0"

# Same WB Admin0 layer as aoi_module.find_country; used here for ISO3 -> ISO2
# (Geofabrik's index keys countries by alpha-2)
WB_COUNTRIES_URL = "https://storage.googleapis.com/city-scan-global-public/wb_countries/WB_countries_Admin0_10m.shp"

# Continent-level ids in Geofabrik's index — used to prefer whole-country
# extracts over subregions when several regions share an alpha-2 code
GEOFABRIK_CONTINENTS = {
    "africa", "asia", "europe", "north-america", "south-america",
    "central-america", "australia-oceania", "antarctica", "russia",
}

# ISO3 → Geofabrik path (continent/country-slug). Extend as scans expand.
ISO3_TO_GEOFABRIK = {
    # Africa
    "ago": "africa/angola",
    "bdi": "africa/burundi",
    "ben": "africa/benin",
    "bfa": "africa/burkina-faso",
    "bwa": "africa/botswana",
    "caf": "africa/central-african-republic",
    "civ": "africa/ivory-coast",
    "cmr": "africa/cameroon",
    "cod": "africa/congo-democratic-republic",
    "cog": "africa/congo-brazzaville",
    "com": "africa/comores",
    "cpv": "africa/cape-verde",
    "dji": "africa/djibouti",
    "dza": "africa/algeria",
    "egy": "africa/egypt",
    "eri": "africa/eritrea",
    "esh": "africa/morocco",
    "eth": "africa/ethiopia",
    "gab": "africa/gabon",
    "gha": "africa/ghana",
    "gin": "africa/guinea",
    "gmb": "africa/senegal-and-gambia",
    "gnb": "africa/guinea-bissau",
    "gnq": "africa/equatorial-guinea",
    "ken": "africa/kenya",
    "lbr": "africa/liberia",
    "lby": "africa/libya",
    "lso": "africa/lesotho",
    "mar": "africa/morocco",
    "mdg": "africa/madagascar",
    "mli": "africa/mali",
    "moz": "africa/mozambique",
    "mrt": "africa/mauritania",
    "mus": "africa/mauritius",
    "mwi": "africa/malawi",
    "nam": "africa/namibia",
    "ner": "africa/niger",
    "nga": "africa/nigeria",
    "rwa": "africa/rwanda",
    "sdn": "africa/sudan",
    "sen": "africa/senegal-and-gambia",
    "sle": "africa/sierra-leone",
    "som": "africa/somalia",
    "ssd": "africa/south-sudan",
    "stp": "africa/sao-tome-and-principe",
    "swz": "africa/swaziland",
    "syc": "africa/seychelles",
    "tcd": "africa/chad",
    "tgo": "africa/togo",
    "tun": "africa/tunisia",
    "tza": "africa/tanzania",
    "uga": "africa/uganda",
    "zaf": "africa/south-africa",
    "zmb": "africa/zambia",
    "zwe": "africa/zimbabwe",
    # Asia — add as needed
    "ind": "asia/india",
    "idn": "asia/indonesia",
    "phl": "asia/philippines",
    "vnm": "asia/vietnam",
    "tha": "asia/thailand",
    "mmr": "asia/myanmar",
    "bgd": "asia/bangladesh",
    "pak": "asia/pakistan",
    "lka": "asia/sri-lanka",
    "npl": "asia/nepal",
    "khm": "asia/cambodia",
    "lao": "asia/laos",
    "uzb": "asia/uzbekistan",
    # Europe — add as needed
    "mlt": "europe/malta",
    "mda": "europe/moldova",
    "alb": "europe/albania",
}


def _default_cache_dir():
    return get_cache_namespace_dir("osm-pbf")


def fetch_features(aoi_4326, tags, cache_dir=None):
    """
    Fetch OSM features for AOI via Geofabrik PBF.

    Parameters
    ----------
    aoi_4326 : GeoDataFrame in EPSG:4326
    tags : dict, OSMnx-style tag selector
    cache_dir : Path, optional
    """
    cache_dir = Path(cache_dir) if cache_dir else _default_cache_dir()
    cache_dir.mkdir(parents=True, exist_ok=True)

    _, _, iso3_list = find_country(aoi=aoi_4326)
    logger.info(f"PBF backend: countries {iso3_list}")

    bbox = aoi_4326.total_bounds  # (minx, miny, maxx, maxy)

    per_country_gdfs = []
    for iso3 in iso3_list:
        pbf_path = _download_country_pbf(iso3, cache_dir)
        if pbf_path is None:
            continue
        gdf = _load_features(pbf_path, tags, bbox)
        if gdf is not None and len(gdf) > 0:
            per_country_gdfs.append(gdf)

    if not per_country_gdfs:
        logger.info("PBF backend: no features matched.")
        return None

    if len(per_country_gdfs) == 1:
        combined = per_country_gdfs[0]
    else:
        combined = gpd.GeoDataFrame(
            pd.concat(per_country_gdfs, ignore_index=True),
            crs=per_country_gdfs[0].crs,
        )
        dedup_col = "id" if "id" in combined.columns else ("osmid" if "osmid" in combined.columns else None)
        if dedup_col is not None:
            combined = combined.drop_duplicates(subset=dedup_col)

    logger.info(f"PBF backend: {len(combined)} features across {len(per_country_gdfs)} country file(s)")
    return combined


def _geofabrik_url_from_index(iso3, cache_dir):
    """Resolve a country's PBF URL from Geofabrik's machine-readable index.

    Fallback for countries missing from ISO3_TO_GEOFABRIK: ISO3 -> ISO2 via
    the WB Admin0 layer, then match the index's iso3166-1:alpha2 codes.
    Returns URL string or None.
    """
    try:
        index_path = cache_dir / "geofabrik-index-v1.json"
        if not index_path.exists() or _stale(index_path):
            r = requests.get(f"{GEOFABRIK_BASE}/index-v1-nogeom.json",
                             headers={"User-Agent": USER_AGENT}, timeout=60)
            r.raise_for_status()
            index_path.write_bytes(r.content)
        features = json.loads(index_path.read_text())["features"]

        countries = gpd.read_file(WB_COUNTRIES_URL, ignore_geometry=True)
        match = countries[countries["ISO_A3"].str.lower() == iso3.lower()]
        if match.empty:
            return None
        alpha2 = str(match.iloc[0]["ISO_A2"]).upper()

        candidates = [
            f["properties"] for f in features
            if alpha2 in f["properties"].get("iso3166-1:alpha2", [])
            and f["properties"].get("urls", {}).get("pbf")
        ]
        if not candidates:
            return None
        # Prefer whole-country extracts (parent = continent) over subregions
        top = [p for p in candidates if p.get("parent") in GEOFABRIK_CONTINENTS]
        props = (top or candidates)[0]
        logger.info(f"  Resolved '{iso3}' via Geofabrik index: {props['id']}")
        return props["urls"]["pbf"]
    except Exception as e:
        logger.warning(f"  Geofabrik index lookup failed for '{iso3}': {e}")
        return None


def _download_country_pbf(iso3, cache_dir):
    """Download country PBF from Geofabrik, cached. Returns Path or None."""
    filename = f"{iso3.lower()}.osm.pbf"
    local_path = cache_dir / filename

    if local_path.exists() and not _stale(local_path):
        logger.info(f"  Using cached PBF: {local_path.name}")
        return local_path

    geofabrik_path = ISO3_TO_GEOFABRIK.get(iso3.lower())
    if geofabrik_path:
        url = f"{GEOFABRIK_BASE}/{geofabrik_path}-latest.osm.pbf"
    else:
        url = _geofabrik_url_from_index(iso3, cache_dir)
        if url is None:
            logger.warning(f"No Geofabrik region for ISO3 '{iso3}' "
                           f"(not in ISO3_TO_GEOFABRIK, not resolvable via index).")
            return None
    logger.info(f"  Downloading {url}")
    try:
        with requests.get(url, stream=True, timeout=(30, 600),
                          headers={"User-Agent": USER_AGENT}) as r:
            r.raise_for_status()
            tmp = local_path.with_suffix(".pbf.part")
            with open(tmp, "wb") as f:
                for chunk in r.iter_content(chunk_size=8 * 1024 * 1024):
                    if chunk:
                        f.write(chunk)
            tmp.replace(local_path)
        size_mb = local_path.stat().st_size / 1e6
        logger.info(f"  Downloaded {local_path.name} ({size_mb:.1f} MB)")
        return local_path
    except Exception as e:
        logger.error(f"  Download failed for {iso3}: {e}")
        return None


def _load_features(pbf_path, tags, bbox):
    """
    Load features from a country PBF into a GeoDataFrame via pyrosm.
    Filters to bbox at parse time (low memory).
    """
    try:
        from pyrosm import OSM
    except ImportError:
        raise ImportError(
            "pyrosm is required for AOIs > 5000 km² (Geofabrik PBF route). "
            "Install with: conda install -c conda-forge pyrosm"
        )

    # pyrosm bounding_box = [minx, miny, maxx, maxy]
    osm = OSM(str(pbf_path), bounding_box=list(bbox))

    pyrosm_filter = _tags_to_pyrosm_filter(tags)
    if "building" in tags:
        gdf = osm.get_buildings(custom_filter=pyrosm_filter)
    else:
        gdf = osm.get_pois(custom_filter=pyrosm_filter)

    if gdf is None or len(gdf) == 0:
        logger.info(f"  No features matching tags in {pbf_path.name}")
        return None
    logger.info(f"  Loaded {len(gdf)} features from {pbf_path.name}")
    return gdf


def _tags_to_pyrosm_filter(tags):
    """Convert OSMnx-style tags dict to pyrosm custom_filter format."""
    # pyrosm wants {"key": [list of values]} or {"key": True}
    out = {}
    for k, v in tags.items():
        if v is True or v is None:
            out[k] = True
        elif isinstance(v, (list, tuple)):
            out[k] = list(v)
        else:
            out[k] = [v]
    return out


def _stale(path):
    if not Path(path).exists():
        return True
    age = datetime.now() - datetime.fromtimestamp(Path(path).stat().st_mtime)
    return age > timedelta(days=MAX_AGE_DAYS)


