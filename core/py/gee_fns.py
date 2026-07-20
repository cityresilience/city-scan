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


def tiled_collection(image, aoi, scale, tile_size_deg=0.5, crs='EPSG:3857', resampling=None):
    """
    Collect a GEE image over a large AOI using tiles.
    Returns a single rioxarray DataArray (mosaic of all tiles).

    image: ee.Image
    aoi: GeoDataFrame
    scale: pixel size in meters
    tile_size_deg: tile size in degrees (default 0.5°)
    crs: projection for xee (default EPSG:3857)
    resampling: rasterio.enums.Resampling for categorical data
    """
    import xarray as xr
    import rioxarray
    import numpy as np
    from rasterio.merge import merge
    from rasterio.io import MemoryFile
    import rasterio
    import logging

    logger = logging.getLogger(__name__)
    tiles = make_tiles(aoi, tile_size_deg)
    logger.info(f"Collecting {len(tiles)} tile(s) at scale={scale}m")

    band_names = list(image.bandNames().getInfo())
    n_bands = len(band_names)
    logger.info(f"  Bands: {band_names}")

    if len(tiles) == 1:
        # Single tile — use standard collection
        _, tile_ee = tiles[0]
        ds = xr.open_dataset(image, engine='ee', geometry=tile_ee, scale=scale, crs=crs)
        if n_bands == 1:
            return xee_to_rio(ds[band_names[0]], resampling=resampling)
        else:
            # Multi-band: process each band, stack
            bands = [xee_to_rio(ds[b], resampling=resampling) for b in band_names]
            stacked = xr.concat(bands, dim='band')
            stacked['band'] = band_names
            return stacked

    # Multi-tile collection
    tile_files = []
    for i, (bounds, tile_ee) in enumerate(tiles):
        logger.info(f"  Tile {i+1}/{len(tiles)}: {bounds[0]:.2f},{bounds[1]:.2f} → {bounds[2]:.2f},{bounds[3]:.2f}")
        try:
            ds = xr.open_dataset(image, engine='ee', geometry=tile_ee, scale=scale, crs=crs)

            if n_bands == 1:
                tile_da = xee_to_rio(ds[band_names[0]], resampling=resampling)
                tile_data = tile_da.values
                if tile_data.ndim == 2:
                    tile_data = tile_data[np.newaxis, :, :]
            else:
                bands = [xee_to_rio(ds[b], resampling=resampling).values for b in band_names]
                tile_data = np.stack(bands)

            memfile = MemoryFile()
            with memfile.open(
                driver='GTiff',
                height=tile_data.shape[1], width=tile_data.shape[2], count=n_bands,
                dtype=tile_data.dtype,
                crs='EPSG:4326',
                nodata=np.nan,
                transform=tile_da.rio.transform() if n_bands == 1 else xee_to_rio(ds[band_names[0]], resampling=resampling).rio.transform(),
            ) as dst:
                dst.write(tile_data)
            tile_files.append(memfile)
        except Exception as e:
            logger.warning(f"  Tile {i+1} failed: {e}")
            continue

    if not tile_files:
        raise RuntimeError("All tiles failed")

    # Merge tiles
    datasets = [f.open() for f in tile_files]
    mosaic, mosaic_transform = merge(datasets, nodata=np.nan)
    for d in datasets:
        d.close()
    for f in tile_files:
        f.close()

    # Wrap into xarray
    import xarray as xr_
    if n_bands == 1:
        da_out = xr_.DataArray(mosaic[0], dims=['y', 'x'])
        da_out = da_out.rio.set_spatial_dims(x_dim='x', y_dim='y')
        da_out = da_out.rio.write_crs('EPSG:4326')
        da_out = da_out.rio.write_transform(mosaic_transform)
    else:
        da_out = xr_.DataArray(mosaic, dims=['band', 'y', 'x'])
        da_out['band'] = band_names
        da_out = da_out.rio.set_spatial_dims(x_dim='x', y_dim='y')
        da_out = da_out.rio.write_crs('EPSG:4326')
        da_out = da_out.rio.write_transform(mosaic_transform)

    logger.info(f"  Mosaic: {mosaic.shape[-1]}x{mosaic.shape[-2]} pixels, {n_bands} band(s)")
    return da_out


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