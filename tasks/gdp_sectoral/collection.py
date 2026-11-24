import os
import rasterio
from rasterio.mask import mask
import numpy as np
from core.py.log_module import setup_logger

logger = setup_logger(__name__)

BASE = "/vsicurl/https://storage.googleapis.com/city-scan-global-public/SectGDP30"
# BASE = "/Users/vivaldirinaldi/Documents/Work/03-multi-scan-materials/SectGDP30"

SECTORS = ["Agriculture", "Industry", "Service"]
YEARS = [2010, 2015, 2020]


def datacollection(aoi, city_name, output_dir):
    """
    Clip SectGDP30 global rasters to AOI.
    Creates one multi-band TIF per sector (bands = years 2010, 2015, 2020).

    Source: Chen et al. (2025), SectGDP30 v2, ESSD.
    """
    logger.info("Starting sectoral GDP data collection...")

    if aoi.crs is None or aoi.crs.to_epsg() != 4326:
        aoi = aoi.to_crs(epsg=4326)

    spatial_dir = os.path.join(output_dir, "spatial")
    os.makedirs(spatial_dir, exist_ok=True)

    shapes = [g.__geo_interface__ for g in aoi.geometry]

    for sector in SECTORS:
        out_path = os.path.join(spatial_dir, f"{city_name}_gdp_{sector.lower()}.tif")
        logger.info(f"Clipping {sector} GDP...")
        bands = []
        meta = None

        for year in YEARS:
            filename = f"{sector}GDP_{year}.tif"
            src_path = f"{BASE}/{filename}"

            try:
                with rasterio.open(src_path) as src:
                    clipped, transform = mask(src, shapes, crop=True, nodata=0)
                    if meta is None:
                        meta = src.meta.copy()
                        meta.update({
                            "height": clipped.shape[1],
                            "width": clipped.shape[2],
                            "transform": transform,
                            "count": len(YEARS),
                            "nodata": 0,
                            "dtype": "float32",
                        })
                    # Convert million USD → thousand USD (×1000)
                    bands.append((clipped[0].astype("float32")) * 1000)
            except Exception as e:
                logger.error(f"Failed to read {filename}: {e}")
                return

        with rasterio.open(out_path, "w", **meta) as dst:
            for i, (band, year) in enumerate(zip(bands, YEARS), start=1):
                dst.write(band, i)
                dst.set_band_description(i, f"gdp_{sector.lower()}_{year}")

        logger.info(f"Saved: {out_path} ({len(YEARS)} bands)")

    # Combined raster: sum of all 3 sectors per year.
    # If a sector's band for a given year is all-zero (upstream data gap — e.g.
    # SectGDP30 ServiceGDP_2020 has holes over parts of Eastern Europe), fall
    # back to that sector's most recent non-empty year ≤ target year.
    combined_out = os.path.join(spatial_dir, f"{city_name}_gdp_combined.tif")
    logger.info("Building combined sectoral GDP raster (sum of all sectors)...")

    sector_rasters = {}
    for sector in SECTORS:
        sector_path = os.path.join(spatial_dir, f"{city_name}_gdp_{sector.lower()}.tif")
        if not os.path.exists(sector_path):
            logger.error(f"Missing {sector_path} for combined raster")
            return
        with rasterio.open(sector_path) as src:
            sector_rasters[sector] = src.read()
            meta = src.meta.copy()

    combined = np.zeros_like(sector_rasters[SECTORS[0]], dtype=np.float32)
    for yi, year in enumerate(YEARS):
        for sector in SECTORS:
            band = sector_rasters[sector][yi]
            if band.sum() == 0:
                # Find most recent non-empty band ≤ current year
                fallback_idx = None
                for prev in range(yi - 1, -1, -1):
                    if sector_rasters[sector][prev].sum() > 0:
                        fallback_idx = prev
                        break
                if fallback_idx is not None:
                    logger.warning(
                        f"{sector} {year} is empty — using {YEARS[fallback_idx]} values in combined raster"
                    )
                    band = sector_rasters[sector][fallback_idx]
                else:
                    logger.warning(f"{sector} {year} is empty and no earlier year available")
            combined[yi] += band

    with rasterio.open(combined_out, "w", **meta) as dst:
        for i, year in enumerate(YEARS, start=1):
            dst.write(combined[i - 1], i)
            dst.set_band_description(i, f"gdp_combined_{year}")

    logger.info(f"Saved: {combined_out} ({len(YEARS)} bands)")

    logger.info("Sectoral GDP collection complete.")
