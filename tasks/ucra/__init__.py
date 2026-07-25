"""UCRA (Urban Climate Risk Assessment) as a City Scan task.

    scan ucra [--multicity]        # run batch if needed, export this city's slice
    scan ucra --analyze [--multicity]   # render maps + peer-context plots only

WHY THIS DIFFERS FROM THE `fcs` TASK
------------------------------------
FCS is a per-city pipeline: one run == one city. UCRA is a *country batch* — its
`bootstrap` discovers every shapefile in `<project_dir>/shapefiles_received/` and
each module loops all cities, writing cross-city aggregate tables
(`stats/avg_temp.csv`, `stats/CCKP/*.csv`, `stats/avg_air_1998_2019.csv`, ... each
one row per city) that the 26 national plots consume as peer comparisons.

Running UCRA once per city would therefore yield 1-row "comparison" tables and
single-city comparison charts — silently destroying their meaning. So instead:

  1. the batch is run ONCE (auto-triggered only when this city's UCRA output
     folder is missing; the batch creates every city folder, so in a multicity
     pass the first city triggers it and the rest skip),
  2. each city's own outputs are exported into its mnt tagged `_ucra`,
  3. the cross-city stats tables are exported too, so per-city charts can place
     the city against its peers,
  4. the figures the R scripts drew into `<project_dir>/plots/` are copied into
     the city's render tree (see `_export_r_plots`).

THE ONE EXCEPTION: `cmip6.py` — downscaled NEX-GDDP-CMIP6 projections are
reduced over a single city's extent, so that module genuinely is per-city and
runs inside this task's normal loop. It is slow and opt-in (`ucra_cmip6`).

Config (inputs/menu.yml):
    ucra: False                  # master toggle for `scan --all`
    ucra_project_dir: ''         # blank -> $CITYSCAN_UCRA_DIR -> <repo parent>/ucra-data
    ucra_env: 'ucra'             # conda env with UCRA deps
    ucra_run_batch_if_missing: True
    ucra_cmip6: False            # per-city CMIP6 projections (slow; see cmip6.py)
    ucra_modules: {...}          # which UCRA batch modules to run

The UCRA pipeline itself is VENDORED at `tasks/ucra/pipeline/` — there is no
external checkout to configure. Only its *data* tree lives outside the repo
(too large to commit); see core/config/paths.py::external_dir for how that is
located.
"""
import shutil
import subprocess
import time
from pathlib import Path

import yaml

from core.config.paths import external_dir, describe_external
from core.py.log_module import setup_logger

logger = setup_logger(__name__)

TAG = "_ucra"

UCRA_DIR = Path(__file__).resolve().parent          # tasks/ucra
PIPELINE_DIR = UCRA_DIR / "pipeline"                # vendored UCRA pipeline
RUN_PIPELINE = PIPELINE_DIR / "run_pipeline.py"

# Where the UCRA data/output tree lives, if not set in menu.yml or the env.
DEFAULT_DATA_NAME = "ucra-data"
ENV_VAR = "CITYSCAN_UCRA_DIR"

# Which batch modules to run. Mirrors configs/ucra_menu.yaml in the vendored
# pipeline; override individually from menu.yml via `ucra_modules`.
DEFAULT_MODULES = {
    "run_urban_coastal": False,
    "run_cckp": False,
    "run_environment": False,
    "run_wsf_drought": True,
    "run_lst_and_stats": True,
}

DEFAULTS = {
    "ucra_project_dir": "",
    "ucra_env": "ucra",
    "ucra_run_batch_if_missing": True,
    "ucra_modules": DEFAULT_MODULES,
    "ucra_ee_project": "",
    "ucra_rscript": "Rscript",
    "ucra_run_plots": True,
    # Master switch for the per-city CMIP6 module. Its own knobs
    # (`ucra_cmip6_vars`, `_first_year`, `_workers`, …) default inside cmip6.py,
    # which stays unimported until this is on — it pulls in matplotlib/sklearn.
    "ucra_cmip6": False,
}


def _cfg(scan, key):
    return (getattr(scan, "menu", {}) or {}).get(key, DEFAULTS[key])


def _project_dir(scan) -> Path:
    """The UCRA data/output tree (shapefiles_received/, data/, <City>/, stats/)."""
    return external_dir(getattr(scan, "menu", {}) or {},
                        "ucra_project_dir", ENV_VAR, DEFAULT_DATA_NAME)


def _city_dir(project_dir: Path, scan) -> Path | None:
    """Resolve this city's UCRA output folder.

    bootstrap names folders `stem.replace('_AOI','').title().replace('_',' ')`,
    e.g. 'Ahmadpur East'. Try the display name, that normalisation, then a
    case-insensitive match so odd casing still resolves.
    """
    disp = str(scan.city_inputs.get("city_name", scan.city_name))
    cands = [disp,
             disp.title(),
             disp.replace("_", " ").title(),
             str(scan.city_name).replace("_", " ").title()]
    for c in cands:
        p = project_dir / c
        if p.is_dir():
            return p
    if project_dir.is_dir():
        want = disp.replace("_", " ").strip().lower()
        for d in project_dir.iterdir():
            if d.is_dir() and d.name.strip().lower() == want:
                return d
    return None


def sync_data(scan) -> None:
    """Pull <ucra_project_dir>/data/ from GCS, if configured to.

    No-op unless `ucra_data_source: 'gcs'`. Unlike FCS there is no useful subset
    to select: the batch runs every module over every city, so it wants the whole
    tree (5,555 files / 62 GB, already mirrored at gs://city-scan-global-data/
    ucra-data/). It is skip-if-present, so the cost on a warm machine is one
    bucket listing. See core/py/global_data.py for why this downloads rather
    than streaming via /vsigs/.
    """
    menu = getattr(scan, "menu", {}) or {}
    if str(menu.get("ucra_data_source", "local")).lower() != "gcs":
        return

    from core.py.global_data import sync

    dest = _project_dir(scan) / "data"
    logger.info(f"UCRA: syncing global data into {dest}")
    sync(menu.get("ucra_data_bucket", "city-scan-global-data"),
         menu.get("ucra_data_prefix", "ucra-data"),
         dest, workers=int(menu.get("ucra_data_workers", 8)))


def _write_config(scan, project_dir: Path) -> Path:
    """Generate the batch config from menu.yml.

    The vendored pipeline ships `configs/ucra_menu.yaml`, but that file carries
    whoever-ran-it-last's absolute paths, EE project and Rscript location. The
    config is generated per run instead, so nothing machine-specific is ever
    committed and menu.yml stays the single place to configure this.
    """
    import os

    modules = {**DEFAULT_MODULES, **(_cfg(scan, "ucra_modules") or {})}
    ee_project = (_cfg(scan, "ucra_ee_project")
                  or os.environ.get("GEE_PROJECT", "")).strip()

    cfg = {
        "project_dir": str(project_dir).replace("\\", "/"),
        "country": (scan.country_name or "").title(),
        "ee_project": ee_project,
        "ee_auth_mode": "notebook",
        "ee_force_auth": False,
        "run_plots": bool(_cfg(scan, "ucra_run_plots")),
        "rscript_path": _cfg(scan, "ucra_rscript"),
        "plot_scripts": ["cckp.R", "landslide.R", "heat.R", "drought.R",
                         "air.R", "spei.R", "slr.R"],
        **modules,
    }

    out_dir = UCRA_DIR / "configs_generated"
    out_dir.mkdir(exist_ok=True)
    path = out_dir / f"ucra_{scan.country_iso3 or 'run'}.yaml".lower()
    path.write_text(yaml.safe_dump(cfg, sort_keys=False), encoding="utf-8")
    return path


def _run_batch(scan, project_dir: Path) -> int:
    """Run the UCRA country batch once (all cities). Returns the exit code."""
    env = _cfg(scan, "ucra_env")
    cfg_path = _write_config(scan, project_dir)

    on = [k.replace("run_", "") for k, v in
          {**DEFAULT_MODULES, **(_cfg(scan, "ucra_modules") or {})}.items() if v]
    logger.info("UCRA: no outputs for this city yet — running the UCRA COUNTRY BATCH "
                "(processes every city in shapefiles_received; this is the slow step, "
                "subsequent cities will reuse it).")
    logger.info(f"UCRA: modules: {', '.join(on) or 'none'}")
    logger.info(f"UCRA: project_dir={project_dir}")

    cmd = ["conda", "run", "-n", env, "--no-capture-output", "python",
           str(RUN_PIPELINE), "--config", str(cfg_path)]
    return subprocess.run(cmd, cwd=str(PIPELINE_DIR)).returncode


def _export(scan, city_dir: Path, project_dir: Path) -> tuple[int, int]:
    """Copy this city's UCRA outputs (+ cross-city stats) into the city's mnt,
    tagged so they sit unambiguously beside City Scan and FCS outputs."""
    tabular = Path(scan.tabular_dir)
    # Rasters go in their OWN subfolder, not flat beside City Scan's. See the
    # same note in tasks/fcs/__init__.py: core/R/fns-util.R::fuzzy_read matches
    # a map layer with str_subset over a non-recursive listing of spatial/, so
    # `<city>_lst_summer_ucra.tif` sitting next to `<city>_lst_summer.tif` gave
    # two hits and silently blanked City Scan's summer/winter LST maps.
    spatial = Path(scan.spatial_dir) / "ucra"
    images = Path(scan.output_dir) / "images"
    for d in (tabular, spatial, images):
        d.mkdir(parents=True, exist_ok=True)
    ext_dest = {".csv": tabular, ".xlsx": tabular,
                ".tif": spatial, ".ovr": spatial, ".gpkg": spatial,
                ".shp": spatial, ".shx": spatial, ".dbf": spatial,
                ".prj": spatial, ".cpg": spatial, ".geojson": spatial}

    def _copy(f: Path, prefix: str = "") -> bool:
        dest = ext_dest.get(f.suffix.lower(), images)
        dest.mkdir(parents=True, exist_ok=True)
        name = f.name
        newname = (f"{prefix}{f.stem}{TAG}{f.suffix}"
                   if not name.endswith(".tif.ovr")
                   else f"{prefix}{name[:-len('.tif.ovr')]}{TAG}.tif.ovr")
        try:
            shutil.copy2(f, dest / newname)
            return True
        except Exception as e:  # noqa
            logger.warning(f"  UCRA export skipped {f.name}: {e}")
            return False

    n_city = sum(_copy(f) for f in city_dir.rglob("*") if f.is_file())

    # Cross-city aggregate tables — country-level context for peer comparisons.
    n_stats = 0
    stats_dir = project_dir / "stats"
    if stats_dir.is_dir():
        n_stats = sum(_copy(f, prefix="ucra_stats_")
                      for f in stats_dir.rglob("*") if f.is_file() and f.suffix.lower() == ".csv")

    n_plots = _export_r_plots(scan, project_dir)
    return n_city, n_stats, n_plots


def _export_r_plots(scan, project_dir: Path) -> int:
    """Copy the figures the UCRA R scripts drew into the city's render tree.

    `r_scripts/*.R` ggsave into `<project_dir>/plots/` — one set for the whole
    batch, covering every city (CCKP anomalies, SPEI, AEP, landslide, air).
    They were never picked up before because `_export` only walked the city
    folder and `stats/`. They land in 03-render-output alongside the maps this
    task draws, prefixed `r_` so it's obvious which came from the R pipeline,
    and are picked up automatically by the Quarto section.
    """
    n = 0
    for sub, dest_name in (("plots", "plots"), ("maps", "maps")):
        src = project_dir / sub
        if not src.is_dir():
            continue
        dest = Path(scan.render_dir) / "ucra" / dest_name
        dest.mkdir(parents=True, exist_ok=True)
        for f in sorted(src.rglob("*")):
            if not f.is_file() or f.suffix.lower() not in (".png", ".jpg", ".jpeg", ".pdf", ".svg"):
                continue
            try:
                shutil.copy2(f, dest / f"r_{f.stem}{TAG}{f.suffix}")
                n += 1
            except Exception as e:  # noqa
                logger.warning(f"  UCRA R-plot export skipped {f.name}: {e}")
    return n


def collect(scan):
    """Ensure UCRA outputs exist for this city, then export them into its mnt."""
    project_dir = _project_dir(scan)

    # Only matters if the batch is about to run; harmless (one listing) if not.
    # Do this BEFORE the existence check: on a fresh machine with
    # `ucra_data_source: gcs` the tree is created by this very call.
    sync_data(scan)

    if not project_dir.is_dir():
        raise RuntimeError(
            f"UCRA data tree not found: {project_dir}\n"
            f"  {describe_external('ucra_project_dir', ENV_VAR, DEFAULT_DATA_NAME)}\n"
            "  It must hold shapefiles_received/ (the AOIs) and data/ (the global rasters).\n"
            "  To fetch data/ from GCS, set `ucra_data_source: 'gcs'` in inputs/menu.yml.")

    city_dir = _city_dir(project_dir, scan)
    if city_dir is None:
        if not _cfg(scan, "ucra_run_batch_if_missing"):
            raise RuntimeError(
                f"No UCRA outputs for '{scan.city_inputs.get('city_name', scan.city_name)}' under {project_dir}, "
                "and ucra_run_batch_if_missing is False. Run the UCRA batch manually first.")
        rc = _run_batch(scan, project_dir)
        city_dir = _city_dir(project_dir, scan)
        if rc != 0 and city_dir is None:
            raise RuntimeError(f"UCRA batch failed (exit {rc}) and produced no folder for this city.")
        if city_dir is None:
            raise RuntimeError(
                f"UCRA batch finished but no output folder matched this city under {project_dir}. "
                "Check that its AOI is staged in shapefiles_received/ (UCRA names folders Title Case).")
    else:
        logger.info(f"UCRA: reusing existing batch outputs at {city_dir}")

    n_city, n_stats, n_plots = _export(scan, city_dir, project_dir)
    logger.info(f"UCRA: exported {n_city} city files + {n_stats} cross-city stats tables "
                f"+ {n_plots} R figures to {scan.output_dir} (tagged {TAG})")
    if n_city == 0:
        logger.warning("  UCRA: city folder held no files — check the batch actually produced outputs.")

    # CMIP6 is the one genuinely per-city UCRA module (see cmip6.py). It is slow
    # and network-bound, so it is opt-in and its failure must not lose the batch
    # export that just succeeded.
    if _cfg(scan, "ucra_cmip6"):
        from . import cmip6 as _cmip6
        try:
            _cmip6.collect(scan)
        except Exception as e:  # noqa
            logger.error(f"UCRA CMIP6 collection failed: {type(e).__name__}: {e}")
            raise
    else:
        logger.info("UCRA: CMIP6 disabled (set `ucra_cmip6: True` in menu.yml to enable)")


def analyze(scan):
    """Render per-city UCRA maps + peer-context plots to 03-render-output/ucra/."""
    from . import render as _render   # lazy: keep matplotlib out of task discovery
    _render.render(scan)

    if _cfg(scan, "ucra_cmip6"):
        from . import cmip6 as _cmip6
        try:
            _cmip6.render(scan)
        except Exception as e:  # noqa
            logger.warning(f"UCRA CMIP6 render failed: {type(e).__name__}: {e}")


def run(scan):
    collect(scan)
    analyze(scan)
