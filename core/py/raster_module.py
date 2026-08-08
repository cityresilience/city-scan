def raster_mask_bytes(raster_bytes, features):
    import rasterio.mask
    from rasterio.io import MemoryFile

    with MemoryFile(raster_bytes) as memfile:
        with memfile.open() as src:
            out_image, out_transform = rasterio.mask.mask(
                src, features, all_touched = True, crop = True)
            out_meta = src.meta.copy()

        out_meta.update({"driver": "GTiff",
                        "height": out_image.shape[1],
                        "width": out_image.shape[2],
                        "transform": out_transform})

    return out_image, out_meta

def raster_mask_file(raster_file, features):
    import rasterio
    import rasterio.mask

    with rasterio.open(raster_file) as src:
        out_image, out_transform = rasterio.mask.mask(
            src, features, all_touched = True, crop = True)
        out_meta = src.meta.copy()

    out_meta.update({"driver": "GTiff",
                    "height": out_image.shape[1],
                    "width": out_image.shape[2],
                    "transform": out_transform})

    return out_image, out_meta

def tile_finder(aoi_file, direction, tile_size = 1):
    import math

    aoi_bounds = aoi_file.bounds

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
        print('tile_finder function error')
        print('Invalid direction. How did this happen?')
        exit()

    for i in range(len(aoi_bounds)):
        if math.floor(coord_min[i]) >= 0:
            hemi = hemi_options[0]
            for y in range(math.floor(coord_min[i] / tile_size) * tile_size, 
                            math.ceil(coord_max[i] / tile_size) * tile_size, 
                            tile_size):
                coord_list.append(f'{hemi}{str(y).zfill(zfill_digits)}')
        elif math.ceil(coord_max[i]) >= 0:
            for y in range(0, 
                            math.ceil(coord_max[i] / tile_size) * tile_size, 
                            tile_size):
                coord_list.append(f'{hemi_options[0]}{str(y).zfill(zfill_digits)}')
            for y in range(math.floor(coord_min[i] / tile_size) * tile_size, 
                            0, 
                            tile_size):
                coord_list.append(f'{hemi_options[1]}{str(-y).zfill(zfill_digits)}')
        else:
            hemi = hemi_options[1]
            for y in range(math.floor(coord_min[i] / tile_size) * tile_size, 
                            math.ceil(coord_max[i] / tile_size) * tile_size, 
                            tile_size):
                coord_list.append(f'{hemi}{str(-y).zfill(zfill_digits)}')

    return coord_list

def coord_converter(coord):
    if coord[0] in ['N', 'E']:
        return int(coord[1:])
    elif coord[0] in ['S', 'W']:
        return int(coord[1:])*(-1)
    else:
        print('invalid input to coord_converter')
        return

def fabdem_big_tile_matcher(small_tile_lat, small_tile_lon):
    small_tile_lat = coord_converter(small_tile_lat)
    small_tile_lon = coord_converter(small_tile_lon)
    
    import math

    big_tile_lat = math.floor(small_tile_lat/10) * 10
    big_tile_lon = math.floor(small_tile_lon/10) * 10

    big_tile_lat = f'{"S" if big_tile_lat < 0 else "N"}{str(abs(big_tile_lat)).zfill(2)}'
    big_tile_lon = f'{"W" if big_tile_lon < 0 else "E"}{str(abs(big_tile_lon)).zfill(3)}'

    return big_tile_lat, big_tile_lon

def fabdem_tile_end_matcher(tile_starter):
    if tile_starter == 'S10':
        return 'N00'
    elif tile_starter == 'W010':
        return 'E000'
    elif tile_starter[0] == 'N' or tile_starter[0] == 'E':
        return f'{tile_starter[0]}{str(int(tile_starter[1:]) + 10).zfill(len(tile_starter) - 1)}'
    elif tile_starter[0] == 'S' or tile_starter[0] == 'W':
        return f'{tile_starter[0]}{str(int(tile_starter[1:]) - 10).zfill(len(tile_starter) - 1)}'
    else:
        print('fabdem_tile_end_matcher function error')
        print('Invalid input. How did this happen?')

def download_raster(download_list, local_data_dir, data_bucket, data_bucket_dir):
    # download requested raster file(s) and return a list of downloaded raster file(s)
    if not download_list:
        print('download_raster function error: download_list is empty')
        exit()

    import requests
    import core.py as utils
    
    downloaded_list = []

    for f in download_list:
        dl_file_name = f.split('/')[-1]

        if utils.download_blob(data_bucket, f'{data_bucket_dir}/{dl_file_name}', f'{local_data_dir}/{dl_file_name}'):
            downloaded_list.append(f'{local_data_dir}/{dl_file_name}')
        else:
            try:
                print(f'downloading {dl_file_name}')
                dl_file = requests.get(f)
                if dl_file.status_code == 200:
                    open(f'{local_data_dir}/{dl_file_name}', 'wb').write(dl_file.content)
                    if utils.upload_blob(data_bucket, f'{local_data_dir}/{dl_file_name}', f'{data_bucket_dir}/{dl_file_name}', type='data'):
                        downloaded_list.append(f'{local_data_dir}/{dl_file_name}')
                else:
                    print(f"Failed to download. HTTP status code: {dl_file.status_code}")
            except Exception as e:
                print(f'{dl_file} download exception: {e}')
    
    return downloaded_list

def mosaic_raster(mosaic_list, local_output_dir, mosaic_file, method = 'first'):
    # mosaic or rename raster file(s) as needed
    import os
    import rasterio
    from rasterio.merge import merge

    # Filter to only existing files (cloud paths may 404).
    # Use rasterio (always available via requirements.txt) — opening in read
    # mode hits GDAL's internal stat/HEAD without loading data. Silence the
    # rasterio._env logger during probes so expected 404s on non-existent
    # tiles (e.g. fallback naming attempts) don't spam the user's console.
    import logging
    rio_env_logger = logging.getLogger('rasterio._env')
    prev_level = rio_env_logger.level
    rio_env_logger.setLevel(logging.ERROR + 1)
    try:
        valid_list = []
        for p in mosaic_list:
            if p.startswith('/vsi'):
                try:
                    with rasterio.open(p):
                        valid_list.append(p)
                except rasterio.errors.RasterioIOError:
                    continue
            elif os.path.exists(p):
                valid_list.append(p)
    finally:
        rio_env_logger.setLevel(prev_level)
    mosaic_list = valid_list

    if len(mosaic_list) > 1:
        try:
            dst_path = f'{local_output_dir}/{mosaic_file}'
            merge(mosaic_list, method=method, dst_path=dst_path)
        except MemoryError:
            print('MemoryError when merging raster files:')
            print(mosaic_list)
            print('Try downloading raw files from cloud storage and using GIS for merging.')
    elif len(mosaic_list) == 1:
        src_path = mosaic_list[0]
        dst_path = f'{local_output_dir}/{mosaic_file}'
        # Can't os.rename cloud paths (/vsigs/, /vsicurl/) — read and write instead
        if src_path.startswith('/vsi'):
            with rasterio.open(src_path) as src:
                with rasterio.open(dst_path, 'w', **src.meta) as dst:
                    dst.write(src.read())
        else:
            os.rename(src_path, dst_path)

def reproject_raster(src_raster_path, dst_raster_path, dst_crs=None, target_raster_path=None, compress=None):
    """
    Reproject a raster to a new CRS, with an option to match the grid to a target raster.
    
    Parameters:
        src_raster_path (str): Path to the input raster.
        dst_raster_path (str): Path to the output raster.
        dst_crs (str, optional): The target CRS (e.g., 'EPSG:4326'). Ignored if target_raster_path is provided.
        target_raster_path (str, optional): Path to the target raster to match the CRS and grid.
    
    Raises:
        ValueError: If neither dst_crs nor target_raster_path is provided.
    """

    import rasterio
    from rasterio.warp import calculate_default_transform, reproject, Resampling

    # Check if both dst_crs and target_raster_path are None
    if dst_crs is None and target_raster_path is None:
        raise ValueError("Either 'dst_crs' or 'target_raster_path' must be specified.")
    
    # If target_raster_path is provided, use its CRS and transform
    if target_raster_path:
        with rasterio.open(target_raster_path) as target_raster:
            dst_crs = target_raster.crs  # Use the CRS from the target raster
            target_transform = target_raster.transform
            target_meta = target_raster.meta.copy()

    # Open the source raster
    with rasterio.open(src_raster_path) as src_raster:
        
        # If we are not matching a target raster, calculate the default transform
        if not target_raster_path:
            transform, width, height = calculate_default_transform(
                src_raster.crs, dst_crs, src_raster.width, src_raster.height, *src_raster.bounds)
        else:
            # Use the target raster's transform (i.e., match its grid)
            transform = target_transform
            width = target_meta['width']
            height = target_meta['height']

        # Create output raster metadata
        dst_meta = src_raster.meta.copy()
        dst_meta.update({
            'crs': dst_crs,
            'transform': transform,
            'width': width,
            'height': height
        })
        # Opt-in compression (default off = unchanged for existing callers).
        # Fathom passes this so its national UTM output stays small on Cloud
        # Run's memory-backed filesystem.
        if compress:
            dst_meta.update({'compress': compress, 'tiled': True,
                             'blockxsize': 512, 'blockysize': 512,
                             'interleave': 'band'})

        # Open the destination raster for writing
        with rasterio.open(dst_raster_path, 'w', **dst_meta) as dst_raster:
            # Reproject and write to the new file
            for i in range(1, src_raster.count + 1):
                reproject(
                    source=rasterio.band(src_raster, i),
                    destination=rasterio.band(dst_raster, i),
                    src_transform=src_raster.transform,
                    src_crs=src_raster.crs,
                    dst_transform=transform,
                    dst_crs=dst_crs,
                    resampling=Resampling.nearest
                )

def get_raster_histogram(input_raster, bins, output_csv):
    import rasterio
    import numpy as np
    import csv

    with rasterio.open(input_raster) as src:
        # Read raster data
        raster_data = src.read(1)
        
        # Calculate histogram
        hist, _ = np.histogram(raster_data, bins=bins)
        
        # Write bins and hist to a CSV file
        with open(output_csv, 'w', newline='') as csvfile:
            writer = csv.writer(csvfile)
            writer.writerow(['Bin', 'Count'])
            for i, count in enumerate(hist):
                bin_range = f"{bins[i]}-{bins[i+1]}"
                writer.writerow([bin_range, count])

def calculate_raster_area(input_raster, value_list):
    import rasterio
    import numpy as np

    with rasterio.open(input_raster) as src:
        pixelSizeX, pixelSizeY = src.res
        array = src.read()

        value_dict = {}
        for v in value_list:
            value_dict[v] = np.count_nonzero(array == v) * pixelSizeX * pixelSizeY

        return value_dict