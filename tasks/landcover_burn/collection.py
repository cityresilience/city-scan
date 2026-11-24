import os
import numpy as np
import rasterio
from rasterio.mask import mask
from core.py.log_module import setup_logger

logger = setup_logger(__name__)

# ESA CCI / Copernicus Global Land Cover class codes → burnability score (0-1)
# Exact mapping from old backend (landcover_burnability.py)
BURN_MAP = {
    0:    [190, 200, 201, 202, 210, 220],
    0.16: [151],
    0.33: [12, 140, 152, 153],
    0.50: [11, 82, 110, 150, 180],
    0.66: [10, 20, 30, 40, 70, 71, 81, 90, 121, 130],
    0.83: [50, 61, 80, 100, 120, 122, 160, 170],
    1.0:  [60, 62],
}

# Invert to class_code → burn_score
CLASS_TO_BURN = {}
for score, codes in BURN_MAP.items():
    for code in codes:
        CLASS_TO_BURN[code] = score

# GCS path for ESA CCI Land Cover raster
GCS_BUCKET = "city-scan-global-data"
LC_BLOB = "ESACCI.tif"


def datacollection(aoi, city_name, output_dir):
    """
    Download ESA CCI Land Cover from GCS, clip to AOI,
    reclassify into burnability scores (0-1).

    Matches old backend landcover_burnability.py exactly.
    """

    logger.info("Starting burnability data collection...")

    if aoi is None or aoi.empty:
        logger.error("AOI is empty.")
        return None

    aoi_shapes = [geom.__geo_interface__ for geom in aoi.geometry]

    # Read from GCS via /vsigs/
    raster_path = f"/vsigs/{GCS_BUCKET}/{LC_BLOB}"
    logger.info(f"Reading ESA CCI landcover from: {raster_path}")

    try:
        with rasterio.open(raster_path) as src:
            clipped, clipped_transform = mask(src, shapes=aoi_shapes, crop=True, nodata=0)
            meta = src.meta.copy()
            meta.update({
                "height": clipped.shape[1],
                "width": clipped.shape[2],
                "transform": clipped_transform,
                "nodata": 0,
            })
    except Exception as e:
        logger.error(f"Failed to read ESA CCI raster: {e}")
        return None

    # Reclassify to burnability
    out_image = np.zeros_like(clipped, dtype=np.float32)
    for class_code, burn_score in CLASS_TO_BURN.items():
        out_image[clipped == class_code] = burn_score

    # Set out-of-range to 0
    out_image[(out_image < 0) | (out_image > 1)] = 0

    meta.update({"dtype": "float32"})

    # Save
    spatial_dir = os.path.join(output_dir, "spatial")
    os.makedirs(spatial_dir, exist_ok=True)
    out_path = os.path.join(spatial_dir, f"{city_name}_lc_burn.tif")

    with rasterio.open(out_path, "w", **meta) as dst:
        dst.write(out_image)

    logger.info(f"Burnability raster saved to: {out_path}")
    return out_path
