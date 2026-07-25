"""Post-processing functions for raster polygonization, clipping, copying, and GeoJSON export."""
import os
import glob
from osgeo import gdal, ogr
import os
import glob
from osgeo import ogr
from shapely.geometry import shape
import geopandas as gpd
import os
import os
import glob
from osgeo import gdal, ogr
import logging
LOGGER = logging.getLogger('city_pipeline')

def _quiet_print(*args, level: str='debug') -> None:
    """Route legacy print-style messages through the pipeline logger."""
    message = ' '.join((str(arg) for arg in args))
    getattr(LOGGER, level, LOGGER.debug)(message)

def polygonize_rasters(input_dir, output_dir, start_keyword, end_keyword):
    """
    Function to loop through rasters, polygonize them, and export as GeoJSON with accurate pixel values.

    Parameters:
        input_dir (str): Directory containing raster files.
        output_dir (str): Directory to save the output GeoJSON files.
        start_keyword (str): Keyword the filenames should start with.
        end_keyword (str): Keyword the filenames should end with.
    """
    os.makedirs(output_dir, exist_ok=True)
    pattern = os.path.join(input_dir, f'{start_keyword}*{end_keyword}')
    raster_files = glob.glob(pattern)
    for raster_file in raster_files:
        base_name = os.path.splitext(os.path.basename(raster_file))[0]
        raster_ds = gdal.Open(raster_file)
        if raster_ds is None:
            _quiet_print(f'Error opening raster file: {raster_file}', level='warning')
            continue
        geotransform = raster_ds.GetGeoTransform()
        band = raster_ds.GetRasterBand(1)
        if band is None:
            _quiet_print(f'Error: No band found in raster file: {raster_file}', level='warning')
            raster_ds = None
            continue
        nodata_value = band.GetNoDataValue()
        output_geojson = os.path.join(output_dir, f'{base_name}.geojson')
        driver = ogr.GetDriverByName('GeoJSON')
        vector_ds = driver.CreateDataSource(output_geojson)
        layer = vector_ds.CreateLayer(base_name, srs=None, geom_type=ogr.wkbPolygon)
        field_defn_value = ogr.FieldDefn('PixelValue', ogr.OFTReal)
        layer.CreateField(field_defn_value)
        temp_mem_vector = '/vsimem/temp_vector'
        mem_driver = ogr.GetDriverByName('Memory')
        mem_vector_ds = mem_driver.CreateDataSource(temp_mem_vector)
        mem_layer = mem_vector_ds.CreateLayer('temp_layer', geom_type=ogr.wkbPolygon)
        mem_layer.CreateField(field_defn_value)
        gdal.Polygonize(band, None, mem_layer, 0, [], callback=None)
        for feature in mem_layer:
            pixel_value = feature.GetField('PixelValue')
            if pixel_value is not None and pixel_value != nodata_value:
                new_feature = ogr.Feature(layer.GetLayerDefn())
                new_feature.SetGeometry(feature.GetGeometryRef().Clone())
                new_feature.SetField('PixelValue', pixel_value)
                layer.CreateFeature(new_feature)
                new_feature = None
        mem_vector_ds = None
        vector_ds = None
        raster_ds = None
        _quiet_print(f'Polygonized {raster_file} to {output_geojson}', level='debug')

def add_fields_to_geojsons(geojson_dir, start_keyword, end_keyword):
    """
    Function to add additional fields to GeoJSON files.

    Parameters:
        geojson_dir (str): Directory containing GeoJSON files.
        start_keyword (str): Keyword the filenames should start with.
        end_keyword (str): Keyword the filenames should end with.
    """
    pattern = os.path.join(geojson_dir, f'{start_keyword}*{end_keyword}')
    geojson_files = glob.glob(pattern)
    _quiet_print(f'Found {len(geojson_files)} files matching the pattern: {pattern}', level='debug')
    for geojson_file in geojson_files:
        _quiet_print(f'Processing file: {geojson_file}', level='debug')
        base_name = os.path.splitext(os.path.basename(geojson_file))[0]
        _quiet_print(f'Base name extracted: {base_name}', level='debug')
        name_parts = base_name.split('_')
        year = name_parts[-1] if len(name_parts) > 1 else 'Unknown'
        scenario = name_parts[-2] if len(name_parts) > 2 else 'Unknown'
        _quiet_print(f'Year extracted: {year}, Scenario extracted: {scenario}', level='debug')
        driver = ogr.GetDriverByName('GeoJSON')
        vector_ds = driver.Open(geojson_file, 1)
        if vector_ds is None:
            _quiet_print(f'Error opening GeoJSON file: {geojson_file}', level='warning')
            continue
        else:
            _quiet_print(f'Successfully opened {geojson_file}', level='debug')
        layer = vector_ds.GetLayer()
        if layer.FindFieldIndex('FileName', 0) == -1:
            _quiet_print(f"Adding 'FileName' field to {geojson_file}", level='debug')
            layer.CreateField(ogr.FieldDefn('FileName', ogr.OFTString))
        else:
            _quiet_print(f"'FileName' field already exists in {geojson_file}", level='debug')
        if layer.FindFieldIndex('Year', 0) == -1:
            _quiet_print(f"Adding 'Year' field to {geojson_file}", level='debug')
            layer.CreateField(ogr.FieldDefn('Year', ogr.OFTString))
        else:
            _quiet_print(f"'Year' field already exists in {geojson_file}", level='debug')
        if layer.FindFieldIndex('Scenario', 0) == -1:
            _quiet_print(f"Adding 'Scenario' field to {geojson_file}", level='debug')
            layer.CreateField(ogr.FieldDefn('Scenario', ogr.OFTString))
        else:
            _quiet_print(f"'Scenario' field already exists in {geojson_file}", level='debug')
        for feature in layer:
            feature.SetField('FileName', base_name)
            feature.SetField('Year', year)
            feature.SetField('Scenario', scenario)
            layer.SetFeature(feature)
        _quiet_print(f'Updated features in {geojson_file}', level='debug')
        vector_ds = None
        _quiet_print(f'Closed the GeoJSON file: {geojson_file}', level='debug')
        _quiet_print(f'Updated {geojson_file} with additional fields', level='debug')

def append_geojsons(geojson_dir, start_keyword):
    """
    Function to append all GeoJSON files that start with a specific keyword,
    add an ID column for polygons, and return the combined features as a dictionary for debugging.

    Parameters:
        geojson_dir (str): Directory containing GeoJSON files.
        start_keyword (str): Keyword that the filenames should start with.

    Returns:
        list: A list of dictionaries representing the combined GeoJSON features.
    """
    if not os.path.exists(geojson_dir):
        _quiet_print(f'Directory does not exist: {geojson_dir}', level='debug')
        return []
    pattern = os.path.join(geojson_dir, f'{start_keyword}*.geojson')
    geojson_files = glob.glob(pattern)
    _quiet_print(f'Found {len(geojson_files)} files matching the pattern: {pattern}', level='debug')
    if not geojson_files:
        _quiet_print('No GeoJSON files found.', level='debug')
        return []
    driver = ogr.GetDriverByName('GeoJSON')
    if not driver:
        _quiet_print('GeoJSON driver not available.', level='debug')
        return []
    combined_features = []
    feature_id = 1
    for geojson_file in geojson_files:
        _quiet_print(f'Processing file: {geojson_file}', level='debug')
        vector_ds = driver.Open(geojson_file, 0)
        if vector_ds is None:
            _quiet_print(f'Error opening GeoJSON file: {geojson_file}', level='warning')
            continue
        layer = vector_ds.GetLayer()
        _quiet_print(f'Layer: {layer.GetName()} - Feature Count: {layer.GetFeatureCount()}', level='debug')
        for feature in layer:
            feature_json = feature.ExportToJson(as_object=True)
            feature_json['properties']['ID'] = feature_id
            combined_features.append(feature_json)
            feature_id += 1
        _quiet_print(f'Appended features from {geojson_file}', level='debug')
    _quiet_print(f'Total features combined: {len(combined_features)}', level='debug')
    return combined_features

def export_to_geojson(panel, output_path):
    """
    Convert a dictionary-based panel with GeoJSON-like geometries to a GeoDataFrame
    and export it as a GeoJSON file.

    Parameters:
        panel (list): List of features where each feature is a dictionary containing
                      "geometry" (GeoJSON-like) and "properties".
        output_path (str): Path to export the combined GeoJSON file.

    Returns:
        gpd.GeoDataFrame: The resulting GeoDataFrame.
    """
    for feature in panel:
        feature['geometry'] = shape(feature['geometry'])
    combined_gdf = gpd.GeoDataFrame([feature['properties'] for feature in panel], geometry=[feature['geometry'] for feature in panel])
    output_dir = os.path.dirname(output_path)
    os.makedirs(output_dir, exist_ok=True)
    _quiet_print(f'Exporting GeoDataFrame to: {output_path}', level='debug')
    try:
        combined_gdf.to_file(output_path, driver='GeoJSON')
        _quiet_print('Export successful!', level='debug')
    except Exception as e:
        _quiet_print(f'Error exporting GeoJSON: {e}', level='warning')
    return combined_gdf
import os
import shutil
from fnmatch import fnmatch

def copy_rasters_with_keyword(source_dir, destination_dir, keyword, file_extension='tif'):
    """
    Copies raster files with a specific keyword in their names from source_dir 
    (including subdirectories) to destination_dir.

    :param source_dir: Path to the source directory.
    :param destination_dir: Path to the destination directory.
    :param keyword: Keyword to search for in filenames.
    :param file_extension: File extension of raster files (default is "tif").
    """
    if not os.path.exists(destination_dir):
        os.makedirs(destination_dir)
    for root, _, files in os.walk(source_dir):
        for file in files:
            if keyword in file and fnmatch(file, f'*.{file_extension}'):
                source_path = os.path.join(root, file)
                destination_path = os.path.join(destination_dir, file)
                _quiet_print(f'source_path- {source_path} ----- destination_path {destination_path}', level='debug')
                shutil.copy2(source_path, destination_path)
                _quiet_print(f'Copied: {source_path} -> {destination_path}', level='debug')

def clip_geojsons(input_folder, output_folder, shapefile_path, skip_keyword):
    """
    Clips all GeoJSON files in a folder using a shapefile.
    
    Parameters:
        input_folder (str): Path to the folder containing GeoJSON files.
        output_folder (str): Path to the folder to save clipped GeoJSON files.
        shapefile_path (str): Path to the shapefile used for clipping.
    """
    os.makedirs(output_folder, exist_ok=True)
    driver = ogr.GetDriverByName('ESRI Shapefile')
    shapefile = driver.Open(shapefile_path, 0)
    if shapefile is None:
        _quiet_print('Failed to open shapefile:', shapefile_path, level='warning')
        return
    clip_layer = shapefile.GetLayer()
    for file_name in os.listdir(input_folder):
        if file_name.endswith('.geojson'):
            if skip_keyword not in file_name:
                input_file_path = os.path.join(input_folder, file_name)
                output_file_path = os.path.join(output_folder, file_name)
                input_driver = ogr.GetDriverByName('GeoJSON')
                input_data = input_driver.Open(input_file_path, 0)
                if input_data is None:
                    _quiet_print(f'Failed to open {file_name}', level='warning')
                    continue
                input_layer = input_data.GetLayer()
                if os.path.exists(output_file_path):
                    os.remove(output_file_path)
                output_data = input_driver.CreateDataSource(output_file_path)
                output_layer = output_data.CreateLayer(input_layer.GetName(), geom_type=input_layer.GetGeomType(), srs=input_layer.GetSpatialRef())
                input_layer_def = input_layer.GetLayerDefn()
                for i in range(input_layer_def.GetFieldCount()):
                    field_def = input_layer_def.GetFieldDefn(i)
                    output_layer.CreateField(field_def)
                for feature in input_layer:
                    geom = feature.GetGeometryRef()
                    if geom is None:
                        continue
                    geom_clone = geom.Clone()
                    for clip_feature in clip_layer:
                        clip_geom = clip_feature.GetGeometryRef()
                        if clip_geom is None:
                            continue
                        if geom_clone.Intersects(clip_geom):
                            clipped_geom = geom_clone.Intersection(clip_geom)
                            new_feature = ogr.Feature(output_layer.GetLayerDefn())
                            new_feature.SetGeometry(clipped_geom)
                            for i in range(input_layer_def.GetFieldCount()):
                                new_feature.SetField(input_layer_def.GetFieldDefn(i).GetNameRef(), feature.GetField(i))
                            output_layer.CreateFeature(new_feature)
                            new_feature = None
                    geom_clone = None
                input_data = None
                output_data = None
                _quiet_print(f'Clipped {file_name} to {output_file_path}', level='debug')
    _quiet_print('Clipping completed!', level='debug')
