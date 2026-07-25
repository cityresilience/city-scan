"""Shared geospatial helper functions for the FCS pipeline."""
import os
import geopandas as gpd
import numpy as np
from rasterstats import zonal_stats
import rasterio
from rasterio.mask import mask
from rasterio.warp import calculate_default_transform, reproject, Resampling
from os.path import exists
from osgeo import gdal, osr
import numpy as np
from pathlib import Path
import logging
LOGGER = logging.getLogger('city_pipeline')

def _quiet_print(*args, level: str='debug') -> None:
    """Route legacy print-style messages through the pipeline logger."""
    message = ' '.join((str(arg) for arg in args))
    getattr(LOGGER, level, LOGGER.debug)(message)

def create_dir(directory):
    """Create a directory if it does not already exist and return its path."""
    if not os.path.exists(directory):
        os.makedirs(directory)
    return directory

def set_paths(base_dir):
    """Create the standard output folder structure and return the key pipeline paths."""
    data = os.path.join(base_dir, 'data')
    output = Path(base_dir) / '02-process-output'
    shapefiles = os.path.join(f'{base_dir}/01-inputs', 'shapefiles')
    maps = os.path.join(output, 'maps')
    rasters = os.path.join(output, 'rasters')
    tables = os.path.join(output, 'tables')
    dirs_list = [data, output, base_dir, shapefiles, maps, rasters, tables]
    for dir in dirs_list:
        if not os.path.exists(dir):
            os.mkdir(dir)
    return (data, shapefiles, maps, rasters, output, tables)

def reproject_gpdf(input_gpdf, raster):
    """Reproject a GeoDataFrame to match the coordinate reference system of a raster dataset."""
    proj = raster.crs.to_proj4()
    reproj = input_gpdf.to_crs(proj)
    return reproj

def list_statistics(stat):
    """Return the list of raster statistics requested for zonal analysis."""
    out_stats = stat
    return out_stats

def calculate_zonal_stats(vector, raster, stats):
    """Calculate zonal statistics for a vector layer over a raster and return the results as a GeoDataFrame."""
    result = zonal_stats(vector, raster, stats=stats, geojson_out=True)
    geostats = gpd.GeoDataFrame.from_features(result)
    for c in stats:
        geostats[c] = np.round(geostats[c], decimals=2)
    return geostats

def clip_and_export_rescale_raster(input_gpdf, raster, out_raster, rescaling_factor):
    """Clip a raster to the analysis boundary, apply a scaling factor, and export the result."""
    Vector = input_gpdf
    with rasterio.open(raster) as src:
        Vector = Vector.to_crs(src.crs)
        out_image, out_transform = mask(src, Vector.geometry, crop=True)
        no_data_value = 0
        out_image = np.where(out_image < 0, no_data_value, out_image)
        out_image = out_image * rescaling_factor
        out_meta = src.meta.copy()
    out_meta.update({'driver': 'Gtiff', 'height': out_image.shape[1], 'width': out_image.shape[2], 'transform': out_transform})
    with rasterio.open(out_raster, 'w', **out_meta) as dst:
        dst.write(out_image)

def clip_and_export_raster(input_gpdf, raster, out_raster):
    """Clip a raster to the analysis boundary and export the result without rescaling."""
    Vector = input_gpdf
    with rasterio.open(raster) as src:
        Vector = Vector.to_crs(src.crs)
        _quiet_print(Vector.crs, src.crs, level='debug')
        out_image, out_transform = mask(src, Vector.geometry, crop=True)
        no_data_value = 0
        out_image = np.where(out_image < 0, no_data_value, out_image)
        out_meta = src.meta.copy()
        _quiet_print(1, level='debug')
    out_meta.update({'driver': 'Gtiff', 'height': out_image.shape[1], 'width': out_image.shape[2], 'transform': out_transform})
    _quiet_print(2, level='debug')
    with rasterio.open(out_raster, 'w', **out_meta) as dst:
        dst.write(out_image)

def reproject_rasters(crs, unprojected_raster, projected_raster):
    """Reproject a raster to the requested EPSG code and save it if the output does not already exist."""
    if not exists(projected_raster):
        with rasterio.open(unprojected_raster) as src:
            dst_crs = 'EPSG:' + str(crs)
            transform, width, height = calculate_default_transform(src.crs, dst_crs, src.width, src.height, *src.bounds)
            kwargs = src.meta.copy()
            kwargs.update({'crs': dst_crs, 'transform': transform, 'width': width, 'height': height})
            with rasterio.open(projected_raster, 'w', **kwargs) as dst:
                for i in range(1, src.count + 1):
                    reproject(source=rasterio.band(src, i), destination=rasterio.band(dst, i), src_transform=src.transform, src_crs=src.crs, dst_transform=transform, dst_crs=dst_crs, resampling=Resampling.nearest)

def reproject_and_clip_raster(input_raster, shapefile, output_raster, target_epsg, multiply_factor=1):
    """Reproject, clip, and apply a multiplication factor to each pixel in a raster, setting NoData and negative values to 0."""
    src = gdal.Open(input_raster)
    src_proj = osr.SpatialReference(wkt=src.GetProjection())
    target_proj = osr.SpatialReference()
    target_proj.ImportFromEPSG(target_epsg)
    temp_raster = '/vsimem/temp_reprojected.tif'
    gdal.Warp(temp_raster, src, format='GTiff', cutlineDSName=shapefile, cropToCutline=True, dstSRS=target_proj.ExportToWkt(), warpOptions=['CUTLINE_ALL_TOUCHED=TRUE'])
    temp_ds = gdal.Open(temp_raster)
    driver = gdal.GetDriverByName('GTiff')
    output_ds = driver.Create(output_raster, temp_ds.RasterXSize, temp_ds.RasterYSize, 1, temp_ds.GetRasterBand(1).DataType)
    output_ds.SetGeoTransform(temp_ds.GetGeoTransform())
    output_ds.SetProjection(temp_ds.GetProjection())
    band = temp_ds.GetRasterBand(1)
    data = band.ReadAsArray()
    nodata_value = band.GetNoDataValue()
    if nodata_value is not None:
        data[data == nodata_value] = 0
    data[data < 0] = 0
    data = data * multiply_factor
    output_band = output_ds.GetRasterBand(1)
    output_band.WriteArray(data)
    output_band.SetNoDataValue(0)
    src = None
    temp_ds = None
    output_ds = None
    gdal.Unlink(temp_raster)

def raster_sum_mean(raster_path):
    """Return raster sum and mean while safely handling empty or all-NoData arrays."""
    _quiet_print(f'Opening: {raster_path}', level='debug')
    dataset = gdal.Open(raster_path)
    if dataset is None:
        raise FileNotFoundError(f'Cannot open {raster_path}')
    band = dataset.GetRasterBand(1)
    array = band.ReadAsArray()
    nodata_value = band.GetNoDataValue()
    if nodata_value is not None:
        array = np.where(array == nodata_value, np.nan, array)
    total_sum = float(np.nansum(array))
    finite_mask = np.isfinite(array)
    mean_value = float(np.nanmean(array)) if finite_mask.any() else float('nan')
    return (total_sum, mean_value)
