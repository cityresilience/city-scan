import os
import numpy as np
import pandas as pd
import geopandas as gpd
from core.py.log_module import setup_logger

logger = setup_logger(__name__)

def compute_stats_gdf(
    city_name: str,
    output_dir: str,
    gdf: gpd.GeoDataFrame,
    value_col: str,
    drop_zeros: bool = True,
    return_df: bool = False
):
    """
    Perform statistics on a GeoDataFrame column.

    Parameters
    ----------
    city_name : str
        City name used for output naming.
    output_dir : str
        Base output directory.
    gdf : geopandas.GeoDataFrame
        Input GeoDataFrame containing values to summarize.
    value_col : str
        Column name containing numeric values (e.g. population, risk).
    drop_zeros : bool, default True
        If True, exclude zero and negative values.
    return_df : bool, default False
        If True, return dataframe.

    Returns
    -------
    stats_df : pandas.DataFrame or None
        DataFrame containing min, p25, median, mean, p75, max, sum.
    """

    logger.info("Starting GeoDataFrame statistics analysis…")

    # -----------------------------------------------------
    # 1. Validation
    # -----------------------------------------------------
    if gdf is None or gdf.empty:
        logger.error("Input GeoDataFrame is empty or None.")
        try: 
            gdf_path = os.path.join(output_dir, "spatial", f"{city_name}_rwi.gpkg")
            gdf = gpd.read_file(gdf_path)
            logger.info(f"reading from {gdf_path} instead")
        except Exception as e:
            logger.error(f"Failed to load gdf: {e}")
            return None
    else:
        logger.info("Using in-memory raster from datacollection().")

    if value_col not in gdf.columns:
        logger.error(f"Column '{value_col}' not found in GeoDataFrame.")
        return None

    # -----------------------------------------------------
    # 2. Prepare data
    # -----------------------------------------------------
    values = pd.to_numeric(gdf[value_col], errors="coerce")

    # Drop NaN
    values = values.dropna()

    if drop_zeros:
        values = values[values > 0]

    if values.empty:
        logger.error("No valid values available after filtering.")
        return None

    arr = values.to_numpy(dtype=float)

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
    logger.info("GeoDataFrame statistics calculated successfully.")

    # -----------------------------------------------------
    # 4. Save output CSV
    # -----------------------------------------------------
    tabular_dir = os.path.join(output_dir, "tabular")
    os.makedirs(tabular_dir, exist_ok=True)

    output_path = os.path.join(
        tabular_dir,
        f"{city_name}_{value_col}_stats.csv"
    )

    try:
        stats_df.to_csv(output_path, index=False)
        logger.info(f"Statistics saved to: {output_path}")
    except Exception as e:
        logger.error(f"Error saving statistics CSV: {e}")

    if return_df:
        return stats_df

    return None


# From Caroline's clean.py — clean_rwi_area()
def compute_histogram(
    city_name: str,
    output_dir: str,
    gdf: gpd.GeoDataFrame = None,
    value_col: str = "rwi",
    return_df: bool = False
):
    """
    Bin RWI values into wealth categories using standard deviation binning.
    Produces rwi_area.csv with columns: bin, count, percentage.
    """

    logger.info("Starting RWI histogram analysis…")

    # Load from disk if not provided
    if gdf is None or gdf.empty:
        gdf_path = os.path.join(output_dir, "spatial", f"{city_name}_rwi.gpkg")
        if not os.path.exists(gdf_path):
            logger.error(f"RWI GeoPackage not found at: {gdf_path}")
            return None
        try:
            gdf = gpd.read_file(gdf_path)
        except Exception as e:
            logger.error(f"Failed to load GeoPackage: {e}")
            return None

    if value_col not in gdf.columns:
        logger.error(f"Column '{value_col}' not found.")
        return None

    gdf_valid = gdf[gdf[value_col].notna()].copy()
    if len(gdf_valid) == 0:
        logger.error("No valid RWI data.")
        return None

    # Reproject to UTM for accurate area calculation
    if gdf_valid.crs and gdf_valid.crs.is_geographic:
        gdf_valid = gdf_valid.to_crs(gdf_valid.estimate_utm_crs())

    gdf_valid['area'] = gdf_valid.geometry.area

    total_area = gdf_valid['area'].sum()
    tabular_dir = os.path.join(output_dir, "tabular")
    os.makedirs(tabular_dir, exist_ok=True)

    # --- City-relative binning (standard deviation of city's own data) ---
    rwi_mean = gdf_valid[value_col].mean()
    rwi_sd = gdf_valid[value_col].std()

    rwi_min = gdf_valid[value_col].min()
    rwi_max = gdf_valid[value_col].max()
    eq_breaks = np.linspace(rwi_min, rwi_max, 6)
    bins_relative = list(eq_breaks)
    labels_relative = [
        f'{eq_breaks[i]:.2f} – {eq_breaks[i+1]:.2f}' for i in range(5)
    ]

    gdf_valid['rwi_category'] = pd.cut(
        gdf_valid[value_col], bins=bins_relative, labels=labels_relative, include_lowest=True
    )

    bin_data_relative = []
    for category in labels_relative:
        category_data = gdf_valid[gdf_valid['rwi_category'] == category]
        count = len(category_data)
        area = category_data['area'].sum() if count > 0 else 0
        percentage = round((area / total_area) * 100, 2) if total_area > 0 else 0
        bin_data_relative.append({'bin': category, 'count': int(count), 'percentage': percentage})

    result_relative = pd.DataFrame(bin_data_relative)
    result_relative = result_relative[result_relative['count'] > 0].copy()

    try:
        output_path = os.path.join(tabular_dir, f"{city_name}_rwi_area.csv")
        result_relative.to_csv(output_path, index=False)
        logger.info(f"RWI relative histogram saved to: {output_path}")
    except Exception as e:
        logger.error(f"Error saving relative histogram CSV: {e}")

    # --- Standardized binning (fixed SD breaks, comparable across cities) ---
    bins_std = [-np.inf, -1.0, -0.5, 0.5, 1.0, np.inf]
    labels_std = ['< -1.0', '-1.0 – -0.5', '-0.5 – 0.5', '0.5 – 1.0', '> 1.0']

    gdf_valid['rwi_category_std'] = pd.cut(
        gdf_valid[value_col], bins=bins_std, labels=labels_std, include_lowest=True
    )

    bin_data_std = []
    for category in labels_std:
        category_data = gdf_valid[gdf_valid['rwi_category_std'] == category]
        count = len(category_data)
        area = category_data['area'].sum() if count > 0 else 0
        percentage = round((area / total_area) * 100, 2) if total_area > 0 else 0
        bin_data_std.append({'bin': category, 'count': int(count), 'percentage': percentage})

    result_std = pd.DataFrame(bin_data_std)
    result_std = result_std[result_std['count'] > 0].copy()

    try:
        output_path_std = os.path.join(tabular_dir, f"{city_name}_rwi_area_standardized.csv")
        result_std.to_csv(output_path_std, index=False)
        logger.info(f"RWI standardized histogram saved to: {output_path_std}")
    except Exception as e:
        logger.error(f"Error saving standardized histogram CSV: {e}")

    if return_df:
        return result_df
    return None
