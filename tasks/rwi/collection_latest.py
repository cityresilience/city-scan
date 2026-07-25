# GEE-based Relative Wealth Index collection — drop-in alternative to collection.py
# ---------------------------------------------------------------------------------
# Uses Meta/Facebook's RWI *global* FeatureCollection from the GEE community catalog
# instead of the per-country CSVs in the city-scan-global-public bucket:
#
#     projects/sat-io/open-datasets/facebook/relative_wealth_index
#
# filterBounds(AOI) returns only the local points, which:
#   - handles the IND_PAK bundling automatically (no per-ISO filename guessing),
#   - removes the dependency on the city-scan-global-public bucket,
#   - keeps everything consistent with the worldpop/demographics GEE approach.
#
# Output is identical to collection.py: {city}_rwi.gpkg with rwi, error,
# wealth_cat_en, wealth_cat_std on ~2.4 km grid polygons clipped to the AOI.
#
# To use later: back up collection.py, then rename this file to collection.py
# (or import datacollection from here). GEE must already be initialized — the scan
# pipeline does this via core.config.auth before tasks run.

import os
import ee
import geopandas as gpd
from shapely.geometry import Polygon
import pandas as pd
import numpy as np
from core.py.log_module import setup_logger

logger = setup_logger(__name__)

RWI_FC = "projects/sat-io/open-datasets/facebook/relative_wealth_index"


def _load_rwi_points(aoi, pad=0.15):
    """Pull Meta RWI points within a buffered AOI bbox from the GEE FeatureCollection.
    Returns a DataFrame with longitude, latitude, rwi, error."""
    minx, miny, maxx, maxy = aoi.to_crs(4326).total_bounds
    region = ee.Geometry.Rectangle([minx - pad, miny - pad, maxx + pad, maxy + pad])
    fc = ee.FeatureCollection(RWI_FC).filterBounds(region)
    n = fc.size().getInfo()
    logger.info(f"RWI FeatureCollection points in buffered AOI bbox: {n}")
    if n == 0:
        return pd.DataFrame(columns=["longitude", "latitude", "rwi", "error"])
    if n > 5000:
        # getInfo() caps at 5000 features; MC AOIs are far smaller, but warn just in case.
        logger.warning(f"RWI: {n} points exceeds the getInfo() 5000 cap; AOI unusually large.")
    feats = fc.limit(5000).getInfo().get("features", [])
    rows = []
    for f in feats:
        props = f.get("properties", {})
        coords = f.get("geometry", {}).get("coordinates", [None, None])
        rows.append({
            "longitude": props.get("longitude", coords[0]),
            "latitude": props.get("latitude", coords[1]),
            "rwi": props.get("rwi"),
            "error": props.get("error"),
        })
    return pd.DataFrame(rows)


def datacollection(
        aoi: gpd.GeoDataFrame,
        city_name: str,
        country_iso3: str,
        output_dir: str,
        return_gdf: bool = True,
        country_iso3_list: list = None,
    ):
    """
    GEE Relative Wealth Index collection. Same signature/return as collection.py.
    `country_iso3` / `country_iso3_list` are accepted for compatibility but unused —
    the global FeatureCollection is filtered by AOI geometry, so multi-country AOIs
    are handled automatically.
    """
    logger.info("Starting Relative Wealth Index data collection (GEE)…")

    if aoi is None or aoi.empty:
        logger.error("AOI is empty. Cannot continue.")
        return None
    if aoi.crs is None:
        logger.error("AOI has no CRS defined.")
        return None
    logger.info(f"AOI CRS: {aoi.crs}")

    try:
        rwi_df = _load_rwi_points(aoi)
        if rwi_df.empty or rwi_df["rwi"].dropna().empty:
            logger.error("No RWI points found within the AOI area")
            return None

        rwi_gdf = gpd.GeoDataFrame(
            rwi_df,
            geometry=gpd.points_from_xy(rwi_df.longitude, rwi_df.latitude),
            crs="EPSG:4326",
        )

        # Project both datasets to a metric CRS (Web Mercator)
        rwi_proj = rwi_gdf.to_crs(3857)
        aoi_proj = aoi.to_crs(3857)

        # ----------------------------------------------------------
        # Estimate spacing from median nearest-neighbor distance
        # ----------------------------------------------------------
        logger.info("Estimating grid spacing from nearest-neighbor distance…")

        coords = np.array([(geom.x, geom.y) for geom in rwi_proj.geometry])

        # Compute pairwise distances (brute force, fine for the AOI-local grid)
        distances = []
        for i in range(len(coords)):
            dx = coords[i, 0] - coords[:, 0]
            dy = coords[i, 1] - coords[:, 1]
            d = np.sqrt(dx ** 2 + dy ** 2)
            d = d[d > 0]  # remove self-distance
            if d.size:
                distances.append(d.min())

        median_spacing = np.median(distances) if distances else 2445.98  # ~RWI grid
        half_spacing = median_spacing / 2
        logger.info(f"Estimated median nearest-neighbor spacing: {median_spacing:.2f} meters")

        # Build polygons around each point
        polygons = []
        for idx, row in rwi_proj.iterrows():
            x, y = row.geometry.x, row.geometry.y
            polygons.append(Polygon([
                (x - half_spacing, y - half_spacing),
                (x + half_spacing, y - half_spacing),
                (x + half_spacing, y + half_spacing),
                (x - half_spacing, y + half_spacing),
            ]))

        rwi_tiles = rwi_proj.copy()
        rwi_tiles["geometry"] = polygons

        # Clip to AOI
        rwi_tiles = gpd.clip(rwi_tiles, aoi_proj)
        rwi_tiles = rwi_tiles.to_crs(aoi.crs)

        if rwi_tiles.empty or rwi_tiles["rwi"].dropna().empty:
            logger.warning("No RWI data points found within AOI after clipping.")
            return None

        # Create categorical bins for RWI
        bins = 5
        labels_en = ["Least Wealthy", "Less Wealthy", "Average", "More Wealthy", "Most Wealthy"]
        try:
            rwi_tiles["wealth_cat_en"] = pd.qcut(
                rwi_tiles["rwi"], bins, labels=labels_en, duplicates='drop'
            )
        except ValueError as e:
            logger.warning(f"Could not create wealth categories: {e}")
            rwi_tiles["wealth_cat_en"] = "Average"

        # Standardized categories (fixed SD breaks, comparable across cities)
        labels_std = ['< -1.0', '-1.0 – -0.5', '-0.5 – 0.5', '0.5 – 1.0', '> 1.0']
        try:
            rwi_tiles["wealth_cat_std"] = pd.cut(
                rwi_tiles["rwi"],
                bins=[-np.inf, -1.0, -0.5, 0.5, 1.0, np.inf],
                labels=labels_std, include_lowest=True,
            )
        except ValueError as e:
            logger.warning(f"Could not create standardized wealth categories: {e}")
            rwi_tiles["wealth_cat_std"] = "-0.5 – 0.5"

    except Exception as e:
        logger.error(f"Error building rwi from GEE: {e}")
        return None

    # Save
    spatial_dir = os.path.join(output_dir, "spatial")
    os.makedirs(spatial_dir, exist_ok=True)
    try:
        rwi_tiles.to_file(f"{spatial_dir}/{city_name}_rwi.gpkg", driver='GPKG', layer='rwi')
    except Exception as e:
        logger.error(f"Error saving rwi gpkg: {e}")
        return None

    logger.info("rwi complete.")
    if return_gdf:
        return rwi_tiles
    return None
