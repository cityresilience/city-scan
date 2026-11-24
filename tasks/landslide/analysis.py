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
    Perform statistics on clipped landslide raster.

    Parameters
    ----------
    city_name : str
        City name used for locating the clipped raster file.
    output_dir : str
        Base output directory.
    clipped_image : np.ndarray, optional
        In-memory clipped raster array from datacollection().
    clipped_meta : dict, optional
        Raster metadata from datacollection().
    return_df : bool
        If True, return dataframe, default is False.

    Returns
    -------
    stats_df : pandas.DataFrame
        DataFrame containing min, p25, median, mean, p75, max, sum.
    """

    logger.info("Starting WorldPop raster analysis…")

    # -----------------------------------------------------
    # 1. Load raster from disk if not provided
    # -----------------------------------------------------
    if clipped_image is None or clipped_meta is None:
        raster_path = os.path.join(output_dir, "spatial", f"{city_name}_landslide.tif")

        if not os.path.exists(raster_path):
            logger.error(f"Clipped raster not found at: {raster_path}")
            return None

        logger.info(f"Loading clipped raster from disk: {raster_path}")

        try:
            with rasterio.open(raster_path) as src:
                clipped_image = src.read()
                clipped_meta = src.meta
        except Exception as e:
            logger.error(f"Failed to load raster: {e}")
            return None
    else:
        logger.info("Using in-memory raster from datacollection().")

    # -----------------------------------------------------
    # 2. Prepare raster data for statistics
    # -----------------------------------------------------
    # Convert to 1D and remove zeros/nodata
    arr = clipped_image.squeeze().astype(float)
    valid = arr[arr > 0]   # assume nodata = 0

    if valid.size == 0:
        logger.error("Raster contains no valid values. Cannot compute statistics.")
        return None

    # -----------------------------------------------------
    # 3. Compute statistics
    # -----------------------------------------------------
    stats = {
        "min": float(np.min(arr)),
        "p5": float(np.percentile(arr, 5)),
        "p25": float(np.percentile(arr, 25)),
        "median": float(np.median(arr)),
        "mean": float(np.mean(arr)),
        "p75": float(np.percentile(arr, 75)),
        "p95": float(np.percentile(arr, 95)),
        "max": float(np.max(arr)),
        "sum": float(np.sum(arr)), 
        "stdev": float(np.std(arr, ddof=0)), # population std dev
        "count": int(arr.size)
    }

    stats_df = pd.DataFrame([stats])
    logger.info("Raster statistics calculated successfully.")

    # -----------------------------------------------------
    # 4. Save output CSV
    # -----------------------------------------------------
    tabular_dir = os.path.join(output_dir, "tabular")
    os.makedirs(tabular_dir, exist_ok=True)

    output_path = os.path.join(tabular_dir, f"{city_name}_landslide_stats.csv")

    try:
        stats_df.to_csv(output_path, index=False)
        logger.info(f"landslide statistics saved to: {output_path}")
    except Exception as e:
        logger.error(f"Error saving statistics CSV: {e}")

    if return_df:
        return stats_df

    return None


# From Caroline's clean.py — clean_ls_area()
def compute_histogram(
        city_name: str,
        output_dir: str,
        clipped_image=None,
        clipped_meta=None,
        include_nodata: bool = False,
        return_df: bool = False
    ):
    """
    Bin landslide susceptibility into categorical levels for visualization.
    Produces ls_area.csv with columns: bin, susceptibility, count, percentage.
    """

    logger.info("Starting landslide histogram analysis…")

    # Load raster from disk if not provided
    if clipped_image is None or clipped_meta is None:
        raster_path = os.path.join(output_dir, "spatial", f"{city_name}_landslide.tif")

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
    data = clipped_image.squeeze().astype(float)
    nodata_value = clipped_meta.get("nodata")
    if nodata_value is not None:
        valid_data = data[data != nodata_value]
    else:
        valid_data = data[~np.isnan(data)]
        valid_data = valid_data[np.isfinite(valid_data)]
    valid_data = valid_data.astype(int)

    if not include_nodata:
        analysis_data = valid_data[valid_data > 0]
    else:
        analysis_data = valid_data

    if analysis_data.size == 0:
        logger.error("No valid landslide values.")
        return None

    # Susceptibility mapping
    if include_nodata:
        susceptibility_mapping = {
            0: {"bin": "No Data", "label": "0"},
            1: {"bin": "Very low", "label": "1"},
            2: {"bin": "Low", "label": "2"},
            3: {"bin": "Medium", "label": "3"},
            4: {"bin": "High", "label": "4"},
            5: {"bin": "Very high", "label": "5"},
        }
    else:
        susceptibility_mapping = {
            1: {"bin": "Very low", "label": "1"},
            2: {"bin": "Low", "label": "2"},
            3: {"bin": "Medium", "label": "3"},
            4: {"bin": "High", "label": "4"},
            5: {"bin": "Very high", "label": "5"},
        }

    total_pixels = len(analysis_data)
    unique_values = np.unique(analysis_data)
    bin_data = []

    for value, mapping in susceptibility_mapping.items():
        count = int(np.sum(analysis_data == value)) if value in unique_values else 0
        bin_data.append({
            'bin': mapping["bin"],
            'susceptibility': mapping["label"],
            'count': count,
            'percentage': round((count / total_pixels) * 100, 2) if total_pixels > 0 else 0
        })

    result_df = pd.DataFrame(bin_data)

    # Sort by susceptibility order
    susceptibility_order = ["No Data", "Very low", "Low", "Medium", "High", "Very high"]
    result_df['sort_order'] = result_df['bin'].map({cat: i for i, cat in enumerate(susceptibility_order)})
    result_df = result_df.sort_values('sort_order').drop('sort_order', axis=1).reset_index(drop=True)

    # Save
    tabular_dir = os.path.join(output_dir, "tabular")
    os.makedirs(tabular_dir, exist_ok=True)
    output_path = os.path.join(tabular_dir, f"{city_name}_ls_area.csv")

    try:
        result_df.to_csv(output_path, index=False)
        logger.info(f"Landslide histogram saved to: {output_path}")
    except Exception as e:
        logger.error(f"Error saving histogram CSV: {e}")

    if return_df:
        return result_df
    return None


if __name__ == "__main__":
    compute_stats(city_name="testcity", output_dir="./outputs")
