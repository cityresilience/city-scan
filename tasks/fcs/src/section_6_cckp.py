"""CCKP NetCDF extraction and plotting functions for climate indicator time series."""
import xarray as xr
import os
import pandas as pd
import geopandas as gpd
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import seaborn as sns
import logging
LOGGER = logging.getLogger('city_pipeline')

def _quiet_print(*args, level: str='debug') -> None:
    """Route legacy print-style messages through the pipeline logger."""
    message = ' '.join((str(arg) for arg in args))
    getattr(LOGGER, level, LOGGER.debug)(message)

def _get_selection_point(vector_file):
    """Return a stable AOI point in WGS84 for gridded climate extraction."""
    aoi_projected = vector_file.to_crs(epsg=3857)
    centroid_projected = aoi_projected.geometry.unary_union.centroid
    centroid_wgs84 = gpd.GeoSeries([centroid_projected], crs=3857).to_crs(epsg=4326).iloc[0]
    return (float(centroid_wgs84.y), float(centroid_wgs84.x))

def export_cckp_data(vector_file, section, data, tables, country, city):
    """Extract CCKP NetCDF values for the study city and export a tidy panel table."""
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
                    ssp = file_name.split('-')[-3].upper()
                    dataset = xr.open_dataset(file_name_path)
                    clean_var_name = variable_name.replace('-', '_')
                    clean_var_name = clean_var_name.replace(':', '')
                    dataset = dataset.rename(name_dict={f'{variable_name}': f'{clean_var_name}'})
                    var_long_label = dataset.variables[clean_var_name].attrs['long_name'].capitalize()
                    var_long_label = var_long_label.replace(':', '')
                    lat, lon = _get_selection_point(vector_file)
                    df = dataset[clean_var_name].sel(lat=lat, lon=lon, method='nearest')
                    df = df.to_dataframe()
                    df = df.dropna().reset_index()
                    df[subdir] = df[clean_var_name]
                    df['Variable'] = var_long_label
                    df['SSP'] = ssp
                    try:
                        df_date = df[df[[subdir]].apply(pd.to_datetime, errors='coerce').isna().all(axis=1)]
                        df_date[subdir] = df_date[subdir] / pd.to_timedelta(1, unit='D')
                        appended_data.append(df_date)
                    except Exception:
                        pass
                        appended_data.append(df)
        appended_data = pd.concat(appended_data, axis=0, join='inner').sort_index()
        appended_data.to_csv(f'{tables}/{country}_{city}_{subdir}_panel.csv')
    return appended_data

def export_cckp_graph(df, x_var_name, y_var_names, section, maps, country, city):
    """Plot CCKP indicator time series and save the chart outputs."""
    subdir = section[0]
    df['date'] = pd.to_datetime(df[f'{x_var_name}'])
    for ssp in df['SSP'].unique():
        for y_var in df[y_var_names].unique():
            sub_df = df[(df['SSP'] == ssp) & (df[y_var_names] == y_var)]
            sub_df = sub_df.sort_values([y_var_names, 'SSP'], ascending=[True, True])
            sns.set_style('whitegrid')
            ax = sns.lineplot(data=sub_df, x=x_var_name, y=subdir, errorbar=None, hue=y_var_names, style=y_var_names, markers=True)
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
    return df
