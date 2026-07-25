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

    """SPEI, air quality, heat, and landslide processing."""

    data_folder = Path('data/SPEI')
    periods = ['01', '12', '48']
    years = range(2011, 2021)

    spei_val = dict({p: dict({c: {} for c in centroids.city}) for p in periods})
    for period in periods:
        spei_nc = xr.open_dataset(data_folder / ('spei'+period+'.nc'))
        for index, row in centroids.iterrows():
            for year in years:
                for month in range(1, 13):
                    time1 = str(year) + '-' + str(month) + '-15'
                    val = spei_nc.sel(lon = row['x'], lat = row['y'], time = time1, method = 'nearest')['spei'].to_dict()['data']
                    spei_val[period][row['city']][time1] = val
    for period in periods:
        with open('stats/spei/spei'+period+'.csv', 'w', encoding='utf-8') as f:
            f.write('city,date,spei\n')
            for city in centroids.city:
                for year in years:
                    for month in range(1, 13):
                        time1 = str(year) + '-' + str(month) + '-15'
                        f.write('%s,%s,%s\n' % (city, time1, spei_val[period][city][time1]))

    data_folder = Path(r'data\Global Annual PM2.5 Grids 1998-2019')
    def unzip_files(data_folder):
        extension = ".zip"
        os.chdir(data_folder)
        for item in os.listdir(data_folder):
            if item.endswith(extension):
                file_name = os.path.abspath(item)
                zip_ref = zipfile.ZipFile(file_name)
                zip_ref.extractall(data_folder)
                zip_ref.close()
                os.remove(file_name)

    def clipdata_air(city, year):
        city_no_space = city
        city_lower = city_no_space.lower()
        file = city / aoi_folder / (city_lower + '_AOI.shp')

        with fiona.open(file, "r") as shapefile:
            features = [feature["geometry"] for feature in shapefile]
            input_raster = f"{data_folder}/sdei-global-annual-gwr-pm2-5-modis-misr-seawifs-aod-v4-gl-03-" + str(year) + ".tif"
            with rasterio.open(input_raster) as src:
                out_image, out_transform = rasterio.mask.mask(src, features, crop=True, all_touched=True)
                out_meta = src.meta.copy()

            out_meta.update({"driver": "GTiff",
                             "height": out_image.shape[1],
                             "width": out_image.shape[2],
                             "transform": out_transform})

            output_file = city_lower + '_air_quality_' + str(year) + '.tif'
            with rasterio.open(Path(city) / output_folder / output_file, "w", **out_meta) as dest:
                dest.write(out_image)

    for city in cities:
        for year in range(1998, 2020):
            clipdata_air(city, year)

    def avg_air(city, year):
        city_nospace = city
        temp_file = city / Path('data') / (city_nospace + '_air_quality_' + str(year) + '.tif')
        with rasterio.open(temp_file) as temp:
            temp_array = temp.read(1).astype(float)
            nodata = temp.nodata
            if nodata is not None:
                temp_array[temp_array == nodata] = np.nan
            temp_array[temp_array < 0] = np.nan
            return float(np.nanmean(temp_array))

    def bad_air(city, year, threshold=5):
        city_nospace = city
        air_file = city / Path('data') / (city_nospace + '_air_quality_' + str(year) + '.tif')
        with rasterio.open(air_file) as air:
            air_array = air.read(1).astype(float)
            nodata = air.nodata
            if nodata is not None:
                valid_mask = air_array != nodata
            else:
                valid_mask = np.isfinite(air_array)
            valid_mask &= air_array >= 0
            if valid_mask.sum() == 0:
                return np.nan
            return float((air_array[valid_mask] >= threshold).sum() / valid_mask.sum())

    cities_avg_air = {}
    for city in cities:
        cities_avg_air[city] = {}
        for year in range(1998, 2020):
            cities_avg_air[city][year] = avg_air(city, year)

    cities_bad_air = {}
    for city in cities:
        cities_bad_air[city] = {}
        for year in range(1998, 2020):
            cities_bad_air[city][year] = bad_air(city, year)

    with open('stats/avg_air_1998_2019.csv', 'w', encoding='utf-8') as f:
        f.write('city,year,avg,pct_bad_air\n')
        for city in cities_avg_air.keys():
            for year in range(1998, 2020):
                f.write("%s,%s,%s,%s\n" % (
                    city,
                    year,
                    cities_avg_air[city][year],
                    cities_bad_air[city][year]
                ))

    data_folder = Path('data/Heat increase due to urban land expansion')
    shp_folder = Path('data/AOI')

    def reproj_heat(input_raster):
        filename = input_raster + '.tif'
        outfile = input_raster + '_4326.tif'
        with rasterio.open(data_folder / filename) as src:
            dst_crs = 'EPSG:4326'
            transform, width, height = calculate_default_transform(
                src.crs, dst_crs, src.width, src.height, *src.bounds)
            kwargs = src.meta.copy()
            kwargs.update({
                'crs': dst_crs,
                'transform': transform,
                'width': width,
                'height': height
            })

            with rasterio.open(data_folder / outfile, 'w', **kwargs) as dst:
                for i in range(1, src.count + 1):
                    reproject(
                        source=rasterio.band(src, i),
                        destination=rasterio.band(dst, i),
                        src_transform=src.transform,
                        src_crs=src.crs,
                        dst_transform=transform,
                        dst_crs=dst_crs,
                        resampling=Resampling.nearest)

    def clip_heat(input_raster):
        input_raster_name = input_raster + '_4326.tif'
        with rasterio.open(data_folder / input_raster_name) as src:
            out_image, out_transform = rasterio.mask.mask(
                src, features, crop=True, all_touched=True)
            out_meta = src.meta.copy()

        out_meta.update({"driver": "GTiff",
                         "height": out_image.shape[1],
                         "width": out_image.shape[2],
                         "transform": out_transform})

        out_file = city.replace(' ', '_').lower() + '_' + input_raster + '.tif'
        with rasterio.open(city / output_folder / out_file, "w", **out_meta) as dest:
            dest.write(out_image)

    raster_list = [ 'urban-ssp1_day_sum', 'urban-ssp1_nig_sum',
                   'urban-ssp2_day_sum', 'urban-ssp2_nig_sum',
                   'urban-ssp3_day_sum', 'urban-ssp3_nig_sum']
    for city in cities:
        aoi_name = city + '_AOI.shp'
        shp = gpd.read_file(city/shp_folder/aoi_name)
        features = shp.geometry
        for raster in raster_list:
            reproj_heat(raster)
            clip_heat(raster)

    def _run_landslide_block(cities):
        landslide_data_folder = Path('data/Landslide')
        landslide_input_raster = "LS_RF_Median_1980_2018_COG"

        def reproj_ls(input_folder, input_raster):
            filename = input_raster + '.tif'
            outfile = input_raster + '_4326.tif'
            with rasterio.open(input_folder / filename) as src:
                dst_crs = 'EPSG:4326'
                transform, width, height = calculate_default_transform(
                    src.crs, dst_crs, src.width, src.height, *src.bounds)
                kwargs = src.meta.copy()
                kwargs.update({
                    'crs': dst_crs,
                    'transform': transform,
                    'width': width,
                    'height': height
                })

                with rasterio.open(input_folder / outfile, 'w', **kwargs) as dst:
                    for i in range(1, src.count + 1):
                        reproject(
                            source=rasterio.band(src, i),
                            destination=rasterio.band(dst, i),
                            src_transform=src.transform,
                            src_crs=src.crs,
                            dst_transform=transform,
                            dst_crs=dst_crs,
                            resampling=Resampling.nearest)

        def clipdata_ls(city):
            city_no_space = city
            city_lower = city_no_space.lower()
            file = city / aoi_folder / (city_lower + '_AOI.shp')
            print('1')

            with fiona.open(file, "r") as shapefile:
                features = [feature["geometry"] for feature in shapefile]
                print('2')
                input_raster = landslide_data_folder / 'LS_RF_Median_1980_2018_COG_4326.tif'
                with rasterio.open(input_raster) as src:
                    out_image, out_transform = rasterio.mask.mask(
                        src, features, crop=True, all_touched=True)
                    out_meta = src.meta.copy()
                    print('3')

                out_meta.update({"driver": "GTiff",
                                 "height": out_image.shape[1],
                                 "width": out_image.shape[2],
                                 "transform": out_transform,
                                 'nodata': 0})

                print('4')
                if np.nansum(out_image) != 0:
                    output_file = city_lower + '_landslide.tif'
                    print('5')
                    with rasterio.open(Path(city) / output_folder / output_file, "w", **out_meta) as dest:
                        dest.write(out_image)
                        print(f'Wrote {output_file}')

        reproj_ls(landslide_data_folder, landslide_input_raster)
        for city in cities:
            clipdata_ls(city)

    _run_landslide_block(cities)

    def landslide(city):
        city_nospace = city
        ls_file = city / Path('data') / (city_nospace + '_landslide.tif')
        with rasterio.open(ls_file) as ls:
            ls_array = ls.read(1).astype(float)
            nodata = ls.nodata
            if nodata is not None:
                ls_array[ls_array == nodata] = np.nan
            return float(np.nanmean(ls_array))

    cities_ls = {}
    for city in cities:
        try:
            landslide_value = landslide(city)
            cities_ls[city] = landslide_value
        except Exception as e:
            print(f"Skipped {city}- {e}")
            pass

    with open('stats/landslide_avg.csv', 'w', encoding='utf-8') as f:
        f.write('city,avg\n')
        for city in cities_ls.keys():
            f.write("%s,%s\n" % (city, cities_ls[city]))

    # --- cell ---
