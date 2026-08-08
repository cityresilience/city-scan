"""Build a scan's spatial outputs by cropping an existing scan's data.

Instead of collecting each layer from source (GEE, Fathom, ...), read the
finished rasters/vectors of a larger scan (e.g. a national scan) and mask each
to *this* scan's smaller AOI. Then `--analyze` recomputes the CSVs from the
cropped data — no re-collection.

Driven by `bucketdata` in the scan's city_inputs.yml:
    bucketdata: crp-city-scan/2026-07-uzbekistan   # <bucket>/<scan-id>
The source spatial dir is `gs://<bucketdata>/02-process-output/spatial/`.

Shape mirrors cogify.py (loop over spatial files). Masking uses the same
rasterio.mask.mask(..., crop=True) as raster_module.raster_mask_file (a windowed
read — only the AOI region is fetched, not the whole national raster). Private
COGs are read locally over /vsicurl with a gcloud bearer token, exactly like
publish/index_cog.qmd.
"""
import os
import re
import subprocess
import tempfile

import geopandas as gpd
import rasterio
import rasterio.mask

from core.py.log_module import setup_logger

logger = setup_logger(__name__)

RASTER_EXT = (".tif", ".tiff")
VECTOR_EXT = (".gpkg", ".geojson", ".fgb")


def _src_url(gs_path):
    """gs://bucket/key -> /vsicurl/https URL (range-readable with a bearer token)."""
    return "/vsicurl/https://storage.googleapis.com/" + gs_path[len("gs://"):]


def _list_spatial(src_spatial):
    """List the source spatial files (gs:// URLs, no trailing-slash 'dirs')."""
    out = subprocess.run(["gcloud", "storage", "ls", src_spatial.rstrip("/") + "/"],
                         capture_output=True, text=True, check=True).stdout
    return [l.strip() for l in out.splitlines()
            if l.strip().startswith("gs://") and not l.strip().endswith("/")]


def _out_name(basename, src_city, city_l):
    """Re-prefix a source filename with this scan's city slug: strip the source
    city prefix if present, prepend the new one (uzbekistan_elevation.tif ->
    chust_elevation.tif). Stem is preserved so fuzzy_string analyze matching still
    works."""
    stem_ext = basename
    if src_city and basename.startswith(src_city + "_"):
        stem_ext = basename[len(src_city) + 1:]
    return stem_ext if stem_ext.startswith(city_l + "_") else f"{city_l}_{stem_ext}"


def _crop_raster(gs_path, aoi, out_dir, src_city, city_l):
    url = _src_url(gs_path)
    out_fn = _out_name(os.path.basename(gs_path), src_city, city_l)
    out_path = os.path.join(out_dir, out_fn)
    try:
        with rasterio.open(url) as src:
            geoms = aoi.to_crs(src.crs).geometry.values     # AOI in the raster's CRS
            img, transform = rasterio.mask.mask(src, geoms, all_touched=True, crop=True)
            meta = src.meta.copy()
            meta.update(driver="GTiff", height=img.shape[1], width=img.shape[2],
                        transform=transform, compress="deflate", tiled=True)
            descriptions = src.descriptions   # band names (e.g. "pop_2020") drive year labels
        with rasterio.open(out_path, "w", **meta) as dst:
            dst.write(img)
            if descriptions and any(descriptions):
                dst.descriptions = descriptions
        logger.info(f"  crop {os.path.basename(gs_path)} -> {out_fn} "
                    f"({img.shape[2]}x{img.shape[1]})")
    except ValueError as e:   # "Input shapes do not overlap raster" -> AOI off this raster
        logger.warning(f"  skip {os.path.basename(gs_path)}: {e}")
    except Exception as e:
        logger.error(f"  crop failed for {os.path.basename(gs_path)}: {e}")


def _crop_vector(gs_path, aoi, out_dir, src_city, city_l):
    out_fn = _out_name(os.path.basename(gs_path), src_city, city_l)
    out_path = os.path.join(out_dir, out_fn)
    with tempfile.TemporaryDirectory() as td:
        local = os.path.join(td, os.path.basename(gs_path))
        try:
            subprocess.run(["gcloud", "storage", "cp", gs_path, local], check=True,
                           capture_output=True, text=True)
            gdf = gpd.read_file(local)
            clipped = gpd.clip(gdf, aoi.to_crs(gdf.crs))
            if clipped.empty:
                logger.warning(f"  skip {os.path.basename(gs_path)}: no features in AOI")
                return
            clipped.to_file(out_path)
            logger.info(f"  clip {os.path.basename(gs_path)} -> {out_fn} "
                        f"({len(clipped)} feats)")
        except Exception as e:
            logger.error(f"  clip failed for {os.path.basename(gs_path)}: {e}")


def run_crop(scan):
    """Crop the `bucketdata` scan's spatial rasters/vectors to this scan's AOI."""
    src = (scan.city_inputs.get("bucketdata") or "").strip().rstrip("/")
    if not src:
        logger.error("crop: no `bucketdata` in city_inputs.yml — nothing to crop from.")
        return
    if not src.startswith("gs://"):
        src = "gs://" + src
    src_scan = src.rstrip("/").split("/")[-1]                 # e.g. 2026-07-uzbekistan
    m = re.match(r"^\d{4}-\d{2}-(.+)$", src_scan)
    src_city = m.group(1) if m else None                      # e.g. uzbekistan
    src_spatial = f"{src}/02-process-output/spatial"
    logger.info(f"Crop source: {src_spatial}  (src city prefix: {src_city})")

    # Bearer token so GDAL/rasterio can range-read the private COGs over /vsicurl
    # (same auth path as publish/index_cog.qmd).
    token = subprocess.run(["gcloud", "auth", "application-default", "print-access-token"],
                           capture_output=True, text=True, check=True).stdout.strip()
    os.environ["GDAL_HTTP_HEADERS"] = f"Authorization: Bearer {token}"

    aoi = scan.aoi                                            # GeoDataFrame, EPSG:4326
    city_l = scan.city_name
    out_dir = str(scan.spatial_dir)
    os.makedirs(out_dir, exist_ok=True)

    files = _list_spatial(src_spatial)
    rasters = [f for f in files if f.lower().endswith(RASTER_EXT)]
    vectors = [f for f in files if f.lower().endswith(VECTOR_EXT)]
    logger.info(f"Cropping {len(rasters)} rasters + {len(vectors)} vectors to AOI "
                f"'{scan.city_inputs['AOI_shp_name']}' -> {out_dir}")

    for f in rasters:
        _crop_raster(f, aoi, out_dir, src_city, city_l)
    for f in vectors:
        _crop_vector(f, aoi, out_dir, src_city, city_l)
    logger.info("Crop complete.")
