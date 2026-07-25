"""Country-level GDP processing functions for city-to-country ratio calculations."""
import os
from utils import reproject_and_clip_raster, raster_sum_mean
import pandas as pd
import geopandas as gpd
from pathlib import Path
from osgeo import gdal
import numpy as np
import csv
import logging
LOGGER = logging.getLogger('city_pipeline')

def _quiet_print(*args, level: str='debug') -> None:
    """Route legacy print-style messages through the pipeline logger."""
    message = ' '.join((str(arg) for arg in args))
    getattr(LOGGER, level, LOGGER.debug)(message)

def export_gdp(shp, vector_file, stat, section, data, tables, rasters, country, city):
    """Clip and summarize GDP rasters for the study city and export a scenario-year table."""
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
                    file_name = os.path.splitext(file_name)[0]
                    Year = file_name[3:7].upper()
                    ssp = file_name[8:14].upper()
                    if int(Year) > 2020:
                        try:
                            var = 'IIASA GDP 2023'
                            input_csv = f'{tables}/{country}_{city}_{var}_rescaled.csv'
                            year = Year
                            ssp_value = ssp
                            rescaling_factor = get_rescaling_factor(input_csv, year, ssp_value)
                            out_rst = f'{rasters}/{country}_processed_{subdir}_{file_name}.tif'
                            _quiet_print(f'rescaling_factor {rescaling_factor}', level='debug')
                            reproject_and_clip_raster(input_raster=file_name_path, shapefile=shp, output_raster=out_rst, target_epsg=crs, multiply_factor=rescaling_factor)
                            _quiet_print(f'clip_and_export_rescale_raster done 1', level='debug')
                            raster_path_clipped = str(Path(out_rst))
                            total_sum, mean_value = raster_sum_mean(raster_path_clipped)
                            _quiet_print(f'Sum: {total_sum}, Mean: {mean_value}', level='debug')
                            row_data = {'Scenario': ssp, 'Year': Year, f'{stats_to_get}': int(total_sum)}
                            row_df = pd.DataFrame([row_data])
                            combined_results.append(row_df)
                            _quiet_print(f'row_df: {row_df}', level='debug')
                        except Exception:
                            _quiet_print(f'Skipped year {Year}, ssp_value {ssp}', level='debug')
                    elif int(Year) == 2020:
                        try:
                            out_rst = f'{rasters}/{country}_processed_{subdir}_{file_name}.tif'
                            rescaling_factor = 1
                            reproject_and_clip_raster(input_raster=file_name_path, shapefile=shp, output_raster=out_rst, target_epsg=crs, multiply_factor=rescaling_factor)
                            _quiet_print(f'clip_and_export_rescale_raster done 2', level='debug')
                            raster_path_clipped = str(Path(out_rst))
                            total_sum, mean_value = raster_sum_mean(raster_path_clipped)
                            _quiet_print(f'Sum: {total_sum}, Mean: {mean_value}', level='debug')
                            row_data = {'Scenario': ssp, 'Year': Year, f'{stats_to_get}': int(total_sum)}
                            row_df = pd.DataFrame([row_data])
                            combined_results.append(row_df)
                            _quiet_print(f'row_df: {row_df}', level='debug')
                        except Exception:
                            _quiet_print(f'Skipped year {Year}, ssp_value {ssp}', level='debug')
    df = gpd.GeoDataFrame(pd.concat(combined_results, ignore_index=True))
    df_tranformed = df.pivot(index=['Scenario'], columns='Year', values=stats_to_get)
    df_tranformed.to_csv(f'{tables}/country_level_{country}_{subdir}.csv')

def get_rescaling_factor(input_csv, year, ssp_value):
    """Look up the rescaling factor for a specific scenario and year from the prepared comparison table."""
    df = pd.read_csv(input_csv)
    df = df[[f'rescaling_factor_{year}_2023_div_{year}_2013', 'SCENARIO']]
    rescaling_factor = df[df['SCENARIO'] == ssp_value][f'rescaling_factor_{year}_2023_div_{year}_2013'].item()
    _quiet_print(f'year--> {year}  ....ssp_value-->> {ssp_value}...rescaling_factor--->> {rescaling_factor}', level='debug')
    return rescaling_factor

def get_ssp2_2013_dataset(data, city, country_iso3, section, dataset, var):
    """Load the 2013 SSP database, filter it to the requested country and model, and align it with the city metadata."""
    gc_city_folder = os.path.join(data, f'{section[0]}/GC_countries/')
    ssp_master_fn = os.path.join(data, f'{section[0]}/{dataset}')
    if '.csv' in dataset:
        ssp_master = pd.read_csv(ssp_master_fn)
    _quiet_print(ssp_master.columns, level='debug')
    ssp_master.columns = [col.upper() for col in ssp_master if col in ssp_master.columns]
    ssp_master['SCENARIO'] = ssp_master['SCENARIO'].str[:4]
    _quiet_print('capital---', ssp_master.columns, level='debug')
    ssp_country = ssp_master.loc[ssp_master['REGION'] == country_iso3]
    _quiet_print(f"variables----->>>> {ssp_country['MODEL'].unique()}", level='debug')
    ssp_country = ssp_country.loc[ssp_country['MODEL'] == var]
    ssp_country.reset_index(inplace=True, drop=True)
    if len(ssp_country) == 0:
        _quiet_print('Country not found in SSP database. Check if ISO3 name of the country is correct, and whether the country is actually available in the SSP database.', level='warning')
        return (0, 0)
    else:
        del ssp_master
    global_cities = pd.read_csv(gc_city_folder + 'GC_{}.csv'.format(country_iso3))
    gc_city = global_cities.loc[global_cities['Location'] == city]
    if len(gc_city) == 0:
        _quiet_print('City not found in the Global Cities database. Manually check if the city name spelling is correct, and whether the city is actually available in the Global Cities database.', level='warning')
        return (0, 0)
    else:
        del global_cities
    iso3 = gc_city['iso3'].unique()[0]
    country_name = gc_city['Country'].unique()[0]
    _quiet_print(iso3, country_name.title(), level='debug')
    ssp_country['iso3'] = iso3.title()
    ssp_country['REGION'] = country_name.title()
    return (ssp_country, country_name, country_iso3)

def get_ssp3_2023_dataset(data, country, section, dataset, var):
    """Load the 2023 SSP database and filter it to the requested country and model."""
    ssp_master_fn = os.path.join(data, f'{section[0]}/{dataset}')
    if '.csv' in dataset:
        ssp_master = pd.read_csv(ssp_master_fn)
    _quiet_print(ssp_master.columns, level='debug')
    ssp_master.columns = [col.upper() for col in ssp_master if col in ssp_master.columns]
    _quiet_print('capital---', ssp_master.columns, level='debug')
    ssp_country = ssp_master.loc[ssp_master['REGION'] == country]
    ssp_country = ssp_country.loc[ssp_country['MODEL'] == var]
    ssp_country.reset_index(inplace=True, drop=True)
    if len(ssp_country) == 0:
        _quiet_print('Country not found in SSP database. Check if ISO3 name of the country is correct, and whether the country is actually available in the SSP database.', level='warning')
        return (0, 0)
    else:
        del ssp_master
    return ssp_country

def create_updated_ssp3_dataset(country_iso3, country_name, city, section, data, tables):
    """Create a merged SSP comparison table and export updated rescaling factors for future years."""
    country_iso3 = 'BGD'
    var = 'IIASA GDP'
    var_proper = 'GDP|PPP'
    dataset = 'SspDb_country_data_2013-06-12.csv'
    ssp_country_2013, country_name, country_iso3 = get_ssp2_2013_dataset(data, city, country_iso3, section, dataset, var)
    ssp_country_2013 = ssp_country_2013[ssp_country_2013['VARIABLE'] == var_proper]
    ssp_country_2013
    dataset = 'gdp_deflator.csv'
    deflator = os.path.join(data, f'{section[0]}/{dataset}')
    deflator = pd.read_csv(deflator)
    deflator = deflator[deflator['Country Code'] == country_iso3]
    deflator_multiplier = (deflator['2017'] / deflator['2005']).item()
    _quiet_print(deflator_multiplier, level='debug')
    cols = ssp_country_2013.columns.tolist()
    for i in range(2025, 2155, 5):
        try:
            y1 = f'{i}'
            _quiet_print(f'y1={y1}, i={i}', level='debug')
            ssp_country_2013[f'{i}'] = ssp_country_2013[y1] * deflator_multiplier
        except ValueError:
            _quiet_print(f'{s} was not an integer', level='debug')
    var = 'IIASA GDP 2023'
    section = ['demographic']
    dataset = '1706548837040-ssp_basic_drivers_release_3.0_full.csv'
    ssp_country = get_ssp3_2023_dataset(data=data, country=country_name, section=section, dataset=dataset, var=var)
    df_merged = ssp_country_2013.merge(ssp_country, how='outer', on=['SCENARIO', 'REGION', 'VARIABLE'], suffixes=('_2013', '_2023'), indicator=True)
    cols = df_merged.columns.tolist()
    for j, s in enumerate(cols):
        for i in range(2025, 2105, 5):
            try:
                a = int(s)
                y1 = f'{i}_2013'
                y2 = f'{i}_2023'
                df_merged[f'rescaling_factor_{y2}_div_{y1}'] = df_merged[y2] / df_merged[y1]
                df_merged[f'updated_{i}'] = df_merged[y1] * df_merged[f'rescaling_factor_{y2}_div_{y1}']
            except ValueError:
                _quiet_print(f'{s} was not an integer', level='debug')
    df_merged.to_csv(f'{tables}/{country_name}_{city}_{var}_rescaled.csv')
    return df_merged
import os
import csv
from osgeo import gdal
import numpy as np

def gdp_ratio(raster1_path, raster2_path):
    """
    Calculate the ratio of the total values of two GDP rasters.

    Parameters:
        raster1_path (str): Path to the first raster file.
        raster2_path (str): Path to the second raster file.

    Returns:
        float: Ratio of raster1's total sum to raster2's total sum.
    """

    def read_raster_as_array(raster_path):
        """Read the first band of a raster into a NumPy array."""
        dataset = gdal.Open(raster_path)
        if dataset is None:
            raise FileNotFoundError(f'Could not open {raster_path}')
        band = dataset.GetRasterBand(1)
        array = band.ReadAsArray()
        dataset = None
        return array
    raster1_array = read_raster_as_array(raster1_path)
    raster2_array = read_raster_as_array(raster2_path)
    raster1_sum = np.nansum(raster1_array)
    raster2_sum = np.nansum(raster2_array)
    if raster2_sum == 0:
        raise ValueError('Sum of raster2 values is zero, division by zero is not allowed.')
    return raster1_sum / raster2_sum

def process_gdp_rasters(folder_path, output_csv_path):
    """
    Process GDP rasters with specific prefixes and a common wildcard suffix, 
    compute ratios, and export results to a CSV.

    Parameters:
        folder_path (str): Path to the folder containing rasters.
        output_csv_path (str): Path to the output CSV file.

    Returns:
        None
    """
    raster_files = [f for f in os.listdir(folder_path) if f.endswith(('.tif', '.TIF'))]
    processed_files = {}
    bangladesh_files = {}
    for file in raster_files:
        if file.startswith('processed_'):
            suffix = file[len('processed_'):]
            processed_files[suffix] = os.path.join(folder_path, file)
        elif file.startswith('Bangladesh_processed_'):
            suffix = file[len('Bangladesh_processed_'):]
            bangladesh_files[suffix] = os.path.join(folder_path, file)
    with open(output_csv_path, mode='w', newline='') as csvfile:
        csv_writer = csv.writer(csvfile)
        csv_writer.writerow(['Raster 1', 'Raster 2', 'GDP Ratio'])
        for suffix, raster1_path in processed_files.items():
            if suffix in bangladesh_files:
                raster2_path = bangladesh_files[suffix]
                try:
                    ratio = gdp_ratio(raster1_path, raster2_path)
                    csv_writer.writerow([os.path.basename(raster1_path), os.path.basename(raster2_path), ratio])
                except Exception as e:
                    _quiet_print(f'Error processing {raster1_path} and {raster2_path}: {e}', level='warning')
            else:
                _quiet_print(f"No matching raster found for suffix '{suffix}' in Bangladesh files.", level='debug')
