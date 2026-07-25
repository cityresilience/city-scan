"""Urban land processing functions for scenario-based land-cover summaries."""
import os
from utils import reproject_and_clip_raster, raster_sum_mean
import pandas as pd
import geopandas as gpd
from pathlib import Path
import logging
LOGGER = logging.getLogger('city_pipeline')

def _quiet_print(*args, level: str='debug') -> None:
    """Route legacy print-style messages through the pipeline logger."""
    message = ' '.join((str(arg) for arg in args))
    getattr(LOGGER, level, LOGGER.debug)(message)

def export_urbanland(shp, vector_file, stat, section, data, tables, rasters, country, city):
    """Clip urban land rasters for the study city and export scenario-year summary values."""
    for subdir in section:
        combined_results = []
        extension = '.tif'
        crs = 4326
        stats_to_get = stat[0]
        for root, dirs_list, files_list in os.walk(os.path.join(data, subdir)):
            for file_name in files_list:
                if os.path.splitext(file_name)[-1] == extension:
                    file_name_path = os.path.join(root, file_name)
                    file_name = os.path.splitext(file_name)[0]
                    _quiet_print(file_name, file_name_path, subdir, level='debug')
                    Year = file_name[5:9].upper()
                    ssp = file_name[0:4].upper()
                    out_rst = f'{rasters}/processed_{subdir}_{file_name}.tif'
                    rescaling_factor = 1
                    reproject_and_clip_raster(input_raster=file_name_path, shapefile=shp, output_raster=out_rst, target_epsg=crs, multiply_factor=rescaling_factor)
                    raster_path_clipped = str(Path(out_rst))
                    total_sum, mean_value = raster_sum_mean(raster_path_clipped)
                    _quiet_print(f'Sum: {total_sum}, Mean: {mean_value}', level='debug')
                    row_data = {'Scenario': ssp, 'Year': Year, f'{stats_to_get}': mean_value}
                    row_df = pd.DataFrame([row_data])
                    combined_results.append(row_df)
                    _quiet_print(f'row_df: {row_df}', level='debug')
        df = gpd.GeoDataFrame(pd.concat(combined_results, ignore_index=True))
        df_tranformed = df.pivot(index=['Scenario'], columns='Year', values=stats_to_get)
        df_graph = df_tranformed.melt(ignore_index=False).reset_index()
        df_tranformed.to_csv(f'{tables}/{country}_{city}_{subdir}.csv')
        _quiet_print(df_tranformed, level='debug')
