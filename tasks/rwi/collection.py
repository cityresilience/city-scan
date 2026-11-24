# import
import os
import geopandas as gpd
from core.py.log_module import setup_logger
from shapely.geometry import Polygon
import pandas as pd
import numpy as np

logger = setup_logger(__name__)

def datacollection(
        aoi: gpd.GeoDataFrame,
        city_name: str,
        country_iso3: str,
        output_dir: str,
        return_gdf: bool = True,
        country_iso3_list: list = None,
    ):
    """
    Download Relative Wealth Index CSV from global bucket for the AOI country and construct geodataframe.

    Parameters
    ----------
    aoi : GeoDataFrame
        AOI polygon(s).
    city_name : str
        City name for naming output files.
    country_iso3 : str
        ISO3 country code (e.g. "IDN", "KHM").
    output_dir : str
        Directory where geodataframe will be saved.
    return_gdf : bool
        If True, return geodataframe.

    Returns
    -------
    Geodataframe or None
    """

    logger.info("Starting Relative Wealth Index data collection…")

    # Validate AOI
    if aoi is None or aoi.empty:
        logger.error("AOI is empty. Cannot continue.")
        return None

    # Ensure AOI is in correct CRS for csv operations
    if aoi.crs is None:
        logger.error("AOI has no CRS defined.")
        return None

    logger.info(f"AOI CRS: {aoi.crs}")

    # Multi-country support
    if country_iso3_list is None:
        country_iso3_list = [country_iso3]

    bucket_base = "https://storage.googleapis.com/city-scan-global-public/"

    try:
        # Download RWI CSV(s) — one per country, concat for multi-country AOIs
        rwi_frames = []
        for iso3 in country_iso3_list:
            iso_upper = iso3.upper()
            rwi_blob = f"relative_wealth_index/{iso_upper}_relative_wealth_index.csv"
            rwi_url = bucket_base + rwi_blob
            logger.info(f"Requesting rwi csv: {rwi_url}")
            try:
                rwi_frames.append(pd.read_csv(rwi_url))
            except Exception as e:
                logger.warning(f"RWI not available for {iso_upper}: {e}")
                continue

        if not rwi_frames:
            logger.error("No RWI data available for any country")
            return None

        rwi_df = pd.concat(rwi_frames, ignore_index=True)
        # RWI values are already z-scored by Meta (mean=0, sd=1 within each country)
        # See: https://www.pnas.org/doi/10.1073/pnas.2113658119

        rwi_gdf = gpd.GeoDataFrame(
            rwi_df,
            geometry=gpd.points_from_xy(rwi_df.longitude, rwi_df.latitude),
            crs="EPSG:4326"
        )
        
        # Project both datasets to a metric CRS (Web Mercator)
        rwi_proj = rwi_gdf.to_crs(3857)
        aoi_proj = aoi.to_crs(3857)

        # ----------------------------------------------------------
        # Estimate spacing from median nearest-neighbor distance
        # ----------------------------------------------------------
        logger.info("Estimating grid spacing from nearest-neighbor distance…")

        coords = np.array([
            (geom.x, geom.y) for geom in rwi_proj.geometry
        ])

        # Compute pairwise distances (brute force, but OK for country-scale grids)
        # Exclude self-distance (0)
        distances = []
        for i in range(len(coords)):
            dx = coords[i, 0] - coords[:, 0]
            dy = coords[i, 1] - coords[:, 1]
            d = np.sqrt(dx**2 + dy**2)
            d = d[d > 0]  # remove self-distance
            distances.append(d.min())

        median_spacing = np.median(distances) #2445.98
        half_spacing = median_spacing / 2

        logger.info(
            f"Estimated median nearest-neighbor spacing: "
            f"{median_spacing:.2f} meters"
        )

        # Build polygons around each point
        polygons = []
        for idx, row in rwi_proj.iterrows():
            x, y = row.geometry.x, row.geometry.y
            poly = Polygon([
                (x - half_spacing, y - half_spacing),
                (x + half_spacing, y - half_spacing),
                (x + half_spacing, y + half_spacing),
                (x - half_spacing, y + half_spacing)
            ])
            polygons.append(poly)

        # Replace geometry with polygons
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

        labels_en = [
            "Least Wealthy",
            "Less Wealthy",
            "Average",
            "More Wealthy",
            "Most Wealthy"
        ]

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
                labels=labels_std, include_lowest=True
            )
        except ValueError as e:
            logger.warning(f"Could not create standardized wealth categories: {e}")
            rwi_tiles["wealth_cat_std"] = "-0.5 – 0.5"



    except Exception as e:
        logger.error(f"Error reading or clipping rwi csv: {e}")
        return None

    # Create output directory
    spatial_dir = os.path.join(output_dir, "spatial")
    os.makedirs(spatial_dir, exist_ok=True)

    # Save clipped csv
    try:
        rwi_tiles.to_file(f"{spatial_dir}/{city_name}_rwi.gpkg", driver = 'GPKG', layer = 'rwi')
    except Exception as e:
        logger.error(f"Error saving clipped csv: {e}")
        return None

    logger.info("rwi complete.")

    if return_gdf:
        return rwi_tiles

    return None
