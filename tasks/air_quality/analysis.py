import os
import numpy as np
import pandas as pd
import rasterio
from core.py.log_module import setup_logger

logger = setup_logger(__name__)


def compute_stats(
        city_name: str,
        output_dir: str,
        clipped_image=None,
        clipped_meta=None,
        return_df: bool = False
    ):
    """
    Compute statistics on the air quality raster (mean_1998_2022 band).
    Stats CSV is already created by datacollection — this verifies it exists.
    """

    logger.info("Starting air quality raster analysis…")

    raster_path = os.path.join(output_dir, "spatial", f"{city_name}_air_quality_pm2_5.tif")
    if not os.path.exists(raster_path):
        logger.error(f"Air quality raster not found at: {raster_path}")
        return None

    logger.info(f"Loading air quality raster: {raster_path}")
    with rasterio.open(raster_path) as src:
        descriptions = [src.descriptions[i] for i in range(src.count)]
        all_data = src.read().astype(np.float32)

    stats_rows = []
    for i, name in enumerate(descriptions):
        if name is None:
            name = f"band_{i+1}"
        band_data = all_data[i]
        valid = band_data[~np.isnan(band_data)]
        if valid.size == 0:
            continue
        stats_rows.append({
            "year": name if not name.isdigit() else int(name),
            "pm2_5_max": float(np.max(valid)),
            "pm2_5_mean": float(np.mean(valid)),
            "pm2_5_median": float(np.median(valid)),
        })

    stats_df = pd.DataFrame(stats_rows)
    tabular_dir = os.path.join(output_dir, "tabular")
    os.makedirs(tabular_dir, exist_ok=True)
    csv_path = os.path.join(tabular_dir, f"{city_name}_air_quality_pm2_5.csv")
    stats_df.to_csv(csv_path, index=False)
    logger.info(f"Air quality stats saved to: {csv_path}")

    if return_df:
        return stats_df
    return None


def compute_histogram(
        city_name: str,
        output_dir: str,
        return_df: bool = False
    ):
    """
    Bin PM2.5 concentration into standard ranges for visualization.
    Uses the mean_1998_2022 band (band 1) from the multi-band raster.
    Produces aq_area.csv with columns: bin, count, percentage.
    """

    logger.info("Starting air quality histogram analysis…")

    raster_path = os.path.join(output_dir, "spatial", f"{city_name}_air_quality_pm2_5.tif")
    if not os.path.exists(raster_path):
        logger.error(f"Air quality raster not found at: {raster_path}")
        return None

    with rasterio.open(raster_path) as src:
        # Band 1 = mean_1998_2022
        pm25_data = src.read(1).astype(np.float32)

    # Filter valid data
    valid_data = pm25_data[~np.isnan(pm25_data)]
    valid_data = valid_data[np.isfinite(valid_data)]
    valid_data = valid_data[valid_data >= 0]

    if valid_data.size == 0:
        logger.error("No valid PM2.5 values.")
        return None

    # PM2.5 concentration bins (μg/m³)
    bins_definition = [
        {"range": "0-5", "min_val": 0, "max_val": 5},
        {"range": "5-10", "min_val": 5, "max_val": 10},
        {"range": "10-15", "min_val": 10, "max_val": 15},
        {"range": "15-20", "min_val": 15, "max_val": 20},
        {"range": "20-30", "min_val": 20, "max_val": 30},
        {"range": "30-40", "min_val": 30, "max_val": 40},
        {"range": "40-50", "min_val": 40, "max_val": 50},
        {"range": "50-100", "min_val": 50, "max_val": 100},
        {"range": "100+", "min_val": 100, "max_val": float('inf')},
    ]

    total_pixels = len(valid_data)
    bin_data = []
    for b in bins_definition:
        if b["max_val"] == float('inf'):
            count = int(np.sum(valid_data >= b["min_val"]))
        else:
            count = int(np.sum((valid_data >= b["min_val"]) & (valid_data < b["max_val"])))
        bin_data.append({
            'bin': b["range"],
            'count': count,
            'percentage': round((count / total_pixels) * 100, 2) if total_pixels > 0 else 0
        })

    result_df = pd.DataFrame(bin_data)

    tabular_dir = os.path.join(output_dir, "tabular")
    os.makedirs(tabular_dir, exist_ok=True)
    output_path = os.path.join(tabular_dir, f"{city_name}_aq_area.csv")
    result_df.to_csv(output_path, index=False)
    logger.info(f"Air quality histogram saved to: {output_path}")

    if return_df:
        return result_df
    return None
