import os
import numpy as np
import pandas as pd
import rasterio
import geopandas as gpd
from core.py.log_module import setup_logger
from shapely.geometry import mapping
from rasterio.merge import merge
from rasterio.warp import calculate_default_transform, reproject, Resampling
from rasterio.transform import array_bounds
from rasterio import Affine
from rasterio.io import MemoryFile
from rasterio.mask import mask

logger = setup_logger(__name__)

def builtup_overtime(
    aoi, 
    output_dir, 
    city_name, 
    threshold = 1200,
):
    """
    Generate a single-band raster indicating the first year a pixel became built-up,
    based on a threshold (default 1200 sqm). Reads yearly rasters from GCS.
    """
    import numpy as np
    
    spatial_dir = os.path.join(output_dir, 'spatial')
    years = list(range(1975, 2035, 5))
    raster_paths = []
    for year in years:
        fname = f"{city_name}_ghs_built_E{year}.tif"
        local_path = os.path.join(spatial_dir, fname)
        raster_paths.append(local_path)

    # Open first raster to get shape, transform, meta
    with rasterio.open(raster_paths[0]) as src0:
        meta = src0.meta.copy()
        shape = (src0.height, src0.width)
        transform = src0.transform
        crs = src0.crs
        dtype = np.uint16  # years fit in uint16

    # Prepare output array: 0 = not built-up, else year
    out_arr = np.zeros(shape, dtype=dtype)

    # For each year, fill pixels where built-up >= threshold and not yet set
    for i, year in enumerate(years):
        with rasterio.open(raster_paths[i]) as src:
            arr = src.read(1)
            mask_year = (arr >= threshold) & (out_arr == 0)
            out_arr[mask_year] = year

    # Clip raster to AOI
    if isinstance(aoi, gpd.GeoDataFrame):
        aoi = aoi.copy()
    else:
        raise ValueError("aoi_file must be a path or a GeoDataFrame")
    aoi_4326 = aoi.to_crs(crs)
    shapes = [mapping(geom) for geom in aoi_4326.geometry]

    # Write to temporary file for masking
    tmp_path = os.path.join(spatial_dir, f"tmp_{city_name}_ghs_built_over_time.tif")
    out_meta = meta.copy()
    out_meta.update({
        "count": 1,
        "dtype": dtype,
        "compress": "deflate"
    })
    with rasterio.open(tmp_path, "w", **out_meta) as dst:
        dst.write(out_arr, 1)

    # Mask with AOI
    with rasterio.open(tmp_path) as src:
        clipped_arr, clipped_transform = mask(src, shapes, crop=True)
        clipped_meta = src.meta.copy()
        clipped_meta.update({
            "height": clipped_arr.shape[1],
            "width": clipped_arr.shape[2],
            "transform": clipped_transform,
            "count": 1,
            "dtype": dtype,
            "compress": "deflate"
        })

    out_path = os.path.join(spatial_dir, f"{city_name}_ghs_built_over_time.tif")
    with rasterio.open(out_path, "w", **clipped_meta) as dst:
        dst.write(clipped_arr[0], 1)

    os.remove(tmp_path)

    logger.info(f"Saved built-up overtime raster: {out_path}")



def compute_stats(
        city_name: str,
        output_dir: str,
        start_year: int = 1975, 
        end_year: int = 2030, 
    ):
    """
    Perform statistics on clipped ghs_built raster from start year to end year.

    Parameters
    ----------
    city_name : str
        City name used for locating the clipped raster file.
    output_dir : str
        Base output directory.

    Returns
    -------
    stats_df : pandas.DataFrame
        DataFrame containing min, p25, median, mean, p75, max, sum.
    """

    logger.info("Starting WorldPop raster analysis…")

    years = range(start_year, end_year+5, 5)
    for year in years:
        # -----------------------------------------------------
        # 1. Load raster from disk if not provided
        # -----------------------------------------------------
        
        raster_path = os.path.join(output_dir, "spatial", f"{city_name}_ghs_built_E{year}.tif")

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
        

        # -----------------------------------------------------
        # 2. Prepare raster data for statistics
        # -----------------------------------------------------
        # Convert to 1D and remove zeros/nodata
        arr = clipped_image.squeeze().astype(float)
        valid = arr[(arr > 0) & (arr <= 10000)]  # assume nodata = 0

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
            "stdev": float(np.std(arr, ddof=0)), # air quality std dev
            "count": int(arr.size)
        }

        stats_df = pd.DataFrame([stats])
        logger.info("Raster statistics calculated successfully.")

        # -----------------------------------------------------
        # 4. Save output CSV
        # -----------------------------------------------------
        tabular_dir = os.path.join(output_dir, "tabular")
        os.makedirs(tabular_dir, exist_ok=True)

        output_path = os.path.join(tabular_dir, f"{city_name}_ghs_built_e{year}.csv")

        try:
            stats_df.to_csv(output_path, index=False)
            logger.info(f"air quality statistics saved to: {output_path}")
        except Exception as e:
            logger.error(f"Error saving statistics CSV: {e}")

        # return None
