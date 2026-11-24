# import
import os
import numpy as np
import pandas as pd
import rasterio
from core.py.log_module import setup_logger

logger = setup_logger(__name__)


def generate_nth_raster(
        fwi_raster_dict: dict,
        nth_percentile: float = 98.6,
        output_dir: str = None,
        city_name: str = None,
        out_meta: dict = None
    ) -> str:
    """
    Compute nth percentile across all rasters (time = 0 axis) and write as GeoTIFF.
    
    Parameters
    ----------
    fwi_raster_dict : dict
        Dictionary {date_str → clipped_raster_array} from datacollection
    nth_percentile : float, optional
        Percentile to compute (default 98.6)
    output_dir : str
        Directory to save output raster
    city_name : str
        City name for naming output file
    out_meta : dict
        Rasterio metadata for writing GeoTIFF
        
    Returns
    -------
    str
        Path to output GeoTIFF file
    """
    
    logger.info(f"Generating {nth_percentile}th percentile raster across {len(fwi_raster_dict)} time steps")
    
    if not fwi_raster_dict or out_meta is None:
        logger.error("Invalid raster dict or metadata provided")
        return None
    
    try:
        # Convert dict values to array (stack rasters along time axis)
        raster_stack = np.array(list(fwi_raster_dict.values()))
        
        # Compute percentile across time dimension (axis 0)
        percentile_raster = np.nanpercentile(raster_stack, nth_percentile, axis=0)
        
        logger.info(f"Computed {nth_percentile}th percentile: min={np.nanmin(percentile_raster):.2f}, max={np.nanmax(percentile_raster):.2f}")
        
        # Squeeze band dimension if present (rasterio expects 2D for single band)
        if percentile_raster.ndim == 3 and percentile_raster.shape[0] == 1:
            percentile_raster = percentile_raster[0]
        
        # Update metadata for single-band output
        out_meta_copy = out_meta.copy()
        out_meta_copy.update({
            "count": 1,
            "dtype": percentile_raster.dtype
        })
        
        # Write to GeoTIFF
        spatial_dir = os.path.join(output_dir, "spatial")
        os.makedirs(spatial_dir, exist_ok=True)
        output_path = os.path.join(spatial_dir, f"{city_name}_fwi_{nth_percentile}.tif")
        
        with rasterio.open(output_path, 'w', **out_meta_copy) as dest:
            dest.write(percentile_raster, 1)
        
        logger.info(f"Successfully wrote {nth_percentile}th percentile raster to {output_path}")
        
        return output_path
        
    except Exception as e:
        logger.error(f"Error generating {nth_percentile}th percentile raster: {e}")
        return None


# Equivalent of Caroline's clean.py — clean_fwi()
def calculate_weekly_nth(
        fwi_raster_dict: dict,
        nth_percentile: float = 95,
        output_dir: str = None,
        city_name: str = None
    ) -> str:
    """
    Calculate nth percentile by week of year across all pixels and years.
    
    Parameters
    ----------
    fwi_raster_dict : dict
        Dictionary {date_str → clipped_raster_array} from datacollection
    nth_percentile : float, optional
        Percentile to compute (default 95)
    output_dir : str
        Directory to save output CSV
    city_name : str
        City name for naming output file
        
    Returns
    -------
    str
        Path to output CSV file
    """
    
    logger.info(f"Calculating weekly {nth_percentile}th percentile across {len(fwi_raster_dict)} rasters")
    
    if not fwi_raster_dict:
        logger.error("Invalid raster dict provided")
        return None
    
    try:
        # Flatten each raster and create dict of lists
        fwi_val_dict = {}
        for date_str, raster_array in fwi_raster_dict.items():
            fwi_val_dict[date_str] = raster_array.flatten().tolist()
        
        # Create DataFrame
        df = pd.DataFrame(list(fwi_val_dict.items()), columns=['date_str', 'fwi'])
        
        # Convert to datetime and extract week
        df['date'] = pd.to_datetime(df['date_str'], format='%Y%m%d', errors='coerce')
        df['week'] = df['date'].dt.isocalendar().week
        
        # Filter out invalid dates
        df = df.dropna(subset=['date', 'week'])
        
        # Explode lists into individual rows
        df = df.explode('fwi', ignore_index=True)
        
        # Convert fwi values to numeric (handle any non-numeric values)
        df['fwi'] = pd.to_numeric(df['fwi'], errors='coerce')
        
        # Group by week and compute percentile
        weekly_pctile = df.groupby('week').agg(
            pctile=('fwi', lambda x: np.nanpercentile(x, nth_percentile))
        ).reset_index()
        weekly_pctile.columns = ['week', f'pctile_{nth_percentile}']
        
        logger.info(f"Computed weekly {nth_percentile}th percentile for {len(weekly_pctile)} weeks")
        logger.info(f"  Week statistics - min: {weekly_pctile[f'pctile_{nth_percentile}'].min():.2f}, max: {weekly_pctile[f'pctile_{nth_percentile}'].max():.2f}")
        
        # Write to CSV
        tabular_dir = os.path.join(output_dir, "tabular")
        os.makedirs(tabular_dir, exist_ok=True)
        output_path = os.path.join(tabular_dir, f"{city_name}_fwi_weekly_{nth_percentile}.csv")
        
        weekly_pctile.to_csv(output_path, index=False)
        
        logger.info(f"Successfully wrote weekly {nth_percentile}th percentile to {output_path}")
        
        return output_path
        
    except Exception as e:
        logger.error(f"Error calculating weekly {nth_percentile}th percentile: {e}")
        return None