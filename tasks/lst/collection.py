from core.py.log_module import setup_logger
logger = setup_logger(__name__)

import os

import ee
import numpy as np
import xarray as xr
import xee

from core.py import gee_fns as fns


def maskL8sr(image):
    """Cloud mask for Landsat 8 Collection 2 Level 2."""
    # Bits 0-4: Fill, Dilated Cloud, Cirrus, Cloud, Cloud Shadow
    qaMask = image.select('QA_PIXEL').bitwiseAnd(int('11111', 2)).eq(0)
    saturationMask = image.select('QA_RADSAT').eq(0)
    # Scale thermal band to Kelvin
    thermalBand = image.select('ST_B10').multiply(0.00341802).add(149.0)
    return image.addBands(thermalBand, None, True).updateMask(qaMask).updateMask(saturationMask)


def datacollection(
    aoi,
    city_name,
    output_dir,
    first_year=2017,
    last_year=2024,
    composite=['summer'],
    return_raster=False
):

    logger.info("Starting LST data collection...")

    # ------------------------------------------------------------------
    # 1. Load AOI and build Landsat 8 collection
    # ------------------------------------------------------------------
    AOI, bounds = fns.aoi_to_ee_geometry(aoi)

    criteria = fns.create_criteria(AOI, first_year, last_year)
    landsat = (ee.ImageCollection('LANDSAT/LC08/C02/T1_L2')
               .filter(criteria)
               .map(maskL8sr)
               .select('ST_B10'))

    comp = fns.Composite(landsat, AOI, first_year, last_year)

    spatial_dir = os.path.join(output_dir, "spatial")
    os.makedirs(spatial_dir, exist_ok=True)

    results = {}

    # ------------------------------------------------------------------
    # 2. Process each requested composite type
    # ------------------------------------------------------------------
    for comp_type in composite:

        if comp_type in ('summer', 'winter'):
            img = comp.seasonal(comp_type, 'mean')

            # Convert Kelvin to Celsius server-side
            img = img.subtract(273.15)

            lst_rio = fns.tiled_collection(img, aoi, scale=30)
            lst_rio = lst_rio.rio.clip(aoi.to_crs(lst_rio.rio.crs).geometry, drop=True)
            lst_rio.rio.write_nodata(np.nan, inplace=True)

            fname = f"{city_name}_lst_{comp_type}.tif"
            tif_path = os.path.join(spatial_dir, fname)
            lst_rio.rio.to_raster(tif_path)
            logger.info(f"Saved {comp_type} LST: {tif_path}")

            results[comp_type] = lst_rio if return_raster else tif_path

        elif comp_type == 'yearly':
            img_col = comp.yearly('mean')

            ds = xr.open_dataset(
                img_col,
                engine='ee',
                geometry=AOI,
                scale=30,
                crs='EPSG:3857'
            )

            lst = ds['ST_B10'] - 273.15
            lst = _reproject_with_time(lst)
            lst = lst.rio.clip(aoi.to_crs(lst.rio.crs).geometry, drop=True)

            zarr_path = os.path.join(spatial_dir, f"{city_name}_lst_yearly.zarr")
            lst.to_dataset(name='lst').to_zarr(zarr_path, mode='w')
            logger.info(f"Saved yearly LST: {zarr_path}")

            results['yearly'] = lst if return_raster else zarr_path

        elif comp_type == 'monthly':
            img_col = comp.monthly('mean')

            ds = xr.open_dataset(
                img_col,
                engine='ee',
                geometry=AOI,
                scale=30,
                crs='EPSG:3857'
            )

            lst = ds['ST_B10'] - 273.15
            lst = _reproject_with_time(lst)
            lst = lst.rio.clip(aoi.to_crs(lst.rio.crs).geometry, drop=True)

            zarr_path = os.path.join(spatial_dir, f"{city_name}_lst_monthly.zarr")
            lst.to_dataset(name='lst').to_zarr(zarr_path, mode='w')
            logger.info(f"Saved monthly LST: {zarr_path}")

            results['monthly'] = lst if return_raster else zarr_path

        else:
            logger.warning(f"Unknown composite type '{comp_type}', skipping")

    return results


def _reproject_with_time(da):
    """Like fns.xee_to_rio but keeps the time dimension for zarr output."""
    x_dim = 'X' if 'X' in da.dims else 'lon'
    y_dim = 'Y' if 'Y' in da.dims else 'lat'

    da = da.transpose('time', y_dim, x_dim)
    da = da.rio.set_spatial_dims(x_dim=x_dim, y_dim=y_dim)
    da = da.rio.write_crs('EPSG:3857')
    da = da.rio.reproject('EPSG:4326')
    return da
