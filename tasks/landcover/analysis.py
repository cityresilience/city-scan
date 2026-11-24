from core.py.log_module import setup_logger
logger = setup_logger(__name__)

import os
import csv
import numpy as np
import rasterio

CLASS_VALUES = {
    10: 'Tree cover',
    20: 'Shrubland',
    30: 'Grassland',
    40: 'Cropland',
    50: 'Built-up',
    60: 'Bare / sparse vegetation',
    70: 'Snow and ice',
    80: 'Permanent water bodies',
    90: 'Herbaceous wetland',
    95: 'Mangroves',
    100: 'Moss and lichen'
}


def dataanalysis(city_name, output_dir):
    """Compute land cover stats CSV from the raster using windowed reads."""

    spatial_dir = os.path.join(output_dir, "spatial")
    tif_path = os.path.join(spatial_dir, f"{city_name}_lc.tif")

    class_vals = np.array(sorted(CLASS_VALUES.keys()))
    pixel_counts = {}
    needs_scale = None

    with rasterio.open(tif_path) as src:
        for _, window in src.block_windows(1):
            block = src.read(1, window=window).astype(float)
            valid = block[~np.isnan(block) & (block != src.nodata if src.nodata is not None else True)].astype(int)
            if len(valid) == 0:
                continue

            # Detect scale on first block
            if needs_scale is None:
                needs_scale = valid.max() <= 10

            if needs_scale:
                valid = valid * 10

            # Snap to nearest valid ESA class
            valid = class_vals[np.argmin(np.abs(valid[:, None] - class_vals[None, :]), axis=1)]

            unique, counts = np.unique(valid, return_counts=True)
            for val, cnt in zip(unique, counts):
                pixel_counts[val] = pixel_counts.get(val, 0) + cnt

    counts_dict = {}
    for class_val, class_name in CLASS_VALUES.items():
        counts_dict[class_name] = pixel_counts.get(class_val, 0)

    tabular_dir = os.path.join(output_dir, "tabular")
    os.makedirs(tabular_dir, exist_ok=True)
    csv_path = os.path.join(tabular_dir, f"{city_name}_lc.csv")

    with open(csv_path, 'w', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=['Land Cover Type', 'Pixel Count'])
        writer.writeheader()
        for class_name, count in counts_dict.items():
            writer.writerow({'Land Cover Type': class_name, 'Pixel Count': count})

    logger.info(f"Land cover stats saved to: {csv_path}")
    return counts_dict
