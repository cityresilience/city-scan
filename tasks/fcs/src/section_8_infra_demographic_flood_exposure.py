"""Flood exposure processing functions for population, infrastructure, and Fathom raster preparation."""
import os
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import seaborn as sns
from osgeo import gdal, osr
import rasterio
from os.path import exists
import math
from pathlib import Path
from rasterio.merge import merge
from rasterio.warp import calculate_default_transform, reproject, Resampling
from rasterio import shutil as rio_shutil
from shutil import copyfile
import shutil
import yaml
from osgeo import gdal, ogr, osr
from osgeo_utils import gdal_calc
import os
import numpy as np
import pandas as pd
from rasterio.vrt import WarpedVRT
from osgeo import ogr, gdal
from osgeo_utils import gdal_calc
import rasterio
import numpy as np
import os
import osmnx as ox
import geopandas as gpd
import logging
LOGGER = logging.getLogger('city_pipeline')

def _load_pipeline_config() -> dict:
    """Load the active pipeline YAML configuration used by the runner."""
    config_candidates = []
    env_path = os.environ.get('FCS_CONFIG_PATH')
    if env_path:
        config_candidates.append(Path(env_path))
    config_candidates.extend([Path('fcs_menue.yaml'), Path('configs.yml')])
    for config_path in config_candidates:
        if config_path.exists():
            with config_path.open('r', encoding='utf-8') as handle:
                return yaml.safe_load(handle)
    raise FileNotFoundError('Could not locate a pipeline config file. Set FCS_CONFIG_PATH or provide fcs_menue.yaml.')


def _quiet_print(*args, level: str='debug') -> None:
    """Route legacy print-style messages through the pipeline logger."""
    message = ' '.join((str(arg) for arg in args))
    getattr(LOGGER, level, LOGGER.debug)(message)

def create_dir(directory):
    """Create a directory if it does not already exist and return its path."""
    if not os.path.exists(directory):
        os.makedirs(directory)
    return directory

def preprocess_fathom(output, city, aoi_file, country):
    """Prepare, mosaic, threshold, and reproject Fathom flood rasters needed for exposure analysis."""
    data_folder = Path('data/fathom') / country
    city_name_l = city.replace(' ', '_').lower()
    city_name_l = city_name_l.lower()
    configs = _load_pipeline_config()
    flood_cfg = configs.get('flood', {})
    run_flood_coastal = bool(configs.get('flood_coastal', flood_cfg.get('coastal', True)))
    run_flood_fluvial = bool(configs.get('flood_fluvial', flood_cfg.get('fluvial', True)))
    run_flood_pluvial = bool(configs.get('flood_pluvial', flood_cfg.get('pluvial', True)))
    _quiet_print('read AOI shapefile', level='debug')
    features = aoi_file.geometry
    aoi_bounds = aoi_file.bounds
    output_path = Path(output)
    create_dir(output_path)
    flood_folder = Path(output_path) / 'flood'
    create_dir(flood_folder)
    output_folder = Path(output_path) / 'fathom_clean'
    create_dir(output_folder)

    def tile_finder(direction, tile_size=1):
        """Build the list of raster tile identifiers that overlap the area of interest."""
        coord_list = []
        if direction == 'lat':
            hemi_options = ['N', 'S']
            coord_min = aoi_bounds.miny
            coord_max = aoi_bounds.maxy
            zfill_digits = 2
        elif direction == 'lon':
            hemi_options = ['E', 'W']
            coord_min = aoi_bounds.minx
            coord_max = aoi_bounds.maxx
            zfill_digits = 3
        else:
            _quiet_print('tile_finder function error', level='warning')
            _quiet_print('Invalid direction. How did this happen?', level='warning')
        for i in range(len(aoi_bounds)):
            if math.floor(coord_min[i]) >= 0:
                hemi = hemi_options[0]
                for y in range(math.floor(coord_min[i] / tile_size) * tile_size, math.ceil(coord_max[i] / tile_size) * tile_size, tile_size):
                    coord_list.append(f'{hemi}{str(y).zfill(zfill_digits)}')
            elif math.ceil(coord_max[i]) >= 0:
                for y in range(0, math.ceil(coord_max[i] / tile_size) * tile_size, tile_size):
                    coord_list.append(f'{hemi_options[0]}{str(y).zfill(zfill_digits)}')
                for y in range(math.floor(coord_min[i] / tile_size) * tile_size, 0, tile_size):
                    coord_list.append(f'{hemi_options[1]}{str(-y).zfill(zfill_digits)}')
            else:
                hemi = hemi_options[1]
                for y in range(math.floor(coord_min[i] / tile_size) * tile_size, math.ceil(coord_max[i] / tile_size) * tile_size, tile_size):
                    coord_list.append(f'{hemi}{str(-y).zfill(zfill_digits)}')
        return coord_list
    failed = []
    rps = configs['flood']['rps']
    lat_tiles = tile_finder('lat')
    lon_tiles = tile_finder('lon')
    flood_threshold = configs['flood']['threshold']
    flood_years = configs['flood']['year']
    flood_ssps = configs['flood']['ssp']
    flood_ssp_labels = {1: '1_2.6', 2: '2_4.5', 3: '3_7.0', 5: '5_8.5'}
    flood_prob_cutoff = configs['flood']['prob_cutoff']
    if not len(flood_prob_cutoff) == 2:
        err_msg = '2 cutoffs required for flood'
        _quiet_print(err_msg, level='debug')
        failed.append(err_msg)
    else:
        flood_rp_bins = {f'lt{flood_prob_cutoff[0]}': [], f'{flood_prob_cutoff[0]}-{flood_prob_cutoff[1]}': [], f'gt{flood_prob_cutoff[1]}': []}
        for rp in rps:
            annual_prob = 1 / rp * 100
            if annual_prob < flood_prob_cutoff[0]:
                flood_rp_bins[f'lt{flood_prob_cutoff[0]}'].append(rp)
            elif annual_prob >= flood_prob_cutoff[0] and annual_prob <= flood_prob_cutoff[1]:
                flood_rp_bins[f'{flood_prob_cutoff[0]}-{flood_prob_cutoff[1]}'].append(rp)
            elif annual_prob > flood_prob_cutoff[1]:
                flood_rp_bins[f'gt{flood_prob_cutoff[1]}'].append(rp)
    if run_flood_coastal or run_flood_fluvial or run_flood_pluvial:
        _quiet_print('prepare flood', level='debug')
        rps = configs['flood']['rps']
        lat_tiles = tile_finder('lat')
        lon_tiles = tile_finder('lon')
        flood_threshold = configs['flood']['threshold']
        flood_years = configs['flood']['year']
        flood_ssps = configs['flood']['ssp']
        flood_ssp_labels = {1: '1_2.6', 2: '2_4.5', 3: '3_7.0', 5: '5_8.5'}
        flood_prob_cutoff = configs['flood']['prob_cutoff']
        if not len(flood_prob_cutoff) == 2:
            err_msg = '2 cutoffs required for flood'
            _quiet_print(err_msg, level='debug')
            failed.append(err_msg)
        else:
            flood_rp_bins = {f'lt{flood_prob_cutoff[0]}': [], f'{flood_prob_cutoff[0]}-{flood_prob_cutoff[1]}': [], f'gt{flood_prob_cutoff[1]}': []}
            for rp in rps:
                annual_prob = 1 / rp * 100
                if annual_prob < flood_prob_cutoff[0]:
                    flood_rp_bins[f'lt{flood_prob_cutoff[0]}'].append(rp)
                elif annual_prob >= flood_prob_cutoff[0] and annual_prob <= flood_prob_cutoff[1]:
                    flood_rp_bins[f'{flood_prob_cutoff[0]}-{flood_prob_cutoff[1]}'].append(rp)
                elif annual_prob > flood_prob_cutoff[1]:
                    flood_rp_bins[f'gt{flood_prob_cutoff[1]}'].append(rp)

            def flood_raster_check(raster):
                """Check whether a prepared flood raster contains only binary values."""
                with rasterio.open(raster) as src:
                    return np.nanmax(src.read(1)) > 1

            def mosaic_flood_tiles_and_threshold(flood_type):
                """Mosaic raw flood tiles, apply the flood threshold, and save the prepared raster set."""
                _quiet_print(f'prepare {flood_type} flood', level='debug')
                flood_type_folder_dict = {'coastal': 'COASTAL_DEFENDED', 'fluvial': 'FLUVIAL_UNDEFENDED', 'pluvial': 'PLUVIAL_DEFENDED'}
                raw_flood_folder = Path(configs['flood_source']) / f'{country}' / flood_type_folder_dict[flood_type]
                for year in flood_years:
                    if year <= 2020:
                        for rp in rps:
                            raster_to_mosaic = []
                            mosaic_file = f'{city_name_l}_{flood_type}_{year}_1in{rp}.tif'
                            if not exists(flood_folder / mosaic_file):
                                for lat in lat_tiles:
                                    for lon in lon_tiles:
                                        raster_file_name = f"{year}/1in{rp}/1in{rp}-{flood_type_folder_dict[flood_type].replace('_', '-')}-{year}_{lat.lower()}{lon.lower()}.tif"
                                        if exists(raw_flood_folder / raster_file_name):
                                            raster_to_mosaic.append(raw_flood_folder / raster_file_name)
                                if len(raster_to_mosaic) == 0:
                                    _quiet_print(f'no raster for {flood_type} {year} 1-in-{rp}', level='warning')
                                elif len(raster_to_mosaic) == 1:
                                    copyfile(raster_to_mosaic[0], flood_folder / mosaic_file)
                                else:
                                    try:
                                        raster_to_mosaic1 = []
                                        for p in raster_to_mosaic:
                                            raster = rasterio.open(p)
                                            raster_to_mosaic1.append(raster)
                                        mosaic, output = merge(raster_to_mosaic1)
                                        output_meta = raster.meta.copy()
                                        output_meta.update({'driver': 'GTiff', 'height': mosaic.shape[1], 'width': mosaic.shape[2], 'transform': output})
                                        with rasterio.open(flood_folder / mosaic_file, 'w', **output_meta) as m:
                                            m.write(mosaic)
                                    except MemoryError:
                                        err_msg = f'MemoryError when merging flood_{flood_type} {year} 1-in-{rp} raster files.'
                                        _quiet_print(err_msg, level='debug')
                                        _quiet_print('Try GIS instead for merging.', level='debug')
                                        failed.append(err_msg)
                            if exists(flood_folder / mosaic_file):

                                def flood_con():
                                    """Apply the flood threshold to the current raster and write the binary output raster."""
                                    with rasterio.open(flood_folder / mosaic_file) as src:
                                        out_image = src.read(1)
                                        out_image[out_image == src.meta['nodata']] = 0
                                        out_image[out_image < flood_threshold] = 0
                                        out_image[out_image >= flood_threshold] = 1
                                        out_meta = src.meta.copy()
                                        out_meta.update({'nodata': 0})
                                    with rasterio.open(flood_folder / f'{mosaic_file[:-4]}_con.tif', 'w', **out_meta) as dest:
                                        dest.write(out_image, 1)
                                flood_con()
                                while flood_raster_check(flood_folder / f'{mosaic_file[:-4]}_con.tif'):
                                    flood_con()
                    elif year > 2020:
                        for ssp in flood_ssps:
                            for rp in rps:
                                raster_to_mosaic = []
                                mosaic_file = f'{city_name_l}_{flood_type}_{year}_ssp{ssp}_1in{rp}.tif'
                                if not exists(flood_folder / mosaic_file):
                                    for lat in lat_tiles:
                                        for lon in lon_tiles:
                                            raster_file_name = f"{year}/SSP{flood_ssp_labels[ssp]}/1in{rp}/1in{rp}-{flood_type_folder_dict[flood_type].replace('_', '-')}-{year}-SSP{flood_ssp_labels[ssp]}_{lat.lower()}{lon.lower()}.tif"
                                            if exists(raw_flood_folder / raster_file_name):
                                                raster_to_mosaic.append(raw_flood_folder / raster_file_name)
                                    if len(raster_to_mosaic) == 0:
                                        _quiet_print(f'no raster for {flood_type} {year} ssp{ssp} 1-in-{rp}', level='warning')
                                    elif len(raster_to_mosaic) == 1:
                                        copyfile(raster_to_mosaic[0], flood_folder / mosaic_file)
                                    else:
                                        try:
                                            raster_to_mosaic1 = []
                                            for p in raster_to_mosaic:
                                                raster = rasterio.open(p)
                                                raster_to_mosaic1.append(raster)
                                            mosaic, output = merge(raster_to_mosaic1)
                                            output_meta = raster.meta.copy()
                                            output_meta.update({'driver': 'GTiff', 'height': mosaic.shape[1], 'width': mosaic.shape[2], 'transform': output})
                                            with rasterio.open(flood_folder / mosaic_file, 'w', **output_meta) as m:
                                                m.write(mosaic)
                                        except MemoryError:
                                            err_msg = f'MemoryError when merging flood_{flood_type} {year} ssp{ssp} 1-in-{rp} raster files.'
                                            _quiet_print(err_msg, level='debug')
                                            _quiet_print('Try GIS instead for merging.', level='debug')
                                            failed.append(err_msg)
                                if exists(flood_folder / mosaic_file):

                                    def flood_con():
                                        """Apply the flood threshold to the current raster and write the binary output raster."""
                                        with rasterio.open(flood_folder / mosaic_file) as src:
                                            out_image = src.read(1)
                                            out_image[out_image == src.meta['nodata']] = 0
                                            out_image[out_image < flood_threshold] = 0
                                            out_image[out_image >= flood_threshold] = 1
                                            if np.nanmax(out_image) > 1:
                                                _quiet_print(mosaic_file, level='debug')
                                                _quiet_print('max value: ', np.nanmax(out_image), level='debug')
                                                exit()
                                            out_meta = src.meta.copy()
                                            out_meta.update({'nodata': 0})
                                        with rasterio.open(flood_folder / f'{mosaic_file[:-4]}_con.tif', 'w', **out_meta) as dest:
                                            dest.write(out_image, 1)
                                    flood_con()
                                    while flood_raster_check(flood_folder / f'{mosaic_file[:-4]}_con.tif'):
                                        flood_con()
            for ft in ['coastal', 'fluvial', 'pluvial']:
                if {'coastal': run_flood_coastal, 'fluvial': run_flood_fluvial, 'pluvial': run_flood_pluvial}[ft]:
                    mosaic_flood_tiles_and_threshold(ft)
    _quiet_print('Fathom mosaiced', level='debug')
    if run_flood_coastal or run_flood_fluvial or run_flood_pluvial:
        features = aoi_file.geometry
        avg_lng = features.unary_union.centroid.x
        utm_zone = math.floor((avg_lng + 180) / 6) + 1
        utm_crs = f'+proj=utm +zone={utm_zone} +ellps=WGS84 +datum=WGS84 +units=m +no_defs'
        aoi_projected = aoi_file.to_crs(utm_crs)
        projected_bounds = aoi_projected.total_bounds
        buffer_distance = float(max(projected_bounds[2] - projected_bounds[0], projected_bounds[3] - projected_bounds[1]))
        buffer_aoi = aoi_projected.buffer(buffer_distance).to_crs(aoi_file.crs).geometry

        def reproject_flood_and_bin(flood_type):
            """Clip, merge, bin, and reproject prepared flood rasters for the requested flood type."""
            for year in flood_years:
                if year <= 2020:
                    for bin in flood_rp_bins:
                        raster_to_merge = [f'{city_name_l}_{flood_type}_{year}_1in{rp}_con.tif' for rp in flood_rp_bins[bin] if exists(flood_folder / f'{city_name_l}_{flood_type}_{year}_1in{rp}_con.tif')]
                        raster_arrays = []
                        for r in raster_to_merge:
                            with rasterio.open(flood_folder / r) as src:
                                out_image, out_transform = rasterio.mask.mask(src, buffer_aoi, all_touched=True, crop=True)
                                out_meta = src.meta.copy()
                            out_meta.update({'driver': 'GTiff', 'height': out_image.shape[1], 'width': out_image.shape[2], 'transform': out_transform})
                            raster_arrays.append(out_image)
                        if raster_arrays:
                            out_image = np.logical_or.reduce(raster_arrays).astype(np.uint8)
                            out_meta.update(dtype=rasterio.uint8)
                            with rasterio.open(output_folder / f'{city_name_l}_{flood_type}_{year}_{bin}.tif', 'w', **out_meta) as dst:
                                dst.write(out_image)
                            with rasterio.open(output_folder / f'{city_name_l}_{flood_type}_{year}_{bin}.tif') as src:
                                transform, width, height = calculate_default_transform(src.crs, utm_crs, src.width, src.height, *src.bounds)
                                kwargs = src.meta.copy()
                                kwargs.update({'crs': utm_crs, 'transform': transform, 'width': width, 'height': height})
                                with rasterio.open(output_folder / f'{city_name_l}_{flood_type}_{year}_{bin}_utm.tif', 'w', **kwargs) as dst:
                                    for i in range(1, src.count + 1):
                                        reproject(source=rasterio.band(src, i), destination=rasterio.band(dst, i), src_transform=src.transform, src_crs=src.crs, dst_transform=transform, dst_crs=utm_crs, resampling=Resampling.nearest)
                elif year > 2020:
                    for ssp in flood_ssps:
                        for bin in flood_rp_bins:
                            raster_to_merge = [f'{city_name_l}_{flood_type}_{year}_ssp{ssp}_1in{rp}_con.tif' for rp in flood_rp_bins[bin] if exists(flood_folder / f'{city_name_l}_{flood_type}_{year}_ssp{ssp}_1in{rp}_con.tif')]
                            raster_arrays = []
                            for r in raster_to_merge:
                                with rasterio.open(flood_folder / r) as src:
                                    out_image, out_transform = rasterio.mask.mask(src, buffer_aoi, all_touched=True, crop=True)
                                    out_meta = src.meta.copy()
                                out_meta.update({'driver': 'GTiff', 'height': out_image.shape[1], 'width': out_image.shape[2], 'transform': out_transform})
                                raster_arrays.append(out_image)
                            if raster_arrays:
                                out_image = np.logical_or.reduce(raster_arrays).astype(np.uint8)
                                out_meta.update(dtype=rasterio.uint8)
                                with rasterio.open(output_folder / f'{city_name_l}_{flood_type}_{year}_ssp{ssp}_{bin}.tif', 'w', **out_meta) as dst:
                                    dst.write(out_image)
                                with rasterio.open(output_folder / f'{city_name_l}_{flood_type}_{year}_ssp{ssp}_{bin}.tif') as src:
                                    transform, width, height = calculate_default_transform(src.crs, utm_crs, src.width, src.height, *src.bounds)
                                    kwargs = src.meta.copy()
                                    kwargs.update({'crs': utm_crs, 'transform': transform, 'width': width, 'height': height})
                                    with rasterio.open(output_folder / f'{city_name_l}_{flood_type}_{year}_ssp{ssp}_{bin}_utm.tif', 'w', **kwargs) as dst:
                                        for i in range(1, src.count + 1):
                                            reproject(source=rasterio.band(src, i), destination=rasterio.band(dst, i), src_transform=src.transform, src_crs=src.crs, dst_transform=transform, dst_crs=utm_crs, resampling=Resampling.nearest)
        for ft in ['coastal', 'fluvial', 'pluvial']:
            if {'coastal': run_flood_coastal, 'fluvial': run_flood_fluvial, 'pluvial': run_flood_pluvial}[ft]:
                reproject_flood_and_bin(ft)
        _quiet_print(f'Fathom processing finished success fully for {city}', level='debug')

def gdal_resample(input_raster, target_pop_raster, ouput_path):
    """
        Warp a raster to an inputted resolution.
        
        Args:
            xres (int): output resolution in x-direction
            yres (int): output resolution in y-direction
            ouput_path (str): filepath to where the output file should be stored

        Returns:  Ouputs a raster file inputted resolution.

        """
    ds = gdal.Open(target_pop_raster)
    gt = ds.GetGeoTransform()
    xsize = gt[1]
    ysize = -gt[-1]
    Projection = ds.GetProjectionRef()
    _quiet_print(f'Projection--{Projection}', level='debug')
    ds = None
    inDs = gdal.Open(input_raster)
    props = inDs.GetGeoTransform()
    options = gdal.WarpOptions(options=['tr'], xRes=xsize, yRes=ysize, targetAlignedPixels=True, resampleAlg=gdal.GRA_Sum, dstSRS=Projection)
    newfile = gdal.Warp(ouput_path, inDs, options=options, overwrite=True, callback=lambda *args, **kwargs: 1)
    newprops = newfile.GetGeoTransform()
    _quiet_print(f'Original sum: {inDs.GetRasterBand(1).Checksum()}, Warped sum::{newfile.GetRasterBand(1).Checksum()}', level='debug')
    return ouput_path

def replace_nodata_and_negatives_with_0(file, outfile):
    """This function replaces nodata and negatives with zeros

    Parameters
    -------------
    file: str 
        A filename 
    outfile: str 
        outfile filename        

    Returns
    ----------
    The clean filename
    
    """
    ds = gdal.Open(file)
    band = ds.GetRasterBand(1)
    arr = band.ReadAsArray()
    [rows, cols] = arr.shape
    arr_min = arr.min()
    arr_max = arr.max()
    arr_mean = int(arr.mean())
    _quiet_print(f'Pre-proccessed: arr_min:{arr_min}  arr_max:{arr_max}  arr_mean:{arr_mean} ', level='debug')
    arr_out = np.where(arr < 0, 0, arr)
    driver = gdal.GetDriverByName('GTiff')
    outdata = driver.Create(outfile, cols, rows, 1, gdal.GDT_UInt16)
    outdata.SetGeoTransform(ds.GetGeoTransform())
    outdata.SetProjection(ds.GetProjection())
    outdata.GetRasterBand(1).WriteArray(arr_out)
    outdata.GetRasterBand(1).SetNoDataValue(0)
    outdata.FlushCache()
    outdata = None
    band = None
    ds = None
    _quiet_print(f'Post-proccessed: arr_min:{arr_out.min()}  arr_max:{arr_out.max()}  arr_mean:{arr_out.mean()} ', level='debug')
    return outfile

def binarize_flood_mosaic(file, outfile, flood_threshold):
    """
    This function burns values 1 for all non-zero values

    Parameters
    -------------
    file: str 
        A filename 
    outfile: str 
        outfile filename        

    Returns
    ----------
    The clean filename
    
    """
    ds = gdal.Open(file)
    band = ds.GetRasterBand(1)
    arr = band.ReadAsArray()
    [rows, cols] = arr.shape
    arr_min = arr.min()
    arr_max = arr.max()
    arr_mean = int(arr.mean())
    _quiet_print(f'Pre-proccessed: arr_min:{arr_min}  arr_max:{arr_max}  arr_mean:{arr_mean} ', level='debug')
    arr_out = arr
    arr_out[arr_out < flood_threshold] = 0
    arr_out[arr_out >= flood_threshold] = 1
    driver = gdal.GetDriverByName('GTiff')
    outdata = driver.Create(outfile, cols, rows, 1, gdal.GDT_UInt16)
    outdata.SetGeoTransform(ds.GetGeoTransform())
    outdata.SetProjection(ds.GetProjection())
    outdata.GetRasterBand(1).WriteArray(arr_out)
    outdata.GetRasterBand(1).SetNoDataValue(0)
    outdata.FlushCache()
    outdata = None
    band = None
    ds = None
    _quiet_print(f'Post-proccessed: arr_min:{arr_out.min()}  arr_max:{arr_out.max()}  arr_mean:{arr_out.mean()} ', level='debug')
    return outfile

def reproject_image_to_master(master, raster_to_be_projected, res=None):
    """This function reprojects an image (``raster_to_be_projected``) to
    match the extent, resolution and projection of another
    (``master``) using GDAL. The newly reprojected image
    is a GDAL VRT file for efficiency. A different spatial
    resolution can be chosen by specifyign the optional
    ``res`` parameter. The function returns the new file's
    name.

    Parameters
    -------------
    master: str 
        A filename (with full path if required) with the 
        master image (that that will be taken as a reference)
    raster_to_be_projected: str 
        A filename (with path if needed) with the image
        that will be reprojected
    res: float, optional
        The desired output spatial resolution, if different 
        to the one in ``master``.

    Returns
    ----------
    The reprojected filename
    """
    raster_to_be_projected_ds = gdal.Open(raster_to_be_projected)
    if raster_to_be_projected_ds is None:
        raise IOError('GDAL could not open raster_to_be_projected file %s ' % raster_to_be_projected)
    raster_to_be_projected_proj = raster_to_be_projected_ds.GetProjection()
    raster_to_be_projected_geotrans = raster_to_be_projected_ds.GetGeoTransform()
    data_type = raster_to_be_projected_ds.GetRasterBand(1).DataType
    n_bands = raster_to_be_projected_ds.RasterCount
    master_ds = gdal.Open(master)
    if master_ds is None:
        raise IOError('GDAL could not open master file %s ' % master)
    master_proj = master_ds.GetProjection()
    master_geotrans = master_ds.GetGeoTransform()
    w = master_ds.RasterXSize
    h = master_ds.RasterYSize
    if res is not None:
        master_geotrans[1] = float(res)
        master_geotrans[-1] = -float(res)
    dst_filename = raster_to_be_projected.replace('.tif', '_crop.tif')
    dst_ds = gdal.GetDriverByName('GTiff').Create(dst_filename, w, h, n_bands, data_type)
    dst_ds.SetGeoTransform(master_geotrans)
    dst_ds.SetProjection(master_proj)
    gdal.ReprojectImage(raster_to_be_projected_ds, dst_ds, raster_to_be_projected_proj, master_proj, gdal.GRA_NearestNeighbour)
    dst_ds = None
    return dst_filename

def convert_raster_array(rasterfn):
    """Read the first raster band into a NumPy array."""
    raster = gdal.Open(rasterfn)
    band = raster.GetRasterBand(1)
    return band.ReadAsArray()

def getNoDataValue(rasterfn):
    """Return the NoData value stored in the first raster band."""
    raster = gdal.Open(rasterfn)
    band = raster.GetRasterBand(1)
    return band.GetNoDataValue()

def convert_array_to_raster(rasterfn, newRasterfn, array):
    """Write a NumPy array to a raster using the georeferencing from a template raster."""
    raster = gdal.Open(rasterfn)
    geotransform = raster.GetGeoTransform()
    originX = geotransform[0]
    originY = geotransform[3]
    pixelWidth = geotransform[1]
    pixelHeight = geotransform[5]
    cols = raster.RasterXSize
    rows = raster.RasterYSize
    driver = gdal.GetDriverByName('GTiff')
    outRaster = driver.Create(newRasterfn, cols, rows, 1, gdal.GDT_Int16)
    outRaster.SetGeoTransform((originX, pixelWidth, 0, originY, 0, pixelHeight))
    outband = outRaster.GetRasterBand(1)
    outband.WriteArray(array)
    outRasterSRS = osr.SpatialReference()
    outRasterSRS.ImportFromWkt(raster.GetProjectionRef())
    outRaster.SetProjection(outRasterSRS.ExportToWkt())
    outband.FlushCache()
    outband = None
    raster = None

def raster_sum(input_raster):
    """Return the sum of raster values after replacing negative values with zero."""
    with rasterio.open(input_raster, 'r') as ds:
        arr = ds.read()
        arr[arr < 0] = 0
        actual_sum = np.nansum(arr)
    return actual_sum

def pop_exposure(pop_raster, input_raster, flood_threshold):
    """Estimate population exposure to flooding and export the resulting exposure raster and summary table."""
    file = input_raster
    outfile = file.replace('.tif', '_clean_delete_me.tif')
    input_raster = binarize_flood_mosaic(file, outfile, flood_threshold)
    out_raster = input_raster.replace('_clean_delete_me.tif', 'upsampled_clean_delete_me.tif')
    upsampled_raster = gdal_resample(input_raster, pop_raster, out_raster)
    rasterfn = input_raster
    newValue = 1
    newRasterfn = out_raster.replace('_clean_delete_me.tif', '_no_data_updated_delete_me.tif')
    rasterArray = convert_raster_array(rasterfn)
    noDataValue = getNoDataValue(rasterfn)
    rasterArray[rasterArray == noDataValue] = newValue
    convert_array_to_raster(rasterfn, newRasterfn, rasterArray)
    out_raster = newRasterfn.replace('_no_data_updated_delete_me.tif', '_no_data_updated_upsampled_delete_me.tif')
    upsampled_raster_b = gdal_resample(newRasterfn, pop_raster, out_raster)
    out_raster_a = upsampled_raster
    out_raster_b = upsampled_raster_b
    out_raster_final = out_raster.replace('_no_data_updated_upsampled_delete_me.tif', '_divided_delete_me.tif')
    out0 = gdal_calc.Calc(calc='A/B*100', A=out_raster_a, B=out_raster_b, outfile=out_raster_final, type='Int16', overwrite=True, extent='intersect', NoDataValue=0, quiet=True)
    out_raster_a = pop_raster
    out_raster_b = out_raster_final
    base_path = Path(file).parents[1]
    file_stem = Path(file).stem
    base_path = os.path.join(base_path, 'Population_exposure')
    create_dir_recursive(base_path)
    out_raster_final = str(Path(os.path.join(base_path, f'{file_stem}.tif')))
    out_raster_final = out_raster_final.replace('max_exposure_', 'final_population_exposure_')
    out = gdal_calc.Calc(calc='A*B/100', A=out_raster_a, B=out_raster_b, outfile=out_raster_final, type='Int16', overwrite=True, extent='intersect', NoDataValue=0, quiet=True)
    pop_rasterArray = convert_raster_array(pop_raster)
    band = out.GetRasterBand(1)
    arr = band.ReadAsArray()
    arr_min = arr.min()
    arr_max = arr.max()
    arr_mean = int(arr.mean())
    arr_sum = int(arr.sum())
    data = {'Total  population': int(pop_rasterArray.sum()), 'Population min': pop_rasterArray.min(), 'Population max': pop_rasterArray.max(), 'Population mean': int(pop_rasterArray.mean()), 'Total Exposed population': int(arr.sum()), 'Exposed population min': arr.min(), 'Exposed population max': arr.max(), 'Exposed population mean': int(arr.mean()), '%Exposed population': int(arr.sum() / pop_rasterArray.sum() * 100)}
    df = pd.DataFrame([data])
    _quiet_print(df, level='debug')
    out0 = None
    out = None
    band = None
    raster_delete = [outfile, out_raster, upsampled_raster, input_raster, newRasterfn, upsampled_raster_b]
    for fname in raster_delete:
        try:
            if os.path.isfile(fname):
                os.remove(fname)
        except Exception as e:
            _quiet_print(f'{fname} couldnt be deleted... {e}', level='debug')
    return (df, out_raster_final)

def create_dir_recursive(directory):
    """Create a directory tree if it does not already exist and return the path."""
    os.makedirs(directory, exist_ok=True)
    return directory

def crop_to_shp(path_name, df):
    """Crop a raster to the geometry of a GeoDataFrame and return the cropped array and metadata."""
    raster = rasterio.open(path_name)
    out_array, out_trans = rasterio.mask.mask(dataset=raster, shapes=df.geometry, crop=True)
    out_meta = raster.meta.copy()
    out_meta.update({'height': out_array.shape[1], 'width': out_array.shape[2], 'transform': out_trans})
    return (out_array, out_meta)

def export_array_to_raster(array, meta, path, fileName):
    """Write an in-memory array and raster metadata to disk."""
    Cropped_outputfile = path / fileName
    with rasterio.open(Cropped_outputfile, 'w', **meta, compress='LZW', tiled=True) as dest:
        dest.write(array)
    return Cropped_outputfile

def multiply_array_list(arrayList, array):
    """Multiply every array in a list by a reference array and stack the results."""
    flood_pop = []
    for i in range(len(arrayList)):
        flood_pop.append(np.multiply(arrayList[i], array))
    flood_pop = np.vstack(flood_pop)
    return flood_pop

def convert_to_bool_int_array(array, numberCategories):
    """Convert a classified array into a list of boolean integer masks for each category."""
    listNumberCat = range(numberCategories)
    list_IntBool_floodCat = []
    for i in listNumberCat:
        intArray = (array == i).astype(dtype=np.int8, copy=False)
        list_IntBool_floodCat.append(intArray)
    return list_IntBool_floodCat

def vrtWarp(inpath, outpath, vrt_settings, city, filePrefix):
    """Align a raster to a target grid using a warped virtual raster and save the aligned output."""
    with rasterio.open(inpath) as src:
        with WarpedVRT(src, **vrt_settings) as vrt:
            data = vrt.read()
            for _, window in vrt.block_windows():
                data = vrt.read(window=window)
            fileName = f'{city}_{filePrefix}_warped.tif'
            Aligned_outputfile = outpath / fileName
            rio_shutil.copy(vrt, Aligned_outputfile, driver='GTiff')
    return Aligned_outputfile

def array3d_sum(array):
    """Summarize the totals of each category in a three-dimensional exposure array."""
    Flood_pop_sums = {'0-NoRiskPop': np.sum(array[0]), '1-LowRiskPop': np.sum(array[1]), '2-ModerateRiskPop': np.sum(array[2]), '3-HighRiskPop': np.sum(array[3]), '4-VeryHighRiskPop': np.sum(array[4]), '5-WaterBodyPop': np.sum(array[5])}
    return Flood_pop_sums

def assess_flood_exposure(fluvial_raster, pluvial_raster, coastal_raster, exposure_var_raster, return_period, ssp, Year, raster_keyword, fathom_alignment_folder, subdir, city_vector, flood_bins, numberCategories, city, country):
    """Prepare aligned flood and exposure rasters and export the merged flood exposure raster."""
    delete_me = []
    floodArray, out_meta = crop_to_shp(fluvial_raster, city_vector)
    flood_type = 'Fluvial'
    output_folder = Path(create_dir_recursive(f'{fathom_alignment_folder}/{flood_type}/{Year}/{ssp}/{flood_type}_{ssp}_{Year}'))
    delete_me.append(output_folder)
    raster_name = f'cropped_{flood_type}_{ssp}_{Year}_1in{return_period}{raster_keyword}.tif'
    FluvialCropped_outputfile = export_array_to_raster(floodArray, out_meta, output_folder, raster_name)
    floodArray, out_meta = crop_to_shp(pluvial_raster, city_vector)
    flood_type = 'Pluvial'
    output_folder = Path(create_dir_recursive(f'{fathom_alignment_folder}/{flood_type}/{Year}/{ssp}/{flood_type}_{ssp}_{Year}'))
    delete_me.append(output_folder)
    raster_name = f'cropped_{flood_type}_{ssp}_{Year}_1in{return_period}{raster_keyword}.tif'
    PluvialCropped_outputfile = export_array_to_raster(floodArray, out_meta, output_folder, raster_name)
    floodArray, out_meta = crop_to_shp(coastal_raster, city_vector)
    flood_type = 'Coastal'
    output_folder = Path(create_dir_recursive(f'{fathom_alignment_folder}/{flood_type}/{Year}/{ssp}/{flood_type}_{ssp}_{Year}'))
    delete_me.append(output_folder)
    raster_name = f'cropped_{flood_type}_{ssp}_{Year}_1in{return_period}{raster_keyword}.tif'
    CoastalCropped_outputfile = export_array_to_raster(floodArray, out_meta, output_folder, raster_name)
    vrt_options = {'resampling': Resampling.sum, 'crs': out_meta['crs'], 'transform': out_meta['transform'], 'height': floodArray.shape[1], 'width': floodArray.shape[2]}
    actual_pop = raster_sum(exposure_var_raster)
    flood_type_1 = 'Population'
    flood_type = 'exposure'
    output_folder = Path(create_dir_recursive(f'{fathom_alignment_folder}/{flood_type}/{Year}/{ssp}/{flood_type_1}_{ssp}_{Year}'))
    raster_name = f'cropped_{flood_type_1}_{ssp}_{Year}_1in{return_period}{raster_keyword}.tif'
    popAligned_outputfile = vrtWarp(exposure_var_raster, output_folder, vrt_options, city, raster_name)
    popArray, out_meta = crop_to_shp(popAligned_outputfile, city_vector)
    popArray = popArray.astype('float32', copy=False)
    out_meta.update({'dtype': 'float32'})
    raster_name = f'cropped_final_{flood_type}_{ssp}_{Year}_1in{return_period}{raster_keyword}.tif'
    export_array_to_raster(popArray, out_meta, output_folder, raster_name)
    popArray[popArray < 0] = 0
    total_pop = np.sum(popArray)
    scaling_factor = actual_pop / total_pop
    popArray = popArray * scaling_factor
    raster_name = f'final_rescaled_warped_and_cropped_{flood_type}_{ssp}_{Year}_1in{return_period}{raster_keyword}.tif'
    export_array_to_raster(popArray, out_meta, output_folder, raster_name)
    flood_type = 'Coastal'
    output_folder = Path(create_dir_recursive(f'{fathom_alignment_folder}/{flood_type}/{Year}/{ssp}/{flood_type}_{ssp}_{Year}'))
    raster_name = f'cropped_warped_{flood_type}_{ssp}_{Year}_1in{return_period}{raster_keyword}.tif'
    cFloodAligned_outputfile = vrtWarp(coastal_raster, output_folder, vrt_options, city, raster_name)
    combinedFloodList = [FluvialCropped_outputfile] + [PluvialCropped_outputfile] + [cFloodAligned_outputfile]
    allFiles = []
    for fp in combinedFloodList:
        src = rasterio.open(fp)
        allFiles.append(src)
    floodArray, out_trans = merge(allFiles, method='max')
    out_meta = allFiles[0].meta.copy()
    out_meta.update({'height': floodArray.shape[1], 'width': floodArray.shape[2], 'transform': out_trans})
    flood_type = 'exposure'
    output_folder = Path(create_dir_recursive(f'{fathom_alignment_folder}/{flood_type}/{Year}/{ssp}/{flood_type}_{ssp}_{Year}'))
    raster_name = f'mosaiced_max_{flood_type}_{ssp}_{Year}_1in{return_period}{raster_keyword}.tif'
    FloodMerged_outputfile = export_array_to_raster(floodArray, out_meta, output_folder, raster_name)
    floodArray, out_meta = crop_to_shp(FloodMerged_outputfile, city_vector)
    output_folder = Path(create_dir_recursive(f'{fathom_alignment_folder}/{flood_type}/{Year}/{ssp}/{flood_type}_{ssp}_{Year}'))
    raster_name = f'max_{flood_type}_{ssp}_{Year}_1in{return_period}{raster_keyword}.tif'
    FloodCropped_outputfile = export_array_to_raster(floodArray, out_meta, output_folder, raster_name)
    exp_df = 0
    return (exp_df, FloodCropped_outputfile)

def conduct_pop_exposure(output, tables, rasters, vector_file, revised_bins_list, flood_bins, numberCategories, city, country):
    """Run the full population exposure workflow across flood years, scenarios, and return periods."""
    flood_folder = Path(output) / 'flood'
    city_name_l = city.replace(' ', '_').lower()
    city_name_l = city_name_l.lower()
    configs = _load_pipeline_config()
    rps = configs['flood']['rps']
    flood_years = configs['flood']['year']
    flood_ssps = configs['flood']['ssp']
    flood_ssp_labels = {1: '1_2.6', 2: '2_4.5', 3: '3_7.0', 5: '5_8.5'}
    fathom_alignment_folder = Path(output)
    create_dir_recursive(fathom_alignment_folder)
    raster_keyword = ''
    raster_keyword_null = ''
    df = []
    df_revised = []
    for year in flood_years:
        if year <= 2020:
            for rp in rps:
                try:
                    ssp_for_pop = 'SSP1'
                    exposure_rasters_list = []
                    return_period = rp
                    fluvial_raster = Path(flood_folder / f'{city_name_l}_fluvial_{year}_1in{rp}{raster_keyword}.tif')
                    pluvial_raster = Path(flood_folder / f'{city_name_l}_pluvial_{year}_1in{rp}{raster_keyword}.tif')
                    coastal_raster = Path(flood_folder / f'{city_name_l}_coastal_{year}_1in{rp}{raster_keyword}.tif')
                    ssp_exposure = ssp_for_pop
                    subdir_for_fathom = 'popdynamics'
                    exposure_var_raster = Path(rasters) / f'processed_{subdir_for_fathom}_{ssp_exposure}_{year}.tif'
                    city_vector = vector_file
                    exposure_df, exported_raster = assess_flood_exposure(fluvial_raster, pluvial_raster, coastal_raster, exposure_var_raster, return_period, ssp_for_pop, year, raster_keyword, fathom_alignment_folder, subdir_for_fathom, city_vector, flood_bins, numberCategories, city, country)
                    exposure_rasters_list.append(exported_raster)
                    for threshold in revised_bins_list:
                        pop_raster = str(exposure_var_raster)
                        input_raster = str(exported_raster)
                        df2, out_raster_final = pop_exposure(pop_raster, input_raster, threshold)
                        df2['Population raster name'] = exposure_var_raster.stem
                        df2['Flood raster name'] = exported_raster.stem
                        df2[f'Flood threshold'] = threshold
                        df2['Year'] = year
                        df2['SSP'] = ssp_for_pop
                        df2['Return period'] = rp
                        df_revised.append(df2)
                except Exception as e:
                    _quiet_print('Failed---->> {} '.format(e), level='warning')
        elif year > 2020:
            for ssp in flood_ssps:
                for rp in rps:
                    try:
                        ssp_for_pop = f'SSP{ssp}'.upper()
                        exposure_rasters_list = []
                        return_period = rp
                        fluvial_raster = Path(flood_folder / f'{city_name_l}_fluvial_{year}_ssp{ssp}_1in{rp}{raster_keyword}.tif')
                        pluvial_raster = Path(flood_folder / f'{city_name_l}_pluvial_{year}_ssp{ssp}_1in{rp}{raster_keyword}.tif')
                        coastal_raster = Path(flood_folder / f'{city_name_l}_coastal_{year}_ssp{ssp}_1in{rp}{raster_keyword}.tif')
                        ssp_exposure = ssp_for_pop
                        subdir_for_fathom = 'popdynamics'
                        exposure_var_raster = Path(rasters) / f'processed_{subdir_for_fathom}_{ssp_exposure}_{year}.tif'
                        exposure_df, exported_raster = assess_flood_exposure(fluvial_raster, pluvial_raster, coastal_raster, exposure_var_raster, return_period, ssp_for_pop, year, raster_keyword, fathom_alignment_folder, subdir_for_fathom, city_vector, flood_bins, numberCategories, city, country)
                        exposure_rasters_list.append(exported_raster)
                        for threshold in revised_bins_list:
                            pop_raster = str(exposure_var_raster)
                            input_raster = str(exported_raster)
                            df2, out_raster_final = pop_exposure(pop_raster, input_raster, threshold)
                            df2['Population raster name'] = exposure_var_raster.stem
                            df2['Flood raster name'] = exported_raster.stem
                            df2['Flood threshold'] = threshold
                            df2['Year'] = year
                            df2['SSP'] = ssp_for_pop
                            df2['Return period'] = rp
                            df_revised.append(df2)
                    except Exception as e:
                        _quiet_print('Failed---->> {} '.format(e), level='warning')
    df2 = pd.concat(df_revised, ignore_index=True)
    df2.to_csv(f'{tables}/{city}_population_exposure_to_flood_panel_revised.csv')
    shutil.rmtree(flood_folder)
    return df2

def fathom_barchart_pop_exposure(df, subtitle, y_var, x_var, cmap, maps, year, i):
    """Create and save a population flood exposure bar chart."""
    df_plot = df.copy()
    df_plot['scenario_year'] = df_plot['SSP'].astype(str)
    g = sns.catplot(data=df_plot, kind='bar', x=x_var, y=y_var, hue='scenario_year', palette=cmap, alpha=0.9, height=5, errorbar=None)
    g.fig.suptitle(f'{subtitle}')
    new_title = 'Scenario'
    g._legend.set_title(new_title)
    y_var = y_var.replace(':', '_')
    g.figure.savefig(f'{maps}/fathom_barchart_{y_var}_barchart_{year}_{i}.png', dpi=300, bbox_inches='tight')
    plt.close(g.figure)

def create_pop_exposure_barchart(df2, revised_bins_list, cmap, maps):
    """Create the full set of population exposure bar charts from the revised exposure table."""
    df4 = df2[['%Exposed population', 'Year', 'SSP', 'Return period', 'Flood threshold']]
    index_cols = [col for col in df4.columns if col not in ['Flood threshold', '%Exposed population']]
    df3 = df4.pivot(index=index_cols, columns='Flood threshold', values='%Exposed population').add_prefix('Flood depth(cm):').reset_index()
    df3 = df3.rename_axis(None, axis=1)
    x_var = 'Return period'
    df = df3
    for i in revised_bins_list:
        y_var = f'Percentage of exposed po more than {i}cm'
        y_var = f'Flood depth(cm):{i}'
        for year in df.Year.unique():
            df_s = df.loc[df.Year == year].copy()
            subtitle = f'Percentage of population exposed \n to a {i}cm flood in year {year}'
            fathom_barchart_pop_exposure(df_s, subtitle, y_var, x_var, cmap, maps, year, i)

def export_roads(vector_file, shapefiles, city):
    """
    Outputs roads shapefile and gpkp
    
    Args:
        vector_file: Path to input read city shapefile ( As vector)
        shapefiles: Output path for shapefile export 
        road raster.
        flood_bins: flood bins for classes
        city: City

    Returns:
         City road network edges  
    """
    index = 0
    polygon = vector_file.reset_index().iloc[index]['geometry']
    G = ox.graph.graph_from_polygon(polygon, network_type='drive')
    G = ox.add_edge_speeds(G)
    G = ox.add_edge_travel_times(G)
    G = ox.projection.project_graph(G, to_crs=3857)
    nodes, gdf_edges = ox.graph_to_gdfs(G)
    gdf_edges_reset = gdf_edges.reset_index()
    edges = gdf_edges_reset.set_index(['u', 'v', 'key'])
    geoms = edges['geometry']
    gdf2 = gpd.GeoDataFrame(geometry=geoms)
    gdf2.to_file(f'{shapefiles}/{city}_road_network_shapefile.shp')
    roads_filepath = f'{shapefiles}/{city}_road_network_graph_gpkg.gpkg'
    ox.save_graph_geopackage(G, filepath=roads_filepath)
    _quiet_print(f' {city} road network exported', level='debug')
    return gdf_edges

def assess_road_network_exposure_to_floods(roads_filepath, fluvial_raster, out_raster_path, roads_with_flood_depth):
    """
    Returns path to flooded road network 

    Args:
        roads_filepath: Path to input roads shapefile 
        fluvial_raster: Path to input flood raster 
        out_raster_path: Outpath for rasterized roads 
        roads_with_flood_depth:Outpath for flooded roads 

    Returns:
        Outpath for flooded roads 

    """
    dataset = ogr.Open(roads_filepath)
    if not dataset:
        _quiet_print('Error: could not open roads', level='warning')
    layer_count = dataset.GetLayerCount()
    layer = dataset.GetLayerByIndex(0)
    raster_ds = gdal.Open(str(fluvial_raster), gdal.GA_ReadOnly)
    if not raster_ds:
        _quiet_print(f'Error: could not open {str(fluvial_raster)}', level='warning')
    ncol = raster_ds.RasterXSize
    nrow = raster_ds.RasterYSize
    proj = raster_ds.GetProjectionRef()
    ext = raster_ds.GetGeoTransform()
    raster_ds = None
    memory_driver = gdal.GetDriverByName('GTiff')
    out_raster_ds = memory_driver.Create(out_raster_path, ncol, nrow, 1, gdal.GDT_Byte)
    out_raster_ds.SetProjection(proj)
    out_raster_ds.SetGeoTransform(ext)
    b = out_raster_ds.GetRasterBand(1)
    b.Fill(0)
    field_for_burning = 'length_m'
    status = gdal.RasterizeLayer(out_raster_ds, [1], layer, None, None, [1], ['ALL_TOUCHED=TRUE'])
    out_raster_ds = None
    if status != 0:
        _quiet_print('Nope rasterization failed', level='warning')
    else:
        gdal_calc.Calc(calc='A*logical_and(A>0,B>0)', A=fluvial_raster, B=out_raster_path, outfile=roads_with_flood_depth, overwrite=True, quiet=True)
        return roads_with_flood_depth

def get_flooded_roads_array(rasterPath, band=1):
    """
    Returns raster band as 2d numpy array

    Args:
        rasterPath: Path to input raster

    Returns:
        numpy array if band exists or None if band does not exist

    """
    if os.path.isfile(rasterPath):
        ds = gdal.Open(rasterPath)
        bands = ds.RasterCount
        if band > 0 and band <= bands:
            array = ds.GetRasterBand(band).ReadAsArray()
            ds = None
            return array
        else:
            return None
    else:
        return None

def reclassif_raster_by_bins(roads_with_flood_depth, roads_with_flood_depth_classified, flood_bins):
    """
    Outputs a reclassified raster 

    Args:
        roads_with_flood_depth: Path to input road raster
        roads_with_flood_depth_classified: Path to output classified 
        road raster.
        flood_bins: flood bins for classes

    Returns:
         None 
    """
    with rasterio.open(roads_with_flood_depth) as src:
        array = src.read()
        profile = src.profile
        bins = np.array(flood_bins)
        inds = np.digitize(array, bins, right=True)
    with rasterio.open(roads_with_flood_depth_classified, 'w', **profile) as dst:
        dst.write(inds)

def conduct_infra_exposure_analysis(output, tables, shapefiles, flood_bins, flood_years, rps, flood_ssps, city, country):
    """Run the road exposure workflow across flood years, scenarios, and return periods."""
    fathom_alignment_folder = Path(output)
    create_dir_recursive(fathom_alignment_folder)
    infra_exposure_dir = Path(fathom_alignment_folder / 'infra_exposure')
    numberCategories = len(flood_bins)
    raster_keyword = ''
    output_df = pd.DataFrame()
    for year in flood_years:
        if year <= 2020:
            for rp in rps:
                ssp_for_pop = 'SSP1'
                df = []
                exposure_rasters_list = []
                return_period = rp
                flood_type = 'exposure'
                output_folder = f'{fathom_alignment_folder}/{flood_type}/{year}/{ssp_for_pop}/{flood_type}_{ssp_for_pop}_{year}'
                flood_fn = Path(output_folder) / f'max_{flood_type}_{ssp_for_pop}_{year}_1in{return_period}{raster_keyword}.tif'
                raster_stem = flood_fn.stem
                roads_filepath = f'{shapefiles}/{city}_road_network_shapefile.shp'
                infra_output_folder = f'{fathom_alignment_folder}/{flood_type}/{year}/{ssp_for_pop}/Roads_exposed_{flood_type}_{ssp_for_pop}_{year}'
                create_dir_recursive(infra_output_folder)
                out_raster_path = str(Path(infra_output_folder) / f'roads_rasterized_{str(raster_stem)}')
                roads_with_flood_depth = str(Path(infra_output_folder) / f'roads_flood_depth{str(raster_stem)}')
                base_path = Path(roads_with_flood_depth).parents[1]
                file_stem = Path(roads_with_flood_depth).stem
                base_path = os.path.join(base_path, 'Roads_exposure')
                create_dir_recursive(base_path)
                out_raster_final = str(Path(os.path.join(base_path, f'{file_stem}.tif')))
                out_raster_final = out_raster_final.replace('roads_flood_depth', 'final')
                out_raster_final = out_raster_final.replace('finalmax_exposure_', 'final_road_exposure_')
                roads_with_flood_depth = out_raster_final
                roads_with_flood_depth_classified = str(Path(infra_output_folder) / f'roads_classified{str(raster_stem)}')
                assess_road_network_exposure_to_floods(roads_filepath, flood_fn, out_raster_path, roads_with_flood_depth)
                rasterPath = roads_with_flood_depth
                get_flooded_roads_array_flooded_roads = get_flooded_roads_array(rasterPath, band=1)
                get_flooded_roads_array_of_all_roads = get_flooded_roads_array(out_raster_path, band=1)
                all_roads_length = np.count_nonzero(get_flooded_roads_array_of_all_roads) * 30
                flooded_roads_length = np.count_nonzero(get_flooded_roads_array_flooded_roads) * 30
                _quiet_print(f'all_roads_length: {all_roads_length}-- flooded_roads_length:{flooded_roads_length}. Fraction={flooded_roads_length / all_roads_length}', level='debug')
                reclassif_raster_by_bins(roads_with_flood_depth, roads_with_flood_depth_classified, flood_bins)
                dicts = {}
                dicts[f'flood_file_name'] = f' flood_file_name {raster_stem}'
                dicts[f'Year'] = year
                dicts[f'SSP'] = ssp_for_pop
                dicts[f'Return period'] = rp
                for i in flood_bins:
                    flooded_more_than_cm = ((i < get_flooded_roads_array_flooded_roads) & (get_flooded_roads_array_flooded_roads < 1000000)).sum() * 30
                    dicts[f'Road length flooded more than {i}cm'] = flooded_more_than_cm
                    frac_flooded_more_than_cm = flooded_more_than_cm / all_roads_length * 100
                    dicts[f'Percentage of road flooded more than {i}cm'] = frac_flooded_more_than_cm
                output_df = pd.concat([output_df, pd.DataFrame([dicts])], ignore_index=True)
        elif year > 2020:
            for ssp in flood_ssps:
                for rp in rps:
                    try:
                        ssp_for_pop = f'SSP{ssp}'.upper()
                        df = []
                        exposure_rasters_list = []
                        return_period = rp
                        ssp_exposure = ssp_for_pop
                        flood_fn = Path(fathom_alignment_folder) / f'max_popdynamics_{city}_{ssp_for_pop}_{year}_1in{rp}{raster_keyword}tif'
                        raster_stem = flood_fn.stem
                        roads_filepath = f'{shapefiles}/{city}_road_network_shapefile.shp'
                        flood_type = 'exposure'
                        output_folder = f'{fathom_alignment_folder}/{flood_type}/{year}/{ssp_for_pop}/{flood_type}_{ssp_for_pop}_{year}'
                        flood_fn = Path(output_folder) / f'max_{flood_type}_{ssp_for_pop}_{year}_1in{return_period}{raster_keyword}.tif'
                        raster_stem = flood_fn.stem
                        roads_filepath = f'{shapefiles}/{city}_road_network_shapefile.shp'
                        infra_output_folder = f'{fathom_alignment_folder}/{flood_type}/{year}/{ssp_for_pop}/Roads_exposed_{flood_type}_{ssp_for_pop}_{year}'
                        create_dir_recursive(infra_output_folder)
                        out_raster_path = str(Path(infra_output_folder) / f'roads_rasterized_{str(raster_stem)}')
                        roads_with_flood_depth = str(Path(infra_output_folder) / f'roads_flood_depth{str(raster_stem)}')
                        base_path = Path(roads_with_flood_depth).parents[1]
                        file_stem = Path(roads_with_flood_depth).stem
                        base_path = os.path.join(base_path, 'Roads_exposure')
                        create_dir_recursive(base_path)
                        out_raster_final = str(Path(os.path.join(base_path, f'{file_stem}.tif')))
                        out_raster_final = out_raster_final.replace('roads_flood_depth', 'final')
                        out_raster_final = out_raster_final.replace('finalmax_exposure_', 'final_road_exposure_')
                        roads_with_flood_depth = out_raster_final
                        roads_with_flood_depth_classified = str(Path(infra_output_folder) / f'roads_classified{str(raster_stem)}')
                        assess_road_network_exposure_to_floods(roads_filepath, flood_fn, out_raster_path, roads_with_flood_depth)
                        rasterPath = roads_with_flood_depth
                        get_flooded_roads_array_flooded_roads = get_flooded_roads_array(rasterPath, band=1)
                        get_flooded_roads_array_of_all_roads = get_flooded_roads_array(out_raster_path, band=1)
                        all_roads_length = np.count_nonzero(get_flooded_roads_array_of_all_roads) * 30
                        flooded_roads_length = np.count_nonzero(get_flooded_roads_array_flooded_roads) * 30
                        reclassif_raster_by_bins(roads_with_flood_depth, roads_with_flood_depth_classified, flood_bins)
                        dicts = {}
                        dicts[f'flood_file_name'] = f' flood_file_name {raster_stem}'
                        dicts[f'Year'] = year
                        dicts[f'SSP'] = ssp_for_pop
                        dicts[f'Return period'] = rp
                        for i in flood_bins:
                            flooded_more_than_cm = ((i < get_flooded_roads_array_flooded_roads) & (get_flooded_roads_array_flooded_roads < 1000000)).sum() * 30
                            dicts[f'Road length flooded more than {i}cm'] = flooded_more_than_cm
                            frac_flooded_more_than_cm = flooded_more_than_cm / all_roads_length * 100
                            dicts[f'Percentage of road flooded more than {i}cm'] = frac_flooded_more_than_cm
                        output_df = pd.concat([output_df, pd.DataFrame([dicts])], ignore_index=True)
                    except Exception as e:
                        _quiet_print('Failed---->> {} '.format(e), level='warning')
    output_df.to_csv(f'{tables}/{city}_road_network_fathom_exposure_mosaic_max_panel_gdal.csv')

def fathom_barchart_infra_exposure(df, subtitle, y_var, x_var, cmap, maps, year, i):
    """Create and save a road exposure bar chart."""
    df_plot = df.copy()
    df_plot['scenario_year'] = df_plot['SSP'].astype(str)
    g = sns.catplot(data=df_plot, kind='bar', x=x_var, y=y_var, hue='scenario_year', palette=cmap, alpha=0.9, height=6, errorbar=None)
    g.fig.suptitle(f'{subtitle}')
    new_title = 'Scenario'
    g._legend.set_title(new_title)
    g.figure.savefig(f'{maps}/fathom_barchart_{y_var}_barchart_{year}_{i}.png', dpi=300, bbox_inches='tight')
    plt.close(g.figure)

def export_infra_exposure_barcharts(tables, revised_bins_list, cmap, maps, city, country):
    """Create the full set of road exposure bar charts from the exported table."""
    x_var = 'Return period'
    df = pd.read_csv(f'{tables}/{city}_road_network_fathom_exposure_mosaic_max_panel_gdal.csv')
    for i in revised_bins_list:
        y_var = f'Percentage of road flooded more than {i}cm'
        for year in df.Year.unique():
            df_s = df.loc[df.Year == year].copy()
            subtitle = y_var + f' in year {year}'
            fathom_barchart_infra_exposure(df_s, subtitle, y_var, x_var, cmap, maps, year, i)

def post_process_dir_cleaning(base_path, directories_to_remove):
    """
    List directories in the given path and remove the ones specified in the list.

    :param base_path: The path to search for directories.
    :param directories_to_remove: A list of directory names to remove.
    """
    all_directories = [d for d in os.listdir(base_path) if os.path.isdir(os.path.join(base_path, d))]
    _quiet_print(f'all_directories -- {all_directories}', level='debug')
    for directory in all_directories:
        if directory in directories_to_remove:
            dir_path = os.path.join(base_path, directory)
            try:
                shutil.rmtree(dir_path)
                _quiet_print(f'Removed directory: {dir_path}', level='debug')
            except Exception as e:
                _quiet_print(f'Error removing directory {dir_path}: {e}', level='warning')
