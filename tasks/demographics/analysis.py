# import
import os
import geopandas as gpd
import rasterio
from rasterio.mask import mask
import pandas as pd
from core.py.log_module import setup_logger
import numpy as np
logger = setup_logger(__name__)

def demographic_aggregate(
    city_name: str,
    output_dir: str,
    demographic_raster: str | None = None,
    clipped_array: np.ndarray | None = None,
    clipped_meta: dict | None = None,
    return_df: bool = True,
):
    """
    Aggregate a multi-band WorldPop demographic raster into tabular format.

    The function first attempts to use an in-memory raster (array + metadata).
    If not provided, it reads a multi-band GeoTIFF from disk.

    Parameters
    ----------
    city_name : str
        City name used for labeling outputs.
    output_dir : str
        Base output directory.
    demographic_raster : str, optional
        Path to multi-band demographic raster. If None, defaults to
        ``{output_dir}/spatial/{city_name}_demographic.tif``.
    clipped_array : np.ndarray, optional
        In-memory raster array with shape (bands, height, width).
    clipped_meta : dict, optional
        Raster metadata dictionary corresponding to ``clipped_array``.
    return_df : bool, default True
        If True, return the aggregated DataFrame.

    Returns
    -------
    pandas.DataFrame or None
        Aggregated demographic table if ``return_df=True``.
    """

    # ------------------------------------------------------------------
    # Prepare output directory
    # ------------------------------------------------------------------
    tabular_dir = os.path.join(output_dir, "tabular")
    os.makedirs(tabular_dir, exist_ok=True)

    rows = []

    # ------------------------------------------------------------------
    # Case 1: Use in-memory raster (preferred if provided)
    # ------------------------------------------------------------------
    if clipped_array is not None and clipped_meta is not None:

        band_descriptions = clipped_meta.get("descriptions")

        if band_descriptions is None:
            raise ValueError("clipped_meta must contain band descriptions")

        for i, band in enumerate(clipped_array):
            desc = band_descriptions[i]
            sex, age_group = desc.split("_", 1)

            population = float(band.sum())

            rows.append({
                "city": city_name,
                "sex": sex,
                "age_group": age_group,
                "population": population
            })

    # ------------------------------------------------------------------
    # Case 2: Read raster from disk
    # ------------------------------------------------------------------
    else:
        if demographic_raster is None:
            demographic_raster = os.path.join(
                output_dir,
                "spatial",
                f"{city_name}_worldpop_demographics.tif"
            )

        logger.info(f"Reading demographic raster from disk: {demographic_raster}")

        with rasterio.open(demographic_raster) as src:

            for band_index in range(1, src.count + 1):
                band = src.read(band_index)
                desc = src.descriptions[band_index - 1]

                sex, age_group = desc.split("_", 1)

                population = float(band.sum())

                rows.append({
                    "city": city_name,
                    "sex": sex,
                    "age_group": age_group,
                    "population": population
                })

    # ------------------------------------------------------------------
    # Convert to DataFrame and write output
    # ------------------------------------------------------------------
    df = pd.DataFrame(rows)

    output_csv = os.path.join(
        tabular_dir,
        f"{city_name}_demographic.csv"
    )
    df.to_csv(output_csv, index=False)

    logger.info(f"Saved demographic table: {output_csv}")

    if return_df:
        return df

    return None


# From Caroline's clean.py — clean_pas()
def clean_pas(
    city_name: str,
    output_dir: str,
    input_df: pd.DataFrame | None = None,
    return_df: bool = False,
):
    """
    Clean up population age structure for visualization as pas.csv.
    Merges 0-1 and 1-4 into 0-4, renames columns, adds percentages.

    Reads from {city}_demographic.csv (output of demographic_aggregate) if
    input_df is not provided.

    Output: {city}_pas.csv with columns: ageBracket, sex, count, percentage
    """

    logger.info("Starting population age structure cleanup…")

    tabular_dir = os.path.join(output_dir, "tabular")

    if input_df is None:
        input_path = os.path.join(tabular_dir, f"{city_name}_demographic.csv")
        if not os.path.exists(input_path):
            logger.error(f"Demographic CSV not found at: {input_path}")
            return None
        input_df = pd.read_csv(input_path)

    # Combine "0-1" and "1-4" age brackets into "0-4"
    df = input_df.copy()
    df['age_group'] = df['age_group'].replace({'0-1': '0-4', '1-4': '0-4'})

    # Group by the new age brackets and sex, summing the population
    df_grouped = df.groupby(['age_group', 'sex'], as_index=False)['population'].sum()

    # Expand sex abbreviations
    df_grouped['sex'] = df_grouped['sex'].replace({'f': 'female', 'm': 'male'})

    # Create result with desired structure
    total_pop = df_grouped['population'].sum()
    result_df = pd.DataFrame({
        'ageBracket': df_grouped['age_group'],
        'sex': df_grouped['sex'],
        'count': df_grouped['population'].round(2),
        'percentage': (df_grouped['population'] / total_pop * 100).round(7) if total_pop > 0 else 0,
    })

    # Sort by age bracket
    age_order = ['0-4', '5-9', '10-14', '15-19', '20-24', '25-29',
                 '30-34', '35-39', '40-44', '45-49', '50-54', '55-59', '60-64',
                 '65-69', '70-74', '75-79', '80+', '80']

    existing_categories = [cat for cat in age_order if cat in result_df['ageBracket'].unique()]
    for bracket in result_df['ageBracket'].unique():
        if bracket not in existing_categories:
            existing_categories.append(bracket)

    result_df['age_sort'] = pd.Categorical(result_df['ageBracket'], categories=existing_categories, ordered=True)
    result_df = result_df.sort_values(['age_sort', 'sex']).drop(columns=['age_sort']).reset_index(drop=True)

    # Save
    os.makedirs(tabular_dir, exist_ok=True)
    output_path = os.path.join(tabular_dir, f"{city_name}_pas.csv")

    try:
        result_df.to_csv(output_path, index=False)
        logger.info(f"Population age structure saved to: {output_path}")
    except Exception as e:
        logger.error(f"Error saving pas CSV: {e}")

    if return_df:
        return result_df
    return None


# From Caroline's clean-tabular.R — clean_adr()
def clean_adr(
    city_name: str,
    output_dir: str,
    input_df: pd.DataFrame | None = None,
    return_df: bool = False,
):
    """
    Calculate age dependency ratios from population age structure.
    Reads from {city}_pas.csv (output of clean_pas) if input_df is not provided.

    Output: {city}_adr.csv with columns: youthDependencyRatio,
    elderlyDependencyRatio, totalDependencyRatio, youthTotal,
    workingAgeTotal, elderlyTotal
    """

    logger.info("Starting age dependency ratio calculation…")

    tabular_dir = os.path.join(output_dir, "tabular")

    if input_df is None:
        input_path = os.path.join(tabular_dir, f"{city_name}_pas.csv")
        if not os.path.exists(input_path):
            logger.error(f"PAS CSV not found at: {input_path}")
            return None
        input_df = pd.read_csv(input_path)

    # Sum population by age bracket (combine male/female)
    age_totals = input_df.groupby('ageBracket', as_index=False)['count'].sum()

    # Define age categories (matching Caroline's approach)
    youth_groups = ['0-4', '5-9', '10-14']
    working_groups = ['15-19', '20-24', '25-29', '30-34', '35-39',
                      '40-44', '45-49', '50-54', '55-59', '60-64']
    elderly_groups = ['65-69', '70-74', '75-79', '80+', '80']

    youth_total = age_totals.loc[age_totals['ageBracket'].isin(youth_groups), 'count'].sum()
    working_total = age_totals.loc[age_totals['ageBracket'].isin(working_groups), 'count'].sum()
    elderly_total = age_totals.loc[age_totals['ageBracket'].isin(elderly_groups), 'count'].sum()

    if working_total == 0:
        logger.error("No working-age population found — cannot compute dependency ratios.")
        return None

    # Calculate dependency ratios (per 100 working-age people)
    youth_ratio = round((youth_total / working_total) * 100)
    elderly_ratio = round((elderly_total / working_total) * 100)
    total_ratio = youth_ratio + elderly_ratio

    result_df = pd.DataFrame([{
        'youthDependencyRatio': youth_ratio,
        'elderlyDependencyRatio': elderly_ratio,
        'totalDependencyRatio': total_ratio,
        'youthTotal': round(youth_total),
        'workingAgeTotal': round(working_total),
        'elderlyTotal': round(elderly_total),
    }])

    # Save
    os.makedirs(tabular_dir, exist_ok=True)
    output_path = os.path.join(tabular_dir, f"{city_name}_adr.csv")

    try:
        result_df.to_csv(output_path, index=False)
        logger.info(f"Age dependency ratios saved to: {output_path}")
    except Exception as e:
        logger.error(f"Error saving adr CSV: {e}")

    if return_df:
        return result_df
    return None

