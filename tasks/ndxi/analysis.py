import os
import numpy as np
import pandas as pd
import rasterio
from core.py.log_module import setup_logger

logger = setup_logger(__name__)


# From Caroline's clean.py — clean_ndvi_area()
def compute_histogram(
        city_name: str,
        output_dir: str,
        clipped_image=None,
        clipped_meta=None,
        return_df: bool = False
    ):
    """
    Bin NDVI values into vegetation categories for visualization.
    Produces ndvi_area.csv with columns: bin, type, count, percentage.
    """

    logger.info("Starting NDVI histogram analysis…")

    # Load raster from disk if not provided
    if clipped_image is None or clipped_meta is None:
        raster_path = os.path.join(output_dir, "spatial", f"{city_name}_ndvi_season.tif")

        if not os.path.exists(raster_path):
            logger.error(f"Clipped raster not found at: {raster_path}")
            return None

        try:
            with rasterio.open(raster_path) as src:
                clipped_image = src.read()
                clipped_meta = src.meta
        except Exception as e:
            logger.error(f"Failed to load raster: {e}")
            return None

    # Prepare valid data
    ndvi_data = clipped_image.squeeze().astype(float)
    nodata_value = clipped_meta.get("nodata")
    if nodata_value is not None:
        valid_data = ndvi_data[ndvi_data != nodata_value]
    else:
        valid_data = ndvi_data[~np.isnan(ndvi_data)]
    valid_data = valid_data[np.isfinite(valid_data)]

    if valid_data.size == 0:
        logger.error("No valid NDVI values.")
        return None

    # NDVI vegetation categories
    bins_definition = [
        {"range": "-1-0.015", "type": "Water", "min_val": -1.0, "max_val": 0.015},
        {"range": "0.015-0.14", "type": "Built-up", "min_val": 0.015, "max_val": 0.14},
        {"range": "0.14-0.18", "type": "Barren", "min_val": 0.14, "max_val": 0.18},
        {"range": "0.18-0.27", "type": "Shrub and Grassland", "min_val": 0.18, "max_val": 0.27},
        {"range": "0.27-0.36", "type": "Sparse", "min_val": 0.27, "max_val": 0.36},
        {"range": "0.36-1", "type": "Dense", "min_val": 0.36, "max_val": 1.0},
    ]

    total_pixels = len(valid_data)
    bin_data = []

    for b in bins_definition:
        if b["range"] == "0.36-1":
            count = int(np.sum((valid_data >= b["min_val"]) & (valid_data <= b["max_val"])))
        else:
            count = int(np.sum((valid_data >= b["min_val"]) & (valid_data < b["max_val"])))
        bin_data.append({
            'bin': b["range"],
            'type': b["type"],
            'count': count,
            'percentage': round((count / total_pixels) * 100, 2) if total_pixels > 0 else 0
        })

    result_df = pd.DataFrame(bin_data)

    # Save
    tabular_dir = os.path.join(output_dir, "tabular")
    os.makedirs(tabular_dir, exist_ok=True)
    output_path = os.path.join(tabular_dir, f"{city_name}_ndvi_area.csv")

    try:
        result_df.to_csv(output_path, index=False)
        logger.info(f"NDVI histogram saved to: {output_path}")
    except Exception as e:
        logger.error(f"Error saving histogram CSV: {e}")

    if return_df:
        return result_df
    return None
