import os
import numpy as np
import pandas as pd
import rasterio
from core.py.log_module import setup_logger

logger = setup_logger(__name__)


# Equivalent of Caroline's clean.py — clean_s()
def compute_slope_histogram(
        city_name: str,
        bins: list | np.ndarray,
        output_dir: str,
        clipped_image=None,
        clipped_meta=None,
        enrich: bool = True,
        return_df: bool = False
    ):
    """
    Compute slope histogram of a clipped raster using user-defined bins.

    Parameters
    ----------
    city_name : str
        City name used for locating the clipped raster file.
    bins : list or np.ndarray
        Histogram bin edges.
    output_dir : str
        Base output directory.
    clipped_image : np.ndarray, optional
        In-memory clipped raster array from datacollection().
    clipped_meta : dict, optional
        Raster metadata from datacollection().
    enrich : bool
        If True, add derived slope statistics (percent, slope, upper range).
    return_df : bool
        If True, return histogram dataframe, default is False.

    Returns
    -------
    hist_df : pandas.DataFrame
        Histogram dataframe. Includes enrichment columns if enabled.
    """

    city_name = city_name.lower()

    logger.info("Starting slope histogram computation…")

    # -----------------------------------------------------
    # 1. Compute histogram — WINDOWED from disk (never holds the full national
    #    grid in RAM) or from an in-memory array. `bins` are fixed edges, so a
    #    single pass of per-block np.histogram sums cleanly.
    # -----------------------------------------------------
    bins_arr = np.asarray(bins)

    if clipped_image is None or clipped_meta is None:
        raster_path = os.path.join(output_dir, "spatial", f"{city_name}_slope.tif")

        if not os.path.exists(raster_path):
            logger.error(f"Raster not found at: {raster_path}")
            return None

        logger.info(f"Loading raster from disk (windowed): {raster_path}")

        try:
            hist = np.zeros(len(bins_arr) - 1, dtype=np.int64)
            with rasterio.open(raster_path) as src:
                for _, window in src.block_windows(1):
                    block = src.read(1, window=window).squeeze().astype(float)
                    valid = block[block > 0]  # assume nodata = 0
                    if valid.size == 0:
                        continue
                    hist += np.histogram(valid, bins=bins_arr)[0].astype(np.int64)
        except Exception as e:
            logger.error(f"Failed to load raster: {e}")
            return None

        if hist.sum() == 0:
            logger.error("Raster contains no valid values. Cannot compute histogram.")
            return None
    else:
        logger.info("Using in-memory raster from datacollection().")
        arr = clipped_image.squeeze().astype(float)
        valid = arr[arr > 0]  # assume nodata = 0

        if valid.size == 0:
            logger.error("Raster contains no valid values. Cannot compute histogram.")
            return None

        hist, _ = np.histogram(valid, bins=bins_arr)

    bin_edges = bins_arr
    bin_labels = [
        f"{bin_edges[i]}-{bin_edges[i+1]}"
        for i in range(len(hist))
    ]

    hist_df = pd.DataFrame({
        "bin": bin_labels,
        "count": hist.astype(int)
    })

    logger.info("Histogram computed successfully.")

    # -----------------------------------------------------
    # 4. Optional enrichment
    # -----------------------------------------------------
    if enrich:
        logger.info("Applying slope enrichment…")

        hist_df = hist_df[hist_df["count"] > 0].copy()

        total = hist_df["count"].sum()

        if total == 0:
            logger.error("Histogram contains no positive counts.")
            return None

        hist_df["percent"] = hist_df["count"] / total * 100
        hist_df["Percent"] = (hist_df["percent"] / 100).apply(lambda x: f"{x:.0%}")

        hist_df["Slope"] = hist_df["bin"].str.extract(r"(\d+)").astype(float)
        hist_df["UpperRange"] = hist_df["bin"].str.extract(r"-(\d+)$").astype(float)

        logger.info("Enrichment complete.")

    # -----------------------------------------------------
    # 5. Save output CSV
    # -----------------------------------------------------
    tabular_dir = os.path.join(output_dir, "tabular")
    os.makedirs(tabular_dir, exist_ok=True)

    output_path = os.path.join(tabular_dir, f"{city_name}_slope.csv")

    try:
        hist_df.to_csv(output_path, index=False)
        logger.info(f"Histogram saved to: {output_path}")
    except Exception as e:
        logger.error(f"Error saving histogram CSV: {e}")

    if return_df:
        return hist_df

    return None

def generate_slope_yaml(
        city_name: str,
        output_dir: str
    ):
    """
    Generate YAML interpretation of dominant slope range.
    """
    import yaml

    city_name = city_name.lower()

    tabular_dir = os.path.join(output_dir, "tabular")
    os.makedirs(tabular_dir, exist_ok=True)

    logger.info("Generating slope interpretation YAML…")

    hist_path = os.path.join(output_dir, "tabular", f"{city_name}_slope.csv")

    if not os.path.exists(hist_path):
        logger.error(f"Histogram not found: {hist_path}")
        return None

    slope = pd.read_csv(hist_path)

    required_cols = {"bin", "percent"}
    if not required_cols.issubset(slope.columns):
        logger.error("Histogram CSV is not enriched. Run compute_slope_histogram(enrich=True).")
        return None

    max_row = slope.loc[slope["percent"].idxmax()]

    summary = {
        "slope_stats":
            f"The most common slope range in the city is {max_row['bin']} degrees, "
            f"with a {max_row['percent']:.2f}% frequency."
    }

    yaml_path = os.path.join(tabular_dir, f"{city_name}_slope_stats.yml")

    try:
        with open(yaml_path, "w") as f:
            yaml.dump(summary, f)
    except Exception as e:
        logger.error(f"Failed writing YAML: {e}")
        return None

    logger.info(f"Slope YAML saved: {yaml_path}")

    return yaml_path
