import os
import numpy as np
import pandas as pd
import rasterio
from rasterio.warp import reproject, Resampling
from core.py.log_module import setup_logger

logger = setup_logger(__name__)


# From Caroline's clean.py — clean_deforestation_area()
def compute_histogram(
        city_name: str,
        output_dir: str,
        base_year: int = 2000,
        auto_align: bool = True,
        return_df: bool = False
    ):
    """
    Compute year-over-year deforestation from forest cover and deforestation rasters.
    Produces deforestation_area.csv with columns: year, forest_remaining,
    deforested_this_year, cumulative_deforested, percent_forest_remaining, percent_forest_lost.
    """

    logger.info("Starting deforestation analysis…")

    spatial_dir = os.path.join(output_dir, "spatial")
    forest_path = os.path.join(spatial_dir, f"{city_name}_forest_cover23.tif")
    deforest_path = os.path.join(spatial_dir, f"{city_name}_deforestation.tif")

    if not os.path.exists(forest_path):
        logger.error(f"Forest cover raster not found at: {forest_path}")
        return None
    if not os.path.exists(deforest_path):
        logger.error(f"Deforestation raster not found at: {deforest_path}")
        return None

    # Read both rasters WINDOWED (block by block) so the national-scale grids are
    # never fully held in RAM. Deforestation is read on the forest grid via a
    # WarpedVRT (nearest resampling, matching the old full-array reproject); an
    # already-aligned deforestation raster passes straight through. Accumulate
    # baseline forest, the full set of deforestation years, and per-year counts
    # within forest pixels across blocks.
    try:
        from rasterio.vrt import WarpedVRT

        with rasterio.open(forest_path) as forest_src, \
             rasterio.open(deforest_path) as deforest_src:
            forest_nodata = forest_src.nodata
            deforest_nodata = deforest_src.nodata

            # Check alignment
            same_crs = forest_src.crs == deforest_src.crs
            same_shape = forest_src.shape == deforest_src.shape
            same_bounds = (abs(forest_src.bounds.left - deforest_src.bounds.left) < 1e-6 and
                          abs(forest_src.bounds.right - deforest_src.bounds.right) < 1e-6 and
                          abs(forest_src.bounds.top - deforest_src.bounds.top) < 1e-6 and
                          abs(forest_src.bounds.bottom - deforest_src.bounds.bottom) < 1e-6)
            same_transform = forest_src.transform == deforest_src.transform
            is_aligned = same_crs and same_shape and same_bounds and same_transform

            if not is_aligned and not auto_align:
                logger.error("TIF files are not aligned. Set auto_align=True.")
                return None
            if not is_aligned:
                logger.info("Auto-aligning deforestation to match forest cover (windowed)...")

            baseline_forest = 0
            all_year_codes = set()
            year_counts = {}

            with WarpedVRT(deforest_src, crs=forest_src.crs,
                           transform=forest_src.transform,
                           width=forest_src.width, height=forest_src.height,
                           resampling=Resampling.nearest,
                           src_nodata=deforest_nodata, nodata=deforest_nodata) as deforest_vrt:
                for _, window in forest_src.block_windows(1):
                    forest_block = forest_src.read(1, window=window)
                    deforest_block = deforest_vrt.read(1, window=window)

                    # Use forest cover as primary mask
                    if forest_nodata is not None:
                        valid_mask = forest_block != forest_nodata
                    else:
                        valid_mask = ~np.isnan(forest_block) & np.isfinite(forest_block)

                    forest_valid = forest_block[valid_mask]
                    if forest_valid.size == 0:
                        continue

                    deforest_valid = deforest_block[valid_mask]
                    if deforest_nodata is not None:
                        deforest_valid = np.where(deforest_valid == deforest_nodata, 0, deforest_valid)
                    if np.issubdtype(deforest_valid.dtype, np.floating):
                        deforest_valid = np.where(np.isnan(deforest_valid), 0, deforest_valid)

                    # Every deforestation year present in valid pixels
                    dv_all = deforest_valid[deforest_valid > 0]
                    if dv_all.size:
                        all_year_codes.update(np.unique(dv_all).tolist())

                    # Deforestation within forest pixels, per year code
                    is_forest = forest_valid == 1
                    baseline_forest += int(np.sum(is_forest))
                    dvals = deforest_valid[is_forest]
                    dvals = dvals[dvals > 0]
                    if dvals.size:
                        uy, uc = np.unique(dvals, return_counts=True)
                        for yc, cc in zip(uy.tolist(), uc.tolist()):
                            year_counts[yc] = year_counts.get(yc, 0) + int(cc)

        baseline_forest = int(baseline_forest)

    except Exception as e:
        logger.error(f"Error reading TIF files: {e}")
        return None

    if baseline_forest == 0:
        logger.warning("No forest pixels found.")
        return None

    # Build year-over-year data
    result_data = [{
        'year': base_year,
        'forest_remaining': baseline_forest,
        'deforested_this_year': 0,
        'cumulative_deforested': 0,
        'percent_forest_remaining': 100.0,
        'percent_forest_lost': 0.0
    }]

    deforest_years = sorted(all_year_codes)
    cumulative_deforested = 0

    for year_code in deforest_years:
        actual_year = base_year + int(year_code)
        deforested_count = int(year_counts.get(year_code, 0))
        cumulative_deforested += deforested_count
        forest_remaining = baseline_forest - cumulative_deforested

        result_data.append({
            'year': actual_year,
            'forest_remaining': int(forest_remaining),
            'deforested_this_year': int(deforested_count),
            'cumulative_deforested': int(cumulative_deforested),
            'percent_forest_remaining': round((forest_remaining / baseline_forest) * 100, 2),
            'percent_forest_lost': round((cumulative_deforested / baseline_forest) * 100, 2)
        })

    result_df = pd.DataFrame(result_data)

    # Save
    tabular_dir = os.path.join(output_dir, "tabular")
    os.makedirs(tabular_dir, exist_ok=True)
    output_path = os.path.join(tabular_dir, f"{city_name}_deforestation_area.csv")

    try:
        result_df.to_csv(output_path, index=False)
        logger.info(f"Deforestation histogram saved to: {output_path}")
    except Exception as e:
        logger.error(f"Error saving histogram CSV: {e}")

    if return_df:
        return result_df
    return None
