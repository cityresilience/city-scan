# Tasks

## Overview

Each scan topic (elevation, flooding, population, etc.) is a self-contained module under `tasks/`. A task typically has:

```
tasks/elevation/
├── __init__.py
├── collection.py
├── analysis.py
├── visualization.py    (optional)
├── analysis.R           (optional, for R-based processing)
└── charts/
    └── index.qmd        (optional, for scan-calculations report)
```

## __init__.py

The only required file. Defines up to four entry point functions:

```python
def collect(scan):    # Download and clip data
def analyze(scan):    # Compute statistics, generate CSVs
def visualize(scan):  # Generate plots/maps (optional)
def run(scan):        # Shorthand — usually calls collect() + analyze()
```

Each function receives a `scan` object (`core.config.scan.Scan`) with:

- `scan.aoi` — GeoDataFrame of the AOI boundary
- `scan.city_name` — lowercase city name (e.g. `"chisinau"`)
- `scan.country_name` — country name (e.g. `"Moldova"`)
- `scan.country_iso3` — ISO3 code (e.g. `"mda"`)
- `scan.output_dir` — path to `02-process-output/`
- `scan.render_dir` — path to `03-render-output/`
- `scan.menu` — dict from `menu.yml`
- `scan.city_inputs` — dict from `city_inputs.yml`
- `scan.scan_id` — e.g. `"2026-03-moldova-chisinau"`
- `scan.flood_year`, `scan.flood_ssp` — flood-specific parameters

## collection.py

Downloads data from external sources (GCS, WorldPop, Overpass API, etc.) and clips to AOI. Saves output to `{output_dir}/spatial/` (rasters, vectors) or `{output_dir}/tabular/` (CSVs).

Naming convention for outputs:
- `{city_name}_elevation.tif`
- `{city_name}_population.tif`
- `{city_name}_flood_wsf.csv`

## analysis.py

Reads spatial/tabular data produced by collection, computes statistics, and writes CSVs. Does not download anything.

## visualization.py (optional)

Python-based plots using matplotlib. Used by some tasks for histograms and basic raster maps. Not all tasks have this — many rely on `charts/index.qmd` instead.

## charts/index.qmd (optional)

Quarto document that generates R-based charts for the scan-calculations report. These are assembled by `scan-calculations-compiler/` into the final HTML report.

Each qmd follows this pattern:

```qmd
---
df-print: paged
execute:
  echo: false
  warning: false
  message: false
---

{r setup}
if (!exists("aoi")) source(here::here("core/R/setup.R"))

{r data-loading}
# Read CSVs from tabular_dir

{r chart-name}
#| results: asis
# ggplot code, use ggplot2:::print.ggplot() to render in asis chunks
# use print_paged_df() for tables
# use print_text() for narrative text
```

## R scripts (optional)

Some tasks have `.R` files for processing that's better suited to R:
- `analysis.R` — e.g. `worldpop/analysis.R` for population benchmarking
- `multianalysis.R` — e.g. `fathom/multianalysis.R` for flood exposure calculations
- `collection.R` — e.g. `earthquake/collection.R` for R-based data download

These are called from `__init__.py` via subprocess:
```python
subprocess.run(
    ["Rscript", "-e", "source(here::here('tasks/earthquake/collection.R'))"],
    check=True
)
```

## GEE tasks

GEE-based tasks live under `tasks/gee/` and share utilities in `tasks/gee/fns.py`:

```
tasks/gee/
├── fns.py          # Shared: aoi_to_ee_geometry(), Composite class, xee_to_rio()
├── forest/
├── landcover/
├── lst/
├── ndxi/
└── nightlight/
```

Each GEE task's collection uses `xr.open_dataset()` with the `ee` engine (via xee) to download Earth Engine imagery, then `fns.xee_to_rio()` to convert to GeoTIFF.

## menu.yml

Controls which tasks run with `--all`. Keys must match task folder names or be defined in ALIASES/MENU_KEYS in `__main__.py`.

```yaml
elevation: True
flood_fluvial: True
flood_pluvial: True
forest: True
population: True        # alias for worldpop
green: True             # alias for ndxi (NDVI)
ndmi: True              # alias for ndxi (NDMI)
buildings: False        # disabled by default
```

Multi-key tasks:
- `fathom` is enabled if any of `flood_fluvial`, `flood_pluvial`, `flood_coastal`, `flood_comb` is True
- `lst` is enabled if either `lst_summer` or `lst_winter` is True

## CLI

```bash
python -m tasks elevation --collect        # collect only
python -m tasks elevation --analyze        # analyze only
python -m tasks elevation                  # collect + analyze (run)
python -m tasks --all                      # all enabled tasks
python -m tasks --all --parallel           # parallel with TUI
python -m tasks --list                     # show available tasks
python -m tasks --all --scan-id 2026-03-tunisia-tunis  # existing city
```

## Adding a new task

1. Create `tasks/{name}/`
2. Add `__init__.py` with at least `collect(scan)` and `run(scan)`
3. Add `collection.py` with your data download logic
4. Add the task name to `inputs/menu.yml`
5. Optionally add `analysis.py`, `charts/index.qmd`, entry in `source/layers.yml`

The task is auto-discovered — no registry edits needed.
