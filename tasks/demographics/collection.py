# import
import os
import geopandas as gpd
import rasterio
import pandas as pd
from core.py.log_module import setup_logger
import numpy as np
logger = setup_logger(__name__)

data_source = None


def age_label(age):
    if age == 0:
        return "0-1"
    elif age == 1:
        return "1-4"
    elif age == 80:
        return "80+"
    else:
        return f"{age}-{age+4}"


def _agesex_image_for_country(iso3, year):
    """Mosaic the GEE community WorldPop age-sex tiles for a country/year into one
    image. In this catalog 'year' is an int, 'iso' is upper-case, and each
    country-year is split into several tiles — so we mosaic them."""
    import ee
    col = ee.ImageCollection('projects/sat-io/open-datasets/WORLDPOP/agesex') \
        .filter(ee.Filter.eq('year', int(year)))
    for code in (iso3.upper(), iso3.lower()):
        sub = col.filter(ee.Filter.eq('iso', code))
        if sub.size().getInfo() > 0:
            return sub.mosaic()
    raise RuntimeError(f"No GEE age-sex image for {iso3} {year}")


def datacollection(
    aoi: gpd.GeoDataFrame,
    city_name: str,
    country_iso3: str,
    output_dir: str,
    return_raster: bool = False,
    year: int = None,
    country_iso3_list: list = None,
):
    """
    Build a multi-band age-sex GeoTIFF from WorldPop R2025A (constrained, 100m),
    sourced from the Google Earth Engine community catalog and clipped to the AOI
    server-side. This replaces the slow whole-country direct downloads.

    Output schema is unchanged: 36 bands ordered f/m x [0-1, 1-4, 5-9, ..., 80+],
    band-described as "{sex}_{age_label}" (e.g. "f_0-1", "m_80+"). The catalog's
    finer 80/85/90 age classes are folded into "80+" to match the existing pyramid.

    Returns (np.ndarray, dict) if return_raster else None.
    """
    import ee
    from core.py import gee_fns as fns

    logger.info("Starting WorldPop demographic data collection (GEE)")

    AGE_GROUPS = [0, 1] + list(range(5, 85, 5))  # 18 groups: 0,1,5,...,80
    SEXES = ["f", "m"]

    if aoi is None or aoi.empty or aoi.crs is None:
        logger.error("Invalid AOI")
        return None

    from datetime import datetime
    current_year = min(year or datetime.now().year, 2030)  # dataset covers 2015-2030
    current_year = max(current_year, 2015)
    logger.info(f"Using WorldPop R2025A age-sex year: {current_year}")

    spatial_dir = os.path.join(output_dir, "spatial")
    os.makedirs(spatial_dir, exist_ok=True)
    output_raster = os.path.join(spatial_dir, f"{city_name}_worldpop_demographics.tif")

    global data_source
    data_source = f"WorldPop R2025A ({current_year})"

    # Multi-country support: mosaic per-country age-sex images
    if country_iso3_list is None:
        country_iso3_list = [country_iso3]

    try:
        imgs = [_agesex_image_for_country(c, current_year) for c in country_iso3_list]
        base = imgs[0] if len(imgs) == 1 else ee.ImageCollection(imgs).mosaic()

        # Build the 36 folded bands in the exact pipeline order. GEE band names
        # can't contain '+'/'-', so use safe names (b00..b35) for the GEE image
        # and keep the real labels (f_0-1 .. m_80+) for the raster descriptions.
        band_labels = []   # real labels written as band descriptions
        gee_names = []      # safe names used inside GEE / for da.sel
        folded = []
        for sex in SEXES:
            for age in AGE_GROUPS:
                gname = f"b{len(folded):02d}"
                band_labels.append(f"{sex}_{age_label(age)}")
                gee_names.append(gname)
                if age == 80:
                    # Fold 80, 85, 90 -> "80+"
                    src = base.select([f"{sex}_80", f"{sex}_85", f"{sex}_90"]).reduce(ee.Reducer.sum())
                else:
                    src = base.select(f"{sex}_{age:02d}")
                folded.append(src.rename(gname))
        multi = ee.Image.cat(folded).toFloat()

        logger.info(f"Fetching {len(band_labels)} age-sex bands from GEE (R2025A {current_year}, AOI-clipped)...")
        da = fns.tiled_collection(multi, aoi, scale=100)

        band_arrays = [
            np.nan_to_num(np.asarray(da.sel(band=g).values, dtype="float32"), nan=0.0)
            for g in gee_names
        ]
        stacked = np.stack(band_arrays, axis=0)
        transform = da.rio.transform()
    except Exception as e:
        logger.error(f"Demographics: GEE age-sex fetch failed ({e}); skipping this layer.")
        return None

    meta = {
        "driver": "GTiff",
        "height": stacked.shape[1],
        "width": stacked.shape[2],
        "count": len(band_labels),
        "dtype": "float32",
        "crs": "EPSG:4326",
        "transform": transform,
        "nodata": 0,
    }

    with rasterio.open(output_raster, "w", **meta) as dst:
        dst.write(stacked)
        for i, lbl in enumerate(band_labels, start=1):
            dst.set_band_description(i, lbl)
    logger.info(f"Saved multi-band raster: {output_raster}")

    if return_raster:
        return stacked, meta
    return None
