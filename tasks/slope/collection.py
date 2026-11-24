from core.py.log_module import setup_logger
logger = setup_logger(__name__)
import requests
import shutil


def datacollection(
    aoi,
    city_name,
    output_dir,
    return_raster=False,
):
    """
    Extract or download FABDEM elevation raster tiles from output folders, perform slope calculation,
    clip to AOI, and save as a city-level slope raster.

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

    Returns
    -------
    (numpy.ndarray, dict) or None
        Clipped raster array and rasterio metadata if return_raster=True,
        otherwise None.
    """

    import os
    import numpy as np
    import geopandas as gpd
    import rasterio
    from rasterio.warp import calculate_default_transform, reproject, Resampling
    from rasterio.mask import mask

    # ------------------------------------------------------------------
    # 1. Normalize AOI CRS
    # ------------------------------------------------------------------
    if aoi.crs is None or aoi.crs.to_epsg() != 4326:
        aoi = aoi.to_crs(epsg=4326)

    aoi_geom = aoi.geometry.values

    spatial_dir = os.path.join(output_dir, "spatial")
    elev_buf_path = os.path.join(spatial_dir, f"{city_name}_elevation_buf.tif")
    slope_output_path = os.path.join(spatial_dir, f"{city_name}_slope.tif")

    # ------------------------------------------------------------------
    # 2. Ensure buffered elevation exists
    # ------------------------------------------------------------------
    if not os.path.exists(elev_buf_path):
        from tasks.elevation import datacollection as elev_collect

        elev_collect.datacollection(
            aoi=aoi,
            city_name=city_name,
            output_dir=output_dir,
            return_raster=False,
            create_raster_buffer=True,
        )

    import math
    from rasterio.vrt import WarpedVRT
    from rasterio.windows import Window
    from rasterio.features import geometry_mask

    STRIP = 2048
    minx, miny, maxx, maxy = aoi.total_bounds

    # ------------------------------------------------------------------
    # 3a. Continental AOI (> ~6° of longitude): a single UTM zone is invalid and
    #     the UTM reproject OOMs (a thin output strip warps from a huge skewed
    #     source region). Compute slope directly in EPSG:4326 with latitude-
    #     corrected pixel spacing (identical slope math), strip-windowed with a
    #     1-row halo, clipped to the AOI. No UTM, no reproject.
    # ------------------------------------------------------------------
    if (maxx - minx) > 6.0:
        aoi_shapes = [geom.__geo_interface__ for geom in aoi.geometry]
        M_PER_DEG = 111320.0
        # Delete any stale output first. GCS-FUSE uses memory-buffered "staged
        # writes" for an EXISTING object — it holds the whole multi-GB file in RAM
        # until close (OOM). For a NEW file written sequentially it uses "streaming
        # writes" (bounded buffer). So: remove stale file + write a STRIPED tiff
        # top-to-bottom (sequential) to stay in streaming mode.
        if os.path.exists(slope_output_path):
            os.remove(slope_output_path)
        SH = 512   # full-width strip height; one strip ~0.3GB, writes are sequential
        with rasterio.open(elev_buf_path) as src:
            px_deg = src.transform.a
            py_deg = -src.transform.e
            sox, soy = src.transform.c, src.transform.f      # src origin (top-left)
            col0 = max(0, math.floor((minx - sox) / px_deg))
            row0 = max(0, math.floor((soy - maxy) / py_deg))
            col1 = min(src.width, math.ceil((maxx - sox) / px_deg))
            row1 = min(src.height, math.ceil((soy - miny) / py_deg))
            out_w, out_h = col1 - col0, row1 - row0
            out_transform = rasterio.transform.from_origin(
                sox + col0 * px_deg, soy - row0 * py_deg, px_deg, py_deg)
            profile = {
                "driver": "GTiff", "count": 1, "dtype": "float32",
                "crs": "EPSG:4326", "transform": out_transform,
                "width": out_w, "height": out_h, "nodata": np.nan,
                "compress": "lzw", "BIGTIFF": "YES", "blockysize": SH,
            }
            py_m = py_deg * M_PER_DEG
            n = math.ceil(out_h / SH)
            logger.info(f"Slope: continental EPSG:4326 path, {out_w}x{out_h}px, {n} strips (streaming)")
            with rasterio.Env(GDAL_CACHEMAX=256):
                with rasterio.open(slope_output_path, "w", **profile) as dst:
                    for i, r in enumerate(range(0, out_h, SH)):
                        h = min(SH, out_h - r)
                        r0 = max(0, row0 + r - 1)                 # 1-row halo above
                        r1 = min(src.height, row0 + r + h + 1)    # and below
                        elev = src.read(1, window=Window(col0, r0, out_w, r1 - r0)).astype(np.float32)
                        if src.nodata is not None:
                            elev[elev == src.nodata] = np.nan
                        lat_c = soy - (row0 + r + h / 2.0) * py_deg   # strip-center latitude
                        px_m = px_deg * M_PER_DEG * math.cos(math.radians(lat_c))
                        dy, dx = np.gradient(elev, py_m, px_m)
                        slope = np.degrees(np.arctan(np.sqrt(dx ** 2 + dy ** 2)))
                        slope[np.isnan(elev)] = np.nan
                        top = (row0 + r) - r0                     # halo rows to skip
                        out = np.array(slope[top:top + h, :])
                        strip_tf = rasterio.windows.transform(Window(0, r, out_w, h), out_transform)
                        inside = geometry_mask(aoi_shapes, out_shape=(h, out_w),
                                               transform=strip_tf, invert=True)
                        out[~inside] = np.nan
                        dst.write(out.astype(np.float32), 1, window=Window(0, r, out_w, h))
                        del elev, dy, dx, slope, out, inside
                        if i % 25 == 0:
                            logger.info(f"Slope: strip {i}/{n}")
        logger.info(f"Writing slope raster (continental EPSG:4326 path): {slope_output_path}")
        if return_raster:
            with rasterio.open(slope_output_path) as src:
                return src.read(), src.meta.copy()
        return None

    # ------------------------------------------------------------------
    # 3. Select projected CRS for slope math (small AOI: one valid UTM zone)
    # ------------------------------------------------------------------
    utm_crs = aoi.estimate_utm_crs()

    slope_proj_path = os.path.join(spatial_dir, f"{city_name}_slope_proj.tif")

    # ------------------------------------------------------------------
    # 4. Reproject elevation to UTM + compute slope, at NATIVE resolution.
    #    Processed in row strips (with a 1-row halo so np.gradient's central
    #    difference is exact at strip seams) so the full national grid + the
    #    ~6 gradient/arctan copies are never held in RAM. WarpedVRT does the
    #    reprojection lazily — no full UTM array is materialised.
    # ------------------------------------------------------------------
    with rasterio.open(elev_buf_path) as src:
        src_nodata = src.nodata
        with WarpedVRT(src, crs=utm_crs, resampling=Resampling.bilinear,
                       src_nodata=src_nodata, nodata=np.nan) as vrt:
            width, height = vrt.width, vrt.height
            transform = vrt.transform
            pixel_x = transform.a
            pixel_y = -transform.e

            profile = {
                "driver": "GTiff", "count": 1, "dtype": "float32",
                "crs": utm_crs, "transform": transform,
                "width": width, "height": height, "nodata": np.nan,
                "tiled": True, "compress": "lzw", "BIGTIFF": "IF_SAFER",
            }

            with rasterio.open(slope_proj_path, "w", **profile) as dst:
                for r in range(0, height, STRIP):
                    h = min(STRIP, height - r)
                    r0 = max(0, r - 1)                 # 1-row halo above
                    r1 = min(height, r + h + 1)        # and below
                    elev = vrt.read(1, window=Window(0, r0, width, r1 - r0)).astype(np.float32)
                    # WarpedVRT already maps source nodata -> nan
                    dy, dx = np.gradient(elev, pixel_y, pixel_x)
                    slope = np.degrees(np.arctan(np.sqrt(dx ** 2 + dy ** 2)))
                    slope[np.isnan(elev)] = np.nan
                    top = r - r0                       # halo rows to skip (0 or 1)
                    dst.write(slope[top:top + h, :].astype(np.float32), 1,
                              window=Window(0, r, width, h))

    # ------------------------------------------------------------------
    # 5. Reproject slope back to EPSG:4326 and clip to the AOI, windowed.
    #    Output grid = AOI bounds snapped to the reprojected pixel grid
    #    (mirrors wsf mosaic_tiles); each strip is masked outside the AOI.
    # ------------------------------------------------------------------
    aoi_shapes = [geom.__geo_interface__ for geom in aoi.geometry]
    with rasterio.open(slope_proj_path) as src:
        with WarpedVRT(src, crs="EPSG:4326", resampling=Resampling.bilinear,
                       nodata=np.nan) as vrt:
            vres_x = vrt.transform.a
            vres_y = -vrt.transform.e
            vox, voy = vrt.transform.c, vrt.transform.f  # vrt grid origin (top-left)

            minx, miny, maxx, maxy = aoi.total_bounds
            col0 = max(0, math.floor((minx - vox) / vres_x))
            row0 = max(0, math.floor((voy - maxy) / vres_y))
            col1 = min(vrt.width, math.ceil((maxx - vox) / vres_x))
            row1 = min(vrt.height, math.ceil((voy - miny) / vres_y))
            out_w, out_h = col1 - col0, row1 - row0
            out_transform = rasterio.transform.from_origin(
                vox + col0 * vres_x, voy - row0 * vres_y, vres_x, vres_y)

            out_profile = {
                "driver": "GTiff", "count": 1, "dtype": "float32",
                "crs": "EPSG:4326", "transform": out_transform,
                "width": out_w, "height": out_h, "nodata": np.nan,
                "tiled": True, "compress": "lzw", "BIGTIFF": "IF_SAFER",
            }

            with rasterio.open(slope_output_path, "w", **out_profile) as dst:
                for r in range(0, out_h, STRIP):
                    h = min(STRIP, out_h - r)
                    data = vrt.read(1, window=Window(col0, row0 + r, out_w, h)).astype(np.float32)
                    strip_tf = rasterio.windows.transform(Window(0, r, out_w, h), out_transform)
                    inside = geometry_mask(aoi_shapes, out_shape=(h, out_w),
                                           transform=strip_tf, invert=True)
                    data[~inside] = np.nan
                    dst.write(data, 1, window=Window(0, r, out_w, h))

    logger.info(f"Writing slope raster: {slope_output_path}")

    # ------------------------------------------------------------------
    # 6. Optional return (reads the written raster back)
    # ------------------------------------------------------------------
    if return_raster:
        with rasterio.open(slope_output_path) as src:
            return src.read(), src.meta.copy()

    return None


