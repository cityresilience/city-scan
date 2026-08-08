import os
import numpy as np
import pandas as pd
import rasterio
from core.py.log_module import setup_logger

logger = setup_logger(__name__)


# From Caroline's clean.py — clean_summer_area()
def compute_histogram(
        city_name: str,
        output_dir: str,
        clipped_image=None,
        clipped_meta=None,
        bin_width: int = 5,
        return_df: bool = False
    ):
    """
    Bin summer surface temperature into ranges for visualization.
    Produces summer_area.csv with columns: bin, count, percentage.
    """

    logger.info("Starting summer LST histogram analysis…")

    # Produce bin_edges + per-bin counts + total_pixels. Reading from disk is
    # done WINDOWED (block by block) so a national-scale raster is never fully
    # held in RAM: pass 1 finds the global min/max to size the bins, pass 2
    # accumulates per-bin counts.
    if clipped_image is None or clipped_meta is None:
        raster_path = os.path.join(output_dir, "spatial", f"{city_name}_lst_summer.tif")

        if not os.path.exists(raster_path):
            logger.error(f"Clipped raster not found at: {raster_path}")
            return None

        try:
            with rasterio.open(raster_path) as src:
                nodata_value = src.nodata

                # Pass 1: global min/max over valid pixels
                min_temp = np.inf
                max_temp = -np.inf
                for _, window in src.block_windows(1):
                    block = src.read(1, window=window).astype(float)
                    if nodata_value is not None:
                        valid = block[block != nodata_value]
                    else:
                        valid = block[~np.isnan(block)]
                        valid = valid[np.isfinite(valid)]
                    if valid.size == 0:
                        continue
                    min_temp = min(min_temp, float(valid.min()))
                    max_temp = max(max_temp, float(valid.max()))

                if not np.isfinite(min_temp):
                    logger.error("No valid temperature values.")
                    return None

                # Dynamic bins based on data range
                bin_start = int(np.floor(min_temp / bin_width) * bin_width)
                bin_end = int(np.ceil(max_temp / bin_width) * bin_width)
                bin_edges = list(range(bin_start, bin_end + bin_width, bin_width))

                # Pass 2: accumulate per-bin counts
                counts = [0] * (len(bin_edges) - 1)
                total_pixels = 0
                for _, window in src.block_windows(1):
                    block = src.read(1, window=window).astype(float)
                    if nodata_value is not None:
                        valid = block[block != nodata_value]
                    else:
                        valid = block[~np.isnan(block)]
                        valid = valid[np.isfinite(valid)]
                    if valid.size == 0:
                        continue
                    total_pixels += int(valid.size)
                    for i in range(len(bin_edges) - 1):
                        lower = bin_edges[i]
                        upper = bin_edges[i + 1]
                        if i == len(bin_edges) - 2:
                            counts[i] += int(np.sum((valid >= lower) & (valid <= upper)))
                        else:
                            counts[i] += int(np.sum((valid >= lower) & (valid < upper)))
        except Exception as e:
            logger.error(f"Failed to load raster: {e}")
            return None
    else:
        # In-memory path (pre-read array from datacollection)
        temp_data = clipped_image.squeeze().astype(float)
        nodata_value = clipped_meta.get("nodata")
        if nodata_value is not None:
            valid_data = temp_data[temp_data != nodata_value]
        else:
            valid_data = temp_data[~np.isnan(temp_data)]
            valid_data = valid_data[np.isfinite(valid_data)]

        if valid_data.size == 0:
            logger.error("No valid temperature values.")
            return None

        # Dynamic bins based on data range
        min_temp = valid_data.min()
        max_temp = valid_data.max()
        bin_start = int(np.floor(min_temp / bin_width) * bin_width)
        bin_end = int(np.ceil(max_temp / bin_width) * bin_width)
        bin_edges = list(range(bin_start, bin_end + bin_width, bin_width))

        total_pixels = len(valid_data)
        counts = [0] * (len(bin_edges) - 1)
        for i in range(len(bin_edges) - 1):
            lower = bin_edges[i]
            upper = bin_edges[i + 1]
            if i == len(bin_edges) - 2:
                counts[i] = int(np.sum((valid_data >= lower) & (valid_data <= upper)))
            else:
                counts[i] = int(np.sum((valid_data >= lower) & (valid_data < upper)))

    # Build per-bin rows
    bin_data = []
    for i in range(len(bin_edges) - 1):
        lower = bin_edges[i]
        upper = bin_edges[i + 1]
        count = int(counts[i])
        bin_data.append({
            'bin': f"{lower}-{upper}",
            'count': count,
            'percentage': round((count / total_pixels) * 100, 2) if total_pixels > 0 else 0
        })

    result_df = pd.DataFrame(bin_data)

    # Save
    tabular_dir = os.path.join(output_dir, "tabular")
    os.makedirs(tabular_dir, exist_ok=True)
    output_path = os.path.join(tabular_dir, f"{city_name}_summer_area.csv")

    try:
        result_df.to_csv(output_path, index=False)
        logger.info(f"Summer LST histogram saved to: {output_path}")
    except Exception as e:
        logger.error(f"Error saving histogram CSV: {e}")

    if return_df:
        return result_df
    return None
