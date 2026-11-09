import ee
import numpy
import xee


# Flatten a geometry to 2D by removing Z coordinates, if present
def flatten_to_2d(geom):
    import shapely
    
    if geom.has_z:
        # If it's a Polygon, handle the exterior and any interiors (holes)
        if geom.geom_type == 'Polygon':
            # Convert to 2D by ignoring the Z coordinate
            new_exterior = [(x, y) for x, y, _ in geom.exterior.coords]
            new_interiors = [[(x, y) for x, y, _ in interior.coords] for interior in geom.interiors]
            return shapely.geometry.Polygon(new_exterior, new_interiors)
        
        # If it's a MultiPolygon, process each Polygon within it
        elif geom.geom_type == 'MultiPolygon':
            new_polygons = []
            for polygon in geom.geoms:
                new_exterior = [(x, y) for x, y, _ in polygon.exterior.coords]
                new_interiors = [[(x, y) for x, y, _ in interior.coords] for interior in polygon.interiors]
                new_polygons.append(shapely.geometry.Polygon(new_exterior, new_interiors))
            return shapely.geometry.MultiPolygon(new_polygons)
    
    # Return the geometry unchanged if it does not have Z coordinates or is not a Polygon/MultiPolygon
    return geom

# returns an ee.Geometry object and its bounds 
def aoi_to_ee_geometry(aoi_file):
    import shapely

    # Conver to 4326
    aoi_file = aoi_file.to_crs(epsg=4326)

    # Remove Z coordinates (convert to 2D)
    aoi_file['geometry'] = aoi_file['geometry'].apply(flatten_to_2d)
    
    AOI = ee.Geometry(shapely.geometry.mapping(aoi_file.unary_union))
    bounds = AOI.bounds()
    
    return AOI, bounds


# simple function to create daterange filter and bounds (for image collection)
def create_criteria(aoi, first_year, last_year):
      return ee.Filter.And(
          ee.Filter.calendarRange(first_year, last_year, 'year'),
          ee.Filter.bounds(aoi)
      )



def make_tiles(aoi, tile_size_deg=0.5):
    """
    Split AOI into tiles for large-area GEE collection.
    Returns list of (tile_bounds, tile_ee_geometry) tuples.
    If AOI fits in a single tile, returns [(aoi_bounds, aoi_ee_geometry)].
    """
    import math
    from shapely.geometry import box

    aoi_4326 = aoi.to_crs(4326)
    xmin, ymin, xmax, ymax = aoi_4326.total_bounds

    # Check if AOI fits in a single tile
    if (xmax - xmin) <= tile_size_deg and (ymax - ymin) <= tile_size_deg:
        AOI, bounds = aoi_to_ee_geometry(aoi)
        return [(aoi_4326.total_bounds, AOI)]

    # Create tile grid
    nx = math.ceil((xmax - xmin) / tile_size_deg)
    ny = math.ceil((ymax - ymin) / tile_size_deg)

    tiles = []
    aoi_union = aoi_4326.unary_union

    for ix in range(nx):
        for iy in range(ny):
            tx0 = xmin + ix * tile_size_deg
            ty0 = ymin + iy * tile_size_deg
            tx1 = min(tx0 + tile_size_deg, xmax)
            ty1 = min(ty0 + tile_size_deg, ymax)

            tile_box = box(tx0, ty0, tx1, ty1)
            if not tile_box.intersects(aoi_union):
                continue

            tile_geom = tile_box.intersection(aoi_union)
            if tile_geom.is_empty:
                continue

            import shapely.geometry
            tile_ee = ee.Geometry(shapely.geometry.mapping(flatten_to_2d(tile_geom)))
            tiles.append(((tx0, ty0, tx1, ty1), tile_ee))

    return tiles


def _export_image_to_cloud(image, aoi, out_path, scale, dtype, nodata=0,
                           fillna=None, round_vals=False, resampling=None,
                           transform_fn=None, bucket='crp-city-scan',
                           crs='EPSG:4326', poll_s=30, timeout_s=12 * 3600):
    """Cloud Run path for tiled_collection: export the image SERVER-SIDE via
    ee.batch.Export.image.toCloudStorage, landing the COG straight at out_path's
    GCS object. No pixels are pulled locally — no xee, no interactive EECU. The
    export bills to the container's ambient EE project (crp on Cloud Run).

    Post-processing mirrors the local strip-write path but is expressed on the
    ee.Image: fillna -> unmask, round_vals -> round, dtype -> toX cast, clip to
    AOI. transform_fn (numpy, e.g. landcover snap) is NOT expressible server-side
    and is skipped — native-res nearest export preserves categorical codes.
    """
    import time, os, glob, subprocess, logging
    from core.py.log_module import setup_logger
    logger = setup_logger(__name__)

    if transform_fn is not None:
        logger.warning("transform_fn not expressible server-side; skipped in cloud export")

    AOI, _ = aoi_to_ee_geometry(aoi)

    img = image
    if fillna is not None:
        img = img.unmask(fillna)
    if round_vals:
        img = img.round()
    _cast = {'int8': 'toInt8', 'uint8': 'toUint8', 'int16': 'toInt16',
             'uint16': 'toUint16', 'int32': 'toInt32', 'uint32': 'toUint32',
             'float32': 'toFloat', 'float64': 'toDouble'}.get(str(dtype))
    if _cast:
        img = getattr(img, _cast)()
    img = img.clip(AOI)

    # out_path is on the FUSE-mounted bucket (gs://crp-city-scan at /app/mnt), so
    # the GCS object key = everything after the mount root. EE appends '.tif'.
    marker = os.sep + "mnt" + os.sep
    object_key = out_path.split(marker, 1)[1] if marker in out_path else os.path.basename(out_path)
    prefix = object_key[:-4] if object_key.endswith(".tif") else object_key

    task = ee.batch.Export.image.toCloudStorage(
        image=img,
        description=os.path.basename(prefix)[:100],
        bucket=bucket,
        fileNamePrefix=prefix,
        region=AOI,
        scale=scale,
        crs=crs,
        maxPixels=int(1e13),
        fileFormat="GeoTIFF",
        formatOptions={"cloudOptimized": True},
    )
    task.start()
    logger.info(f"Cloud export started: gs://{bucket}/{prefix}.tif  (task {task.id}, scale {scale}m)")

    waited = 0
    timed_out = False
    while True:
        status = task.status()
        state = status.get("state")
        if state == "COMPLETED":
            break
        if state in ("FAILED", "CANCELLED", "CANCEL_REQUESTED"):
            raise RuntimeError(f"Cloud export {state}: {status.get('error_message')}")
        if waited >= timeout_s:
            # Poll gave up, but EE may already have written the output — batch-queue
            # congestion can outlast the poll. Fall through to shard detection and
            # salvage whatever was produced; only fail if nothing was written.
            logger.warning(f"Cloud export poll gave up after {waited}s (task {task.id}, "
                           f"state {state}); checking for output written so far")
            timed_out = True
            break
        time.sleep(poll_s)
        waited += poll_s

    # EE either wrote a single COG at out_path, or (for large AOIs) sharded into
    # {stem}NNNNNNNNNN-NNNNNNNNNN.tif tiles. Detect shards by their NUMERIC suffix
    # — a bare {stem}*.tif glob would also match a stale/pre-existing out_path or a
    # sibling like {stem}_buf.tif. Shard existence (not out_path existence) decides
    # whether we mosaic, so a stale leftover out_path can't short-circuit it.
    stem = out_path[:-4]
    shards = []
    for _ in range(6):  # let GCS-FUSE see the just-written objects
        shards = sorted(glob.glob(stem + "[0-9]*.tif"))
        if shards:
            break
        time.sleep(10)
    if shards:
        logger.warning(f"Cloud export sharded into {len(shards)} files; mosaicking → {out_path}")
        vrt = stem + ".mosaic.vrt"
        subprocess.run(['gdalbuildvrt', '-q', vrt] + shards, check=True)
        subprocess.run(['gdal_translate', '-q', '-of', 'COG',
                        '-co', 'COMPRESS=DEFLATE', '-co', 'BIGTIFF=IF_SAFER', vrt, out_path], check=True)
        os.remove(vrt)
        for s in shards:
            os.remove(s)
        logger.info(f"Cloud export COMPLETED (mosaicked {len(shards)} shards): {out_path}")
    elif timed_out:
        # Poll gave up AND nothing was written (no shards, and any out_path is a
        # stale leftover we can't trust) — this is a real timeout.
        raise TimeoutError(f"Cloud export timed out after {waited}s (task {task.id}) "
                           f"with no output written")
    else:
        # No shards → single-file export; EE wrote (overwriting any stale) out_path.
        if not os.path.exists(out_path):
            raise RuntimeError(f"Cloud export COMPLETED but no output at {out_path} and no shards found")
        logger.info(f"Cloud export COMPLETED: {out_path}")


def tiled_collection(image, aoi, out_path, scale, dtype, nodata=0, fillna=None,
                     round_vals=False, resampling=None, transform_fn=None,
                     tile_size_deg=0.5, crs='EPSG:3857', strip_rows=2048,
                     output_dir=None):
    """Collect a GEE image over a large AOI at native `scale` and write it
    STRAIGHT to out_path, streaming strip-by-strip. The national array is never
    held in RAM (that in-memory merge/materialise was the OOM).

    Each tile -> compressed GeoTIFF -> gdalbuildvrt -> the VRT is copied to
    out_path one row-strip at a time, applying per strip: AOI geometry_mask
    (clip), fillna, round, optional transform_fn, and the target dtype. Mirrors
    tasks/wsf/collection.py mosaic_tiles (strip windows + geometry_mask +
    from_origin). Peak memory = one strip.

    When `output_dir` is given the per-tile GeoTIFFs are cached under
    mnt/<scan-id>/cache/gee-tiles/ (persistent, GCS-FUSE), keyed by a hash of
    (scale, tile, crs, resampling, bands). A cache hit skips the xee pull
    entirely — so a re-run or a retry after an OOM costs 0 EECU for tiles
    already collected. Cross-container writes are serialised with a file lock.
    Without output_dir everything falls back to one private tempdir (no cache),
    cleaned at the end.

    dtype/nodata : output dtype + nodata (e.g. 'int8'/0, 'float32'/np.nan).
    fillna       : value to replace NaN with before casting (None = keep NaN).
    round_vals   : round before casting (for categorical → int).
    transform_fn : optional callable(strip_ndarray)->ndarray (e.g. landcover snap).
    """
    from core.config.auth import _on_cloud_run
    if _on_cloud_run():
        # Cloud Run (national/large AOI): skip xee entirely — GEE exports the COG
        # server-side straight to the scan's GCS spatial dir. No local tiles, no
        # interactive EECU, no national array in RAM.
        return _export_image_to_cloud(
            image, aoi, out_path, scale, dtype, nodata=nodata, fillna=fillna,
            round_vals=round_vals, resampling=resampling, transform_fn=transform_fn)

    import xarray as xr
    import numpy as np
    import rasterio
    from rasterio.windows import Window
    from rasterio.windows import transform as window_transform
    from rasterio.features import geometry_mask
    from rasterio.transform import from_origin
    import logging, math, tempfile, subprocess, os, shutil, hashlib, uuid
    from pathlib import Path
    from core.py import cache as cache_utils
    from core.py.log_module import setup_logger

    logger = setup_logger(__name__)

    tiles = make_tiles(aoi, tile_size_deg)
    band_names = list(image.bandNames().getInfo())
    n_bands = len(band_names)
    logger.info(f"Collecting {len(tiles)} tile(s) at scale={scale}m → {out_path}")

    # Server-side image identity — so composites that share a band name but hold
    # different data (e.g. summer vs winter LST, both band 'ST_B10') don't collide
    # in the tile cache. Same image object (fabdem for elevation + elevation_buf)
    # still shares its interior tiles.
    try:
        image_id = hashlib.sha1(image.serialize().encode('utf-8')).hexdigest()[:16]
    except Exception:
        image_id = 'noimgid'

    # Persistent hash-keyed tile cache (survives across runs) so a retry skips
    # already-pulled tiles = 0 EECU. VRT + per-tile .part scratch go under
    # mnt/<scan-id>/temp/ and are deleted. No output_dir -> one private tempdir.
    tmp_context = None
    if output_dir:
        cache_root = cache_utils.get_scan_cache_dir(output_dir, namespace='gee-tiles')
        scratch_dir = cache_utils.get_scan_temp_dir(output_dir, run_id=f"gee-tiles-{uuid.uuid4().hex[:8]}")
    else:
        tmp_context = tempfile.TemporaryDirectory(prefix="collect_", dir=os.path.dirname(out_path) or ".")
        cache_root = scratch_dir = Path(tmp_context.name)

    try:
        tile_paths = []
        for i, (bounds, tile_ee) in enumerate(tiles):
            logger.info(f"  Tile {i+1}/{len(tiles)}: {bounds[0]:.2f},{bounds[1]:.2f} → {bounds[2]:.2f},{bounds[3]:.2f}")

            tile_key = (
                f"{image_id}|{scale}|{tile_size_deg}|{crs}|{resampling}|{n_bands}|{'-'.join(band_names)}|"
                f"{bounds[0]:.6f},{bounds[1]:.6f},{bounds[2]:.6f},{bounds[3]:.6f}"
            )
            tile_hash = hashlib.sha1(tile_key.encode('utf-8')).hexdigest()[:20]
            tile_path = cache_root / f"tile_{tile_hash}.tif"

            if output_dir and cache_utils.is_valid_cached_raster(tile_path):
                logger.info(f"  Tile {i+1} cache hit: {tile_path.name}")
                tile_paths.append(str(tile_path))
                continue

            lock_fd = None
            lock_path = tile_path.with_suffix(tile_path.suffix + '.lock')
            tmp_path = None
            ds = None
            try:
                if output_dir:
                    lock_fd = cache_utils.acquire_lock(lock_path)
                    if lock_fd is None:
                        raise TimeoutError(f"Timeout waiting for tile cache lock: {lock_path}")
                    if cache_utils.is_valid_cached_raster(tile_path):
                        logger.info(f"  Tile {i+1} cache hit after wait: {tile_path.name}")
                        tile_paths.append(str(tile_path))
                        continue

                ds = xr.open_dataset(image, engine='ee', geometry=tile_ee, scale=scale, crs=crs)
                if n_bands == 1:
                    tile_da = xee_to_rio(ds[band_names[0]], resampling=resampling)
                else:
                    bands = [xee_to_rio(ds[b], resampling=resampling) for b in band_names]
                    tile_da = xr.concat(bands, dim='band')
                    tile_da['band'] = band_names
                tile_da.rio.write_nodata(np.nan, inplace=True)

                tmp_path = scratch_dir / f"{tile_path.name}.part.{os.getpid()}"
                tile_da.rio.to_raster(str(tmp_path), compress='deflate', tiled=True)
                os.replace(str(tmp_path), str(tile_path))
                tile_paths.append(str(tile_path))
                del tile_da
            except Exception as e:
                logger.warning(f"  Tile {i+1} failed: {e}")
                continue
            finally:
                if ds is not None:
                    ds.close()
                if tmp_path is not None and tmp_path.exists():
                    tmp_path.unlink(missing_ok=True)
                if lock_fd is not None:
                    os.close(lock_fd)
                    lock_path.unlink(missing_ok=True)

        if not tile_paths:
            raise RuntimeError("All tiles failed")

        vrt = os.path.join(str(scratch_dir), "mosaic.vrt")
        subprocess.run(
            ['gdalbuildvrt', '-q', '-resolution', 'highest',
             '-srcnodata', 'nan', '-vrtnodata', 'nan', vrt] + tile_paths,
            check=True)

        # Strip-windowed clip + type write. Output grid = AOI bounds snapped to the
        # VRT pixel grid (like mosaic_tiles). Peak memory = one strip.
        aoi_4326 = aoi.to_crs(4326)
        aoi_shapes = [g.__geo_interface__ for g in aoi_4326.geometry]
        with rasterio.open(vrt) as src:
            resx, resy = abs(src.transform.a), abs(src.transform.e)
            vox, voy = src.transform.c, src.transform.f
            minx, miny, maxx, maxy = aoi_4326.total_bounds
            col0 = max(0, math.floor((minx - vox) / resx))
            row0 = max(0, math.floor((voy - maxy) / resy))
            col1 = min(src.width, math.ceil((maxx - vox) / resx))
            row1 = min(src.height, math.ceil((voy - miny) / resy))
            width, height = col1 - col0, row1 - row0
            out_transform = from_origin(vox + col0 * resx, voy - row0 * resy, resx, resy)

            profile = {
                "driver": "GTiff", "width": width, "height": height, "count": n_bands,
                "dtype": dtype, "crs": "EPSG:4326", "transform": out_transform,
                "nodata": nodata, "tiled": True, "compress": "deflate", "BIGTIFF": "IF_SAFER",
            }
            with rasterio.open(out_path, "w", **profile) as dst:
                for r in range(0, height, strip_rows):
                    h = min(strip_rows, height - r)
                    data = src.read(window=Window(col0, row0 + r, width, h)).astype(np.float32)
                    strip_tf = window_transform(Window(0, r, width, h), out_transform)
                    inside = geometry_mask(aoi_shapes, out_shape=(h, width),
                                           transform=strip_tf, invert=True)
                    data[:, ~inside] = np.nan
                    if fillna is not None:
                        data = np.where(np.isnan(data), fillna, data)
                    if round_vals:
                        data = np.round(data)
                    if transform_fn is not None:
                        data = transform_fn(data)
                    dst.write(data.astype(dtype), window=Window(0, r, width, h))

        logger.info(f"  Wrote {width}x{height}, {n_bands} band(s) → {out_path}")
    finally:
        # scratch (VRT + .part) is disposable; the tile cache under cache_root
        # is deliberately kept so re-runs skip the xee pull.
        if output_dir:
            shutil.rmtree(scratch_dir, ignore_errors=True)
        if tmp_context is not None:
            tmp_context.cleanup()


class Composite:
    """
    Server-side temporal composite for ee.ImageCollection.
    Seasonal month detection uses ERA5-Land and is cached after first call.

    Usage:
        criteria = create_criteria(AOI, 2017, 2024)
        col = ee.ImageCollection('COPERNICUS/S2_SR_HARMONIZED').filter(criteria)
        comp = Composite(col, AOI, 2017, 2024)

        comp.monthly('median')
        comp.seasonal('summer', 'median')
        comp.yearly('median')
        comp.period('median')
    """
    def __init__(self, col, aoi, first_year, last_year):
        self.col = col
        self.aoi = aoi
        self.first_year = first_year
        self.last_year = last_year
        self._seasonal_months = {}

    def _reduce(self, img_col, reducer='median'):
        return getattr(img_col, reducer)()

    def _get_seasonal_months(self, season='summer'):
        import xarray as xr

        if season not in self._seasonal_months:
            # Load Era 5 (replacing CRU with ERA5-Land for better spatial resolution and more recent data)
            era5 = ee.ImageCollection('ECMWF/ERA5_LAND/MONTHLY_AGGR') \
                .select('temperature_2m') \
                .filter(create_criteria(self.aoi, self.first_year, self.last_year))

            # load in meemory via xarray and compute monthly averages across the AOI
            ds = xr.open_dataset(era5, engine='ee', geometry=self.aoi, scale=11132,
                                 projection=era5.first().projection())
            
            # compute monthly avereage
            monthly_avg = ds['temperature_2m'].groupby('time.month').mean().mean(dim=['lon', 'lat'])

            #convert to dictionary
            vals = {int(m): float(monthly_avg.sel(month=m)) for m in monthly_avg.month}
            
            # compute 3-month rolling average and find peak month for summer (or trough for winter) 
            avg = {}
            for m in range(1, 13):
                avg[m] = numpy.nanmean([vals[m], vals[m % 12 + 1], vals[(m + 1) % 12 + 1]])

            # find max for summer, min for winter
            peak = max(avg, key=avg.get) if season == 'summer' else min(avg, key=avg.get)
            self._seasonal_months[season] = [peak, peak % 12 + 1, (peak + 1) % 12 + 1]

        return self._seasonal_months[season]

    def monthly(self, reducer='median'):
        months = ee.List.sequence(1, 12)
        return ee.ImageCollection(months.map(lambda m:
            self._reduce(
                self.col.filter(ee.Filter.calendarRange(m, m, 'month')), reducer
            ).set('month', m)
        ))

    def seasonal(self, season='summer', reducer='median'):
        months = self._get_seasonal_months(season)
        img = self._reduce(
            self.col.filter(ee.Filter.Or(*[ee.Filter.calendarRange(m, m, 'month') for m in months])),
            reducer
        )
        return img.set('system:time_start', ee.Date.fromYMD(self.last_year, months[0], 1).millis())

    def yearly(self, reducer='median'):
        years = ee.List.sequence(self.first_year, self.last_year)
        return ee.ImageCollection(years.map(lambda y:
            self._reduce(
                self.col.filter(ee.Filter.calendarRange(y, y, 'year')), reducer
            ).set('system:time_start', ee.Date.fromYMD(y, 1, 1).millis())
              .set('year', y)
        ))

    def period(self, reducer='median'):
        months = ee.List.sequence(1, 12)
        years = ee.List.sequence(self.first_year, self.last_year)
        return ee.ImageCollection(years.map(lambda y:
            months.map(lambda m:
                self._reduce(
                    self.col.filter(ee.Filter.calendarRange(y, y, 'year'))
                           .filter(ee.Filter.calendarRange(m, m, 'month')),
                    reducer
                ).set('system:time_start', ee.Date.fromYMD(y, m, 1).millis())
                  .set('year', y).set('month', m)
            )
        ).flatten())


def to_geotiff(da, output_path, bands=None, resampling=None):
    """
    Export xarray Dataset/DataArray to GeoTIFF via xee_to_rio.

    da: xarray Dataset or DataArray from xr.open_dataset with xee
    output_path: path to save the .tif file
    bands: list of band names to export (Dataset only), e.g. ['B4', 'B3', 'B2']
    resampling: rasterio.enums.Resampling for categorical data (e.g. Resampling.nearest)
    """
    import rioxarray

    if bands:
        da = da[bands]

    da = xee_to_rio(da, resampling=resampling)
    da.rio.to_raster(output_path)
    


def xee_to_rio(da, resampling=None):
    """Convert xee xarray DataArray/Dataset to rasterio-compatible format.
    Handles: time dim drop, eager load, transpose to (Y, X), CRS, reproject to 4326.

    resampling: rasterio.enums.Resampling, use Resampling.nearest for categorical data
    """
    import rasterio
    from rasterio.transform import from_bounds
    from rasterio.warp import calculate_default_transform, reproject as rio_reproject
    from rasterio.enums import Resampling
    import numpy as np

    x_dim = 'X' if 'X' in da.dims else 'lon'
    y_dim = 'Y' if 'Y' in da.dims else 'lat'

    if 'time' in da.dims:
        da = da.isel(time=0).drop_vars('time')

    # Force eager load
    da = da.load()

    # Get coordinates and data as numpy
    x_vals = da[x_dim].values
    y_vals = da[y_dim].values
    data = da.values.astype(np.float32)

    # Ensure (Y, X) order
    if da.dims.index(y_dim) > da.dims.index(x_dim):
        data = data.T

    # Sort Y descending (north to south) for proper raster orientation
    if len(y_vals) > 1 and y_vals[0] < y_vals[-1]:
        y_vals = y_vals[::-1]
        data = data[::-1, :]

    # Build transform from coordinates
    res_x = abs(float(x_vals[1] - x_vals[0])) if len(x_vals) > 1 else 30.0
    res_y = abs(float(y_vals[0] - y_vals[1])) if len(y_vals) > 1 else 30.0
    src_transform = from_bounds(
        float(x_vals.min()) - res_x / 2,
        float(y_vals.min()) - res_y / 2,
        float(x_vals.max()) + res_x / 2,
        float(y_vals.max()) + res_y / 2,
        len(x_vals), len(y_vals)
    )

    # Reproject from EPSG:3857 to EPSG:4326
    dst_transform, dst_width, dst_height = calculate_default_transform(
        'EPSG:3857', 'EPSG:4326',
        len(x_vals), len(y_vals),
        left=float(x_vals.min()) - res_x / 2,
        bottom=float(y_vals.min()) - res_y / 2,
        right=float(x_vals.max()) + res_x / 2,
        top=float(y_vals.max()) + res_y / 2,
    )

    dst_data = np.empty((dst_height, dst_width), dtype=np.float32)
    dst_data[:] = np.nan

    resamp = resampling if resampling else Resampling.bilinear

    rio_reproject(
        source=data,
        destination=dst_data,
        src_transform=src_transform,
        src_crs='EPSG:3857',
        dst_transform=dst_transform,
        dst_crs='EPSG:4326',
        resampling=resamp,
    )

    # Wrap back into xarray DataArray with proper geo metadata
    import xarray as xr_
    import rioxarray

    da_out = xr_.DataArray(
        dst_data[np.newaxis, :, :],  # add band dim
        dims=['band', 'y', 'x'],
    )
    da_out = da_out.rio.set_spatial_dims(x_dim='x', y_dim='y')
    da_out = da_out.rio.write_crs('EPSG:4326')
    da_out = da_out.rio.write_transform(dst_transform)
    da_out = da_out.squeeze('band', drop=True)

    return da_out