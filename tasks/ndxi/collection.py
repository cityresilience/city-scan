from core.py.log_module import setup_logger
logger = setup_logger(__name__)

import os

import ee
import xarray as xr
import xee

from core.py import gee_fns as fns

INDEX_BANDS = {
    'ndvi': ('B8', 'B4'),   # NIR - Red
    'ndmi': ('B8', 'B11'),  # NIR - SWIR
}


def maskS2clouds(image):
    qa = image.select('QA60')
    cloudBitMask = 1 << 10
    cirrusBitMask = 1 << 11
    mask = qa.bitwiseAnd(cloudBitMask).eq(0).And(qa.bitwiseAnd(cirrusBitMask).eq(0))
    return image.updateMask(mask).divide(10000).copyProperties(image, ['system:time_start'])


def compute_ndxi(ds, index_type):
    nir_band, other_band = INDEX_BANDS[index_type]
    nir = ds[nir_band]
    other = ds[other_band]
    return (nir - other) / (nir + other)


def _reproject_with_time(da):
    """Like fns.xee_to_rio but keeps the time dimension for zarr output."""
    x_dim = 'X' if 'X' in da.dims else 'lon'
    y_dim = 'Y' if 'Y' in da.dims else 'lat'

    da = da.transpose('time', y_dim, x_dim)
    da = da.rio.set_spatial_dims(x_dim=x_dim, y_dim=y_dim)
    da = da.rio.write_crs('EPSG:3857')
    da = da.rio.reproject('EPSG:4326')
    return da


def datacollection(
    aoi,
    city_name,
    output_dir,
    index_type='ndvi',
    first_year=2017,
    last_year=2024,
    composite=['summer'],
    return_raster=False
):

    import warnings
    warnings.filterwarnings("ignore", message=".*system:time_start.*")

    if index_type not in INDEX_BANDS:
        raise ValueError(f"index_type must be one of {list(INDEX_BANDS.keys())}, got '{index_type}'")

    logger.info(f"Starting {index_type.upper()} data collection...")

    # ------------------------------------------------------------------
    # 1. Load AOI and build Sentinel-2 collection
    # ------------------------------------------------------------------
    AOI, bounds = fns.aoi_to_ee_geometry(aoi)

    nir_band, other_band = INDEX_BANDS[index_type]

    criteria = fns.create_criteria(AOI, first_year, last_year)
    s2 = (ee.ImageCollection('COPERNICUS/S2_HARMONIZED')
          .filter(criteria)
          .filter(ee.Filter.lt('CLOUDY_PIXEL_PERCENTAGE', 10))
          .map(maskS2clouds)
          .select([nir_band, other_band]))

    comp = fns.Composite(s2, AOI, first_year, last_year)

    spatial_dir = os.path.join(output_dir, "spatial")
    os.makedirs(spatial_dir, exist_ok=True)

    results = {}

    # ------------------------------------------------------------------
    # 2. Process each requested composite type
    # ------------------------------------------------------------------
    for comp_type in composite:

        if comp_type in ('summer', 'winter'):
            img = comp.seasonal(comp_type, 'median')

            # Compute NDXI server-side
            nir = img.select(nir_band)
            other = img.select(other_band)
            ndxi_img = nir.subtract(other).divide(nir.add(other)).rename(index_type)

            ndxi_rio = fns.tiled_collection(ndxi_img, aoi, scale=10)
            ndxi_rio = ndxi_rio.rio.clip(aoi.to_crs(ndxi_rio.rio.crs).geometry, drop=True)
            ndxi_rio.name = index_type.upper()

            fname = f"{city_name}_{index_type}_season.tif"
            tif_path = os.path.join(spatial_dir, fname)
            ndxi_rio.rio.to_raster(tif_path)
            logger.info(f"Saved {comp_type} composite: {tif_path}")

            results[comp_type] = ndxi_rio if return_raster else tif_path

        elif comp_type == 'yearly':
            # yearly() returns an ee.ImageCollection with time dim
            img_col = comp.yearly('median')

            ds = xr.open_dataset(
                img_col,
                engine='ee',
                geometry=AOI,
                scale=10,
                crs='EPSG:3857'
            )

            ndxi = compute_ndxi(ds, index_type)
            ndxi = _reproject_with_time(ndxi)
            ndxi = ndxi.rio.clip(aoi.to_crs(ndxi.rio.crs).geometry, drop=True)

            zarr_path = os.path.join(spatial_dir, f"{city_name}_{index_type}_yearly.zarr")
            ndxi.to_dataset(name=index_type).to_zarr(zarr_path, mode='w')
            logger.info(f"Saved yearly composite: {zarr_path}")

            results['yearly'] = ndxi if return_raster else zarr_path

        elif comp_type == 'monthly':
            # monthly() returns an ee.ImageCollection with time dim (12 months)
            img_col = comp.monthly('median')

            ds = xr.open_dataset(
                img_col,
                engine='ee',
                geometry=AOI,
                scale=10,
                crs='EPSG:3857'
            )

            ndxi = compute_ndxi(ds, index_type)
            ndxi = _reproject_with_time(ndxi)
            ndxi = ndxi.rio.clip(aoi.to_crs(ndxi.rio.crs).geometry, drop=True)

            zarr_path = os.path.join(spatial_dir, f"{city_name}_{index_type}_monthly.zarr")
            ndxi.to_dataset(name=index_type).to_zarr(zarr_path, mode='w')
            logger.info(f"Saved monthly composite: {zarr_path}")

            results['monthly'] = ndxi if return_raster else zarr_path

        else:
            logger.warning(f"Unknown composite type '{comp_type}', skipping")

    return results
