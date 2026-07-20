# import
import os
import geopandas as gpd
import rasterio
from rasterio.mask import mask
import pandas as pd
from core.py.log_module import setup_logger
from core.py.cache import get_cache_namespace_dir, read_bytes_with_cache
import numpy as np
logger = setup_logger(__name__)

data_source = None


def _demographics_cache_path(iso3, sex, age, year):
    """Return deterministic cache path for one demographics age-sex raster."""
    cache_dir = get_cache_namespace_dir("demographics")
    cache_dir.mkdir(parents=True, exist_ok=True)
    age_str = f"{age:02d}"
    fname = f"{iso3.lower()}_{sex}_{age_str}_{year}_CN_100m_R2025A_v1.tif"
    return cache_dir / fname


def age_label(age):
    if age == 0:
        return "0-1"
    elif age == 1:
        return "1-4"
    elif age == 80:
        return "80+"
    else:
        return f"{age}-{age+4}"


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
    Download, clip, and stack WorldPop age–sex rasters into a single multi-band GeoTIFF.

    Parameters
    ----------
    aoi : GeoDataFrame
        AOI polygon(s).
    city_name : str
        City name for naming output files.
    country_iso3 : str
        ISO3 country code (e.g. "IDN", "KHM").
    output_dir : str
        Directory where clipped raster will be saved.
    return_raster : bool, default False
        If True, return (array, metadata) for the stacked raster.

    Returns
    -------
    (np.ndarray, dict) or None
        Multi-band raster array and metadata if return_raster=True.
    """

    logger.info("Starting WorldPop demographic data collection")

    # AGE_GROUPS = [0, 1] + list(range(5, 85, 5))  # 18 groups (old: Global_2000_2020_Constrained)
    AGE_GROUPS = [0, 1] + list(range(5, 85, 5))  # 18 groups (R2025A has 85, 90 too but keeping consistent)
    SEXES = ["f", "m"]

    if aoi is None or aoi.empty or aoi.crs is None:
        logger.error("Invalid AOI")
        return None

    # Old data source (2020 only, Global_2000_2020_Constrained)
    # bucket_base = "https://storage.googleapis.com/city-scan-global-public/"
    # WORLDPOP_BASE = "https://data.worldpop.org/GIS/AgeSex_structures/Global_2000_2020_Constrained/2020"
    # filename pattern: {iso3}_{sex}_{age}_2020_constrained.tif

    # New data source: WorldPop Global 2015-2030 R2025A (configurable year, default current)
    from datetime import datetime
    current_year = min(year or datetime.now().year, 2030)  # clamp to dataset max (2015-2030)
    logger.info(f"Using WorldPop R2025A year: {current_year}")
    WORLDPOP_BASE = f"https://data.worldpop.org/GIS/AgeSex_structures/Global_2015_2030/R2025A/{current_year}/{country_iso3.upper()}/v1/100m/constrained"

    spatial_dir = os.path.join(output_dir, "spatial")
    os.makedirs(spatial_dir, exist_ok=True)

    output_raster = os.path.join(
        spatial_dir,
        f"{city_name}_worldpop_demographics.tif"
    )

    global data_source
    data_source = f"WorldPop R2025A ({current_year})"
    import urllib.request
    from rasterio.io import MemoryFile
    from concurrent.futures import ThreadPoolExecutor

    # Multi-country support
    if country_iso3_list is None:
        country_iso3_list = [country_iso3]
    multi_country = len(country_iso3_list) > 1

    # Build list of (sex, age) tuples
    file_list = []
    for sex in SEXES:
        for age in AGE_GROUPS:
            file_list.append((sex, age))

    total = len(file_list)

    def _download_and_clip(item):
        sex, age = item
        age_str = f"{age:02d}"

        if multi_country:
            # Download from each country, window to AOI extent, mosaic, then clip
            from rasterio.merge import merge
            aoi_bounds = aoi.total_bounds
            country_clips = []
            for iso3 in country_iso3_list:
                iso_lower = iso3.lower()
                iso_upper = iso3.upper()
                wp_base = f"https://data.worldpop.org/GIS/AgeSex_structures/Global_2015_2030/R2025A/{current_year}/{iso_upper}/v1/100m/constrained"
                filename = f"{iso_lower}_{sex}_{age_str}_{current_year}_CN_100m_R2025A_v1.tif"
                url = f"{wp_base}/{filename}"
                cache_path = _demographics_cache_path(iso3, sex, age, current_year)
                try:
                    raw = read_bytes_with_cache(url=url, cache_path=cache_path, log_prefix="Demographics")
                    with MemoryFile(raw) as full_mf:
                        with full_mf.open() as rsrc:
                            win = rasterio.windows.from_bounds(*aoi_bounds, rsrc.transform)
                            rdata = rsrc.read(window=win)
                            rtransform = rsrc.window_transform(win)
                            rmeta = rsrc.meta.copy()
                            rmeta.update({"height": rdata.shape[1], "width": rdata.shape[2], "transform": rtransform})
                    mf = MemoryFile()
                    with mf.open(**rmeta) as dst:
                        dst.write(rdata)
                    country_clips.append(mf)
                    del rdata
                except Exception as e:
                    logger.debug(f"  {iso3} {sex}_{age_str} not available: {e}")
                    continue

            if not country_clips:
                return None

            datasets = [mf.open() for mf in country_clips]
            if len(datasets) == 1:
                src = datasets[0]
            else:
                mosaic_data, mosaic_transform = merge(datasets)
                mosaic_meta = datasets[0].meta.copy()
                mosaic_meta.update({
                    "height": mosaic_data.shape[1],
                    "width": mosaic_data.shape[2],
                    "transform": mosaic_transform,
                })
                mosaic_mf = MemoryFile()
                with mosaic_mf.open(**mosaic_meta) as dst:
                    dst.write(mosaic_data)
                src = mosaic_mf.open()

            aoi_proj = aoi.to_crs(src.crs) if aoi.crs != src.crs else aoi
            shapes = [g.__geo_interface__ for g in aoi_proj.geometry]
            clipped, transform = mask(src, shapes=shapes, crop=True, nodata=0)
            clipped[clipped == src.nodata] = 0
            meta = src.meta.copy()
            meta.update({"height": clipped.shape[1], "width": clipped.shape[2], "transform": transform})

            for ds in datasets:
                ds.close()
            for mf in country_clips:
                mf.close()

            return sex, age, clipped[0], meta, f"{sex}_{age_label(age)}"
        else:
            # Single country — use cache
            filename = f"{country_iso3.lower()}_{sex}_{age_str}_{current_year}_CN_100m_R2025A_v1.tif"
            url = f"{WORLDPOP_BASE}/{filename}"
            cache_path = _demographics_cache_path(country_iso3, sex, age, current_year)
            raw = read_bytes_with_cache(url=url, cache_path=cache_path, log_prefix="Demographics")
            with MemoryFile(raw) as memfile:
                with memfile.open() as src:
                    aoi_proj = aoi.to_crs(src.crs) if aoi.crs != src.crs else aoi
                    shapes = [g.__geo_interface__ for g in aoi_proj.geometry]
                    clipped, transform = mask(src, shapes=shapes, crop=True, nodata=0)
                    clipped[clipped == src.nodata] = 0
                    meta = src.meta.copy()
                    meta.update({"height": clipped.shape[1], "width": clipped.shape[2], "transform": transform})
            return sex, age, clipped[0], meta, f"{sex}_{age_label(age)}"

    logger.info(f"Downloading {total} age-sex rasters (3 parallel){' from ' + str(len(country_iso3_list)) + ' countries' if multi_country else ''}...")
    results = []
    with ThreadPoolExecutor(max_workers=3) as pool:
        for i, result in enumerate(pool.map(_download_and_clip, file_list), 1):
            if result is not None:
                results.append(result)
            print(f"  Downloaded {i}/{total}", end="\r")
    print()

    # Reassemble in order
    band_arrays = [r[2] for r in results]
    band_descriptions = [r[4] for r in results]
    first_meta = results[0][3]
    meta = first_meta.copy()
    meta.update({"count": total, "nodata": 0})

    # Write multi-band raster to disk
    with rasterio.open(output_raster, "w", **meta) as dst:
        for i, band in enumerate(band_arrays, start=1):
            dst.write(band, i)
            dst.set_band_description(i, band_descriptions[i - 1])

    logger.info(f"Saved multi-band raster: {output_raster}")

    # Optional in-memory return
    if return_raster:
        stacked_array = np.stack(band_arrays, axis=0)
        return stacked_array, meta

    return None

