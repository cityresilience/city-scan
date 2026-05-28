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
    out_meta.update({'count': band_count, 'dtype': 'float32'})

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

    rp_temp_files = []
    successful_rps = []

    for rp in flood_rps:

        # ---------------------------------------------------
        # 1️⃣ Collect tile paths for this return period
        # ---------------------------------------------------
        def _build_tile_paths(naming):
            """Build tile paths using 'flat' or 'folder' naming."""
            paths = []
            for lat in lat_tiles:
                for lon in lon_tiles:
                    tile = f"{lat.lower()}{lon.lower()}.tif"
                    if naming == "flat":
                        if year <= 2020:
                            p = (f"{GCS_FATHOM_BASE}/"
                                f"1in{rp}-{flood_type_folder_dict[flood_type]}-{year}"
                                f"_{lat.lower()}{lon.lower()}.tif")
                        else:
                            p = (f"{GCS_FATHOM_BASE}/"
                                f"1in{rp}-{flood_type_folder_dict[flood_type]}-{year}-"
                                f"SSP{flood_ssp_labels[ssp]}_{lat.lower()}{lon.lower()}.tif")
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

        naming_attempts = ["flat", "folder"]

        # ---------------------------------------------------
        # 2️⃣ Mosaic tiles (CRITICAL alignment step)
        # ---------------------------------------------------
        tmp_mosaic_name = (
            f"tmp_{city_name}_{flood_type}_{year}"
            f"{'' if ssp is None else f'_ssp{ssp}'}_rp{rp}.tif"
        )

        tmp_mosaic_path = os.path.join(spatial_dir, tmp_mosaic_name)

        mosaic_ok = False
        for naming in naming_attempts:
            tile_paths = _build_tile_paths(naming)
            try:
                raster_pro.mosaic_raster(
                    tile_paths,
                    spatial_dir,
                    tmp_mosaic_name
                )
                # mosaic_raster filters to existing tiles and silently no-ops
                # when none exist — verify output actually got written before
                # declaring success, otherwise fall through to next naming.
                if not os.path.exists(tmp_mosaic_path):
                    continue
                mosaic_ok = True
                break
            except Exception as e:
                logger.debug(f"Mosaic failed ({naming} naming) for RP {rp}: {str(e)}")
                continue

        if not mosaic_ok:
            continue

        # ---------------------------------------------------
        # 3️⃣ Mask mosaic to AOI (ensures identical grid)
        # ---------------------------------------------------
        try:
            with rasterio.open(tmp_mosaic_path) as src:
                out_image, out_transform = mask(
                    src,
                    buffer_aoi.geometry,
                    crop=True
                )

                out_meta = src.meta.copy()
                out_meta.update({
                    "height": out_image.shape[1],
                    "width": out_image.shape[2],
                    "transform": out_transform
                })

        except Exception as e:
            logger.debug(f"Mask failed for RP {rp}: {str(e)}")
            continue

        # ---------------------------------------------------
        # 4️⃣ Apply threshold + probability weighting
        # ---------------------------------------------------
        out_image, out_meta = apply_flood_threshold(
            out_image,
            out_meta,
            flood_threshold,
            100 / rp
        )

        # Write thresholded result to temp file (instead of holding in RAM)
        rp_temp_name = (
            f"tmp_{city_name}_{flood_type}_{year}"
            f"{'' if ssp is None else f'_ssp{ssp}'}_rp{rp}_thresh.tif"
        )
        rp_temp_path = os.path.join(spatial_dir, rp_temp_name)
        rp_meta = out_meta.copy()
        rp_meta.update({'count': 1, 'dtype': 'float32'})
        with rasterio.open(rp_temp_path, 'w', **rp_meta) as dst:
            dst.write(np.squeeze(out_image).astype(np.float32), 1)

        rp_temp_files.append(rp_temp_path)
        successful_rps.append(rp)

        # Free memory and remove mosaic temp
        del out_image
        try:
            os.remove(tmp_mosaic_path)
        except Exception:
            pass

    # -------------------------------------------------------
    # 5️⃣ Composite across return periods (from temp files)
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
    # 6️⃣ Reproject to UTM (same as old code)
    # -------------------------------------------------------
    utm_output = output_raster.replace(".tif", "_utm.tif")

    raster_pro.reproject_raster(
        output_raster,
        utm_output,
        dst_crs=utm_crs
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
        Aligns by band description and takes max across flood types.
        """
        # Collect all unique band descriptions across TIFs
        all_bands = {}  # {description: [(tif_path, band_index), ...]}
        for p in tif_list:
            with rasterio.open(p) as src:
                for i in range(1, src.count + 1):
                    desc = src.descriptions[i - 1] or f"band_{i}"
                    all_bands.setdefault(desc, []).append((p, i))

        # Ensure max_probability is first, then sorted RP bands
        band_order = ["max_probability"] + sorted(
            [b for b in all_bands if b != "max_probability"],
            key=lambda x: int(x.replace("r", "")) if x.startswith("r") else 0
        )

        # Read band 1 from first TIF to get grid/meta
        with rasterio.open(tif_list[0]) as ref:
            ref_meta = ref.meta.copy()
            h, w = ref.height, ref.width
            ref_transform = ref.transform

        merged_arrays = []
        band_descs = []

        for desc in band_order:
            if desc not in all_bands:
                continue
            # Stack this band from all flood types, take max
            stack = []
            for p, idx in all_bands[desc]:
                try:
                    with rasterio.open(p) as src:
                        stack.append(src.read(idx).astype(np.float32))
                except Exception:
                    continue
            if not stack:
                continue
            combined = np.maximum.reduce(stack)
            merged_arrays.append(combined)
            band_descs.append(desc)

        if not merged_arrays:
            return

        ref_meta.update({"count": len(merged_arrays), "dtype": "float32"})
        with rasterio.open(output_path, 'w', **ref_meta) as dst:
            for i, (arr, desc) in enumerate(zip(merged_arrays, band_descs), 1):
                dst.write(arr, i)
                dst.set_band_description(i, desc)

    if menu.get('flood_comb', False):
        for year in flood_years:

            if year <= 2020:
                comb_list = [
                    f'{spatial_dir}/{city_name}_{ft}_{year}.tif'
                    for ft in flood_types
                    if exists(f'{spatial_dir}/{city_name}_{ft}_{year}.tif')
                ]

                if comb_list:
                    comb_path = f'{spatial_dir}/{city_name}_comb_{year}.tif'
                    _combine_flood_rasters(comb_list, comb_path)

                    raster_pro.reproject_raster(
                        comb_path,
                        f'{spatial_dir}/{city_name}_comb_{year}_utm.tif',
                        dst_crs=utm_crs
                    )

            else:
                for ssp in flood_ssps:
                    comb_list = [
                        f'{spatial_dir}/{city_name}_{ft}_{year}_ssp{ssp}.tif'
                        for ft in flood_types
                        if exists(f'{spatial_dir}/{city_name}_{ft}_{year}_ssp{ssp}.tif')
                    ]

                    if comb_list:
                        comb_path = f'{spatial_dir}/{city_name}_comb_{year}_ssp{ssp}.tif'
                        _combine_flood_rasters(comb_list, comb_path)

                        raster_pro.reproject_raster(
                            f'{spatial_dir}/{city_name}_comb_{year}_ssp{ssp}.tif',
                            f'{spatial_dir}/{city_name}_comb_{year}_ssp{ssp}_utm.tif',
                            dst_crs=utm_crs
                        )

