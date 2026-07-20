from core.py.log_module import setup_logger
logger = setup_logger(__name__)

# Tracks which data source was used (set by collection functions)
data_source = None

def normalize_fabdem_tile_name(tile_name: str) -> str:
    """
    Normalize FABDEM tile name to match filenames inside ZIP archives.
    FABDEM uses 2-digit latitude, 3-digit longitude (e.g. N36E010).

    Examples
    --------
    N036E010 -> N36E010
    S003W098 -> S3W098
    N15E120  -> N15E120
    """
    import re

    match = re.match(r"([NS])0*(\d+)([EW])0*(\d+)", tile_name)
    if not match:
        return tile_name

    lat_hem, lat_deg, lon_hem, lon_deg = match.groups()
    return f"{lat_hem}{int(lat_deg)}{lon_hem}{int(lon_deg):03d}"



def identify_tiles(aoi, bucket_base):
    """
    Load the FABDEM tile index from GCS and find tiles intersecting the AOI.

    Parameters
    ----------
    aoi : geopandas.GeoDataFrame
        AOI polygon(s) in EPSG:4326.
    bucket_base : str
        Base URL of the public GCS bucket.

    Returns
    -------
    geopandas.GeoDataFrame
        Rows from the tile index whose geometries intersect the AOI.
    """
    import geopandas as gpd

    logger.info("Loading FABDEM tile index")
    tile_index_path = "fabdem/FABDEM_v1-2_tiles.geojson"
    fabdem_tiles = gpd.read_file(bucket_base + tile_index_path)

    logger.info("Intersecting AOI with FABDEM tiles")
    intersecting = fabdem_tiles[fabdem_tiles.intersects(aoi.unary_union)]

    if intersecting.empty:
        logger.error("No FABDEM tiles found for AOI")
        raise RuntimeError("No FABDEM tiles found for AOI")

    tile_names = intersecting["tile_name"].unique().tolist()
    zip_files = intersecting["zipfile_name"].unique().tolist()
    logger.info(tile_names)
    logger.info(zip_files)
    logger.info(
        f"Found {len(tile_names)} FABDEM tiles across {len(zip_files)} ZIP archives"
    )

    return intersecting


def read_elevation_tiffs(intersecting, bucket_base):
    """
    Open FABDEM TIFFs directly from remote ZIP archives via GDAL virtual paths.

    Parameters
    ----------
    intersecting : geopandas.GeoDataFrame
        Intersecting tile rows with columns ``tile_name`` and ``zipfile_name``.
    bucket_base : str
        Base URL of the public GCS bucket.

    Returns
    -------
    list
        Open rasterio dataset handles. Caller is responsible for closing.
    """
    import rasterio

    logger.info("Opening FABDEM TIFFs directly from remote ZIP archives")

    src_files = []
    attempted = 0
    successful = 0

    pairs = (
        intersecting[["tile_name", "zipfile_name"]]
        .drop_duplicates()
        .itertuples(index=False)
    )

    for tile_name, zip_name in pairs:
        normalized_tile = normalize_fabdem_tile_name(tile_name)
        member_name = f"{normalized_tile}_FABDEM_V1-2.tif"
        zip_url = f"{bucket_base}fabdem/{zip_name}"
        remote_tif_path = f"/vsizip//vsicurl/{zip_url}/{member_name}"
        attempted += 1

        logger.debug(f"Opening remote TIFF: {remote_tif_path}")
        try:
            src = rasterio.open(remote_tif_path)
            src_files.append(src)
            successful += 1
        except Exception as e:
            logger.warning(
                f"Failed to open remote TIFF {member_name} from {zip_name}: {e}"
            )

    logger.info(f"Opened {successful}/{attempted} remote FABDEM TIFFs")
    return src_files


def mosaic_tiles(src_files):
    """
    Mosaic a list of open rasterio datasets into a single array.

    Parameters
    ----------
    src_files : list
        Open rasterio dataset handles.

    Returns
    -------
    tuple
        (mosaic_array, mosaic_meta) — array and rasterio metadata dict.
    """
    from rasterio.merge import merge

    logger.info("Mosaicing FABDEM tiles")
    mosaic_array, mosaic_transform = merge(src_files)

    mosaic_meta = src_files[0].meta.copy()
    mosaic_meta.update({
        "height": mosaic_array.shape[1],
        "width": mosaic_array.shape[2],
        "transform": mosaic_transform,
    })

    return mosaic_array, mosaic_meta


def clip_raster_to_buffered_aoi(aoi, mosaic_array, mosaic_meta, buffer_m=500):
    """
    Buffer the AOI by ``buffer_m`` metres and clip the mosaic to that extent.

    Parameters
    ----------
    aoi : geopandas.GeoDataFrame
        AOI polygon(s) in EPSG:4326.
    mosaic_array : numpy.ndarray
        Raster array from a mosaic operation.
    mosaic_meta : dict
        Rasterio metadata dict for the mosaic.
    buffer_m : int, optional
        Buffer distance in metres. Default 500.

    Returns
    -------
    tuple
        (buf_array, buf_meta)
    """
    import rasterio
    from rasterio.mask import mask

    logger.info("Clipping elevation to buffered AOI")

    utm_crs = aoi.estimate_utm_crs()
    aoi_utm = aoi.to_crs(utm_crs)
    buffered = aoi_utm.buffer(buffer_m)
    buffered_wgs = buffered.to_crs(epsg=4326)
    buffered_geom = buffered_wgs.values

    with rasterio.io.MemoryFile() as memfile:
        with memfile.open(**mosaic_meta) as dataset:
            dataset.write(mosaic_array)

            buf_array, buf_transform = mask(
                dataset,
                buffered_geom,
                crop=True,
                nodata=mosaic_meta.get("nodata"),
            )

            buf_meta = dataset.meta.copy()
            buf_meta.update({
                "height": buf_array.shape[1],
                "width": buf_array.shape[2],
                "transform": buf_transform,
            })

    return buf_array, buf_meta


def gee_fabdem(aoi, city_name, output_dir, return_raster=False, create_raster_buffer=True):
    """Fallback 1: download FABDEM from GEE community catalog when GCS zip is unavailable."""
    import os
    import ee
    import geopandas as gpd
    from core.py import gee_fns as fns

    logger.info("Starting GEE FABDEM elevation data collection...")
    global data_source

    try:
        fabdem = ee.ImageCollection("projects/sat-io/open-datasets/FABDEM").mosaic()

        spatial_dir = os.path.join(output_dir, "spatial")
        os.makedirs(spatial_dir, exist_ok=True)

        elev_rio = fns.tiled_collection(fabdem, aoi, scale=30)
        elev_rio = elev_rio.rio.clip(aoi.to_crs(elev_rio.rio.crs).geometry, drop=True)
        tif_path = os.path.join(spatial_dir, f"{city_name}_elevation.tif")
        elev_rio.rio.to_raster(tif_path)
        data_source = "FABDEM (GEE)"
        logger.info(f"Elevation raster saved to: {tif_path}")

        if create_raster_buffer:
            aoi_buf = gpd.GeoDataFrame(geometry=aoi.buffer(0.001), crs=aoi.crs)
            elev_buf_rio = fns.tiled_collection(fabdem, aoi_buf, scale=30)
            tif_path_buf = os.path.join(spatial_dir, f"{city_name}_elevation_buf.tif")
            elev_buf_rio.rio.to_raster(tif_path_buf)
            logger.info(f"Buffered elevation raster saved to: {tif_path_buf}")

        if return_raster:
            return elev_rio, elev_buf_rio if create_raster_buffer else None

        return None

    except Exception as e:
        logger.warning(f"GEE FABDEM failed: {e} — falling back to SRTM")
        return gee_srtm(aoi, city_name, output_dir, return_raster, create_raster_buffer)


def gee_srtm(aoi, city_name, output_dir, return_raster=False, create_raster_buffer=True):
    """Fallback 2: download SRTM elevation from GEE when FABDEM is unavailable."""
    import os
    import ee
    import geopandas as gpd
    from core.py import gee_fns as fns

    logger.info("Starting GEE SRTM elevation data collection...")
    global data_source
    data_source = "SRTM (GEE)"

    elevation = ee.Image("USGS/SRTMGL1_003")

    spatial_dir = os.path.join(output_dir, "spatial")
    os.makedirs(spatial_dir, exist_ok=True)

    elev_rio = fns.tiled_collection(elevation, aoi, scale=30)
    elev_rio = elev_rio.rio.clip(aoi.to_crs(elev_rio.rio.crs).geometry, drop=True)
    tif_path = os.path.join(spatial_dir, f"{city_name}_elevation.tif")
    elev_rio.rio.to_raster(tif_path)
    logger.info(f"Elevation raster saved to: {tif_path}")

    if create_raster_buffer:
        aoi_buf = gpd.GeoDataFrame(geometry=aoi.buffer(0.001), crs=aoi.crs)
        elev_buf_rio = fns.tiled_collection(elevation, aoi_buf, scale=30)
        tif_path_buf = os.path.join(spatial_dir, f"{city_name}_elevation_buf.tif")
        elev_buf_rio.rio.to_raster(tif_path_buf)
        logger.info(f"Buffered elevation raster saved to: {tif_path_buf}")

    if return_raster:
        return elev_rio, elev_buf_rio if create_raster_buffer else None

    return None


def datacollection(
    aoi,
    city_name,
    output_dir,
    return_raster=False,
    create_raster_buffer=True,
):
    """
    Download FABDEM raster tiles from internal cloud storage, mosaic,
    clip to AOI, and save as a city-level elevation raster.

    Parameters
    ----------
    aoi : geopandas.GeoDataFrame
        AOI polygon(s). Must be convertible to EPSG:4326.
    city_name : str
        City name used for output file naming.
    output_dir : str
        Base directory where outputs will be written.
    return_raster : bool, optional
        If True, return clipped raster array and metadata.
    create_raster_buffer : bool, optional
        If True, raster will be clipped to buffered AOI (used for slope analysis)

    Returns
    -------
    (numpy.ndarray, dict) or None
        Clipped raster array and rasterio metadata if return_raster=True,
        otherwise None.
    """
    import os
    import rasterio
    from rasterio.mask import mask

    # ------------------------------------------------------------------
    # 1. Normalize AOI CRS
    # ------------------------------------------------------------------
    logger.info("Normalizing AOI CRS to EPSG:4326")

    if aoi.crs is None or aoi.crs.to_epsg() != 4326:
        aoi = aoi.to_crs(epsg=4326)

    aoi_geom = aoi.geometry.values

    # ------------------------------------------------------------------
    # 2. Prepare output directories
    # ------------------------------------------------------------------
    spatial_dir = os.path.join(output_dir, "spatial")
    os.makedirs(spatial_dir, exist_ok=True)

    output_raster_path = os.path.join(
        spatial_dir, f"{city_name}_elevation.tif"
    )

    bucket_base = "https://storage.googleapis.com/city-scan-global-public/"

    # ------------------------------------------------------------------
    # 3-4. Identify intersecting FABDEM tiles
    # ------------------------------------------------------------------
    intersecting = identify_tiles(aoi, bucket_base)

    # ------------------------------------------------------------------
    # 5. Open FABDEM TIFFs from remote ZIP archives
    # ------------------------------------------------------------------
    src_files = read_elevation_tiffs(intersecting, bucket_base)

    if not src_files:
        logger.warning("No FABDEM TIFFs opened from remote ZIPs — trying FABDEM from GEE")
        return gee_fabdem(aoi, city_name, output_dir, return_raster, create_raster_buffer)

    global data_source
    data_source = "FABDEM (GCS)"

    try:
        # ------------------------------------------------------------------
        # 6. Mosaic tiles
        # ------------------------------------------------------------------
        mosaic_array, mosaic_meta = mosaic_tiles(src_files)

        # ------------------------------------------------------------------
        # 7. Clip mosaic to AOI
        # ------------------------------------------------------------------
        logger.info("Clipping mosaic to AOI")

        with rasterio.io.MemoryFile() as memfile:
            with memfile.open(**mosaic_meta) as dataset:
                dataset.write(mosaic_array)

                clipped_array, clipped_transform = mask(
                    dataset,
                    aoi_geom,
                    crop=True,
                    nodata=mosaic_meta.get("nodata"),
                )

                clipped_meta = dataset.meta.copy()
                clipped_meta.update({
                    "height": clipped_array.shape[1],
                    "width": clipped_array.shape[2],
                    "transform": clipped_transform,
                })

        # ------------------------------------------------------------------
        # 8. Write output raster
        # ------------------------------------------------------------------
        logger.info(f"Writing elevation raster to {output_raster_path}")

        with rasterio.open(output_raster_path, "w", **clipped_meta) as dst:
            dst.write(clipped_array)

        # ------------------------------------------------------------------
        # 9. Clip raster to buffered AOI (for slope analysis)
        # ------------------------------------------------------------------
        if create_raster_buffer:
            logger.info("Creating buffered AOI for slope-safe raster")

            buf_array, buf_meta = clip_raster_to_buffered_aoi(
                aoi, mosaic_array, mosaic_meta
            )

            buf_output_path = os.path.join(
                spatial_dir, f"{city_name}_elevation_buf.tif"
            )

            logger.info(f"Writing buffered elevation raster: {buf_output_path}")

            with rasterio.open(buf_output_path, "w", **buf_meta) as dst:
                dst.write(buf_array)

    finally:
        for src in src_files:
            src.close()

    # ------------------------------------------------------------------
    # 10. Optional return
    # ------------------------------------------------------------------
    if return_raster:
        return clipped_array, clipped_meta

    return None
