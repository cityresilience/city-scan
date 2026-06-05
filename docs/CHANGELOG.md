# Changelog

---
## 2026-06-05

### Added
- `--gcs` / `--download={01,02,03}` flags (`core/config/cli.py`, `tasks/__main__.py`, `core/py/gcs_module.py::download_scan_folder`) — connect a scan stored in GCS to a local working copy. `--gcs` always pulls `01-user-input` local and syncs the full project into `mnt/` once (when missing); `--download` pulls 02/03 (symmetric to `--upload`); `--gcs --render` streams 02 from GCS (`USE_GCS=true`, prints `STREAMING DATA FROM GCS`). Rejects `--parallel`.

### Fixed
- `tasks/fathom/collection.py::_combine_flood_rasters` — combine by band description over the union extent (per-band `rasterio.merge`), so flood types with different RP bands or extents no longer error/clip (issue #13). Adds `Flood Types: combined (...)` + `Generated:` logs.
- `core/py/gcs_module.py` — `01-user-input` now uploaded to GCS via new `upload_inputs()`, called once per run (backfill + before task run, serial/parallel); was only uploading `02`/`03`.

### Changed
- `source/layers.yml` — `combined_flooding` fuzzy_string `combined_flooding_2020.tif$` → `comb_2020.tif$`; maps now read the collection output.

### Removed
- `core/R/pre-mapping.R::combine_flood_types` — legacy R workaround that produced `combined_flooding_2020.tif`; superseded by the collection fix above.

---
## 2026-05-07

### New
- `core/R/fns-util.R::auto_root_here()` — finds the calling script via `sys.frames()$ofile` (or active editor via `rstudioapi` for "Run Cell"), walks up to `.here`, sets cwd + re-roots `here()`. Lets sourcing/running chart scripts from `mnt/<scan-id>/` work without manual setwd.

### Changed
- `core/R/setup.R` — moved `fns.R` source + `auto_root_here()` to top (right after `library(here)`); scan_id derivation/validation now runs before `dir.create` so a failed root doesn't pollute canonical with `01-`/`02-`/`03-` folders. Validation `stop()`s loudly.
- `core/config/inputs.py::prepare_inputs` — AOI copy filtered by `AOI_shp_name` from `city_inputs.yml`; was copying every shapefile in `inputs/AOI/` (issue #5).
- `tasks/wsf/analysis.py::harmonize_wsf` — takes `aoi: gpd.GeoDataFrame` (was glob-reading first `.shp` from spatial_dir); `tasks/wsf/__init__.py` passes `scan.aoi`.
- `tasks/*/charts/index.qmd` — dropped `USE_GCS <<- FALSE` (14 files). `setup.R` already defaults `USE_GCS` to false; the override forced it even when GCS was wanted.
- `.vscode/settings.json` — `excludeGitIgnore` was hiding `mnt/`; replaced with explicit `files.exclude` for the root junk we want hidden.

### Fixed
- `core/R/map-building-footprints.R:23` — `!is.null(roads)` → `inherits(roads, "SpatVector")`. PR #6 patched line 34 only; line 23 (gating the `crop()` that produced the error) was missed. `fuzzy_read` returns `NA` not `NULL`.

### Removed
- `core/R/user-inputs.R` — silent fallback that hardcoded a city when `scan_id` couldn't be derived (ran nouakchott when user wanted a different city). Replaced by loud `stop()` in `setup.R`.
- `core/R/validate-data-files.R` — unreferenced.

---
## 2026-05-04

### Changed
- `core/R/fns.R` — split into 10 topic files (`fns-util`, `fns-text`, `fns-geometry`, `fns-aggregation`, `fns-maps-aes`, `fns-maps-static`, `fns-maps-web`, `fns-charts`, `fns-web` + existing `fns-pop`). `fns.R` is now a manifest; `setup.R` still sources only `fns.R`.
- `core/R/maps-static.R` — render-target resolution → `resolve_render_targets()`, overview plots → `plot_wards_overview()`/`plot_landmarks_overview()`, autozoom → `autozoom_bounds()`.
- `core/R/maps-static-experimental.R` — **EXPERIMENTAL.** Smoothing + hex aggregation paths live here (`apply_smoothing`, `aggregate_hex`, `build_aggregate_lookups`). Standard `maps-static.R` is plain plot path only.
- `tasks/*/maps.yml` — **EXPERIMENTAL.** Per-layer aggregation overrides via mixed-list `layers:` (plain string or `name: {overrides}` dict).
- `core/R/map-flooding.R` — removed smoothing + hex aggregation blocks. Kept built-up hatch overlay, WSF legend ordering, dynamic population overlay grep, band-1 select.
- File renames: 11× `chart-*.R` (per-layer chart builders), `plot-building-footprints.R` → `map-building-footprints.R`, `flood-wsf-probability.R` → `data-flood-wsf-probability.R`. Establishes `map-*` / `chart-*` / `data-*` prefixes; callers updated.
- `scan-calculations/generate-index.R` — dropped `menu.yml` gating; `sections.yml` is now the sole section-inclusion control.
- `docs/reference/workflow-graph.md` — added "How a static map is built" and "How `scan-calculations.html` is built" sections with PNG diagrams (`workflow-maps.png`, `workflow-scan-calculations.png`) + reading-key bullets.

### New
- `add_roads_underlay()` / `add_wards_labels()` in `fns-maps-static.R` — defined, not yet wired. `setup.R` loads `road_network` global from `{city}_major_roads.gpkg`.

### Fixed
- `tasks/elevation/analysis.py` + `core/R/map-elevation.R` — FABDEM water sentinels (0.0) treated as NA both analysis-side and plot-side; was leaking into the lowest bin.
- `tasks/flood_events/collection.R` — disable S2 before `st_make_valid()`; S2 can't fix self-intersecting polygons (was dropping DRC 2014-10-04).
- `core/R/maps-static.R` — `aggregate_if_too_fine()` + multi-band → band 1 added to standard loop. Prevents OOM on dense rasters (Lobito port).
- `aggregate_hex()` — **EXPERIMENTAL.** Hex `value` column renamed to layer's `data_variable` so `plot_static_layer` lookup matches (Lobito port).

### Removed
- `plot_static_layer` — dead `if (plot_roads)` block; `plot_roads` parameter dropped.
- `source/generic-text.bkp.yml` — unused backup.

---
## 2026-04-28

### Fixed
- `core/R/maps-static.R` — task-mode layer filter now gates on `render_tasks` instead of `!is.null(render_layers)`. A task with only `custom:` and no `layers:` (e.g. `buildings`) had `render_layers` collapse to `NULL` (R's `c()`), so the guard fell through and ALL standard layers rendered.

### New
- `docs/reference/maps-customization.md` — full reference for `source/layers.yml` and `tasks/{name}/maps.yml` parameters (binning, scale, hex aggregation, smoothing, custom scripts), including allowed values for `binning_method`, `oob`, `aggregate_mode`, `aggregate_fun`.

---
## 2026-04-24

### Fixed
- `core/py/raster_module.py::mosaic_raster` — `osgeo` isn't in `requirements.txt`, so the GDAL stat check silently ImportError'd on fresh envs. Swapped to `rasterio.open()` (always available).
- `tasks/fathom/collection.py` — flat→folder naming fallback treated silent no-op as success. Now checks the temp mosaic file exists before declaring success.
- `core/R/gcs-overrides.R::file.exists` — absolute paths (tempfiles, `/tmp/...`) were getting `city_dir` prepended and returning FALSE. Broke coastal_erosion collect (tempfile for ShorelineMonitor CSV). Leaves leading-`/` paths alone.
- `tasks/coastal_erosion/collection.R` — AOI buffer 1 km → 10 km so ShorelineMonitor transects a few km offshore get captured.
- `gs://city-scan-global-public/ SectGDP30/` had a leading space, causing 404s in gdp_sectoral. Renamed to `SectGDP30/`.
- `tasks/basic_info/collection.py` + `tasks/worldpop/charts/index.qmd` — moved `benchmark-assembly.R` from chart render to basic_info collect. Benchmark CSVs now exist before any chart reads them.

### Changed
- `requirements.txt` — removed `pyrosm` (broken PyPI build). Install separately via `conda install -c conda-forge pyrosm` for AOIs > 5000 km².
- `core/py/osm_pbf.py` — lazy import of `pyrosm` with a clear ImportError pointing to the conda install.
- `docs/` — reorganized into `getting-started/`, `interface/`, `reference/`, `archived/`. `inputs-config.md` covers all YAML parameters. Workflow graph and repo structure split out of the root README.
- `docs/getting-started/setup.md` — added `conda init zsh` note for VS Code terminals, latest stable R requirement, recommended VS Code extensions.
- `inputs/` — untracked from git, templates synced to `templates/`, `.gitkeep` placeholders in `inputs/` and `mnt/`.
- `README.md` — rewritten around the `scan` CLI.

---
## 2026-04-23

### Fixed
- `core/config/auth.py::init_gee()` — dropped `devstorage.full_control` scope (was forcing a browser re-login mid-scan since gcloud ADC doesn't carry it by default). Kept `earthengine` + `cloud-platform`.
- `core/config/auth.py::init_gee()` — rewritten as non-interactive tiered fallback (existing creds → gcloud ADC → fail with clear fix command). No more hanging mid-run on auth.

### Changed
- `core/config/check_env.py::check_gee()` — on failure, prompts to run `gcloud auth application-default login --scopes=...,earthengine` (the scope gcloud ADC doesn't include by default).

---
## 2026-04-21

### New
- `python -m tasks --check` — environment preflight. Runs all six targets (`r`, `python`, `gee`, `gcs`, `quarto`, `inputs`) by default; scope to a subset with `--check r gee`. Reports per-check ✓/✗, prints fix commands for failures, and prompts interactively to auto-install missing R packages (`here`, `librarian`). Non-interactive fixes (auth, gcloud login) print the command without prompting. Entry point: `core/config/check_env.py::run_checks`.

### Changed
- `core/py/run.py` → `core/config/run.py` (moved). Orchestration (`run_task`, `run_multicity`) now lives alongside the other config/orchestrator modules (`scan.py`, `cli.py`, `tasks.py`). `core/py/` is now exclusively utilities.
- `core/py/multitask.py` → `core/config/multitask.py` (moved). Same reasoning — parallel task runner with TUI is orchestration.
- `core/config/run.py` — R multianalysis subprocess now **streams** output live instead of buffering. Replaced `subprocess.run(..., capture_output=True)` with `subprocess.Popen` + line-by-line read loop; output still captured for the post-run `'Error'` scan. Long R jobs (fathom, gdp_sectoral multianalysis) no longer make the terminal look frozen.
- `core/config/run.py` — the multianalysis `Rscript -e` command now prepends an `install.packages('here')` check so fresh R installs self-heal. `setup.R` can't install `here` because its entry uses `here::here()` — chicken-and-egg. The inline guard breaks the cycle for the one call site that goes through `run_task`.
- `tasks/__main__.py` — when `-k` or `--scan-id` is set, rebind `tasks` imports to the city folder: remove canonical root from `sys.path`, prepend `city_dir`, clear `tasks.*` from `sys.modules`, `importlib.invalidate_caches()`. Before this, city-local `tasks/*/…py` edits were ignored because `run_task`'s `importlib.import_module('tasks.X')` returned the canonical-cached module. With the fix, `-k` and `--scan-id` actually run the city-specific code as intended.
- `tasks/wsf/analysis.py::harmonize_wsf` — `dist_thresh` (backdating cutoff for disputed tracker-2016 pixels) is now auto-computed as the 90th percentile of the actual disputed-pixel-to-nearest-evo distances. Dense cities land at ≈ 5-10 px (same behavior as before); sparse AOIs (e.g. Lobito Corridor) auto-scale to tens/hundreds of pixels so rural dev undercounted by Evolution gets backdated instead of stacking into the 2016 bucket and producing an artificial growth spike at 2015→2016. Logs median + 90th percentile + prior manual default so the picked value is inspectable.
- `core/R/fns.R` — `parse_agg_fun()` helper added; `fun = "q25"` / `"q90"` / any `q{N}` now works as a weighted quantile in `hexbin_aggregate`, `h3_aggregate`, and `cell_aggregate` (built-in exactextractr stats like `mean`/`median`/`min` still work unchanged). Useful for WSF hex maps where median smears early-built pixels later — `q25` surfaces the earliest-quarter build year per hex without being dragged by outliers like `min`.
- `tasks/gdp_sectoral/collection.py` — `BASE` switched back to `/vsicurl/https://storage.googleapis.com/city-scan-global-public/SectGDP30` now that the GCS copy has been refreshed. Local path is retained as a commented fallback.

### Fixed
- `tasks/__main__.py` — serial mode now wraps `run_task()` in try/except. Previously, any task that raised (e.g. `subprocess.CalledProcessError` from a missing R package) propagated up and killed the rest of the run; only `--parallel` mode had per-task exception isolation. Serial mode now matches `core/config/multitask.py:319-333`: the failure is logged, `all_results[name]` gets `{"error": ...}`, and the loop continues to the next task.

---
## 2026-04-17

### New
#### Tasks & Data
- GDP sectoral task (`tasks/gdp_sectoral/`) — agriculture, industry, service, and combined sectoral GDP layers from Chen et al. (2025) SectGDP30 v2 (2020 where present, 2015 fallback for service)
- `gdp_sectoral` section added to `scan-calculations/sections.yml`
- Sectoral GDP entries in `source/layers.yml` (`gdp_agriculture`, `gdp_industry`, `gdp_service`, `gdp_combined`) with per-sector palettes
- `gridded_gdp` task renamed to `gdp_gridded` (matches `gdp_*` naming convention); menu and orchestration docs updated
- `inputs/menu.yml`: `water_risk: True` added (was missing); `gridded_gdp` → `gdp_gridded`; `gdp_sectoral: True` added
- `pyrosm==0.6.2` added to `requirements.txt` (Geofabrik PBF parsing for the new OSM client)

#### Maps
- `core/R/map-sectoral-gdp-flood.R` — sectoral GDP base layers with combined flooding overlay
- `core/R/map-gdp-flood.R` — combined flooding on gridded GDP total and GDP per capita base layers (moved out of the quarto runtime into a dedicated map script)

#### Python Modules
- `core/py/osm_client.py` — unified OSM access layer that routes to Geofabrik PBF for large AOIs and Overpass for typical cities
- `core/py/osm_pbf.py` — Geofabrik PBF download + attribute filter helpers
- `core/py/aoi_buffer.py` — AOI buffer utilities in meters for OSM queries

#### Earthquake source merge
- `tasks/earthquake/collection.R`: collection now merges **USGS FDSN** (comprehensive catalog, M ≥ 1, server-side 500 km radius, since 1900) with **NOAA NCEI** (curated damage metadata) into a single CSV. Dedup rule: same date ±1 day + within 50 km + |mag diff| ≤ 0.8 → NCEI row kept (carries damage). USGS-only rows have NA in NCEI-specific columns (`damageAmountOrder`, `deaths`, `intensity`, `tsunamiEventId`, etc.). New `source` column distinguishes provenance
- `tasks/earthquake/charts/index.qmd`: per-row schema-aware rendering — NCEI rows go through the original significance OR-chain with 4-line damage labels; USGS-only rows pass a magnitude floor (`USGS_MIN_MAG = 4.5`) with simple 2-line labels. `coalesce(...,FALSE)` protects the OR-chain so USGS-only rows aren't silently dropped via NA propagation
- `tasks/earthquake/charts/index.qmd`: y-axis now adaptive — earliest event year as ymax with 5/10/20-yr breaks based on time range (no more empty 1900–1970 dead space)

### Changed
#### Multi-country AOI support (Lobito Corridor driver)
- `core/py/aoi_module.py`: `find_country()` now returns a 3-tuple `(country_iso3, country_name, country_iso3_list)` — sorted by intersection area, so cross-border AOIs are first-class
- `core/config/scan.py`: `scan_init()` accepts `country_name=None` for multi-country AOIs (scan_id becomes e.g. `2026-04-lobito_corridor` with no country segment); `Scan` exposes `country_iso3_list` and `multi_country` flag for downstream tasks
- `core/R/setup.R`: `scan_id` regex relaxed (`^[0-9]{4}-[0-9]{2}-[a-z_-]+$`) so multi-country IDs validate; added `exactextractr` and `h3o` to library shelf
- `tasks/worldpop`, `tasks/demographics`, `tasks/rwi`: collections accept `country_iso3_list` and mosaic per-country WorldPop / RWI files before clipping to AOI. Single-country path unchanged
- `tasks/elevation/__init__.py`: tracks `data_source` on `scan.sources["elevation"]` (FABDEM-GCS / FABDEM-GEE / SRTM-GEE) for the source-tracking report

#### Diacritic-insensitive city matching
- `core/R/benchmark-helper.R`: Oxford lookup matches via `stringi::stri_trans_general(... "Latin-ASCII")`, e.g. "Chișinău" matches "Chisinau" in the Oxford table; canonical Oxford spelling adopted as `city` after match
- `tasks/basic_info/collection.py`: same diacritic-stripping for `in_oxford` flag on the Python side

#### Maps & Layers
- `rwi_relative` title reverted to `'Relative wealth'`, subtitle to `'Standard deviations of estimated household wealth from national mean'`
- `water_risk_overall` subtitle trimmed to `'WRI Aqueduct v4'` (risk class hint removed)
- `core/R/map-schools-health-proximity.R`: `add_builtup_hatch(..., underlay = TRUE)` for school/health point overlays — hatch slides beneath the points instead of obscuring them

#### Tasks
- Buildings collection rerouted through `core/py/osm_client` (PBF for large AOIs, Overpass otherwise) — replaces inline Overpass call in `tasks/buildings/collection.py`
- Accessibility POI collection rerouted through `core/py/osm_client` — same osm_client routing as buildings; removes inline OSMnx setup from `tasks/accessibility/collection.py`
- Worldpop charts: section title "Population" → "WorldPop"; growth plot file renamed `oxford-pop-growth.png` → `worldpop-pop-growth.png`; G1/G2 tables now include `Source` column
- Worldpop `maps.yml`: `aggregate_fun: sum` (correct for population aggregation when hex mode is on)
- `tasks/oxford/charts/index.qmd`: factor levels (`Group`, `Location`, `Indicator`, sector orderings) restored after CSV round-trip — fixes ordering bugs in shares charts when read from disk; added Population Growth (Oxford) chart; fallback `in_oxford` detection from CSV presence in case the flag is stale
- `tasks/fathom/maps.yml`: `depends:` on `worldpop`, `wsf`, `accessibility` — when running `--render maps fathom`, dependency layers are auto-included so flood overlay composites have the base plots they need

#### CLI & Orchestration
- `--upload` extended: with task = new outputs, with `--render` = new renders, alone = backfill all existing files to GCS
- `core/config/sync.py`: logs which folders/tasks were synced ("Synced: core, source, tasks (all)") instead of going silent
- `core/py/multitask.py`: `run_parallel` accepts `auto_exit=True` so `--multicity --parallel --auto-exit` doesn't wait on a final keypress
- `scan-calculations/generate-index.R`: dropped `source(core/R/pre-charting.R)` from the generated index 
- `docs/orchestration.md`: `gridded_gdp` → `gdp_gridded` in the `--render` example

### Fixed
- `tasks/fathom/collection.py`: `composite_flood_raster` rewritten to use windowed/strip processing (512-row strips, reads RP files via `dst_path` arg) — fixes OOM on large AOIs (Lobito Corridor) where holding all RP arrays in memory simultaneously crashed
- `tasks/accessibility/analysis.py`: `make_isochrone` returns an empty `GeoDataFrame` instead of crashing when no edges fall within any distance threshold (common on disconnected-graph AOIs)
- `tasks/forest/analysis.py`: "No forest pixels found" downgraded from `error` to `warning` so the pipeline continues
- `tasks/landcover/collection.py`: GEE `reproject(crs='EPSG:3857', scale=10)` pins server-side grid so categorical class codes stay integer; residual fractional values snapped to nearest valid ESA WorldCover class (`{0,10,…,95,100}`); output written as `uint8`
- `core/R/pre-mapping.R`: `deforestation-edit.tif` written with `INT2U` datatype (year values stay integer, no thousands-comma formatting like "2,020" in legends)
- `core/py/raster_module.py`: `mosaic_raster` now (a) filters input list to existing files via `gdal.VSIStatL` (cloud paths can 404), (b) writes via `merge(..., dst_path=...)` instead of holding mosaic in memory, (c) handles single-file case for `/vsigs/` paths via rasterio read/write (was `os.rename`, which fails on virtual paths)
- `core/py/log_module.py`: file handler opened in `'w'` mode — log overwrites per run instead of appending forever; removed the manual run-separator banner that was double-writing
- `tasks/cyclones/charts/index.qmd`, `flood_events/charts/index.qmd`, `groundwater/charts/index.qmd`: `ggplot2:::print.ggplot()` → `print()` (ggplot2 4.0 removed the internal print method); added `here::i_am()` guards; trailing `cat("\n\n")` so subsequent text isn't rendered next to the chart

---
## 2026-04-08

### Changed
#### GEE Tiling for Large AOIs
- `core/py/gee_fns.py`: added `make_tiles(aoi, tile_size_deg=0.5)` — splits AOI into 0.5° tiles for GEE download
- `core/py/gee_fns.py`: added `tiled_collection(image, aoi, scale)` — downloads via tiles, auto-mosaics, handles single/multi-band
- Updated all GEE tasks to use `tiled_collection`: landcover, forest, nightlight, lst, ndxi, elevation (FABDEM + SRTM)
- Landcover analysis: switched to rasterio windowed reads instead of full raster load

#### Maps
- Custom map scripts now driven by `maps.yml` per task instead of hardcoded list in `maps-static.R`
- Old hardcoded list commented out, auto-discovery scans `tasks/*/maps.yml` for `custom:` entries

#### CLI & Multi-City
- Render confirmation prompt skipped when running from city folder (`python -m tasks` inside `mnt/{city}`)
- `multipolygon:` mode in `multi_inputs.yml` — run `--multicity` from a single vector file (GPKG, SHP, GeoJSON). Each row becomes a city, AOI extracted to `inputs/AOI/`
- `multipolygon` + `cities` combo: extracts all AOIs from the vector file, but only runs cities listed in `cities:`. Errors if a city name isn't in the multipolygon file
- `demographics_year` config in `city_inputs.yml` / `multi_inputs.yml` — override WorldPop year (default: current year, range 2015–2030)
- `--sync` now works with `--render` (previously `--render` skipped sync even with `--sync` flag)
- `city_inputs.yml` always updated on `--multicity` runs to keep config in sync with `multi_inputs.yml`

#### Docs
- Combined `cli.md` + `running-cities.md` into `docs/orchestration.md`
- Added note: `scan` always resolves to repo root (needs `--scan-id`), `python -m tasks` works from city folder without it

### New
- GDP flood exposure analysis (`tasks/gdp_gridded/multianalysis.R`) — overlays flood zones with gridded GDP raster, outputs `flood_gdp.csv`. Combined = sum of individual types (not union)
- GDP flood exposure chart (`tasks/gdp_gridded/charts/index.qmd`) — time series of exposed GDP per flood type (1990–2020)
- GDP + flood overlay maps (`core/R/map-gdp-flood.R`) — renders combined flooding on top of GDP total and GDP per capita base layers
- Census task for Chisinau (`tasks/census/`) — population growth charts from Moldova 1959–2024 census data
- Demographics collection updated to WorldPop R2025A (2015–2030), configurable year via `demographics_year`

### Fixed
- `water_risk/collection.py`: fixed import path `tasks.gee.fns` → `core.py.gee_fns`
- RWI charts: `list.files()[1]` returns NA not NULL — `file.exists(NA)` crashed. Changed to `!is.na()` check
- `gcs-overrides.R`: `file.exists` override crashed on NA filepath (from `list.files()[1]` on missing data). Added early return for NA/NULL
- Fathom multianalysis: R script errors (tryCatch) didn't propagate to Python — status showed OK despite failures. Now captures R output and sets WARNING if "Error" detected
- `setup.R`: `scan_id` regex didn't allow underscores in country name — failed for `democratic_republic_of_the_congo`, fell back to old Nouakchott scan_id from `user-inputs.R`
- `setup.R`: `city_string` now uses underscores instead of hyphens (matches Python `slugify`)
- `pre-mapping.R`: combined flooding filename used `city` (with spaces/capitals) instead of `city_string` — produced `Lobito Corridor_combined_flooding_2020.tif`
- `pre-mapping.R`: all `values()` calls replaced with disk-backed terra operations (`classify(filename=)`, `global()`, `app(filename=)`) — fixes OOM crash on large AOIs like Lobito Corridor (58,440 km²)
- `pre-mapping.R`: `builtup_extent_2025` uses `aggregate_if_too_fine()` before `as.polygons()` to avoid OOM
- `__main__.py`: `scan_id` referenced before assignment in header line

---
## 2026-04-07

### Changed
#### CLI & Orchestration
- `--sync` now accepts targets: `--sync tasks`, `--sync source`, `--sync core`, `--sync scan-calculations`. No target = sync all. `-t` is shortcut for `--sync tasks`
- Removed `-o` and `-c` flags — replaced by `--sync` targets
- Centralized CLI flag parsing in `core/config/cli.py` (single source of truth)
- `sync.py` accepts `sync_targets` list instead of boolean override/copy_tasks_only
- City header in CLI shows scan_id name (e.g. "Namibia Windhoek") instead of generic "City Scan Automation"

#### Benchmark System
- Benchmark cities: merge `bm_cities_manual` + `bm_cities_oxford` (auto-detect) instead of one overriding the other
- New `benchmark_mode` in city_inputs.yml: `sibling` (only sibling scans), `oxford` (only Oxford auto-detect), `auto` (both, default)
- New `benchmark_backup` in city_inputs.yml: `citypopulation` (citypopulation.de + OSM boundary), `worldpop_ucdb` (WorldPop + UCDB), or null
- Group labels in data: city name, "Benchmark - sibling", "Benchmark - Oxford", "Benchmark - backup"
- Oxford collection filters to non-sibling benchmarks only
- Consolidated `benchmark-worldpop.R` into `benchmark-helper.R`
- Added `docs/benchmarks.md` reference doc

#### Maps
- Ward lines: darkened from grey60 to grey40, linewidth 0.35 → 0.5
- Seismic hazard map: broader extent (like burnt area), uses raster extent instead of AOI
- Seismic hazard collection: buffer AOI by 1 degree for broader context
- Built-up area hatch overlay added to landslide, liquefaction, infrastructure maps
- Infrastructure hatch: underlay mode (hatch drawn beneath points, not on top)
- `add_builtup_hatch()` moved from `map-schools-health-proximity.R` to `fns.R`
- Standard plots loop: early check for valid SpatRaster/SpatVector before `vectorize_if_coarse()` — cleaner "No data" messages instead of cryptic cellSize errors

#### Charts
- WSF chart titles: "Built-up area expansion, 1985–2025" / "Built-up area exposed to X flooding"
- Donut plots: removed legend (same as map), added `show_legend` parameter to `ggdonut()`
- Donut plots: removed titles for elevation and slope, landcover keeps legend
- Elevation and slope charts: added data tables
- Solar PV chart: moved table below chart
- Landcover chart: fixed `print("\n")` debug output, added `cat("\n\n")` break
- RWI charts: removed subtitles, confirmed values are already z-scored by Meta (mean=0, sd=1 nationally)
- Removed bold title styling from RWI and fathom charts
- All 16 task charts: standardized `##` headers
- Worldpop: removed subtitles from G1/G2 individual and benchmark charts, removed "comparison (YYYY)" text
- Worldpop: renamed `wpop_df` to `wp_ridge`
- Worldpop: new "Benchmark Cities Population (WorldPop G1 + Oxford)" combined chart
- Worldpop: density scatter skips Oxford cities when many siblings and only 1 Oxford city
- Removed empty "Benchmark Cities" heading and UCDB note from worldpop charts

#### Fathom Charts Reorganization
- Reorganized by flood type: each section has max prob chart → return period chart → WSF stats table → population table → infrastructure table
- Used helper functions (`.flood_max_plot`, `.flood_rp_plot`, `.flood_wsf_table`, `.flood_pop_table`, `.flood_infra_table`)
- Narrative text (roads/infrastructure/population in flood zone) generated from current CSV format, placed after tables
- Section headers with `####` titles
- Harmonized WSF combined chart: uses points for individual types (matches combined max prob chart style)
- Combined flood labels: "River", "Rainwater", "Combined" instead of "fu", "pu", "comb"
- Harmonized WSF chart moved inside combined section (before tables)
- No-data guard: skips chart + text when all exposure is 0

### Fixed
- Fathom multianalysis: WSF harmonized CSV was read without filtering by source, causing 3x duplicate rows. Now reads only "WSF Harmonized" source
- Fathom multianalysis: `full_join` → `inner_join` with flood_wsf — no more NA rows for years without WSF data
- Fathom charts: `tail(df, 1)` picked unsorted NA rows — now filters + sorts by year
- Coastal erosion collection: case-insensitive country name match (was missing all data for Namibia)
- SLR collection: replaced `file.exists()` (doesn't work on `/vsigs/` paths) with `tryCatch` around `rast()`
- Oxford charts: `hues` mapped to "Benchmark - Oxford" group label
- ErrorTracker: added `no_data_count` and `NO_DATA` status

### New
- LST charts task (`tasks/lst/charts/`) — OJS-based chart using `plot_summer_area` from `core/ojs/plots.js`
- Scan-calculations: floating TOC (`toc: true`, `toc-location: right`)
- `core/ojs/plots.js` updated to latest version (from Nouakchott)

---
## 2026-04-02

### New 
#### CLI & Orchestration
- `scan` CLI entry point — install with `pip install -e .` from repo root, then run `scan` instead of `python -m tasks`
- Multi-city batch runner: `scan --all --multicity` reads `inputs/multi_inputs.yml`, auto-detects AOI shapefiles per city from `inputs/AOI/{city_name}/`
- `--render` flag: run maps-static, scan-calculations, or task charts from root (e.g. `scan --render maps --scan-id ...`)
- `--sync` flag: sync project files (core/, tasks/, source/) to city folder without running tasks
- `-k` / `--keep` flag: run tasks using code already in city folder, skip syncing
- Flag behavior: `-e` use existing folder, `-o` override everything, `-t` copy tasks only, `-k` keep as-is

#### Tasks & Data
- Water risk task (`tasks/water_risk/`) — WRI Aqueduct v4 from GEE
- Groundwater task (`tasks/groundwater/`) — G3P collection, auto-detects aquifer basin
- RWI charts task (`tasks/rwi/charts/`) with dual mode: standardized (fixed SD breaks) + city-relative (equal interval histogram)
- Building footprints plot in `maps-static.R`
- Built-up area 2025 hatch overlay on accessibility and flood maps (`ggpattern`)
- Infra + flooding stats tables in fathom charts (split by flood type)
- Task report (`logs/task_report.txt`) — persistent status table with source, messages, last update
- Data source tracking on `scan.sources` (elevation, demographics, groundwater)
- Task validation — typos caught early with suggestions

#### Architecture
Cleaning up scan initialization:
- `source/tasks.yml` — task config (auth, aliases, dependencies) in YAML instead of hardcoded
- `core/config/tasks.py` — reads tasks.yml, provides registry and helpers
- `core/config/utils.py` — shared `slugify()` (was duplicated 4 times)
- `core/config/sync.py` — `sync_project_files()` with t/o/a prompt, extracted from Scan
- `core/config/inputs.py` — `prepare_inputs()` unified from Scan._copy_inputs + multicities
- `core/config/scan.py` — `scan_init()` for folder detection, slim Scan class
- `core/py/error_tracker.py` — extracted from `__main__.py`
- `core/py/run.py` — extracted `run_task()` and `run_multicities()` from `__main__.py`

### Changed
#### Fathom / Flooding
- GCS tile naming: supports both flat (`1in10-FLUVIAL-UNDEFENDED-2020_s24e017.tif`) and folder (`GLOBAL-1ARCSEC-NW_OFFSET-1in10-.../s24e017.tif`) — tries flat first, falls back to folder
- Combined flood map: per-band merge (max across flood types per RP) instead of naive mosaic
- Flood maps: read only band 1 (max_probability) — fixes tidyterra multi-band warning
- Flood labels: changed from probability (0.1-1%, 1-10%, >10%) to return periods (1-in-1,000, 1-in-100, 1-in-10 year)
- Combined flooding line added to harmonized flood + WSF chart
- Fathom charts: reads CSVs directly (run `--multianalysis` separately), no longer sources multianalysis.R

### 
#### Data Sources
- Demographics: upgraded from WorldPop Global_2000_2020 (2020 only) to R2025A (current year, 2015-2030), downloads directly from WorldPop (no GCS dependency)
- WorldPop: parallel downloads (3 workers) for both G1 and demographics
- Elevation fallback chain: GCS FABDEM → GEE FABDEM → GEE SRTM
- Benchmark assembly: sibling scan collects both WorldPop G1 and G2, ensures GCS auth
- Worldpop charts: G1 and G2 benchmark sections filter by Source (no more mixing)

#### Maps & Charts
- RWI city-relative: equal interval bins with explicit numeric values (was quantile with "Least wealthy" labels)
- WSF charts: added titles to Evolution and Tracker plots
- AOI stroke linewidth 0.6, ward linewidth 0.25
- `cat("\n\n")` added after all plot `print()` calls across 16 chart qmds — prevents text rendering beside chart

#### Pipeline
- Multicities: detects country from AOI shapefile (no `country` field needed in multi_inputs.yml)
- Multicities: finds existing city folders instead of always creating new ones
- FABDEM download failure → warning (fallback succeeds)
- Forest "no pixels" → warning
- FWI missing dates → warning (skips and continues)
- Log file overwrites each run (no stale error accumulation)
- Summary table prints after both parallel and sequential runs
- `scan-calculations/index.qmd` deleted — always generated by `generate-index.R`
- RWI added to `scan-calculations/sections.yml`

### Fixed
- ggplot2 4.0: replaced removed `ggplot2:::print.ggplot()` with `print()` across 16 chart qmds + 2 core/R files. `setup.R` auto-updates ggplot2 if < 4.0
- `here::i_am()` added to all chart qmds — fixes `here()` resolving to `charts/` instead of city root in VSCode
- R `$` partial matching: `params$breaks` matched `params$breaks_method`. Renamed to `binning_method`
- Benchmark sibling scan: `base::list.files` (GCS override broke it), `as.character()` for integer year column
- Fathom charts: missing `prob_colors`/`prob_linetypes`, missing `flood_total` variable, `pivot_longer` crash on missing RP column, line gap between Evolution/Tracker periods
- Built-up hatch overlay zoom mismatch on flood + school/health maps: `coord_3857_bounds()` + clip to AOI
- Oxford `collection.R`: guards against empty `oxford_full` tibble
- `tryCatch_named()` prints error message inline
- Auto-exit parallel TUI with `--multicity`
- Missing imports in `core/py/run.py`: `shutil`, `OUTPUTS`
- Infrastructure points: `rbind` crash when OSM returns mixed point/polygon geometries — convert to centroids before combining
- Landcover analysis: `if max < 100: *=10` heuristic broke when raster had real ESA values (10-90) — changed to `max <= 10` + snap to nearest valid class (handles resampling artifacts)
- Fathom single-tile cities: `mosaic_raster()` tried `os.rename()` on `/vsigs/` cloud paths — now reads and writes for virtual paths
- Fathom charts: `flood_road`/`flood_osm`/`flood_pop` crash when no flood data — now reads CSVs with tryCatch, shows "No data available"

---
## 2026-03-24
### New
- Demographics charts task (age-sex distribution, demographic indicators)
- Scan.py prompts before overwriting city source files (c/o/a)

### Fixed
- Oxford Economics case-insensitive city lookup
- Elevation column name mismatch (Elevation_Band → Bin)
- GEE elevation fallback now masks to AOI, not just bbox
- Elevation static map crops to AOI boundary
- Fathom flood analysis uses nested return period bands instead of max probability bins

### Changed
- Setup docs: clone single branch only
- Demographics added to scan-calculations sections
