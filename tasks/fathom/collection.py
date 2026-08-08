# import
import os
import geopandas as gpd
import rasterio
from rasterio.mask import mask
from core.py.log_module import setup_logger
import numpy as np
from core.py import raster_module as raster_pro
logger = setup_logger(__name__)
from os.path import exists
GCS_FATHOM_BASE = "/vsigs/city-scan-global-private/Fathom/v2023"
from core.config.gdal_auth import configure_gdal_gcs

configure_gdal_gcs()

def apply_flood_threshold(out_image, out_meta, flood_threshold, prob):
    import numpy as np

    # Ensure out_image is a NumPy array
    out_image = np.asarray(out_image)

    # Replace nodata values with 0
    out_image[out_image == out_meta['nodata']] = 0

    # Apply flood threshold
    out_image = np.where(out_image < flood_threshold, 0, out_image)
    out_image = np.where(out_image >= flood_threshold, 1, out_image)

    # Multiply by probability
    out_image = out_image * prob

    # Update metadata
    out_meta.update({'nodata': 0, 'dtype': 'float32'})

    return out_image, out_meta

def composite_flood_raster(rp_files, output_raster, flood_rps=None):
    """Composite per-RP thresholded rasters into a single multi-band TIF.

    Band 1: max probability across all RPs (for mapping)
    Bands 2+: binary flooded/not per RP (for charting)

    Reads from per-RP temp files using windowed IO to avoid holding
    all arrays in memory simultaneously.
    """
    import numpy as np
    import rasterio
    from rasterio.windows import Window

    # Get output dimensions from first RP file
    with rasterio.open(rp_files[0]) as ref:
        out_meta = ref.meta.copy()
        height, width = ref.height, ref.width

    band_count = 1 + len(rp_files)  # max_prob + one binary band per RP
    # Compress + tile (memory-backed FS on Cloud Run; mostly-zero bands).
    # interleave='band' so per-strip band-by-band writes never revisit an
    # already-flushed compressed block (which GDAL can't rewrite).
    out_meta.update({'count': band_count, 'dtype': 'float32',
                     'compress': 'deflate', 'tiled': True,
                     'blockxsize': 512, 'blockysize': 512,
                     'interleave': 'band'})

    # Process in horizontal strips to limit memory
    strip_height = min(512, height)

    with rasterio.open(output_raster, 'w', **out_meta) as dst:
        for row_off in range(0, height, strip_height):
            h = min(strip_height, height - row_off)
            win = Window(0, row_off, width, h)

            # Read this strip from all RP files
            strips = []
            for f in rp_files:
                with rasterio.open(f) as src:
                    strips.append(src.read(1, window=win).astype(np.float32))

            # Band 1: max probability
            max_prob = np.maximum.reduce(strips)
            dst.write(max_prob, 1, window=win)

            # Bands 2+: binary (flooded = value > 0)
            for i, strip in enumerate(strips, 2):
                dst.write((strip > 0).astype(np.float32), i, window=win)

        # Set band descriptions
        dst.set_band_description(1, 'max_probability')
        if flood_rps:
            for i, rp in enumerate(flood_rps, 2):
                dst.set_band_description(i, f'r{rp}')


def _windowed_rp_raster(tile_paths, buffer_aoi, flood_threshold, prob, out_path):
    """Mosaic the given Fathom tiles over the AOI, mask to the AOI, apply the
    flood threshold, and write a single-band float32 raster — all in horizontal
    strips so a national-scale raster never materializes in memory. Returns True
    if the output was written, False if no tile covered the AOI.

    Replaces the old mosaic (rasterio.merge, full array in RAM) + mask(crop=True,
    full array in RAM) path. Tiles form a virtual mosaic via gdalbuildvrt (an XML
    index — no pixels read); the heavy reads are windowed rasterio reads from the
    VRT (in-process GDAL auth, same as everywhere else), bounded to one strip.
    Mirrors composite_flood_raster's windowed-strip pattern.
    """
    import re
    import subprocess
    import tempfile
    import numpy as np
    import rasterio
    from rasterio.windows import Window, from_bounds, transform as window_transform
    from rasterio.transform import from_origin
    from rasterio.features import geometry_mask

    # Keep only tiles that actually exist (cloud paths may 404), deduped by
    # geographic tile so a location never appears twice in the VRT. tile_paths is
    # folder-first, and we keep the first occurrence, so folder (authoritative
    # v3.0) wins over legacy flat on any overlap — matching the old
    # merge(method='first') behaviour (gdalbuildvrt otherwise lets the LAST
    # source win, which would be the wrong scheme).
    existing = []
    seen = set()
    for p in tile_paths:
        m = re.search(r'([ns]\d+[ew]\d+)\.tif$', os.path.basename(p))
        key = m.group(1) if m else p
        if key in seen:
            continue
        try:
            with rasterio.open(p):
                existing.append(p)
                seen.add(key)
        except rasterio.errors.RasterioIOError:
            continue
    if not existing:
        return False

    # Grid parameters from a reference tile (all tiles share the global grid)
    with rasterio.open(existing[0]) as ref:
        res = abs(ref.transform.a)
        src_nodata = ref.nodata if ref.nodata is not None else 0
        out_meta = ref.meta.copy()

    # Fixed output grid = AOI bounds snapped outward to the tile grid. Computed
    # from the AOI (not per-tile coverage) so every RP writes an identical grid
    # and composite_flood_raster can read them with a shared window.
    import math
    minx, miny, maxx, maxy = buffer_aoi.total_bounds
    minx = math.floor(minx / res) * res
    miny = math.floor(miny / res) * res
    maxx = math.ceil(maxx / res) * res
    maxy = math.ceil(maxy / res) * res
    width = int(round((maxx - minx) / res))
    height = int(round((maxy - miny) / res))
    if width <= 0 or height <= 0:
        return False
    out_transform = from_origin(minx, maxy, res, res)

    # Compress + tile: on Cloud Run the filesystem is memory-backed, and the
    # per-RP national temps accumulate (all RPs alive before compositing), so an
    # uncompressed national raster (~11 GB) would blow RAM. These are binary/
    # mostly-zero, so deflate shrinks them ~50-100x.
    out_meta.update({'driver': 'GTiff', 'count': 1, 'dtype': 'float32',
                     'nodata': 0, 'height': height, 'width': width,
                     'transform': out_transform,
                     'compress': 'deflate', 'tiled': True,
                     'blockxsize': 512, 'blockysize': 512})

    with tempfile.NamedTemporaryFile(suffix='.vrt', delete=False) as tf:
        vrt = tf.name
    try:
        subprocess.run(['gdalbuildvrt', '-q', vrt] + existing, check=True)

        with rasterio.open(vrt) as src:
            # Target window in VRT pixel space (grids share phase, so integer)
            base = from_bounds(minx, miny, maxx, maxy, src.transform)
            col0, row0 = int(round(base.col_off)), int(round(base.row_off))

            strip_height = min(512, height)
            with rasterio.open(out_path, 'w', **out_meta) as dst:
                for row_off in range(0, height, strip_height):
                    h = min(strip_height, height - row_off)
                    # Read this strip from the mosaic (boundless: fill any tile
                    # gap for this RP with nodata rather than failing).
                    src_win = Window(col0, row0 + row_off, width, h)
                    data = src.read(1, window=src_win, boundless=True,
                                    fill_value=src_nodata).astype(np.float32)

                    # Mask outside the AOI geometry, then threshold + weight
                    # (matches apply_flood_threshold: nodata/outside -> 0,
                    #  >=threshold -> 1, then * probability).
                    strip_tf = window_transform(Window(0, row_off, width, h),
                                                out_transform)
                    outside = geometry_mask(buffer_aoi.geometry,
                                            out_shape=(h, width),
                                            transform=strip_tf)
                    data[data == src_nodata] = 0
                    data[outside] = 0
                    data = np.where(data < flood_threshold, 0.0, 1.0).astype(
                        np.float32) * prob

                    dst.write(data, 1, window=Window(0, row_off, width, h))
        return True
    finally:
        if os.path.exists(vrt):
            os.unlink(vrt)


def _process_year(
    flood_type,
    year,
    ssp,
    flood_rps,
    lat_tiles,
    lon_tiles,
    flood_type_folder_dict,
    flood_threshold,
    spatial_dir,
    buffer_aoi,
    utm_crs,
    city_name,
    flood_ssp_labels=None
):
    """
    Process one flood_type-year-(optional ssp) combination.

    Methodology preserved from old code:
    tiles → mosaic → mask → threshold → stack (max reduce) → write → reproject
    """

    # Idempotent resume: skip this scenario only if BOTH outputs already exist
    # AND are valid, complete rasters — so a rerun after a crash doesn't redo
    # finished scenarios, but a stub/corrupt/truncated file (e.g. an _utm killed
    # mid-write by an OOM) is NOT skipped and gets regenerated. A flood output is
    # always multi-band (max_prob + one band per RP), so a bad file fails here.
    # To force a regeneration, delete the .tif (or _utm.tif).
    _sfx = "" if ssp is None else f"_ssp{ssp}"
    _out = os.path.join(spatial_dir, f"{city_name}_{flood_type}_{year}{_sfx}.tif")
    _utm = _out.replace(".tif", "_utm.tif")

    def _valid(path):
        try:
            with rasterio.open(path) as s:
                return s.count >= 2 and s.width > 0 and s.height > 0
        except Exception:
            return False

    if _valid(_out) and _valid(_utm):
        logger.info(f"Skip (valid output exists): {os.path.basename(_out)}")
        return {"wgs84": _out, "utm": _utm}

    rp_temp_files = []
    successful_rps = []

    for rp in flood_rps:

        # ---------------------------------------------------
        # 1. Collect tile paths for this return period
        # ---------------------------------------------------
        def _build_tile_paths(naming):
            """Build tile paths using 'flat' or 'folder' naming."""
            paths = []
            for lat in lat_tiles:
                for lon in lon_tiles:
                    tile = f"{lat.lower()}{lon.lower()}.tif"
                    if naming == "flat":
                        p = (f"{GCS_FATHOM_BASE}/"
                             f"1in{rp}-{flood_type_folder_dict[flood_type]}-{year}"
                             f"_{lat.lower()}{lon.lower()}.tif")
                    else:
                        if year <= 2020:
                            p = (f"{GCS_FATHOM_BASE}/"
                                 f"GLOBAL-1ARCSEC-NW_OFFSET-1in{rp}-"
                                 f"{flood_type_folder_dict[flood_type]}-DEPTH-{year}-"
                                 f"PERCENTILE50-v3.0/{tile}")
                        else:
                            p = (f"{GCS_FATHOM_BASE}/"
                                 f"GLOBAL-1ARCSEC-NW_OFFSET-1in{rp}-"
                                 f"{flood_type_folder_dict[flood_type]}-DEPTH-{year}-"
                                 f"SSP{flood_ssp_labels[ssp]}-PERCENTILE50-v3.0/{tile}")
                    paths.append(p)
            return paths

        # Tiles live under two naming conventions (legacy "flat" and the
        # complete "folder"/GLOBAL v3.0 set) and neither is guaranteed complete
        # on its own, so mosaic the UNION of both — mosaic_raster probes each
        # path and keeps only the tiles that actually exist, so listing both
        # schemes is safe and works regardless of which one a tile lives under.
        # folder is listed first so it wins on any overlap (method='first').
        # The flat path format doesn't encode SSP, so it's only added for
        # <=2020; folder naming covers every year/SSP.
        naming_used = ["folder", "flat"] if year <= 2020 else ["folder"]

        # ---------------------------------------------------
        # 2-4. Virtual mosaic -> mask to AOI -> threshold, all windowed so a
        #      national-scale raster never materializes in memory. Writes the
        #      thresholded single-band result straight to the per-RP temp file.
        # ---------------------------------------------------
        tile_paths = [p for naming in naming_used
                      for p in _build_tile_paths(naming)]

        rp_temp_name = (
            f"tmp_{city_name}_{flood_type}_{year}"
            f"{'' if ssp is None else f'_ssp{ssp}'}_rp{rp}_thresh.tif"
        )
        rp_temp_path = os.path.join(spatial_dir, rp_temp_name)

        try:
            wrote = _windowed_rp_raster(
                tile_paths, buffer_aoi, flood_threshold, 100 / rp, rp_temp_path
            )
        except Exception as e:
            logger.debug(f"Windowed mosaic/mask failed for RP {rp}: {str(e)}")
            wrote = False
        if not wrote:
            continue

        rp_temp_files.append(rp_temp_path)
        successful_rps.append(rp)

    # -------------------------------------------------------
    # 5. Composite across return periods (from temp files)
    # -------------------------------------------------------
    if not rp_temp_files:
        logger.warning(
            f"{flood_type} {year}"
            + (f" SSP{ssp}" if ssp else "")
            + " : no valid RP data"
        )
        return None

    if ssp is None:
        out_name = f"{city_name}_{flood_type}_{year}.tif"
    else:
        out_name = f"{city_name}_{flood_type}_{year}_ssp{ssp}.tif"

    output_raster = os.path.join(spatial_dir, out_name)

    composite_flood_raster(
        rp_temp_files,
        output_raster,
        flood_rps=successful_rps
    )

    # Clean up per-RP temp files
    for f in rp_temp_files:
        try:
            os.remove(f)
        except Exception:
            pass

    # -------------------------------------------------------
    # 6. Reproject to UTM (same as old code)
    # -------------------------------------------------------
    utm_output = output_raster.replace(".tif", "_utm.tif")

    raster_pro.reproject_raster(
        output_raster,
        utm_output,
        dst_crs=utm_crs,
        compress='deflate'
    )

    logger.info(f"Generated: {out_name}")

    return {
        "wgs84": output_raster,
        "utm": utm_output
    }

def datacollection(
        aoi: gpd.GeoDataFrame,
        city_name: str,
        city_inputs: dict,
        menu: dict,
        output_dir: str,
    ):
    """
    Collect Fathom flood rasters from private GCS bucket,
    clip to AOI, threshold, and generate composite rasters.

    Access control:
    - Team member (IAM access): full analysis runs
    - Public user (no IAM access): flood section skipped
    """

    logger.info("Starting Fathom data collection (GCS-native)…")

    # -----------------------------
    # Validate AOI
    # -----------------------------
    if aoi is None or aoi.empty:
        logger.error("AOI is empty.")
        return

    if aoi.crs is None:
        logger.error("AOI has no CRS defined.")
        return

    logger.info(f"AOI CRS: {aoi.crs}")

    # -----------------------------
    # Parameters
    # -----------------------------
    flood_threshold = city_inputs['flood']['threshold']
    flood_years = city_inputs['flood']['year']
    if isinstance(flood_years, int):
        flood_years = [flood_years]

    flood_ssps = city_inputs['flood']['ssp']
    flood_rps = city_inputs['flood']['return_period']

    flood_types = ['coastal', 'fluvial', 'pluvial']

    flood_ssp_labels = {
        1: '1_2.6',
        2: '2_4.5',
        3: '3_7.0',
        5: '5_8.5'
    }

    flood_type_folder_dict = {
        'coastal': 'COASTAL-UNDEFENDED',
        'fluvial': 'FLUVIAL-UNDEFENDED',
        'pluvial': 'PLUVIAL-DEFENDED'
    }

    spatial_dir = os.path.join(output_dir, "spatial")
    os.makedirs(spatial_dir, exist_ok=True)

    # -----------------------------
    # AOI preparation — match R's static_map_bounds
    # -----------------------------
    from core.py.aoi_buffer import static_map_buffer
    buffer_aoi = static_map_buffer(aoi)

    # OLD: buffered by max(width, height) in degrees — too large for corridor AOIs
    # aoi_bounds = aoi.bounds
    # buffer_aoi = aoi.buffer(
    #     np.nanmax([
    #         aoi_bounds.maxx - aoi_bounds.minx,
    #         aoi_bounds.maxy - aoi_bounds.miny
    #     ])
    # )

    lat_tiles = raster_pro.tile_finder(buffer_aoi, 'lat')
    lon_tiles = raster_pro.tile_finder(buffer_aoi, 'lon')
    logger.info(f"found: {lat_tiles, lon_tiles}")

    utm_crs = aoi.estimate_utm_crs()

    # -----------------------------
    # Main processing loop
    # -----------------------------
    for ft in flood_types:
        logger.info(f"Flood Types: {ft}")
        if not menu.get(f'flood_{ft}', False):
            continue

        for year in flood_years:

            if year <= 2020:
                try:
                    _process_year(
                        ft, year, None, flood_rps, lat_tiles, lon_tiles,
                        flood_type_folder_dict, flood_threshold,
                        spatial_dir, buffer_aoi, utm_crs, city_name
                    )
                except Exception as e:
                    import traceback
                    logger.error(
                        f"Failed to process {ft} {year}: {e}\n{traceback.format_exc()}"
                    )
                    continue

            else:
                for ssp in flood_ssps:
                    try:
                        _process_year(
                            ft, year, ssp, flood_rps, lat_tiles, lon_tiles,
                            flood_type_folder_dict, flood_threshold,
                            spatial_dir, buffer_aoi, utm_crs, city_name,
                            flood_ssp_labels
                        )
                    except Exception as e:
                        import traceback
                        logger.error(
                            f"Failed to process {ft} {year} SSP{ssp}: {e}\n{traceback.format_exc()}"
                        )
                        continue

    # -----------------------------
    # Combined flood map
    # -----------------------------
    def _combine_flood_rasters(tif_list, output_path):
        """Merge multi-band flood TIFs (max across flood types, per RP band).

        Each TIF has: band 1 = max_probability, band 2+ = per-RP binary (r10, r100, r1000).
        Flood types can differ in BOTH which RP bands exist (a type may be missing
        r100 where no Fathom tiles exist there) and their extent, so align by band
        description and take max across types over the UNION extent.

        rasterio.merge does the union/pad/max per band. Because flood types can
        have different band counts, a single positional merge won't work — instead
        merge once per band description over single-band views, passing one shared
        union bounds so every band lands on the same grid (and can be stacked).
        All types share the same Fathom grid + resolution, so merge copies pixels
        without resampling (binary RP bands stay 0/1).
        """
        from rasterio.merge import merge
        from rasterio.io import MemoryFile

        if not tif_list:
            return

        # Map each band description to the (tif, band index) pairs that contain it
        band_sources = {}  # desc -> [(path, band_idx), ...]
        base_profile = None
        res = None
        bounds_list = []
        for p in tif_list:
            with rasterio.open(p) as src:
                bounds_list.append(src.bounds)
                if base_profile is None:
                    base_profile = src.profile.copy()
                    res = src.res
                for i in range(1, src.count + 1):
                    desc = src.descriptions[i - 1] or f"band_{i}"
                    band_sources.setdefault(desc, []).append((p, i))

        # max_probability first, then return-period bands ascending
        band_order = ["max_probability"] + sorted(
            [d for d in band_sources if d != "max_probability"],
            key=lambda x: int(x.replace("r", "")) if x.startswith("r") else 0
        )
        band_order = [d for d in band_order if d in band_sources]

        # One shared union extent (left, bottom, right, top) so every band aligns
        union_bounds = (
            min(b.left for b in bounds_list),
            min(b.bottom for b in bounds_list),
            max(b.right for b in bounds_list),
            max(b.top for b in bounds_list),
        )
        nodata = base_profile.get("nodata")

        # Per band, per row-strip: windowed max across the contributing flood-type
        # rasters. Never holds a full national band in memory (national comb OOMs
        # otherwise). Same result as merge(method='max') over the union grid.
        from rasterio.windows import from_bounds, bounds as win_bounds, Window
        from rasterio.transform import from_origin
        from rasterio.enums import Resampling

        xres, yres = res
        left, bottom, right, top = union_bounds
        width = int(round((right - left) / xres))
        height = int(round((top - bottom) / yres))
        out_transform = from_origin(left, top, xres, yres)
        fill = nodata if nodata is not None else 0
        STRIP = 2048

        out_profile = base_profile.copy()
        out_profile.update(count=len(band_order), height=height, width=width,
                           transform=out_transform, tiled=True,
                           compress='deflate', BIGTIFF='IF_SAFER')
        with rasterio.open(output_path, 'w', **out_profile) as dst:
            for out_i, desc in enumerate(band_order, 1):
                dst.set_band_description(out_i, desc)
                srcs = [(rasterio.open(p), idx) for p, idx in band_sources[desc]]
                try:
                    for r in range(0, height, STRIP):
                        h = min(STRIP, height - r)
                        sb = win_bounds(Window(0, r, width, h), out_transform)
                        acc = None
                        for src, idx in srcs:
                            data = src.read(
                                idx, window=from_bounds(*sb, src.transform),
                                out_shape=(h, width), boundless=True,
                                fill_value=fill, resampling=Resampling.nearest,
                            ).astype(np.float32)
                            acc = data if acc is None else np.maximum(acc, data)
                        dst.write(acc.astype(out_profile['dtype']), out_i,
                                  window=Window(0, r, width, h))
                finally:
                    for src, _ in srcs:
                        src.close()

    if menu.get('flood_comb', False):
        for year in flood_years:

            if year <= 2020:
                comb_types = [
                    ft for ft in flood_types
                    if exists(f'{spatial_dir}/{city_name}_{ft}_{year}.tif')
                ]
                comb_list = [
                    f'{spatial_dir}/{city_name}_{ft}_{year}.tif'
                    for ft in comb_types
                ]

                if comb_list:
                    logger.info(f"Flood Types: combined ({', '.join(comb_types)})")
                    comb_path = f'{spatial_dir}/{city_name}_comb_{year}.tif'
                    _combine_flood_rasters(comb_list, comb_path)
                    logger.info(f"Generated: {os.path.basename(comb_path)}")

                    raster_pro.reproject_raster(
                        comb_path,
                        f'{spatial_dir}/{city_name}_comb_{year}_utm.tif',
                        dst_crs=utm_crs,
                        compress='deflate'
                    )

            else:
                for ssp in flood_ssps:
                    comb_types = [
                        ft for ft in flood_types
                        if exists(f'{spatial_dir}/{city_name}_{ft}_{year}_ssp{ssp}.tif')
                    ]
                    comb_list = [
                        f'{spatial_dir}/{city_name}_{ft}_{year}_ssp{ssp}.tif'
                        for ft in comb_types
                    ]

                    if comb_list:
                        logger.info(f"Flood Types: combined ({', '.join(comb_types)})")
                        comb_path = f'{spatial_dir}/{city_name}_comb_{year}_ssp{ssp}.tif'
                        _combine_flood_rasters(comb_list, comb_path)
                        logger.info(f"Generated: {os.path.basename(comb_path)}")

                        raster_pro.reproject_raster(
                            f'{spatial_dir}/{city_name}_comb_{year}_ssp{ssp}.tif',
                            f'{spatial_dir}/{city_name}_comb_{year}_ssp{ssp}_utm.tif',
                            dst_crs=utm_crs,
                            compress='deflate'
                        )

