# Walkthrough Workshop

A three-part walkthrough of the City Scan repo for new users. Part 1 covers environment setup and running a first scan end-to-end. Part 2 covers customizing maps and creating charts. Part 3 covers more technical material and newer features.


---
## Part 1: Foundation & First Scan 
---
### Setup *(expected to be done prior to workshop)*
- Clone the repo 
- Create conda env + activate cityscan 
- Installing City Scan as Python Package via `pip install -e` . for the scan CLI 
- GCS and GEE authentication via `gcloud auth application-default login` 
- Install Quarto 
- Run `scan --check` to verify everything passes 


### Outputs tour 
- Maps & charts 
- Slide deck 
<!-- - Web version  -->
<!-- - Transparencies?  -->

---
### Running first city scan
1. **Configuring inputs** 
    - Drop AOI shapefile into `inputs/AOI/`
    - Edit `inputs/city_inputs.yml` 
    - Edit `inputs/menu.yml` 
    <!-- - Optional wards shapefile () -->

2. **Running scan –all (or with –parallel)** 
    - Watch the flow: sync code → collect → analyze 
    - Inspect mnt/{scan_id}/ folder structure (01-user-input, 02-process-output, 03-output) 
    - Inspect logs
        - ErrorTracker statuses: OK / WARNING / ERROR / NO_DATA 
        - logs/app.log 
        - logs/task_report.txt 

3. **Selective run and --multianalysis** 
    - `scan wsf, scan wsf --collect, scan wsf –analyze (if something failed)  
    - scan --multianalysis fathom 
    <!-- -k / -e / --sync  -->


4. **Rendering outputs: scan --render maps / charts / scan-calculations**
    - core/R/maps-static.R driven by per-task maps.yml 
    - Palettes in source/layers.yml 
    - Custom map scripts (flooding, sectoral GDP) 
    - Task charts: tasks/{name}/charts/index.qmd + _quarto.yml 
    - Scan-calculations report: sections.yml + generate-index.R 
    <!-- - Web version  -->


*During data collection/rendering process, the following can be discussed:*
##### Command Line Interface and Flags
- Two equivalent entry points: `scan` (from repo root) and `python -m tasks` (from repo root or city folder)
- Flag categories:
  - **Step flags**: `--collect`, `--analyze`, `--multianalysis`, `--render`
  - **Scope flags**: `--all`, task names, `--scan-id`, `--multicity`
  - **Sync/code flags**: `--sync`, `-k` (keep city code), `-e` (use existing folder)
  - **Execution flags**: `--parallel`, `--auto-exit`, `--upload`
  - **Diagnostics**: `--check`, `--list`, `--help`


<!-- #### Orchestration flow (what happens on `scan --all`):
  1. CLI parsed in `core/config/cli.py` → flags dict
  2. `core/config/scan.py::scan_init()` resolves scan_id (auto from city_inputs.yml, or supplied via `--scan-id`)
  3. If new city → create `mnt/{scan_id}/`, copy `inputs/` to `01-user-input/`, sync code from root
  4. If existing city → check sync prompt (skip with `-k` / `-e` / `--sync`)
  5. Load `menu.yml` → list of enabled tasks
  6. Load `source/tasks.yml` → task registry (entry points, dependencies, auth needs)
  7. Auth: GEE + GCS initialized once via `core/config/auth.py`
  8. For each task: run `collect` → `analyze` (serial loop with try/except, or parallel via `core/config/multitask.py`)
  9. Each task tracked via `ErrorTracker` → status, messages, source recorded on `scan.sources`
  10. Final: write `logs/task_report.txt` summary, optional render + upload
 -->

---
## Part 2: Customization
---
### Modifying Maps
**Basic understanding of map rendering**
   - `core/R/maps-static.R` — main driver, runs once per scan
   - per task config vs global configs
        - common keys to modify
            - `sources/layers.yml`
                - `title`, `subtitle`, `palette`, `breaks`, `na_color`, `oob`
            - `tasks/{name}/maps.yml`
                - `layers:` — list of yaml_keys this task contributes (must match `layers.yml`)
                <!-- - `aggregate_fun: mean / sum / median / min / max` — how to aggregate raster pixels per cell
                - `aggregate_size` — target cell size in meters
                - `min_coverage` — drop cells with low pixel coverage
                - `smoothing:` (optional) — `gaussian` / `median` / `modal` pre-smoothing -->
   - Custom map scripts
        - Pattern: read base raster, read overlay raster/vector, layer them with `tidyterra::geom_spatraster()` + `geom_sf()`
        - Hooked in via `tasks/{name}/maps.yml` `custom:` entries

**Common overlays and styling**
   - Built-up hatch (`add_builtup_hatch()` in `core/R/fns.R`) — `underlay = TRUE` to slide below points
   - Ward + AOI overlays


---
### Creating Charts

**Quarto basics for those new**
   - YAML frontmatter (`title`, `format`, `execute` options)
   - R chunks: ` ```{r} ... ``` `
   - `here::i_am("tasks/{name}/charts/index.qmd")` — anchors paths so `here::here()` resolves to repo/city root, not the chart folder
   - Output: tables (paged via `print_paged_df()`), ggplots, plotly widgets


**Chart anatomy — pattern to copy**
   - Setup chunk: load libraries, source helpers, read CSVs, restore factor levels (factor levels are lost in CSV round-trip)
   - One section per chart with `##` header
   - `print()` ggplots inside the chunk
   - `cat("\n\n")` after `print()` to prevent text rendering beside the chart


**Adding a new chart to an existing task**
    -Create `tasks/{name}/charts/index.qmd` + `_quarto.yml`
   - Copy `_quarto.yml` from another task as a starting point — they're nearly identical
   - Open the task's `charts/index.qmd`
   - Add a new `##` section
   - Read the CSV you need from `02-process-output/tabular/`
   - Build the ggplot, `print()`, `cat("\n\n")`
   - Rerender: `scan --render charts {task}`
   - Add task to `scan-calculations/sections.yml` so it appears in the combined report
   - Rerender scan-calculations: `scan --render scan-calculations`

**Common gotchas**
   - Factor levels lost in CSV round-trip → restore in setup chunk
   - `here()` resolving to charts folder instead of root → add `here::i_am(...)` at top
   - Bootstrap 5 paged tables look weird → `pagedtable-fix.scss` overrides applied automatically
   - Empty data → guard with `nrow(df) > 0` check, fall back to "No data available" text
   - `ggplot2 >= 4.0` removed `:::print.ggplot()` — use plain `print()`
--- 


### Benchmarks
- `bm_cities_manual` vs `bm_cities_oxford`
- `benchmark_mode`: sibling / oxford / auto
- `benchmark_backup`: citypopulation / worldpop_ucdb

---

## Part 3: Advanced Topics
---

#### Orchestration flow (what happens on `scan --all`):
  1. CLI parsed in `core/config/cli.py` → flags dict
  2. `core/config/scan.py::scan_init()` resolves scan_id (auto from city_inputs.yml, or supplied via `--scan-id`)
  3. If new city → create `mnt/{scan_id}/`, copy `inputs/` to `01-user-input/`, sync code from root
  4. If existing city → check sync prompt (skip with `-k` / `-e` / `--sync`)
  5. Load `menu.yml` → list of enabled tasks
  6. Load `source/tasks.yml` → task registry (entry points, dependencies, auth needs)
  7. Auth: GEE + GCS initialized once via `core/config/auth.py`
  8. For each task: run `collect` → `analyze` (serial loop with try/except, or parallel via `core/config/multitask.py`)
  9. Each task tracked via `ErrorTracker` → status, messages, source recorded on `scan.sources`
  10. Final: write `logs/task_report.txt` summary, optional render + upload

Where to look when something is unclear:
  - "What does this flag do?" → `core/config/cli.py`
  - "What runs when?" → `core/config/run.py::run_task`
  - "How are tasks registered?" → `source/tasks.yml` + `core/config/tasks.py`
  - "What auth does this need?" → `core/config/auth.py`

---

#### Multi-city batch runner
- `inputs/multi_inputs.yml` structure
- `cities:` mode (separate AOI folders)
- `multipolygon:` mode (single vector file, one row per city)
- Combo mode (multipolygon + cities filter)
- `scan --all --multicity`
- `--parallel` + `--auto-exit`

---

#### Multi-country AOI
- How `find_country` returns a country list
- Cross-border scan_ids (no country segment)
- Per-country mosaicking in worldpop / demographics / rwi

---
#### Hex aggregation & map customization
- `aggregate_mode`: none / cell / hexbin / h3
- `aggregate_fun`: mean / sum / median / min / max / q25 / q50 / q90
- `aggregate_size`, `min_coverage`
- Optional `smoothing:` (gaussian / median / modal)
- Picking the right function per task (WSF → q25, population → sum/mean, temporal → modal only)

---

#### GCS uploads
- `--upload` with a task (new outputs)
- `--upload` with `--render` (new renders)
- `--upload` alone (backfill existing files)