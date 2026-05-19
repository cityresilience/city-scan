# Repository Structure

```
city-scan-automation/
├── tasks/
├── core/
├── source/
├── inputs/
├── mnt/
├── scan-calculations/
├── templates/
├── docs/
└── logs/
```

---

## tasks/

```
tasks/
├── elevation/
│   ├── __init__.py
│   ├── collection.py
│   ├── analysis.py
│   ├── maps.yml
│   └── charts/
│       ├── _quarto.yml
│       └── index.qmd
├── fathom/
│   ├── __init__.py
│   ├── collection.py
│   ├── analysis.py
│   ├── multianalysis.R
│   ├── maps.yml
│   └── charts/
│       ├── _quarto.yml
│       └── index.qmd
├── worldpop/
├── wsf/
├── earthquake/        # R-based collection
├── oxford/            # R-based collection
└── ...
```

- Each scan topic is a self-contained module
- `__init__.py` registers entry points: `collect()`, `analyze()`, `visualize()`
- `collection.py` (or `.R`) downloads and clips data to AOI
- `analysis.py` (or `.R`) computes statistics and generates CSVs
- `maps.yml` declares the layers this task contributes (matched against `source/layers.yml`) and any custom map scripts
- `charts/index.qmd` renders Quarto charts for the scan-calculations report
- Some tasks have `multianalysis.R` for cross-task R-based post-processing (e.g. fathom flood exposure)
- Tasks are auto-registered via `source/tasks.yml`
- CLI entry point: `tasks/__main__.py` (parses flags, dispatches to `core/config/run.py`)

---

## core/

### core/config/

```
core/config/
├── scan.py
├── auth.py
├── paths.py
├── tasks.py
├── cli.py
├── run.py
├── multitask.py
├── inputs.py
├── sync.py
├── check_env.py
└── utils.py
```

- `scan.py` — Scan class: loads AOI, city config, creates city output folders in `mnt/`
- `auth.py` — initializes GEE and GCS authentication (tiered: existing creds → gcloud ADC → fail-fast)
- `paths.py` — auto-detects input/output directories based on project structure
- `tasks.py` — task registry (reads `source/tasks.yml`)
- `cli.py` — CLI flag parsing (single source of truth for all flags)
- `run.py` — `run_task()`, `run_multicity()` execution logic
- `multitask.py` — parallel task runner with TUI for `--parallel` flag
- `inputs.py` — `prepare_inputs()` for staging user inputs into city folders
- `sync.py` — `sync_project_files()` for `--sync` flag
- `check_env.py` — environment preflight for `--check` flag
- `utils.py` — shared `slugify()` and other helpers

### core/py/

```
core/py/
├── log_module.py
├── error_tracker.py
├── gcs_module.py
├── aoi_module.py
├── osm_client.py
├── osm_pbf.py
├── aoi_buffer.py
├── gee_fns.py
├── raster_module.py
└── gdal_auth.py
```

- `log_module.py` — logging setup (console + rotating file output)
- `error_tracker.py` — counts errors per task, surfaces OK / WARNING / ERROR / NO_DATA status
- `gcs_module.py` — GCS upload/download, file tracking for `--upload` flag
- `aoi_module.py` — detects country name(s) and ISO3 codes from AOI intersection (multi-country aware)
- `osm_client.py` — unified OSM access (routes to Geofabrik PBF for large AOIs, Overpass otherwise)
- `osm_pbf.py` — Geofabrik PBF download + attribute filter helpers
- `aoi_buffer.py` — AOI buffer utilities in meters for OSM queries
- `gee_fns.py` — GEE tiling helpers (`make_tiles`, `tiled_collection`)
- `raster_module.py` — raster mosaic, masking, GCS-safe operations
- `gdal_auth.py` — configures GDAL for `/vsigs/` access to private GCS buckets

### core/R/

```
core/R/
├── setup.R
├── fns.R
├── pre-mapping.R
├── maps-static.R
├── map-flooding.R
├── map-elevation.R
├── map-sectoral-gdp-flood.R
├── map-schools-health-proximity.R
├── benchmark-helper.R
├── pop-backup.R
├── global-data-paths.R
└── ...
```

- `setup.R` — R session setup: loads packages, reads AOI, sets directory paths
- `fns.R` — `plot_static_layer()`, `prepare_parameters()`, `parse_agg_fun()`, `cell_aggregate()`, `hexbin_aggregate()`, `h3_aggregate()`, and other shared helpers
- `pre-mapping.R` — data preprocessing before mapping (combine flood zones, edit WSF tracker, adjust deforestation years)
- `maps-static.R` — orchestrates static map generation: standard layers loop + custom map scripts
- `map-*.R` — custom map scripts for layers that need special handling (flood overlays, sectoral GDP, schools/health proximity, etc.)
- `benchmark-helper.R` — benchmark city selection and Oxford lookup (diacritic-insensitive)
- `pop-backup.R` — population fallback functions (UN data, citypopulation.de, GHS-POP)

### core/ojs/

```
core/ojs/
└── plots.js
```

- Observable JS interactive charts (D3-based) used in the web report

---

## source/

```
source/
├── layers.yml
├── tasks.yml
├── generic-text.yml
├── custom.scss
└── pagedtable-fix.scss
```

- Canonical config files, copied to each city folder on first run
- `layers.yml` — map layer styling (palettes, breaks, labels, fuzzy_string per layer)
- `tasks.yml` — task config (auth requirements, aliases, dependencies)
- `generic-text.yml` — report text templates per section
- `custom.scss` — report CSS styling
- `pagedtable-fix.scss` — Bootstrap table styling overrides

---

## inputs/

```
inputs/
├── city_inputs.yml
├── multi_inputs.yml
├── menu.yml
└── AOI/
```

- User-facing configuration for new scans (not tracked in git — see `templates/` for starting copies)
- `city_inputs.yml` — single-city config: name, AOI, year ranges, flood/accessibility/benchmark params
- `multi_inputs.yml` — multi-city batch config: city list (or multipolygon file) + shared settings
- `menu.yml` — toggle which tasks to enable or disable
- `AOI/` — boundary shapefile(s) for the city or cities

---

## mnt/

```
mnt/
└── 2026-03-tunisia-tunis/
    ├── 01-user-input/
    ├── 02-process-output/
    │   ├── spatial/
    │   └── tabular/
    ├── 03-render-output/
    │   ├── maps/
    │   └── plots/
    ├── tasks/
    ├── core/
    ├── source/
    └── scan-calculations/
```

- City output folders, auto-created per scan by the `Scan` class
- Each city gets its own copy of `tasks/`, `core/`, `source/`, `scan-calculations/`
- `01-user-input/` — copied from `inputs/`
- `02-process-output/spatial/` — rasters and vector data (.tif, .gpkg, .fgb)
- `02-process-output/tabular/` — CSVs and statistics
- `03-render-output/maps/` — static map PNGs
- `03-render-output/plots/` — chart PNGs

---

## scan-calculations/

```
scan-calculations/
├── _quarto.yml
├── sections.yml
├── generate-index.R
└── ...
```

- Quarto project that compiles per-task `charts/index.qmd` into a single combined HTML report
- `sections.yml` defines which tasks appear and in what order
- `generate-index.R` reads `sections.yml` and assembles the per-task qmds into `index.qmd`

---

## templates/

```
templates/
├── city_inputs.yml
├── multi_inputs.yml
├── menu.yml
├── manual-text.md
└── README.md
```

- Boilerplate input configs and starter files
- Copy `city_inputs.yml`, `multi_inputs.yml`, `menu.yml` to `inputs/` and edit before running

---

## docs/

```
docs/
├── README.md
├── CHANGELOG.md
├── getting-started/
├── interface/
├── reference/
└── archived/
```

See [docs/README.md](../README.md) for the full index.

---

## logs/

```
logs/
├── app.log
└── task_report.txt
```

- Auto-created on first task run
- `app.log` — full run log (overwrites per run)
- `task_report.txt` — per-task status summary (status, source, messages, last update)
