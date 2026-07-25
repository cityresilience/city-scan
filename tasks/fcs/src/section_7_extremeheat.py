"""Extreme heat extraction and plotting functions for climate indicators."""
import xarray as xr
import os
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import seaborn as sns
from osgeo import gdal, osr
import logging
LOGGER = logging.getLogger('city_pipeline')

def _quiet_print(*args, level: str='debug') -> None:
    """Route legacy print-style messages through the pipeline logger."""
    message = ' '.join((str(arg) for arg in args))
    getattr(LOGGER, level, LOGGER.debug)(message)

def export_extreme_heat_cckp_data(vector_file, section, data, rasters, tables, country, city):
    """Extract extreme heat indicators from NetCDF files and prepare raster and tabular outputs."""
    appended_data = []
    for subdir in section:
        extension = '.nc'
        for root, dirs_list, files_list in os.walk(os.path.join(data, subdir)):
            for file_name in files_list:
                if os.path.splitext(file_name)[-1] == extension:
                    file_name_path = os.path.join(root, file_name)
                    file_name = os.path.splitext(file_name)[0]
                    variable_name = file_name.split('_')[0]
                    Year = file_name.split('_')[-1].upper()
                    ssp = file_name.split('-')[-2].upper()
                    ssp = ssp.split('_')[0].upper()
                    dataset = xr.open_dataset(file_name_path)
                    _quiet_print(f'Varname-->>{list(dataset.keys())}', level='debug')
                    clean_var_name = variable_name.replace('-', '_')
                    clean_var_name = clean_var_name.replace(':', '')
                    dataset = dataset.rename(name_dict={f'{variable_name}': f'{clean_var_name}'})
                    var_long_label = dataset.variables[clean_var_name].attrs['long_name'].capitalize()
                    var_long_label = var_long_label.replace(':', '')
                    _quiet_print(variable_name, '----', clean_var_name, '----', var_long_label, level='debug')
                    gpdf = vector_file
                    gpdf['centroid'] = gpdf['geometry'].centroid
                    gpdf['lat'] = gpdf['centroid'].y
                    gpdf['lon'] = gpdf['centroid'].x
                    lat = gpdf['centroid'].y[0]
                    lon = gpdf['centroid'].x[0]
                    bounds = vector_file.total_bounds
                    min_long, min_lat, max_long, max_lat = bounds
                    _quiet_print(f'Min Latitude: {min_lat}--Max Latitude: {max_lat}-- Min Longitude: {min_long}--- Max Longitude: {max_long}', level='debug')
                    _quiet_print(f'Centroid Latitude: {lat}--  Centroid lon: {lon}', level='debug')
                    df = dataset[clean_var_name].sel(lat=slice(int(lat), int(lat)), lon=slice(int(lon), int(lon)))
                    df = df.to_dataframe()
                    df = df.dropna().reset_index()
                    _quiet_print(f'values for the variable: {df[clean_var_name].value_counts()}', level='debug')
                    df[subdir] = df[clean_var_name]
                    df['Variable'] = var_long_label
                    df['SSP'] = ssp
                    try:
                        df_date = df[df[[subdir]].apply(pd.to_datetime, errors='coerce').isna().all(axis=1)]
                        df_date[subdir] = df_date[subdir] / pd.to_timedelta(1, unit='D')
                        _quiet_print(f'Max value of days: {df_date[subdir].max()}---Mean value of days: {df_date[subdir].mean()}', level='debug')
                        max_value = df_date[subdir].max()
                    except Exception:
                        pass
                        _quiet_print(f'Passing {var_long_label}', level='debug')
                    if max_value < 1e-05:
                        offset = 0.25
                        _quiet_print(f'setting {offset}', level='debug')
                        _quiet_print(f'int(lat-offset) , int(lat+offset): {lat - offset} , {lat + offset}---Mint(lon-offset) , int(lon+offset)): {lon - offset} , {lon + offset}', level='debug')
                        df = dataset[clean_var_name].sel(lat=slice(lat - offset, lat + offset), lon=slice(lon - offset, lon + offset))
                        df = df.to_dataframe()
                        df = df.dropna().reset_index()
                        _quiet_print(f'values for the variable: {df[clean_var_name].value_counts()}-- max value: {df[clean_var_name].max()}', level='debug')
                        df[subdir] = df[clean_var_name]
                        df['Variable'] = var_long_label
                        df['SSP'] = ssp
                        try:
                            df_date = df[df[[subdir]].apply(pd.to_datetime, errors='coerce').isna().all(axis=1)]
                            df_date[subdir] = df_date[subdir] / pd.to_timedelta(1, unit='D')
                            appended_data.append(df_date)
                            _quiet_print(f'Max value of days: {df_date[subdir].max()}---Mean value of days: {df_date[subdir].mean()}', level='debug')
                        except Exception:
                            pass
                            appended_data.append(df)
                    else:
                        offset >= 1e-05
                        _quiet_print(f'Not setting setting {offset}', level='debug')
                        df = dataset[clean_var_name].sel(lat=slice(lat, lat), lon=slice(lon, lon))
                        df = df.to_dataframe()
                        df = df.dropna().reset_index()
                        _quiet_print(f'values for the variable: {df[clean_var_name].value_counts()}-- max value: {df[clean_var_name].max()}', level='debug')
                        df[subdir] = df[clean_var_name]
                        df['Variable'] = var_long_label
                        df['SSP'] = ssp
                        try:
                            df_date = df[df[[subdir]].apply(pd.to_datetime, errors='coerce').isna().all(axis=1)]
                            df_date[subdir] = df_date[subdir] / pd.to_timedelta(1, unit='D')
                            appended_data.append(df_date)
                            _quiet_print(f'Max value of days: {df_date[subdir].max()}---Mean value of days: {df_date[subdir].mean()}', level='debug')
                        except Exception:
                            pass
                            appended_data.append(df)
                    _quiet_print(f'step 2', level='debug')
                    data_1 = xr.open_dataset(file_name_path)
                    offset = 1
                    _quiet_print(f'setting {offset}', level='debug')
                    _quiet_print(f'int(lat-offset) , int(lat+offset): {lat - offset} , {lat + offset}---Mint(lon-offset) , int(lon+offset)): {lon - offset} , {lon + offset}', level='debug')
                    _quiet_print(f'step 3', level='debug')
                    _quiet_print(f'data_1 {data_1}', level='debug')
                    var_data = data_1[variable_name].sel(lat=slice(lat - offset, lat + offset), lon=slice(lon - offset, lon + offset))
                    if '_FillValue' in var_data.attrs:
                        fill_value = var_data.attrs['_FillValue']
                        var_data = var_data.where(var_data != fill_value, np.nan)
                    var_data = var_data.fillna(0)
                    _quiet_print(f'step 4', level='debug')
                    monthly_sum = var_data.groupby('time.month').sum(dim='time')
                    lons = var_data['lon'].values
                    lats = var_data['lat'].values
                    if np.any(np.diff(lons) < 0):
                        lons = lons[::-1]
                        monthly_sum = monthly_sum[:, :, ::-1]
                    if np.any(np.diff(lats) < 0):
                        lats = lats[::-1]
                        monthly_sum = monthly_sum[:, ::-1, :]
                    _quiet_print(f'step 5', level='debug')
                    pixel_width = (lons.max() - lons.min()) / (len(lons) - 1)
                    pixel_height = (lats.max() - lats.min()) / (len(lats) - 1)
                    for month in range(1, 13):
                        month_data = monthly_sum.sel(month=month).values
                        month_data = np.nan_to_num(month_data, nan=0.0)
                        output_tiff = f'{rasters}/{file_name}_monthly_sum_{month:02d}_new.tif'
                        driver = gdal.GetDriverByName('GTiff')
                        out_raster = driver.Create(output_tiff, month_data.shape[1], month_data.shape[0], 1, gdal.GDT_Float32)
                        geotransform = (lons.min(), pixel_width, 0, lats.max(), 0, -pixel_height)
                        out_raster.SetGeoTransform(geotransform)
                        srs = osr.SpatialReference()
                        srs.ImportFromEPSG(4326)
                        out_raster.SetProjection(srs.ExportToWkt())
                        out_raster.FlushCache()
                        out_raster = None
                        _quiet_print(f'GeoTIFF saved as {output_tiff}', level='debug')
        appended_data = pd.concat(appended_data, axis=0, join='inner').sort_index()
        appended_data.to_csv(f'{tables}/{country}_{city}_{subdir}_panel.csv')
    return appended_data

def export_extreme_heat_cckp_graph(df, x_var_name, y_var_names, maps, section, country, city):
    """Plot extreme heat indicator time series and save the chart outputs."""
    subdir = section[0]
    df['date'] = pd.to_datetime(df[f'{x_var_name}'])
    for ssp in df['SSP'].unique():
        for y_var in df[y_var_names].unique():
            sub_df = df[(df['SSP'] == ssp) & (df[y_var_names] == y_var)]
            sub_df = sub_df.sort_values([y_var_names, 'SSP'], ascending=[True, True])
            sns.set_style('whitegrid')
            ax = sns.lineplot(data=sub_df, x='date', y=subdir, errorbar=None, hue=y_var_names, style=y_var_names, markers=True)
            ax.set_title(f'{subdir} in {city} for {ssp}', fontdict={'size': 13, 'weight': 'bold'})
            ax.set_xlabel(f'Month')
            plt.legend(frameon=False, loc='lower left', bbox_to_anchor=(0, -0.3), ncol=1)
            ax.xaxis.set_major_formatter(mdates.DateFormatter('%b'))
            ax.xaxis.set_major_locator(mdates.AutoDateLocator(interval_multiples=False))
            GREY91 = '#e8e8e8'
            ax.tick_params(axis='x', length=12, color=GREY91)
            ax.tick_params(axis='y', length=8, color=GREY91)
            sns.despine()
            ax.figure.savefig(f'{maps}/{country}_{city}_{subdir}_graph.png', bbox_inches='tight', dpi=300)
            plt.close(ax.figure)
    return sub_df
