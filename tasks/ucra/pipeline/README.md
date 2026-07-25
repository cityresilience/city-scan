# Urban Climate Risk Assessment (UCRA) Pipeline

> **This is the vendored upstream pipeline.** Inside City Scan you normally run
> it as a task — `scan ucra --multicity` — which generates its config from
> `inputs/menu.yml` into `tasks/ucra/configs_generated/`; the `configs/*.yaml`
> documented below is **not** read on that path. See
> [docs/fcs-ucra-integration.md](../../../docs/fcs-ucra-integration.md) for the
> integration (and why UCRA must run as a country batch, not per city). Use this
> file when driving the pipeline standalone.

A modular, reproducible workflow for generating city-level urban climate risk diagnostics using Python, Google Earth Engine, geospatial analytics, raster processing, and automated R visualizations.

This repository is designed for practitioners, researchers, consultants, analysts, and technical teams who need a structured way to assess climate and environmental risks across cities.

It supports multi-city workflows and can be adapted country by country through a simple configuration file.

## What this repository does

The UCRA Pipeline automates the creation of climate-risk evidence for cities.

It processes multiple datasets and generates indicators such as:

- temperature trends
- extreme heat
- rainfall changes
- drought metrics
- air quality
- landslide susceptibility
- sea level rise exposure
- urban expansion and built-up area growth
- land surface temperature
- publication-ready charts and figures

Instead of manually preparing hundreds of files, this pipeline standardizes the process from raw geospatial inputs to final plot outputs.

## Repository structure

```text
UCRA/
│── run_pipeline.py
│── plots.py
│── requirements.txt
│── README.md
│
├── configs/
│   └── ucra_menu.yaml
│
├── r_scripts/
│   ├── cckp.R
│   ├── landslide.R
│   ├── heat.R
│   ├── drought.R
│   ├── air.R
│   ├── spei.R
│   └── slr.R
│
├── src/
│   └── ucra/
│       ├── config.py
│       ├── context.py
│       ├── ee_utils.py
│       ├── pipeline.py
│       └── modules/
│           ├── bootstrap.py
│           ├── urban_coastal.py
│           ├── cckp.py
│           ├── environment.py
│           ├── wsf_drought.py
│           └── lst_and_stats.py
│
├── shapefiles_received/
└── data/
```

The Python pipeline entry point is `run_pipeline.py`, which reads the YAML config, initializes Earth Engine, and launches the modular pipeline. The plot entry point is `plots.py`, which runs the R plotting scripts and supports either all scripts or a selected subset. `pipeline.py` orchestrates the module order as `bootstrap`, `urban_coastal`, `cckp`, `environment`, `wsf_drought`, and `lst_and_stats`. `config.py` reads the YAML configuration, and `ee_utils.py` handles Earth Engine initialization and authentication behavior. fileciteturn42file1 fileciteturn42file0 fileciteturn42file5 fileciteturn42file2 fileciteturn42file4

## System requirements

Recommended:

- Windows 10 or 11
- 16 GB RAM minimum
- 32 GB RAM preferred for large raster workloads
- SSD storage strongly recommended
- Python 3.11
- R 4.x
- stable internet connection
- Google Earth Engine account

## Installation

### 1. Install Python

Use Python 3.11 if possible.

Check version:

```bash
python --version
```

### 2. Create a virtual environment

Windows:

```bash
python -m venv venv
venv\Scripts\activate
```

### 3. Install Python dependencies

Place the provided `requirements.txt` in the repo root and run:

```bash
pip install --upgrade pip
pip install -r requirements.txt
```

### 4. Install R

Install base R from CRAN and confirm that `Rscript` works:

```bash
Rscript --version
```

### 5. Install required R packages

Open R and run:

```r
install.packages(c(
  "tidyverse",
  "lubridate",
  "scales"
))
```

These are the core R packages used by the plotting scripts you shared. fileciteturn37file4 fileciteturn37file5 fileciteturn37file6 fileciteturn37file7

## Google Earth Engine setup

Some modules use Earth Engine, especially land surface temperature processing.

Authenticate once if needed:

```bash
earthengine authenticate
```

The repository’s Earth Engine helper will attempt initialization first and, if credentials are missing or invalid, will start authentication using the configured auth mode. fileciteturn42file4

## Configuration file

Main config:

```text
configs/ucra_menu.yaml
```

Example:

```yaml
project_dir: /path/to/ucra-data
country: Malaysia

ee_project: your-project-id
ee_auth_mode: notebook
ee_force_auth: false

run_urban_coastal: true
run_cckp: true
run_environment: true
run_wsf_drought: true
run_lst_and_stats: true

run_plots: true
rscript_path: "C:/Program Files/R/R-4.4.1/bin/Rscript.exe"

plot_scripts:
  - cckp.R
  - landslide.R
  - heat.R
  - drought.R
  - air.R
  - spei.R
  - slr.R
```

The plotting wrapper already supports `--scripts` to run a subset of plotting scripts, and it resolves `Rscript` either from a full path or from PATH. fileciteturn42file0

## What each config field means

- `project_dir`: project folder where all outputs are created
- `country`: country name used by the pipeline and country boundary matching
- `ee_project`: Earth Engine or GCP project ID
- `ee_auth_mode`: Earth Engine auth mode, for example `notebook`
- `ee_force_auth`: force a fresh authentication
- `run_urban_coastal`, `run_cckp`, `run_environment`, `run_wsf_drought`, `run_lst_and_stats`: module on or off switches
- `run_plots`: whether plots should run automatically after the Python pipeline
- `rscript_path`: full path to `Rscript.exe` or simply `Rscript` if it is on PATH
- `plot_scripts`: list of R scripts to run

## Input data requirements

### A. AOI shapefiles

Put city AOI shapefiles in:

```text
shapefiles_received/
```

Examples:

```text
Kuala_Lumpur_AOI.shp
Penang_AOI.shp
Johor_Bahru_AOI.shp
```

Each shapefile must include its normal sidecar files:

- `.shp`
- `.dbf`
- `.shx`
- `.prj`

The bootstrap module scans `shapefiles_received`, creates project folders, builds centroids, generates AOI copies, and writes `centroids.csv` and `shapefile/centroids.shp`. It also derives EPSG codes for each city and returns the shared runtime context used by later modules. fileciteturn42file6 fileciteturn42file3

### B. Data folder

Depending on the modules you run, the `data/` folder must contain the required raw datasets. Examples from the code include:

- `data/CCKP`
- `data/SPEI`
- `data/Landslide`
- `data/GDP`
- `data/Heat increase due to urban land expansion`
- `data/Global Annual PM2.5 Grids 1998-2019`
- `data/WSFevolution`
- `data/WSF2019`
- `data/wb_countries_admin0_10m`

These paths are referenced directly in the modules you uploaded. fileciteturn42file7 fileciteturn42file8 fileciteturn42file10 fileciteturn42file11 fileciteturn42file6

## Running the full pipeline

Run:

```bash
python run_pipeline.py --config configs/ucra_menu.yaml
```

This entry point reads the YAML config, initializes Earth Engine, and then launches the modular pipeline. fileciteturn42file1

The current module execution order is:

1. `bootstrap`
2. `urban_coastal`
3. `cckp`
4. `environment`
5. `wsf_drought`
6. `lst_and_stats`

fileciteturn42file5

## Running only plots

You can also run plotting separately:

```bash
python plots.py --config configs/ucra_menu.yaml --rscript "C:\Program Files\R\R-4.4.1\bin\Rscript.exe"
```

The plotting wrapper creates the `plots` folder if needed and runs the configured R scripts against the configured `project_dir`. fileciteturn42file0

## Running selected modules only

One of the practical benefits of `ucra_menu.yaml` is that you can switch modules on and off.

Example: run only LST and then plots later.

```yaml
run_urban_coastal: false
run_cckp: false
run_environment: false
run_wsf_drought: false
run_lst_and_stats: true
```

This is useful when a long multi-step country run has already produced most intermediate files.

## Running selected plot scripts only

Example YAML:

```yaml
run_plots: true
plot_scripts:
  - heat.R
  - slr.R
```

Or manually from the command line:

```bash
python plots.py --config configs/ucra_menu.yaml --rscript "C:\Program Files\R\R-4.4.1\bin\Rscript.exe" --scripts heat.R slr.R
```

## What the modules do

### bootstrap.py

Responsible for project setup:

- scans AOI shapefiles
- creates project folders
- converts geometries to EPSG:4326
- flattens Z-dimension geometries
- writes country and centroid shapefiles
- computes approximate UTM EPSG codes
- returns the shared `PipelineContext`

fileciteturn42file6

### urban_coastal.py

Handles:

- GDP raster clipping
- urban growth and built-up raster clipping and reprojection
- sea level rise tile mosaics
- sea level rise city raster generation

It also buffers the country boundary in projected CRS before clipping built-up rasters, which is important for stable raster masking. fileciteturn42file10

### cckp.py

Processes climate model outputs and writes climate statistics CSVs for:

- temperature
- precipitation
- dry days
- extreme precipitation
- heat indicators
- selected future return-period metrics

Outputs are written under `stats/CCKP`. fileciteturn42file7

### environment.py

Processes:

- SPEI time series and CSV outputs
- PM2.5 clipping and air summary statistics
- urban heat increase rasters
- landslide clipping and landslide averages

This module is the source of `stats/avg_air_1998_2019.csv` and `stats/landslide_avg.csv` when using the updated version. fileciteturn42file8

### wsf_drought.py

Handles:

- WSF tile downloads
- WSF mosaics
- WSF clipping and reprojection
- built-up statistics
- SLR tabulation CSV generation
- drought clipping and drought CSV sampling

It also standardizes city slugs with underscores and writes drought CSVs under `output/drought`. fileciteturn42file11

### lst_and_stats.py

Handles Landsat-based land surface temperature through Earth Engine:

- summer LST export
- winter LST export
- fallback export scales when requests are too large
- final `stats/avg_temp.csv`
- final `stats/avg_temp_extended.csv`

fileciteturn42file9

## Output structure

Typical project output structure:

```text
Malaysia/
├── plots/
├── stats/
│   ├── avg_temp.csv
│   ├── avg_temp_extended.csv
│   ├── avg_air_1998_2019.csv
│   ├── landslide_avg.csv
│   ├── CCKP/
│   ├── spei/
│   └── drought/
├── output/
├── shapefile/
└── city folders/
```

## Typical first run for a new country

1. Create a project folder, for example `D:/UCRA/Indonesia`
2. Put the new AOI shapefiles in `shapefiles_received/`
3. Update `configs/ucra_menu.yaml`
4. Confirm required datasets exist in `data/`
5. Run:

```bash
python run_pipeline.py --config configs/ucra_menu.yaml
```

If `run_plots: true`, the plots will follow automatically.

## Troubleshooting

### Earth Engine authentication fails

Run:

```bash
earthengine authenticate
```

Then retry.

### Rscript not found

Use a full path in YAML:

```yaml
rscript_path: "C:/Program Files/R/R-4.4.1/bin/Rscript.exe"
```

or run `plots.py` with the full `--rscript` path. The plotting wrapper explicitly checks for this and raises a clear error if `Rscript` cannot be found. fileciteturn42file0

### Missing plot CSVs

The R plots depend on specific CSV outputs. If a plot fails, first confirm the expected CSV exists in `stats/` or `output/drought/`.

### Large Earth Engine export errors

The LST module already includes fallback export scales when the requested payload is too large. That is expected behavior for larger cities. fileciteturn42file9

### xarray `FutureWarning` messages in CCKP

These warnings relate to timedelta decoding and are noisy but not fatal. Your CCKP module still writes outputs in the current workflow. fileciteturn42file7

### Shapefile errors

Check that each AOI includes all required shapefile sidecar files and that filenames follow the `*_AOI.shp` pattern expected by the pipeline. The bootstrap module relies on that naming convention. fileciteturn42file6

## Best practices

- use Python 3.11
- keep AOI filenames consistent
- use SSD storage for raster-heavy runs
- test one country at a time
- switch modules off when re-running only a later stage
- keep raw datasets backed up separately
- validate a few representative outputs before distributing results

## Minimal example

```bash
python run_pipeline.py --config configs/ucra_menu.yaml
```

That single command can run the Python analytics pipeline and, if enabled in the YAML, the plotting stage as well.

## Notes

This repository is modular and intended for professional analytical use. It is a strong operational workflow, but outputs should still be reviewed before use in formal decision-making or external reporting.
