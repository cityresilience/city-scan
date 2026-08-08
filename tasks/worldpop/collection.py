# import
import os
import hashlib
import numpy as np
import geopandas as gpd
import rasterio
from rasterio.io import MemoryFile
from core.py.log_module import setup_logger
from core.py.cache import get_cache_namespace_dir, read_bytes_with_cache

logger = setup_logger(__name__)

# GCS bucket path for Global 2 (windowed reads, no full download needed)
GCS_G2_BASE = "/vsicurl/https://storage.googleapis.com/city-scan-global-public/world_population/WorldPop-Global-2"

# URL templates for direct WorldPop download (keyed by dataset name)
WP_URLS = {
    "g1": "https://data.worldpop.org/GIS/Population/Global_2000_2020_1km_UNadj/{year}/{ISO}/{iso}_ppp_{year}_1km_Aggregated_UNadj.tif",
    "g2": "https://data.worldpop.org/GIS/Population/Global_2015_2030/R2025A/{year}/{ISO}/v1/100m/constrained/{iso}_pop_{year}_CN_100m_R2025A_v1.tif",
}


def _worldpop_cache_path(dataset, iso3, year, url):
    """Return deterministic cache path for one WorldPop artifact."""
    cache_dir = get_cache_namespace_dir("worldpop")
    cache_dir.mkdir(parents=True, exist_ok=True)
    url_sig = hashlib.sha1(url.encode("utf-8")).hexdigest()[:10]
    fname = f"{dataset}_{iso3.lower()}_{year}_{url_sig}.tif"
    return cache_dir / fname

def _wp_direct_download(iso3, years, dataset, aoi_bounds):
    """Download WorldPop rasters, windowed read of AOI only. GENERATOR:
    yields (year, array, meta) one at a time so the caller can write each band
    to disk and free it — never all years in memory at once.
    Works for both Global 1 and Global 2 — pass dataset='g1' or 'g2'.
    Downloads 3 files in parallel for speed; yields as they complete."""
    from concurrent.futures import ThreadPoolExecutor, as_completed

    iso_lower = iso3.lower()
    iso_upper = iso3.upper()
    url_template = WP_URLS[dataset]
    total = len(years)

    def _fetch(year):
        url = url_template.format(year=year, ISO=iso_upper, iso=iso_lower)
        cache_path = _worldpop_cache_path(dataset=dataset, iso3=iso3, year=year, url=url)
        if not cache_path.exists():
            # populate the cache; drop the raw bytes immediately (the windowed
            # read below comes from the DISK cache, not from RAM)
            read_bytes_with_cache(url=url, cache_path=cache_path, log_prefix="WorldPop")
        with rasterio.open(cache_path) as src:
            window = rasterio.windows.from_bounds(*aoi_bounds, src.transform)
            data = src.read(window=window)
            transform = src.window_transform(window)
            meta = src.meta.copy()
            meta.update({"height": data.shape[1], "width": data.shape[2], "transform": transform})
        return year, data, meta

    # Sliding window of 3 in-flight fetches: bounds memory to ~3 pending
    # results even when the consumer (band writer) is slower than downloads
    done = 0
    with ThreadPoolExecutor(max_workers=3) as pool:
        it = iter(years)
        pending = {pool.submit(_fetch, y) for y in
                   [y for y, _ in zip(it, range(3))]}
        while pending:
            fut = next(as_completed(pending))
            pending.remove(fut)
            nxt = next(it, None)
            if nxt is not None:
                pending.add(pool.submit(_fetch, nxt))
            done += 1
            print(f"  Downloading {dataset.upper()} from WorldPop... {done}/{total}", end="\r")
            yield fut.result()
    print()


def _wp_multi_country_download(iso3_list, years, dataset, aoi_bounds):
    """Download WorldPop rasters for multiple countries, windowed read of AOI only per country,
    mosaic per year. GENERATOR: yields (year, array, meta) one year at a time so
    the caller can write each band to disk and free it — never all years in memory."""
    from rasterio.merge import merge

    total_years = len(years)
    logger.info(f"Multi-country download: {len(iso3_list)} countries ({', '.join(iso3_list)}), {total_years} years, {dataset.upper()}")

    for yi, year in enumerate(years, 1):
        country_clips = []
        for iso3 in iso3_list:
            try:
                iso_lower = iso3.lower()
                iso_upper = iso3.upper()
                url = WP_URLS[dataset].format(year=year, ISO=iso_upper, iso=iso_lower)
                cache_path = _worldpop_cache_path(dataset=dataset, iso3=iso3, year=year, url=url)
                raw = read_bytes_with_cache(url=url, cache_path=cache_path, log_prefix="WorldPop")
                with MemoryFile(raw) as memfile:
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
                del data
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

        # Clean up before yielding so the per-country handles free promptly
        for ds in datasets:
            ds.close()
        for mf in country_clips:
            mf.close()

        print(f"  Downloading {dataset.upper()} ({len(iso3_list)} countries)... {yi}/{total_years}", end="\r")
        yield year, data, meta
    print()


def _write_bands_streaming(band_gen, aoi_shapes, out_path, years, band_prefix="pop"):
    """Write a multi-band TIF from a generator yielding (year, array, meta),
    masking each year to the AOI polygon and freeing it before the next — so
    peak memory is ONE year, not all of them. Years may arrive out of order;
    each is placed at years.index(year). Outside-polygon pixels -> NaN
    (nodata declared -99999, matching prior behaviour; downstream filters >0).
    """
    from rasterio.features import geometry_mask

    n = len(years)
    dst = None
    inside = None
    try:
        for year, data, meta in band_gen:
            band = data.squeeze().astype("float32")  # (H, W)
            if dst is None:
                profile = meta.copy()
                profile.update({
                    "count": n, "dtype": "float32", "nodata": -99999,
                    "driver": "GTiff", "compress": "deflate", "BIGTIFF": "IF_SAFER",
                })
                dst = rasterio.open(out_path, "w", **profile)
                inside = geometry_mask(aoi_shapes, out_shape=band.shape,
                                       transform=profile["transform"], invert=True)
            band[~inside] = np.nan
            idx = years.index(year) + 1
            dst.write(band, idx)
            dst.set_band_description(idx, f"{band_prefix}_{year}")
            del data, band
    finally:
        if dst is not None:
            dst.close()
    return dst is not None  # False if the generator yielded nothing


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

    # Download, mask, and write each year to disk one at a time (peak = 1 year)
    if multi_country:
        g1_gen = _wp_multi_country_download(country_iso3_list, g1_years, "g1", aoi_bounds)
    else:
        g1_gen = _wp_direct_download(country_iso3, g1_years, "g1", aoi_bounds)

    g1_out = os.path.join(spatial_dir, f"{city_name}_worldpop_2000_2020.tif")
    if _write_bands_streaming(g1_gen, aoi_shapes, g1_out, g1_years):
        logger.info(f"WorldPop Global 1 saved to: {g1_out} ({len(g1_years)} bands)")
    else:
        logger.warning("WorldPop Global 1: no data written.")

    # ==================================================================
    # Global 2 (R2025A) — 100m constrained, 2015-2030, multi-band TIF
    # GCS primary, WorldPop direct download fallback
    # ==================================================================
    logger.info("Starting WorldPop Global 2 data collection (2015-2030)...")

    g2_years = list(range(2015, 2031))

    # G2 on GCS is ONE 16-band file per country (band i = year 2015+i)
    g2_gcs_name = f"{iso_lower}_pop_2015_2030_CN_100m_R2025A_v1.tif"

    def _g2_gcs_gen():
        """Windowed per-band reads from the single multiband GCS file
        (single-country fast path — one HTTP file, ~one band in memory)."""
        with rasterio.open(f"{GCS_G2_BASE}/{g2_gcs_name}") as src:
            window = rasterio.windows.from_bounds(*aoi_bounds, src.transform)
            transform = src.window_transform(window)
            for bi, year in enumerate(g2_years, start=1):
                data = src.read(bi, window=window)[np.newaxis, :, :]
                meta = src.meta.copy()
                meta.update({"height": data.shape[1], "width": data.shape[2],
                             "transform": transform, "count": 1})
                yield year, data, meta

    if multi_country:
        g2_gen = _wp_multi_country_download(country_iso3_list, g2_years, "g2", aoi_bounds)
    else:
        # Probe the single GCS file; fall back to WorldPop direct download.
        try:
            with rasterio.open(f"{GCS_G2_BASE}/{g2_gcs_name}"):
                pass
            g2_gen = _g2_gcs_gen()
        except Exception as e:
            logger.info(f"  GCS failed ({e}), downloading from WorldPop directly")
            g2_gen = _wp_direct_download(country_iso3, g2_years, "g2", aoi_bounds)

    g2_out = os.path.join(spatial_dir, f"{city_name}_worldpop_2015_2030.tif")
    if _write_bands_streaming(g2_gen, aoi_shapes, g2_out, g2_years):
        logger.info(f"WorldPop Global 2 saved to: {g2_out} ({len(g2_years)} bands)")
    else:
        logger.warning("WorldPop Global 2: no data written.")

    # ==================================================================
    # Single year population raster (current year, from Global 2)
    # Re-read the one current-year band from the file just written (cheap)
    # ==================================================================
    from datetime import datetime
    current_year = datetime.now().year
    pop_year = min(max(current_year, 2015), 2030)  # clamp to G2 range

    output_path = os.path.join(spatial_dir, f"{city_name}_population.tif")
    logger.info(f"Extracting {pop_year} population from Global 2 (100m)...")

    band_idx = g2_years.index(pop_year)
    with rasterio.open(g2_out) as src:
        clipped_image = src.read(band_idx + 1)[np.newaxis, :, :]
        clipped_meta = src.meta.copy()
    clipped_meta.update({"count": 1})
    with rasterio.open(output_path, "w", **clipped_meta) as dst:
        dst.write(clipped_image)
    logger.info(f"WorldPop {pop_year} (G2, 100m) saved to: {output_path}")

    logger.info("WorldPop complete.")

    # Note: return_raster kept for signature compatibility but no longer returns
    # the full multi-year arrays (they pinned ~30 GB and nothing consumed them —
    # analysis.py reads the written files). Always returns None now.
    return None
