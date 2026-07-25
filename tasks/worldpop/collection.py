# import
import os
import urllib.request
import numpy as np
import geopandas as gpd
import rasterio
from rasterio.mask import mask
from rasterio.io import MemoryFile
from core.py.log_module import setup_logger

logger = setup_logger(__name__)

# GCS bucket path for Global 2 (windowed reads, no full download needed)
GCS_G2_BASE = "/vsicurl/https://storage.googleapis.com/city-scan-global-public/world_population/WorldPop-Global-2"

# URL templates for direct WorldPop download (keyed by dataset name)
WP_URLS = {
    "g1": "https://data.worldpop.org/GIS/Population/Global_2000_2020_1km_UNadj/{year}/{ISO}/{iso}_ppp_{year}_1km_Aggregated_UNadj.tif",
    "g2": "https://data.worldpop.org/GIS/Population/Global_2015_2030/R2025A/{year}/{ISO}/v1/100m/constrained/{iso}_pop_{year}_CN_100m_R2025A_v1.tif",
}


def _urlopen_retry(url, timeout=90, retries=2, backoff=5):
    """urlopen with a socket timeout + retries so a hung/slow WorldPop server
    fails after a bounded time instead of blocking the whole run forever."""
    import time as _time
    last_err = None
    for attempt in range(1, retries + 1):
        try:
            return urllib.request.urlopen(url, timeout=timeout)
        except Exception as e:
            last_err = e
            logger.warning(f"  download attempt {attempt}/{retries} failed ({e}): {url}")
            if attempt < retries:
                _time.sleep(backoff * attempt)
    raise last_err


def _gee_worldpop_g2(aoi, iso3, years):
    """Fetch WorldPop Global-2 (R2025A constrained, 100m) per year from the GEE
    community catalog, clipped to the AOI server-side (no whole-country download).
    Returns a list of (array(1,H,W) float32, meta) per year — the same format the
    direct-download path returns, so _stack_mask and everything downstream is
    unchanged. Same dataset/release as the old direct download."""
    import ee
    import numpy as np
    from core.py import gee_fns as fns

    col = ee.ImageCollection('projects/sat-io/open-datasets/WORLDPOP/pop') \
        .filter(ee.Filter.eq('country', iso3.upper()))
    year_bands = []
    for y in years:
        # 'year' is stored as a string here; mosaic handles any tiled countries
        yi = col.filter(ee.Filter.eq('year', str(y))).mosaic()
        year_bands.append(yi.rename(f'pop_{y}'))
    multi = ee.Image.cat(year_bands).toFloat()

    da = fns.tiled_collection(multi, aoi, scale=100)
    transform = da.rio.transform()
    out = []
    for y in years:
        arr = np.asarray(da.sel(band=f'pop_{y}').values, dtype='float32')[np.newaxis, :, :]
        meta = {
            'driver': 'GTiff', 'height': arr.shape[1], 'width': arr.shape[2],
            'count': 1, 'dtype': 'float32', 'crs': 'EPSG:4326',
            'transform': transform, 'nodata': np.nan,
        }
        out.append((arr, meta))
    return out


def _wp_direct_download(iso3, years, dataset, aoi_bounds):
    """Download WorldPop rasters, windowed read of AOI only, return list of (array, meta).
    Works for both Global 1 and Global 2 — pass dataset='g1' or 'g2'.
    Downloads 3 files in parallel for speed."""
    from concurrent.futures import ThreadPoolExecutor

    iso_lower = iso3.lower()
    iso_upper = iso3.upper()
    url_template = WP_URLS[dataset]
    total = len(years)

    def _fetch(year):
        url = url_template.format(year=year, ISO=iso_upper, iso=iso_lower)
        response = _urlopen_retry(url)
        with MemoryFile(response.read()) as memfile:
            with memfile.open() as src:
                window = rasterio.windows.from_bounds(*aoi_bounds, src.transform)
                data = src.read(window=window)
                transform = src.window_transform(window)
                meta = src.meta.copy()
                meta.update({"height": data.shape[1], "width": data.shape[2], "transform": transform})
        return year, data, meta

    results_dict = {}
    with ThreadPoolExecutor(max_workers=3) as pool:
        for i, (year, data, meta) in enumerate(pool.map(_fetch, years), 1):
            results_dict[year] = (data, meta)
            print(f"  Downloading {dataset.upper()} from WorldPop... {i}/{total}", end="\r")
    print()

    return [(results_dict[y][0], results_dict[y][1]) for y in years]


def _wp_multi_country_download(iso3_list, years, dataset, aoi_bounds):
    """Download WorldPop rasters for multiple countries, windowed read of AOI only per country,
    mosaic per year. Downloads full file but only keeps AOI window in memory."""
    from rasterio.merge import merge

    all_bands = []
    total_years = len(years)
    logger.info(f"Multi-country download: {len(iso3_list)} countries ({', '.join(iso3_list)}), {total_years} years, {dataset.upper()}")

    for yi, year in enumerate(years, 1):
        country_clips = []
        for iso3 in iso3_list:
            try:
                iso_lower = iso3.lower()
                iso_upper = iso3.upper()
                url = WP_URLS[dataset].format(year=year, ISO=iso_upper, iso=iso_lower)
                response = _urlopen_retry(url)
                with MemoryFile(response.read()) as memfile:
                    with memfile.open() as src:
                        window = rasterio.windows.from_bounds(*aoi_bounds, src.transform)
                        data = src.read(window=window)
                        transform = src.window_transform(window)
                        meta = src.meta.copy()
                        meta.update({"height": data.shape[1], "width": data.shape[2], "transform": transform})
                # Store windowed result in MemoryFile for merge
                clip_mf = MemoryFile()
                with clip_mf.open(**meta) as dst:
                    dst.write(data)
                country_clips.append(clip_mf)
                logger.info(f"  {dataset.upper()} {year} {iso3.upper()}: OK")
                del data, response
            except Exception as e:
                logger.warning(f"  {dataset.upper()} {year} {iso3.upper()}: failed ({e})")
                continue

        if not country_clips:
            logger.warning(f"  No data for year {year} from any country")
            continue

        # Mosaic clipped country rasters for this year
        datasets = [mf.open() for mf in country_clips]
        if len(datasets) == 1:
            data = datasets[0].read()
            transform = datasets[0].transform
            meta = datasets[0].meta.copy()
        else:
            data, transform = merge(datasets)
            meta = datasets[0].meta.copy()
            meta.update({
                "height": data.shape[1],
                "width": data.shape[2],
                "transform": transform,
            })

        all_bands.append((data, meta))

        # Clean up
        for ds in datasets:
            ds.close()
        for mf in country_clips:
            mf.close()

        print(f"  Downloading {dataset.upper()} ({len(iso3_list)} countries)... {yi}/{total_years}", end="\r")
    print()

    return all_bands


def _stack_mask(band_list, aoi_shapes):
    """Stack list of (array, meta) into multi-band array and mask to AOI polygon.
    Returns (clipped_image, clipped_meta)."""
    # Collect single-band arrays and use first file's meta as reference
    bands = [arr.squeeze() for arr, _ in band_list]  # each is (1, H, W) -> (H, W)
    ref_meta = band_list[0][1].copy()

    # Stack into multi-band: shape (n_years, H, W)
    stacked = np.stack(bands, axis=0)
    ref_meta.update({"count": len(bands)})

    # Use MemoryFile so rasterio.mask can read without writing to disk
    with MemoryFile() as memfile:
        with memfile.open(**ref_meta) as mem_dst:
            mem_dst.write(stacked)

        with memfile.open() as mem_src:
            clipped, clipped_transform = mask(mem_src, shapes=aoi_shapes, crop=True, nodata=np.nan)
            clipped_meta = mem_src.meta.copy()
            clipped_meta.update({
                "height": clipped.shape[1],
                "width": clipped.shape[2],
                "transform": clipped_transform,
                "nodata": -99999,
                "count": len(bands),
            })

    return clipped, clipped_meta


def datacollection(
        aoi: gpd.GeoDataFrame,
        city_name: str,
        country_iso3: str,
        output_dir: str,
        return_raster: bool = True,
        country_iso3_list: list = None,
    ):
    """
    Download WorldPop rasters and clip to AOI.
    Downloads Global 1 (2020 single + 2000-2020 multi-year) and Global 2 (2015-2030).

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
    return_raster : bool
        If True, return clipped raster array & metadata.

    Returns
    -------
    (array, metadata) or None
    """

    logger.info("Starting WorldPop data collection…")

    # Validate AOI
    if aoi is None or aoi.empty:
        logger.error("AOI is empty. Cannot continue.")
        return None

    if aoi.crs is None:
        logger.error("AOI has no CRS defined.")
        return None

    logger.info(f"AOI CRS: {aoi.crs}")

    # Common setup used by all three downloads
    spatial_dir = os.path.join(output_dir, "spatial")
    os.makedirs(spatial_dir, exist_ok=True)
    aoi_bounds = aoi.total_bounds  # (minx, miny, maxx, maxy) for windowed reads
    aoi_shapes = [geom.__geo_interface__ for geom in aoi.geometry]  # for polygon masking
    iso_lower = country_iso3.lower()

    # Multi-country support
    if country_iso3_list is None:
        country_iso3_list = [country_iso3]
    multi_country = len(country_iso3_list) > 1

    # ==================================================================
    # Global 1 — 1km UN adjusted, 2000-2020, multi-band TIF
    # Direct download from WorldPop (not on GCS)
    # ==================================================================
    logger.info("Starting WorldPop Global 1 data collection (2000-2020)...")

    g1_years = list(range(2000, 2021))

    # Download and crop each year into memory
    if multi_country:
        g1_bands = _wp_multi_country_download(country_iso3_list, g1_years, "g1", aoi_bounds)
    else:
        g1_bands = _wp_direct_download(country_iso3, g1_years, "g1", aoi_bounds)
    # Stack all years and mask to AOI polygon
    g1_image, g1_meta = _stack_mask(g1_bands, aoi_shapes)

    # Save multi-band TIF
    g1_out = os.path.join(spatial_dir, f"{city_name}_worldpop_2000_2020.tif")
    with rasterio.open(g1_out, "w", **g1_meta) as dst:
        dst.write(g1_image)
        for i, year in enumerate(g1_years):
            dst.set_band_description(i + 1, f"pop_{year}")
    logger.info(f"WorldPop Global 1 saved to: {g1_out} ({len(g1_years)} bands)")

    # ==================================================================
    # Global 2 (R2025A) — 100m constrained, 2015-2030, multi-band TIF
    # GCS primary, WorldPop direct download fallback
    # ==================================================================
    logger.info("Starting WorldPop Global 2 data collection (2015-2030)...")

    g2_years = list(range(2015, 2031))

    if multi_country:
        # Multi-country: download from WorldPop directly for all countries, mosaic per year
        g2_bands = _wp_multi_country_download(country_iso3_list, g2_years, "g2", aoi_bounds)
    else:
        # Fetch from Google Earth Engine (community WorldPop R2025A constrained,
        # 100m), clipped to the AOI server-side — same dataset/release as the old
        # whole-country direct download, but ~instant. Falls back to the direct
        # download only if GEE is unavailable for this ISO/year.
        try:
            g2_bands = _gee_worldpop_g2(aoi, country_iso3, g2_years)
        except Exception as e:
            logger.warning(f"  GEE WorldPop g2 fetch failed ({e}); falling back to direct download")
            g2_bands = _wp_direct_download(country_iso3, g2_years, "g2", aoi_bounds)

    # Stack all years and mask to AOI polygon
    g2_image, g2_meta = _stack_mask(g2_bands, aoi_shapes)

    # Save multi-band TIF
    g2_out = os.path.join(spatial_dir, f"{city_name}_worldpop_2015_2030.tif")
    with rasterio.open(g2_out, "w", **g2_meta) as dst:
        dst.write(g2_image)
        for i, year in enumerate(g2_years):
            dst.set_band_description(i + 1, f"pop_{year}")
    logger.info(f"WorldPop Global 2 saved to: {g2_out} ({len(g2_years)} bands)")

    # ==================================================================
    # Single year population raster (current year, from Global 2)
    # ==================================================================
    from datetime import datetime
    current_year = datetime.now().year
    # Clamp to G2 range (2015-2030)
    pop_year = min(max(current_year, 2015), 2030)

    output_path = os.path.join(spatial_dir, f"{city_name}_population.tif")
    logger.info(f"Extracting {pop_year} population from Global 2 (100m)...")

    band_idx = g2_years.index(pop_year)
    clipped_image = g2_image[band_idx:band_idx+1, :, :]
    clipped_meta = g2_meta.copy()
    clipped_meta.update({"count": 1})
    with rasterio.open(output_path, "w", **clipped_meta) as dst:
        dst.write(clipped_image)
    logger.info(f"WorldPop {pop_year} (G2, 100m) saved to: {output_path}")

    logger.info("WorldPop complete.")

    if return_raster:
        arrays = {"wp_2020": clipped_image, "g1_multiyear": g1_image, "g2": g2_image}
        metas = {"wp_2020": clipped_meta, "g1_multiyear": g1_meta, "g2": g2_meta}
        return arrays, metas

    return None
