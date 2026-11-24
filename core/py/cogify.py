"""
Cogify step: turn a scan's 02-process-output rasters into Cloud-Optimized
GeoTIFFs (COGs) and write them, plus copies of the vector/tabular outputs and a
manifest, to a delivery target.

Driven by cogify.yml (per-scan, in 01-user-input; falls back to inputs/cogify.yml).
Invoked as a scan-level step: `python -m tasks --cogify --scan-id <id>`.

COG conversion streams tile-by-tile (gdal_translate -of COG), so it is
memory-safe even for national rasters — no windowing needed here.
"""
import os
import re
import csv
import glob
import shutil
import subprocess
import tempfile

import yaml

from core.py.log_module import setup_logger

logger = setup_logger(__name__)

RASTER_EXT = (".tif", ".tiff")
VECTOR_EXT = (".gpkg", ".geojson", ".fgb")
TABULAR_EXT = (".csv", ".yml", ".yaml")

# Output-file stem prefixes owned by a task, for a scoped cogify (when task
# names are passed, e.g. `--cogify fathom` only re-COGs that task's outputs).
# Stems are matched after the `{city}_` prefix is stripped.
TASK_OUTPUT_PREFIXES = {
    "fathom": ("comb", "fluvial", "pluvial", "coastal", "flood"),
    "elevation": ("elevation",),          # elevation, elevation_buf
    "slope": ("slope",),                  # slope, slope_proj
    "landcover": ("lc",),                 # lc
    "forest": ("forest_cover", "deforestation"),
    "lst": ("lst_summer",),               # summer only (winter not regenerated)
    "glaciers": ("glacier_extent", "glacier_ndsi"),
    "wind": ("wind",),
    "precipitation": ("precip_trend", "precip_anomaly", "rainfall_deficit"),
    "dust": ("dust",),
    "aerosol": ("aerosol",),
}


def _load_config(scan):
    """Load cogify.yml from the scan's 01-user-input, else repo inputs/."""
    from core.config.paths import INPUTS
    candidates = [os.path.join(str(scan.input_dir), "cogify.yml"),
                  os.path.join(str(INPUTS), "cogify.yml")]
    for p in candidates:
        if os.path.exists(p):
            logger.info(f"Cogify config: {p}")
            with open(p) as f:
                return yaml.safe_load(f) or {}
    logger.warning("No cogify.yml found — using defaults (nearest, same-bucket).")
    return {}


def _is_gs(base):
    return base.startswith("gs://")


def _raster_dst(out_base, fn):
    """A GDAL-writable destination path (local, or /vsigs for a gs:// target)."""
    if _is_gs(out_base):
        return "/vsigs/" + out_base[len("gs://"):].rstrip("/") + "/" + fn
    return os.path.join(out_base, fn)


def _put_file(src, out_base, fn):
    """Copy a non-raster file to the target (local or gs://)."""
    if _is_gs(out_base):
        subprocess.run(["gcloud", "storage", "cp", src,
                        out_base.rstrip("/") + "/" + fn], check=True)
    else:
        os.makedirs(out_base, exist_ok=True)
        shutil.copy(src, os.path.join(out_base, fn))


def _load_manifest(manifest_base):
    """Read an existing manifest.csv from the target (gs:// or local). Returns a
    list of row dicts, or [] if none/unreadable."""
    if _is_gs(manifest_base):
        try:
            out = subprocess.run(
                ["gcloud", "storage", "cat", manifest_base.rstrip("/") + "/manifest.csv"],
                capture_output=True, text=True, check=True).stdout
            return list(csv.DictReader(out.splitlines()))
        except subprocess.CalledProcessError:
            return []
    path = os.path.join(manifest_base, "manifest.csv")
    if os.path.exists(path):
        with open(path, newline="") as f:
            return list(csv.DictReader(f))
    return []


def _write_cog(src, out_fn, raster_base, compress, resampling):
    """Create a COG from src. For a gs:// target, gdal can't write a COG over
    /vsigs (COG creation needs random writes, unsupported on GCS), so stage the
    COG to a local temp file and upload the finished file. Local targets write
    directly."""
    gdal_args = ["-of", "COG", "-co", f"COMPRESS={compress}",
                 "-co", "BIGTIFF=IF_SAFER",
                 "-co", f"RESAMPLING={resampling}", "-q"]
    if _is_gs(raster_base):
        with tempfile.NamedTemporaryFile(suffix=".tif", delete=False) as tf:
            tmp = tf.name
        try:
            subprocess.run(["gdal_translate", src, tmp] + gdal_args, check=True)
            subprocess.run(["gcloud", "storage", "cp", tmp,
                            raster_base.rstrip("/") + "/" + out_fn], check=True)
        finally:
            if os.path.exists(tmp):
                os.unlink(tmp)
    else:
        os.makedirs(raster_base, exist_ok=True)
        subprocess.run(["gdal_translate", src, os.path.join(raster_base, out_fn)]
                       + gdal_args, check=True)


def _lookup(stem, layers, default_resampling):
    """Resolve (resampling, out_name) for a raster stem, honoring _utm/_proj
    fallback to the base layer and the default resampling."""
    def _entry(key):
        e = layers.get(key)
        return e if isinstance(e, dict) else None

    entry = _entry(stem)
    if entry is None:
        for suf in ("_utm", "_proj"):
            if stem.endswith(suf):
                entry = _entry(stem[: -len(suf)])
                if entry:
                    break
    resampling = (entry or {}).get("resampling", default_resampling)
    name = (entry or {}).get("name")  # None -> keep original
    return resampling, name


def run_cogify(scan, only_tasks=None):
    """Cogify + copy a scan's outputs to the configured delivery target.

    only_tasks: optional list of task names (e.g. ['fathom']). When given, only
    those tasks' output files are (re-)COGged/copied and the existing manifest is
    MERGED with the new rows rather than overwritten — so re-delivering one task
    after a rerun doesn't touch the other layers. None = every output (default).
    """
    cfg = _load_config(scan)
    layers = cfg.get("layers", {}) or {}
    cog_cfg = cfg.get("cog", {}) or {}
    compress = cog_cfg.get("compress", "DEFLATE")
    default_resampling = cog_cfg.get("default_resampling", "nearest")

    # Resolve the delivery target + layout:
    #   bucket == local -> same scan folder: 02-process-output/cogs/ (COGs +
    #                      manifest; vectors/CSVs already live in this folder)
    #   bucket == <name> -> gs://<name>/<prefix>/spatial/ (COGs + vectors),
    #                       /tabular/ (CSVs), manifest.csv at the root
    tgt = cfg.get("target", {}) or {}
    bucket = tgt.get("bucket", "local")
    if bucket == "local":
        root = os.path.join(str(scan.output_dir), "cogs")
        os.makedirs(root, exist_ok=True)
        raster_base = root
        vector_base = None        # vectors already in this scan folder
        tabular_base = None       # CSVs already in this scan folder
        manifest_base = root
    else:
        prefix = tgt.get("prefix") or scan.cityscan_id
        root = f"gs://{bucket.rstrip('/')}/{prefix.strip('/')}"
        raster_base = root + "/spatial"
        vector_base = root + "/spatial"
        tabular_base = root + "/tabular"
        manifest_base = root
    logger.info(f"Cogify target: {root}")

    # City slug used as the filename prefix (e.g. 'uzbekistan')
    city_l = re.sub(r"[^a-z0-9]+", "_", scan.city_name.lower()).strip("_")

    def _stem(path):
        base = os.path.splitext(os.path.basename(path))[0]
        pre = city_l + "_"
        return base[len(pre):] if base.startswith(pre) else base

    # Scope predicate: with only_tasks, keep files whose stem starts with one of
    # the requested tasks' output prefixes; otherwise keep everything.
    scope_prefixes = None
    if only_tasks:
        scope_prefixes = tuple(
            pre for t in only_tasks for pre in TASK_OUTPUT_PREFIXES.get(t, ())
        )
        unknown = [t for t in only_tasks if t not in TASK_OUTPUT_PREFIXES]
        if unknown:
            logger.warning(f"Cogify scope: no output prefixes known for {unknown} "
                           f"(known: {sorted(TASK_OUTPUT_PREFIXES)})")
        logger.info(f"Cogify scoped to {list(only_tasks)} -> stems {list(scope_prefixes)}")

    def _in_scope(path):
        return scope_prefixes is None or _stem(path).startswith(scope_prefixes)

    manifest = []  # rows: {output, type, resampling, source}

    # 1. Rasters -> COG
    rasters = sorted(
        p for ext in RASTER_EXT
        for p in glob.glob(os.path.join(str(scan.spatial_dir), f"*{ext}"))
        if _in_scope(p)
    )
    for src in rasters:
        stem = _stem(src)
        resampling, name = _lookup(stem, layers, default_resampling)
        out_fn = (name or stem) + os.path.splitext(src)[1]
        # gdal writes the prefix back so the delivered file stays city-scoped
        out_fn = f"{city_l}_{out_fn}" if not out_fn.startswith(city_l + "_") else out_fn
        logger.info(f"  COG {os.path.basename(src)} -> {out_fn} (resampling={resampling})")
        try:
            _write_cog(src, out_fn, raster_base, compress, resampling)
            manifest.append({"output": out_fn, "type": "raster (COG)",
                             "resampling": resampling, "source": os.path.basename(src)})
        except subprocess.CalledProcessError as e:
            logger.error(f"  cogify failed for {os.path.basename(src)}: {e}")

    # 2. Vectors -> spatial/ , tabular -> tabular/ (delivery only; local mode
    #    leaves them in place since raw already sits in the same scan folder).
    #    Still listed in the manifest either way.
    def _copy_group(src_dir, exts, dst_base, kind):
        for src in sorted(p for ext in exts
                          for p in glob.glob(os.path.join(str(src_dir), f"*{ext}"))
                          if _in_scope(p)):
            fn = os.path.basename(src)
            if dst_base is not None:
                logger.info(f"  copy {fn} ({kind})")
                try:
                    _put_file(src, dst_base, fn)
                except subprocess.CalledProcessError as e:
                    logger.error(f"  copy failed for {fn}: {e}")
            manifest.append({"output": fn, "type": kind, "resampling": "", "source": fn})

    _copy_group(scan.spatial_dir, VECTOR_EXT, vector_base, "vector")
    _copy_group(scan.tabular_dir, TABULAR_EXT, tabular_base, "tabular")

    # 3. Manifest (table of contents). On a scoped run, merge the new rows into
    #    the existing manifest (replace same-output rows, keep the rest) so the
    #    other tasks' entries survive; on a full run, write it fresh.
    if cfg.get("manifest", True) and manifest:
        if scope_prefixes is not None:
            merged = {r["output"]: r for r in _load_manifest(manifest_base)}
            for r in manifest:
                merged[r["output"]] = r
            rows = list(merged.values())
        else:
            rows = manifest
        with tempfile.NamedTemporaryFile("w", suffix=".csv", delete=False, newline="") as tf:
            w = csv.DictWriter(tf, fieldnames=["output", "type", "resampling", "source"])
            w.writeheader()
            w.writerows(rows)
            tmp = tf.name
        _put_file(tmp, manifest_base, "manifest.csv")
        os.unlink(tmp)
        logger.info(f"Wrote manifest.csv ({len(rows)} entries)")

    logger.info(f"Cogify complete -> {root}")
    return root
