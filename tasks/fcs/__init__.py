"""FCS (Future City Scan) as a City Scan task.

`scan fcs [--multicity]` runs the vendored Future City Scan pipeline for each
city's AOI. FCS lives in its own conda env (`fcs-pipeline`) with heavy geospatial
deps that differ from the cityscan env, so this adapter drives it as a subprocess
via `conda run -n <fcs_env>`, streaming its per-section log into the scan output.

The FCS runner already tracks every section as SUCCESS / SKIPPED / FAILED and
continues past failures — matching how City Scan treats task errors. This adapter
raises only if the pipeline crashes wholesale (non-zero exit); individual layer
failures are logged and summarised, never fatal.

Layer activation + paths come from menu.yml:
    fcs_layers: {population: True, gdp: True, ...}   # per-section on/off
    fcs_base_dir: ''    # blank -> $CITYSCAN_FCS_DIR -> <repo parent>/FCS
    fcs_env: 'fcs-pipeline'                           # conda env with FCS deps
Outputs land in <fcs_base_dir>/02-process-output/ as Pakistan_<City>_*.
"""
import glob
import json
import os
import shutil
import subprocess
import time
from pathlib import Path

import yaml

from core.config.paths import external_dir, describe_external
from core.py.log_module import setup_logger

logger = setup_logger(__name__)

FCS_DIR = Path(__file__).resolve().parent            # tasks/fcs (vendored pipeline)
DEFAULT_ENV = "fcs-pipeline"

# The FCS *code* is vendored here; only its data/output tree lives outside the
# repo (~160 GB, uncommittable). See core/config/paths.py::external_dir.
DEFAULT_DATA_NAME = "FCS"
ENV_VAR = "CITYSCAN_FCS_DIR"
TAG = "_fsca"                                          # appended to FCS output filenames

# All 17 sections on by default; overridden by menu.yml `fcs_layers`.
DEFAULT_LAYERS = {
    "population_rescaling": True, "population": True, "gdp_rescaling": True,
    "gdp": True, "urbanland": True, "heatflux": True, "urbanheatisland": True,
    "cckp_precipitation": True, "cckp_temperature": True,
    "flood_population_exposure": True, "flood_infrastructure_exposure": True,
    "cleanup": True, "demographics": True, "cyclones": True, "erosion": True,
    "country_population_ratio": True, "country_gdp_ratio": True,
}

# Which folders under <base_dir>/data/ each layer reads. Used only when pulling
# from GCS (`fcs_data_source: gcs`) so a run fetches what its ENABLED layers
# need and nothing else — with the Pakistan layer set that is ~34 GB instead of
# the ~121 GB the full pipeline can touch. Derived by grepping the canonical
# pipeline's src/*.py; layers absent from this map need no bulk data.
LAYER_DATA = {
    "urbanland": ["urbanland"],
    "population": ["popdynamics"],
    "population_rescaling": ["popdynamics"],
    "country_population_ratio": ["popdynamics"],
    "heatflux": ["heatflux"],
    "urbanheatisland": ["urbanheatisland"],
    "demographics": ["demographic"],
    "cckp_precipitation": ["CCKP"],
    "cckp_temperature": ["CCKP"],
    "gdp": ["gdp"],
    "gdp_rescaling": ["gdp"],
    "country_gdp_ratio": ["gdp"],
    "erosion": ["globalErosionProjections"],
    "flood_population_exposure": ["fathom"],
    "flood_infrastructure_exposure": ["fathom"],
}

DEFAULT_DATA_BUCKET = "city-scan-global-data"
DEFAULT_DATA_PREFIX = "fcs-data"
DEFAULT_INPUTS_PREFIX = "fcs-inputs"

# Default flood analysis settings (mirrors fcs_menue.yaml).
DEFAULT_FLOOD = {
    "coastal": True, "fluvial": True, "pluvial": True, "threshold": 15,
    "year": [2020, 2030, 2050, 2080], "ssp": [1, 2, 3, 5],
    "prob_cutoff": [1, 10], "rps": [10, 100, 1000, 20, 200, 50, 500],
}


def _write_aoi(scan, shp_dir: Path, city: str) -> Path:
    """Write the city's AOI (already WGS84) to AOI_<city>_Final.shp for FCS."""
    shp_dir.mkdir(parents=True, exist_ok=True)
    gdf = scan.aoi.copy()
    gdf["__k"] = 0
    gdf = gdf.dissolve(by="__k").reset_index(drop=True)[["geometry"]]
    out = shp_dir / f"AOI_{city}_Final.shp"
    gdf.to_file(out)
    return out


def sync_data(scan, base_dir: Path, layers: dict) -> None:
    """Pull the global inputs this run's enabled layers need, if configured to.

    No-op unless `fcs_data_source: 'gcs'`. The pipeline itself is untouched — it
    still reads plain local paths; this only guarantees they exist first. See
    core/py/global_data.py for why it's a download rather than /vsigs/ streaming.
    """
    menu = getattr(scan, "menu", {}) or {}
    if str(menu.get("fcs_data_source", "local")).lower() != "gcs":
        return

    from core.py.global_data import sync

    wanted = sorted({folder
                     for layer, on in layers.items() if on
                     for folder in LAYER_DATA.get(layer, [])})
    if not wanted:
        logger.info("FCS: no enabled layer needs bulk data — nothing to sync")
    else:
        logger.info(f"FCS: syncing global data for enabled layers: {', '.join(wanted)}")
        sync(menu.get("fcs_data_bucket", DEFAULT_DATA_BUCKET),
             menu.get("fcs_data_prefix", DEFAULT_DATA_PREFIX),
             base_dir / "data", include=wanted,
             workers=int(menu.get("fcs_data_workers", 8)))

    # Country borders live outside data/ but nothing runs without them.
    sync(menu.get("fcs_data_bucket", DEFAULT_DATA_BUCKET),
         menu.get("fcs_inputs_prefix", DEFAULT_INPUTS_PREFIX) + "/shapefiles",
         base_dir / "01-inputs" / "shapefiles",
         workers=int(menu.get("fcs_data_workers", 8)))


def _summarise(base_dir: Path):
    """Read the newest FCS run summary JSON. Returns the raw rows, or None."""
    logs = sorted(glob.glob(str(base_dir / "02-process-output" / "logs" / "pipeline_run_summary_*.json")))
    if not logs:
        return None
    try:
        return json.load(open(logs[-1], encoding="utf-8"))
    except Exception:
        return None


# Known failure signatures -> (plain-English cause, expected?).
#
# The raw pipeline output is a wall of pandas tracebacks whose top frame says
# something like "No objects to concatenate" — technically true, useless as a
# diagnosis, and identical for four different root causes. Each entry maps a
# (step, error_type, error_message-fragment) to what actually went wrong.
#
# `expected=True` means "this cannot succeed for this city and that is a
# property of the input data, not a bug" — those are reported as a WARNING and
# summarised; anything else is surfaced loudly as needing attention.
_IIASA = ("city is not in the IIASA Global Cities database, so national SSP "
          "figures cannot be downscaled to it")
FAILURE_CAUSES = [
    # (step-name predicate, error fragment, cause, expected)
    ("population_rescaling", "not enough values to unpack", _IIASA, True),
    ("gdp_rescaling", "not enough values to unpack", _IIASA, True),
    ("demographics", "cannot concatenate object of type", _IIASA, True),
    ("gdp", "No objects to concatenate",
     "no GDP raster overlapped the AOI (follows from the rescaling step above)", True),
    ("country_gdp_ratio", "No objects to concatenate",
     "no GDP raster overlapped the country boundary (follows from gdp)", True),
    ("erosion", "No objects to concatenate",
     "inland city — no shoreline inside the AOI to measure erosion against", True),
    ("cyclones", "No objects to concatenate",
     "no cyclone track intersects the AOI", True),
]


def _explain(step: str, error_type: str, error_message: str):
    """(cause, expected). Falls back to the raw error when we don't recognise it."""
    msg = error_message or ""
    for name, fragment, cause, expected in FAILURE_CAUSES:
        if step == name and fragment.lower() in msg.lower():
            return cause, expected
    return f"{error_type}: {msg}" if msg else "unknown error", False


def _report(rows, city: str, log_dir: Path):
    """Print a readable account of what ran, what didn't, and why.

    Replaces reading 100+ lines of interleaved tracebacks to answer "did this
    work?". Ordering is deliberate: failures needing attention first, then the
    expected ones, then skips, then a one-line success roll-up.
    """
    by_status = {"SUCCESS": [], "SKIPPED": [], "FAILED": []}
    for r in rows:
        by_status.setdefault(r.get("status", "?"), []).append(r)

    ok, skipped, failed = by_status["SUCCESS"], by_status["SKIPPED"], by_status["FAILED"]

    explained = []
    for r in failed:
        cause, expected = _explain(r.get("name", "?"), r.get("error_type") or "",
                                   r.get("error_message") or "")
        explained.append((r.get("name", "?"), cause, expected))
    unexpected = [e for e in explained if not e[2]]
    expected = [e for e in explained if e[2]]

    w = max([len(n) for n, _, _ in explained] +
            [len(r.get("name", "")) for r in skipped] + [12])

    out = [f"\n  FCS — {city}: {len(ok)} succeeded, {len(skipped)} skipped, "
           f"{len(failed)} failed",
           f"  {'─' * 66}"]

    if ok:
        names = ", ".join(r.get("name", "?") for r in ok)
        out.append(f"  OK       {names}")

    if skipped:
        out.append("")
        out.append("  SKIPPED  (input data not present — nothing to compute)")
        for r in skipped:
            # The pipeline's skip message is a bare path; the useful part is
            # which dataset is missing, not where it looked for it.
            m = r.get("message", "") or ""
            m = m.split(":")[0].strip() if ":" in m else m
            out.append(f"    {r.get('name', '?'):<{w}}  {m}")

    if expected:
        out.append("")
        out.append("  FAILED   (expected for this city — data limitation, not a defect)")
        for name, cause, _ in expected:
            out.append(f"    {name:<{w}}  {cause}")

    if unexpected:
        out.append("")
        out.append("  FAILED   ** UNEXPECTED — worth investigating **")
        for name, cause, _ in unexpected:
            out.append(f"    {name:<{w}}  {cause}")

    out.append("")
    out.append(f"  Full tracebacks: {log_dir}")
    print("\n".join(out) + "\n", flush=True)

    return ok, skipped, expected, unexpected


def _export_to_mnt(scan, base_dir: Path, since: float) -> int:
    """Copy the FCS outputs produced by THIS run into the city's mnt output dir,
    tagged with TAG so they sit alongside City Scan outputs and are distinguishable.
    csv -> tabular/, tif/gpkg/shp -> spatial/, images -> images/. Only files touched
    at/after `since` (this city's run) are taken, so multicity stays per-city."""
    src_root = base_dir / "02-process-output"
    tabular = Path(scan.tabular_dir)
    # Rasters go in their OWN subfolder, not flat beside City Scan's.
    # core/R/fns-util.R::fuzzy_read resolves a map layer by str_subset over a
    # NON-recursive listing of spatial/ — so a file whose name merely extends a
    # City Scan layer name gives two matches, and fuzzy_read then warns "Too
    # many" and returns NA, silently killing that map. (UCRA's
    # `<city>_lst_summer_ucra.tif` did exactly this to City Scan's
    # `<city>_lst_summer.tif`.) A subfolder keeps the flat namespace clean;
    # the recursive fallback inside fuzzy_read only runs when the top-level
    # match count is zero, so this stays invisible to City Scan.
    spatial = Path(scan.spatial_dir) / "fcs"
    images = Path(scan.output_dir) / "images"
    for d in (tabular, spatial, images):
        d.mkdir(parents=True, exist_ok=True)
    ext_dest = {".csv": tabular, ".xlsx": tabular,
                ".tif": spatial, ".ovr": spatial, ".gpkg": spatial,
                ".shp": spatial, ".shx": spatial, ".dbf": spatial,
                ".prj": spatial, ".cpg": spatial, ".geojson": spatial}
    count = 0
    for sub in ("tables", "rasters", "maps"):
        d = src_root / sub
        if not d.exists():
            continue
        for f in d.rglob("*"):
            if not f.is_file() or f.stat().st_mtime < since - 1:
                continue
            dest_dir = ext_dest.get(f.suffix.lower(), images)
            dest_dir.mkdir(parents=True, exist_ok=True)
            # tag before the final extension; keep ".tif.ovr" style sidecars grouped
            name = f.name
            if name.endswith(".tif.ovr"):
                newname = name[:-len(".tif.ovr")] + TAG + ".tif.ovr"
            else:
                newname = f.stem + TAG + f.suffix
            try:
                shutil.copy2(f, dest_dir / newname)
                count += 1
            except Exception as e:  # noqa
                logger.warning(f"  FCS export skipped {f.name}: {e}")
    return count


def collect(scan):
    """Run the full FCS pipeline for this city's AOI, logging per-section results."""
    menu = getattr(scan, "menu", {}) or {}
    base_dir = external_dir(menu, "fcs_base_dir", ENV_VAR, DEFAULT_DATA_NAME)
    env = menu.get("fcs_env", DEFAULT_ENV)
    layers = {**DEFAULT_LAYERS, **(menu.get("fcs_layers") or {})}

    # Before anything else: make sure the global inputs are on disk. No-op in
    # the default 'local' mode, so this costs one dict lookup for existing runs.
    # Runs BEFORE the existence check: on a fresh machine with
    # `fcs_data_source: gcs` this call is what creates the tree.
    sync_data(scan, base_dir, layers)

    if not (base_dir / "data").is_dir():
        raise RuntimeError(
            f"FCS data tree not found: {base_dir}\n"
            f"  {describe_external('fcs_base_dir', ENV_VAR, DEFAULT_DATA_NAME)}\n"
            "  It must hold data/ (the global rasters) and 01-inputs/shapefiles/.\n"
            "  To fetch it from GCS, set `fcs_data_source: 'gcs'` in inputs/menu.yml.")

    city = scan.city_inputs.get("city_name", scan.city_name)
    country = (scan.country_name or "").title() or "Pakistan"
    iso3 = (scan.country_iso3 or "PAK").upper()

    shp_dir = base_dir / "01-inputs" / "shapefiles"
    aoi_path = _write_aoi(scan, shp_dir, city)

    cfg = {
        "city_name": city,
        "base_dir": str(base_dir).replace("\\", "/") + ("/" if not str(base_dir).endswith(("/", "\\")) else ""),
        "AOI_path": str(aoi_path).replace("\\", "/"),
        "AOI_path_countries": str(shp_dir / "WB_countries_Admin0_10m.shp").replace("\\", "/"),
        "country_name": country,
        "country_iso3": iso3,
        "flood_source": str(base_dir / "data" / "fathom").replace("\\", "/"),
        "flood": DEFAULT_FLOOD,
        "pipeline_steps": layers,
    }
    cfg_dir = FCS_DIR / "configs_generated"
    cfg_dir.mkdir(exist_ok=True)
    cfg_path = cfg_dir / f"fcs_{scan.city_name}.yaml"
    cfg_path.write_text(yaml.safe_dump(cfg, sort_keys=False), encoding="utf-8")

    enabled = [k for k, v in layers.items() if v]
    logger.info(f"FCS: {city} ({country}/{iso3}) | {len(enabled)}/{len(layers)} layers enabled | env={env}")
    logger.info(f"FCS: base_dir={base_dir}")

    cmd = ["conda", "run", "-n", env, "--no-capture-output", "python",
           str(FCS_DIR / "run_fcs_pipeline.py"), "--config", str(cfg_path)]
    run_start = time.time()
    verbose = bool(menu.get("fcs_verbose", False))
    proc = _run_pipeline(cmd, verbose=verbose)

    # Mirror this city's FCS outputs into mnt/<id>/02-process-output/ (tagged _fsca).
    n_exported = _export_to_mnt(scan, base_dir, run_start)
    logger.info(f"FCS: exported {n_exported} output files to {scan.output_dir} (tagged {TAG})")

    log_dir = base_dir / "02-process-output" / "logs"
    rows = _summarise(base_dir)
    unexpected = []
    if rows is not None:
        ok, skipped, expected, unexpected = _report(rows, city, log_dir)
        # ErrorTracker reads the log stream, so the task's OK/WARNING/ERROR
        # verdict still has to come from a logger call, not just the printout.
        if unexpected:
            logger.error(f"FCS {city}: {len(unexpected)} unexpected failure(s): "
                         f"{', '.join(n for n, _, _ in unexpected)}")
        elif expected or skipped:
            logger.warning(
                f"FCS {city}: {len(ok)} ok, {len(skipped)} skipped, "
                f"{len(expected)} failed — all expected for this city")
        else:
            logger.info(f"FCS {city}: all {len(ok)} layers succeeded")

    if proc.returncode != 0:
        raise RuntimeError(
            f"FCS pipeline crashed for {city} (exit {proc.returncode}). "
            f"See {log_dir} for details."
        )
    logger.info(f"FCS complete for {city}. Outputs in {base_dir/'02-process-output'}")


def _run_pipeline(cmd, verbose=False):
    """Run the FCS pipeline, filtering its console noise unless `verbose`.

    The pipeline prints a full Python traceback for every failed section. Those
    are already written to its own log file, and per-failure diagnosis is done
    from the run-summary JSON in `_report`, so echoing them here buries the
    steps that DID work. Keep the RUN/DONE/FAIL/SKIP progress lines, drop the
    traceback bodies. Set `fcs_verbose: True` in menu.yml to see everything.
    """
    if verbose:
        return subprocess.run(cmd, cwd=str(FCS_DIR))

    proc = subprocess.Popen(cmd, cwd=str(FCS_DIR), stdout=subprocess.PIPE,
                            stderr=subprocess.STDOUT, text=True, bufsize=1,
                            encoding="utf-8", errors="replace")
    in_traceback = False
    for line in proc.stdout:
        stripped = line.rstrip("\n")
        if stripped.startswith("Traceback (most recent call last)"):
            in_traceback = True
            continue
        if in_traceback:
            # Traceback bodies are indented; the final "SomeError: msg" line is
            # not. That last line ends the block — and we drop it too, because
            # _report restates it in plain English.
            if stripped[:1].isspace() or not stripped.strip():
                continue
            in_traceback = False
            continue
        print(stripped, flush=True)
    proc.wait()
    return proc


def analyze(scan):
    """Second pass: render curated FCS maps + plots to 03-render-output/fcs/.
    Reads the city's _fsca outputs; each map/plot is isolated so one failure
    never aborts the rest."""
    from . import render as _render   # lazy import keeps matplotlib out of task discovery
    _render.render(scan)


def run(scan):
    """Convenience single-phase entry (mirrors other run-style tasks)."""
    collect(scan)
    analyze(scan)
