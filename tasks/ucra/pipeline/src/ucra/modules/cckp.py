
from __future__ import annotations

from pathlib import Path
from ucra.context import PipelineContext


def run(ctx: PipelineContext) -> None:
    import math
    import os
    import shutil
    import zipfile
    from functools import reduce
    from os.path import exists
    from pathlib import Path
    from shutil import copyfile

    import contextily as cx
    import ee
    import fiona
    import geopandas as gpd
    import matplotlib.pyplot as plt
    import numpy as np
    import osmnx as ox
    import pandas as pd
    import plotly.express as px
    import rasterio
    import rasterio.mask
    import requests
    import xarray as xr
    from matplotlib.lines import Line2D
    from rasterio.features import shapes
    from rasterio.merge import merge
    from rasterio.warp import Resampling, calculate_default_transform, reproject
    from shapely.geometry import MultiPolygon, Polygon

    project_dir = ctx.project_dir
    country = ctx.country
    crp_dir = ctx.crp_dir
    aoi_folder = ctx.aoi_folder
    output_folder = ctx.output_folder
    cities = ctx.cities
    centroids = ctx.centroids
    epsg_dict = ctx.epsg_dict

    """CCKP climate statistics processing."""

    data_folder = Path('data/CCKP')
    # Keep a dedicated intermediate/output folder for CCKP side products.
    int_output_folder = Path('output/CCKP')
    int_output_folder.mkdir(parents=True, exist_ok=True)

    # --- cell ---

    # ssps = ['245', '370'] # Gabon SSP2-4.5 and SSP3-7.0, 
    # ssps = ['245', '585'] #For Bangladesh cluster analysis
    # ssps = ['119','245', '370'] # Bhutan under SSP1-1.9, SSP2-4.5 and SSP3-7.0,  , 
    # ssps = ['119','245', '370','585'] # Burundi under SSP1-1.9, SSP2-4.5 and SSP3-7.0, '585' , 
    ssps = ['119','245', '370'] # Zambia under SSP1-1.9, SSP2-4.5 and SSP3-7.0
    periods = ['2040-2059']
    varias0 = ['tas', 'txx', 'pr', 'r95ptot', 'cdd']
    varias1 = ['hd35', 'tr26', 'wsdi', 'r20mm', 'r50mm']
    varias = varias0 + varias1
    rps = ['20yr', '50yr']

    # --- cell ---

    abs_val = dict({s: dict({p: dict({v: {} for v in varias + ['spei12']}) for p in periods}) for s in ssps})
    ano_val = dict({s: dict({p: dict({v: {} for v in varias}) for p in periods}) for s in ssps})

    # --- cell ---

    # processing for variables without timedelta
    for ssp in ssps:
        for period in periods:
            for varia in varias0:
                clim = xr.open_dataset(data_folder / ('climatology-'+varia+'-annual-mean_cmip6_annual_all-regridded-bct-ssp'+ssp+'-climatology_median_'+period+'.nc'))
                anom = xr.open_dataset(data_folder / ('anomaly-'+varia+'-annual-mean_cmip6_annual_all-regridded-bct-ssp'+ssp+'-climatology_median_'+period+'.nc'))

                for index, row in centroids.iterrows():
                    x_coords = [row['x']-1, row['x'], row['x']+1]
                    y_coords = [row['y']-1, row['y'], row['y']+1]
                    clim_val_coords = []
                    clim_val_vals = []
                    anom_val_coords = []
                    anom_val_vals = []

                    for x in x_coords:
                        for y in y_coords:
                            clim_val_df = clim.sel(lon=x, lat=y, method='nearest').to_dataframe().reset_index()
                            anom_val_df = anom.sel(lon=x, lat=y, method='nearest').to_dataframe().reset_index()

                            clim_lon = clim_val_df['lon'].iloc[0]
                            clim_lat = clim_val_df['lat'].iloc[0]
                            anom_lon = anom_val_df['lon'].iloc[0]
                            anom_lat = anom_val_df['lat'].iloc[0]

                            if (clim_lon, clim_lat) not in clim_val_coords:
                                clim_val_coords.append((clim_lon, clim_lat))
                                clim_val_vals.append(clim_val_df['climatology-'+varia+'-annual-mean'].mean())
                            if (anom_lon, anom_lat) not in anom_val_coords:
                                anom_val_coords.append((anom_lon, anom_lat))
                                anom_val_vals.append(anom_val_df['anomaly-'+varia+'-annual-mean'].mean())

                    clim_val = np.nanmean(clim_val_vals)
                    anom_val = np.nanmean(anom_val_vals)

                    abs_val[ssp][period][varia][row['city']] = clim_val
                    ano_val[ssp][period][varia][row['city']] = anom_val

    # --- cell ---

    # processing for variables with timedelta
    for ssp in ssps:
        for period in periods:
            for varia in varias1:
                clim = xr.open_dataset(data_folder / ('climatology-'+varia+'-annual-mean_cmip6_annual_all-regridded-bct-ssp'+ssp+'-climatology_median_'+period+'.nc'))
                anom = xr.open_dataset(data_folder / ('anomaly-'+varia+'-annual-mean_cmip6_annual_all-regridded-bct-ssp'+ssp+'-climatology_median_'+period+'.nc'))

                for index, row in centroids.iterrows():
                    x_coords = [row['x']-1, row['x'], row['x']+1]
                    y_coords = [row['y']-1, row['y'], row['y']+1]
                    clim_val_coords = []
                    clim_val_vals = []
                    anom_val_coords = []
                    anom_val_vals = []

                    for x in x_coords:
                        for y in y_coords:
                            clim_val_df = clim.sel(lon=x, lat=y, method='nearest').to_dataframe().reset_index()
                            anom_val_df = anom.sel(lon=x, lat=y, method='nearest').to_dataframe().reset_index()

                            clim_lon = clim_val_df['lon'].iloc[0]
                            clim_lat = clim_val_df['lat'].iloc[0]
                            anom_lon = anom_val_df['lon'].iloc[0]
                            anom_lat = anom_val_df['lat'].iloc[0]

                            if (clim_lon, clim_lat) not in clim_val_coords:
                                clim_val_coords.append((clim_lon, clim_lat))
                                clim_val_vals.append(np.timedelta64(clim_val_df['climatology-'+varia+'-annual-mean'].mean()).astype('timedelta64[D]') / np.timedelta64(1, 'D'))
                            if (anom_lon, anom_lat) not in anom_val_coords:
                                anom_val_coords.append((anom_lon, anom_lat))
                                anom_val_vals.append(np.timedelta64(anom_val_df['anomaly-'+varia+'-annual-mean'].mean()).astype('timedelta64[D]') / np.timedelta64(1, 'D'))

                    clim_val = np.nanmean(clim_val_vals)
                    anom_val = np.nanmean(anom_val_vals)

                    abs_val[ssp][period][varia][row['city']] = clim_val
                    ano_val[ssp][period][varia][row['city']] = anom_val

    # --- cell ---

    # processing for spei12
    varia = 'spei12'
    for ssp in ssps:
        for period in periods:
            clim = xr.open_dataset(data_folder / ('climatology-'+varia+'-annual-mean_cmip6_annual_all-regridded-bct-ssp'+ssp+'-climatology_median_'+period+'.nc'))

            for index, row in centroids.iterrows():
                    x_coords = [row['x']-1, row['x'], row['x']+1]
                    y_coords = [row['y']-1, row['y'], row['y']+1]
                    clim_val_coords = []
                    clim_val_vals = []

                    for x in x_coords:
                        for y in y_coords:
                            clim_val_df = clim.sel(lon=x, lat=y, method='nearest').to_dataframe().reset_index()
                            clim_lon = clim_val_df['lon'].iloc[0]
                            clim_lat = clim_val_df['lat'].iloc[0]

                            if (clim_lon, clim_lat) not in clim_val_coords:
                                clim_val_coords.append((clim_lon, clim_lat))
                                clim_val_vals.append(clim_val_df['climatology-'+varia+'-annual-mean'].mean())

                    clim_val = np.nanmean(clim_val_vals)
                    abs_val[ssp][period][varia][row['city']] = clim_val

    # --- cell ---

    # write to csv
    for ssp in ssps:
        for varia in varias + ['spei12']:
            with open('stats/CCKP/clim_'+varia+'_ssp'+ssp+'.csv', 'w') as f:
                f.write('city,'+periods[0]+'\n')
                for city in centroids.city:
                    f.write("%s,%s\n"%(city, abs_val[ssp][periods[0]][varia][city]))
            if varia != 'spei12':
                with open('stats/CCKP/anom_'+varia+'_ssp'+ssp+'.csv', 'w') as f:
                    f.write('city,'+periods[0]+'\n')
                    for city in centroids.city:
                        f.write("%s,%s\n"%(city, ano_val[ssp][periods[0]][varia][city]))

    # --- cell ---

    aep_val = dict({s: dict({r: {} for r in rps}) for s in ssps})
    # processing for future return period change factor
    for ssp in ssps:
        for period in ['2035-2064']:
            for rp in rps:
                aep = xr.open_dataset(data_folder / ('changefactorfaep'+rp+'-rx5day-period-mean_cmip6_period_all-regridded-bct-ssp'+ssp+'-climatology_median_'+period+'.nc'))

                for index, row in centroids.iterrows():
                    x_coords = [row['x']-1, row['x'], row['x']+1]
                    y_coords = [row['y']-1, row['y'], row['y']+1]
                    aep_val_coords = []
                    aep_val_vals = []

                    for x in x_coords:
                        for y in y_coords:
                            aep_val_df = aep.sel(lon=x, lat=y, method='nearest').to_dataframe().reset_index()
                            aep_lon = aep_val_df['lon'].iloc[0]
                            aep_lat = aep_val_df['lat'].iloc[0]

                            if (aep_lon, aep_lat) not in aep_val_coords:
                                aep_val_coords.append((aep_lon, aep_lat))
                                aep_val_vals.append(aep_val_df['changefactorfaep'+rp+'-rx5day-period-mean'].mean())

                    aep_val1 = np.nanmean(aep_val_vals)

                    aep_val[ssp][rp][row['city']] = aep_val1

    # --- cell ---

    # write to csv
    for ssp in ssps:
        for rp in rps:
            with open('stats/CCKP/aep_'+rp+'_ssp'+ssp+'.csv', 'w') as f:
                f.write('city,'+'2035-2064'+'\n')
                for city in centroids.city:
                    f.write("%s,%s\n"%(city, aep_val[ssp][rp][city]))

    # --- cell ---

    # Raw data folder. Change file path as needed
