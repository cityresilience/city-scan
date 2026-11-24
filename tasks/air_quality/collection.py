import os
import numpy as np
import geopandas as gpd
import rasterio
from rasterio.mask import mask
from rasterio.io import MemoryFile
from core.py.log_module import setup_logger

logger = setup_logger(__name__)

# GCS bucket path for air quality rasters (v5, VIIRS)
GCS_AQ_BASE = "/vsicurl/https://storage.googleapis.com/city-scan-global-public/air_quality"
AQ_TEMPLATE = "sdei-global-annual-gwr-pm2-5-modis-misr-seawifs-viirs-aod-v5-gl-04-{year}-geotiff.tif"

YEARS = list(range(1998, 2023))  # 1998-2022


def datacollection(
        aoi: gpd.GeoDataFrame,
        city_name: str,
        output_dir: str,
        return_raster: bool = True
    ):
    """
    Download PM2.5 air quality rasters (1998-2022) from GCS, crop to AOI,
    compute summary bands (mean, mean_2013_2022, trend_2013_2022),
    and save as multi-band TIF + stats CSV.

    Matches R data-collection.R logic.
    """

    logger.info("Starting Air Quality data collection…")

    if aoi is None or aoi.empty:
        logger.error("AOI is empty. Cannot continue.")
        return None

    if aoi.crs is None:
        logger.error("AOI has no CRS defined.")
        return None

    logger.info(f"AOI CRS: {aoi.crs}")

    spatial_dir = os.path.join(output_dir, "spatial")
    os.makedirs(spatial_dir, exist_ok=True)
    aoi_shapes = [geom.__geo_interface__ for geom in aoi.geometry]

    # ------------------------------------------------------------------
    # 1. Download and crop each year
    # ------------------------------------------------------------------
    bands = []
    band_names = []

    for idx, year in enumerate(YEARS, 1):
        fname = AQ_TEMPLATE.format(year=year)
        raster_path = f"{GCS_AQ_BASE}/{fname}"

        try:
            with rasterio.open(raster_path) as src:
                clipped, clipped_transform = mask(src, shapes=aoi_shapes, crop=True, nodata=np.nan)
                meta = src.meta.copy()
                meta.update({
                    "height": clipped.shape[1],
                    "width": clipped.shape[2],
                    "transform": clipped_transform,
                    "nodata": np.nan,
                    "dtype": "float32",
                })
            bands.append(clipped.squeeze().astype(np.float32))
            band_names.append(fname.replace(".tif", ""))
            print(f"  Air quality: {idx}/{len(YEARS)} ({year})", end="\r")
        except Exception as e:
            logger.error(f"Failed to read air quality raster for {year}: {e}")
            return None

    print()
    logger.info(f"Downloaded {len(bands)} yearly PM2.5 rasters")

    # ------------------------------------------------------------------
    # 2. Compute summary bands (matching R logic)
    # ------------------------------------------------------------------
    stacked = np.stack(bands, axis=0)  # (n_years, H, W)

    # Mean across all years (1998-2022)
    mean_all = np.nanmean(stacked, axis=0)

    # Mean 2013-2022 (indices 15:25 in 0-based, years 2013-2022)
    idx_2013 = YEARS.index(2013)
    mean_2013_2022 = np.nanmean(stacked[idx_2013:], axis=0)

    # Trend 2013-2022 (linear regression slope per pixel)
    subset = stacked[idx_2013:]  # (10, H, W)
    x = np.arange(2013, 2023, dtype=np.float32)
    x_mean = x.mean()
    x_var = ((x - x_mean) ** 2).sum()
    # Vectorized slope: sum((x - x_mean) * (y - y_mean)) / sum((x - x_mean)^2)
    y_mean = np.nanmean(subset, axis=0)
    numerator = np.nansum((x[:, None, None] - x_mean) * (subset - y_mean[None, :, :]), axis=0)
    trend_2013_2022 = numerator / x_var

    # ------------------------------------------------------------------
    # 3. Build multi-band TIF: summary bands first, then yearly bands
    # ------------------------------------------------------------------
    all_bands = [mean_all, mean_2013_2022, trend_2013_2022] + bands
    all_names = ["mean_1998_2022", "mean_2013_2022", "trend_2013_2022"] + band_names

    out_stack = np.stack(all_bands, axis=0)  # (n_bands, H, W)
    out_meta = meta.copy()
    out_meta.update({
        "count": len(all_bands),
        "driver": "GTiff",
        "dtype": "float32",
    })

    output_path = os.path.join(spatial_dir, f"{city_name}_air_quality_pm2_5.tif")
    with rasterio.open(output_path, "w", **out_meta) as dst:
        dst.write(out_stack)
        for i, name in enumerate(all_names):
            dst.set_band_description(i + 1, name)
    logger.info(f"Air quality raster saved to: {output_path} ({len(all_bands)} bands)")

    logger.info("Air quality collection complete.")

    if return_raster:
        return out_stack, out_meta
    return None
