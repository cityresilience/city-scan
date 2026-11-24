import os
import warnings
from typing import Optional
import geopandas as gpd
import pandas as pd
from tqdm import tqdm
from core.py.log_module import setup_logger

logger = setup_logger(__name__)


def datacollection(
    aoi: gpd.GeoDataFrame,
    city_name: str,
    output_dir: str,
    first_year: int = 2001,
    last_year: int = 2020,
    buffer_degrees: float = 1.0,
    return_gdf: bool = True
) -> Optional[gpd.GeoDataFrame]:

    logger.info("Starting burned area data collection.")

    if aoi is None or aoi.empty:
        logger.error("AOI is empty.")
        return None

    if aoi.crs is None:
        logger.error("AOI has no CRS defined.")
        return None

    # Ensure geographic CRS for degree buffering
    if not aoi.crs.is_geographic:
        logger.info("Reprojecting AOI to EPSG:4326 for degree buffering.")
        aoi = aoi.to_crs(4326)

    aoi_buffered = aoi.buffer(buffer_degrees)
    aoi_union = aoi_buffered.unary_union
    bbox = tuple(aoi_buffered.total_bounds)

    years = range(first_year, last_year + 1)
    months = range(1, 13)

    records = []

    for year in years:
        for month in tqdm(months, desc=f"Year {year}"):

            path = (
                "https://storage.googleapis.com/"
                "city-scan-global-public/globfire_fgb/"
                f"MODIS_BA_GLOBAL_1_{month}_{year}.fgb"
            )

            try:
                gdf = gpd.read_file(
                    path,
                    engine="pyogrio",
                    use_arrow=True,
                    bbox=bbox,
                    where="Type = 'FinalArea'",
                )
            except Exception as e:
                logger.warning(f"Failed reading {year}-{month}: {e}")
                continue

            if gdf.empty:
                continue

            if gdf.crs != aoi.crs:
                gdf = gdf.to_crs(aoi.crs)

            gdf = gdf[gdf.intersects(aoi_union)]

            if gdf.empty:
                continue

            # --- suppress geographic centroid warning intentionally ---
            with warnings.catch_warnings():
                warnings.filterwarnings(
                    "ignore",
                    message="Geometry is in a geographic CRS.*"
                )
                centroids = gdf.geometry.centroid

            records.extend(
                zip(
                    [year] * len(centroids),
                    [month] * len(centroids),
                    centroids,
                    centroids.x,
                    centroids.y,
                )
            )

    if not records:
        logger.warning("No burned areas found within buffered AOI.")
        return None

    compiled_gdf = gpd.GeoDataFrame(
        records,
        columns=["year", "month", "geometry", "x", "y"],
        crs=aoi.crs
    )

    # -------------------------
    # Export spatial (retain geometry + x/y)
    # -------------------------
    spatial_dir = os.path.join(output_dir, "spatial")
    os.makedirs(spatial_dir, exist_ok=True)

    spatial_path = os.path.join(
        spatial_dir,
        f"{city_name}_globfire_centroids.gpkg"
    )

    compiled_gdf.to_file(
        spatial_path,
        driver="GPKG",
        layer="centroids"
    )

    # -------------------------
    # Export tabular (drop geometry only)
    # -------------------------
    tabular_dir = os.path.join(output_dir, "tabular")
    os.makedirs(tabular_dir, exist_ok=True)

    tabular_path = os.path.join(
        tabular_dir,
        f"{city_name}_globfire_centroids.csv"
    )

    compiled_gdf.drop(columns="geometry").to_csv(
        tabular_path,
        index=False
    )

    logger.info("Burned area data collection complete.")

    return compiled_gdf if return_gdf else None
