# Future City Scan Pipeline

> **This is the vendored upstream pipeline.** Inside City Scan you normally run
> it as a task — `scan fcs --multicity` — which generates its config from
> `inputs/menu.yml`; the `fcs_menue.yaml` documented below is **not** read on
> that path. See [docs/fcs-ucra-integration.md](../../docs/fcs-ucra-integration.md)
> for the integration, and use this file when driving the pipeline standalone.

## Overview

The Future City Scan Pipeline is a Python-based geospatial workflow for producing a city-level future urban risk and development scan from a single area of interest and a standardized set of raster and tabular inputs.

The pipeline orchestrates the following analytical modules:

1. Population rescaling and population dynamics rasters
2. GDP rescaling and GDP rasters
3. Urban land statistics
4. Anthropogenic heat flux
5. Urban heat island indicators
6. Climate Change Knowledge Portal, or CCKP, precipitation and temperature indicators
7. Flood population exposure and flood infrastructure exposure
8. Demographic projection outputs
9. Tropical cyclone wind-speed outputs
10. Erosion tables, points, and transects
11. City-to-country population and GDP ratio tables

The runner script is:

```bash
python run_fcs_pipeline.py --config fcs_menue.yaml
```

A successful run produces step-by-step console logging, detailed file logs, tabular outputs, maps, rasters, and a machine-readable run summary. This command structure and the step names below match the working runner output you have already tested. See the example run logs in your working session. fileciteturn12file0

## Recommended setup

Use **Conda**. This pipeline depends on GDAL, GeoPandas, Rasterio, Fiona, PyProj, and other compiled geospatial libraries. These are much more reliable through Conda than through plain `pip`, especially on Windows.

You may still use `venv` and `pip` if you are comfortable solving binary dependency issues yourself, but the supported and recommended path for this project is Conda.

## Repository contents

A standard pipeline folder should contain:

```text
fcs_pipeline/
├── run_fcs_pipeline.py
├── fcs_menue.yaml
├── environment.yml
├── requirements.txt
└── src/
    ├── __init__.py
    ├── utils.py
    ├── section_1_population.py
    ├── section_1_1_population.py
    ├── section_2_gdp.py
    ├── section_2_1_gdp.py
    ├── section_3_urbanland.py
    ├── section_4_heatflux.py
    ├── section_5_urbanheatisland.py
    ├── section_6_cckp.py
    ├── section_7_extremeheat.py
    ├── section_8_infra_demographic_flood_exposure.py
    ├── section_9_demographics.py
    ├── section_10_cyclones.py
    ├── section_11_erosion.py
    └── section_12_post_processing.py
```

The code expects the broader Future City Scan data folders to exist under your configured `base_dir`. The exact input data live outside the script folder and are referenced through `fcs_menue.yaml`.

## Expected data and directory structure

The YAML points to a project base directory, and the runner derives the standard subfolders from that base.

At minimum, the broader project structure should look like this:

```text
<base_dir>/
├── 01-inputs/
│   └── shapefiles/
│       ├── AOI_<CITY>_Final.shp
│       └── WB_countries_Admin0_10m.shp
├── 02-process-output/
│   ├── logs/
│   ├── maps/
│   ├── rasters/
│   ├── shapefiles/
│   └── tables/
└── data/
    ├── demographic/
    ├── popdynamics/
    ├── gdp/
    ├── urbanland/
    ├── heatflux/
    ├── urbanheatisland/
    ├── Precipitation/
    ├── Temperature/
    ├── tropicalcyclones/
    ├── globalerosion/
    └── fathom/
```

The exact section names under `data/` depend on the datasets packaged for your project. The runner and source modules already encode the expected section names used in your working setup.

## Configuration file

The pipeline uses `fcs_menue.yaml`.

A working example looks like this:

```yaml
city_name: 'Chittagong'
base_dir: '/path/to/FCS/'
AOI_path: '/path/to/FCS/01-inputs/shapefiles/AOI_Chittagong_Final.shp'
AOI_path_countries: '/path/to/FCS/01-inputs/shapefiles/WB_countries_Admin0_10m.shp'
country_name: 'Bangladesh'
country_iso3: 'BGD'

flood_source: '/path/to/FCS/data/fathom'

flood:
  coastal: true
  fluvial: true
  pluvial: true
  threshold: 15
  year:
    - 2020
    - 2030
    - 2050
    - 2080
  ssp:
    - 1
    - 2
    - 3
    - 5
  prob_cutoff:
    - 1
    - 10
  rps:
    - 10
    - 100
    - 1000
    - 20
    - 200
    - 50
    - 500

pipeline_steps:
  population_rescaling: true
  population: true
  gdp_rescaling: true
  gdp: true
  urbanland: true
  heatflux: true
  urbanheatisland: true
  cckp_precipitation: true
  cckp_temperature: true
  flood_population_exposure: true
  flood_infrastructure_exposure: true
  cleanup: true
  demographics: true
  cyclones: true
  erosion: true
  country_population_ratio: true
  country_gdp_ratio: true
```

### Required top-level keys

- `city_name`: city label used across outputs
- `base_dir`: project root
- `AOI_path`: path to the city AOI shapefile
- `AOI_path_countries`: country boundary layer used by some modules
- `country_name`: country label used across outputs
- `country_iso3`: ISO3 code used in demographic and country-level tables
- `flood_source`: root path for Fathom inputs

### Flood block

The `flood:` block controls which flood hazards are included and which years, SSPs, and return periods are used in the flood analyses.

### Step toggles

The `pipeline_steps:` block lets you switch any pipeline step on or off.

Set a step to `false` to skip it in a normal run.

Example:

```yaml
pipeline_steps:
  cckp_precipitation: false
  cckp_temperature: false
  erosion: false
```

If you pass explicit steps on the command line, the command line overrides the YAML toggles.

## Environment setup

### Option 1. Conda on Windows, recommended

From the pipeline folder:

```powershell
conda env create -f environment.yml
conda activate fcs-pipeline
python run_fcs_pipeline.py --config fcs_menue.yaml
```

If you need to rebuild the environment from scratch:

```powershell
conda deactivate
conda env remove -n fcs-pipeline
conda env create -f environment.yml
conda activate fcs-pipeline
python run_fcs_pipeline.py --config fcs_menue.yaml
```

### Option 2. Conda on macOS or Linux, recommended

From the pipeline folder:

```bash
conda env create -f environment.yml
conda activate fcs-pipeline
python run_fcs_pipeline.py --config fcs_menue.yaml
```

### Option 3. `venv` and `pip`, not the recommended route for Windows geospatial stacks

Create and activate an environment:

#### Windows PowerShell

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
python run_fcs_pipeline.py --config fcs_menue.yaml
```

#### macOS or Linux

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
pip install -r requirements.txt
python run_fcs_pipeline.py --config fcs_menue.yaml
```

Important: if GDAL, Fiona, Rasterio, or PyProj fail to install with `pip`, switch to the Conda workflow above. That is expected on some systems.

## Verifying the environment

Before running the full pipeline, you can test the environment with:

```bash
python -c "import geopandas, rasterio, osgeo, xarray, netCDF4, h5netcdf, h5py; print('Environment OK')"
```

If this command fails, fix the missing dependency before running the pipeline.

## Running the pipeline

### Run all steps controlled by the YAML toggles

```bash
python run_fcs_pipeline.py --config fcs_menue.yaml
```

### Run only selected steps

```bash
python run_fcs_pipeline.py --config fcs_menue.yaml --steps population gdp urbanland
```

### List step names

The current runner uses the following step names:

- `population_rescaling`
- `population`
- `gdp_rescaling`
- `gdp`
- `urbanland`
- `heatflux`
- `urbanheatisland`
- `cckp_precipitation`
- `cckp_temperature`
- `flood_population_exposure`
- `flood_infrastructure_exposure`
- `cleanup`
- `demographics`
- `cyclones`
- `erosion`
- `country_population_ratio`
- `country_gdp_ratio`

## What the console output means

A standard run prints concise step status lines:

- `LOG`: location of the detailed run log file
- `RUN`: a step has started
- `DONE`: a step completed successfully
- `SKIP`: a step was intentionally skipped because a required input was missing
- `FAIL`: a step failed but the runner continued

Example:

```text
LOG  pipeline                      D:/.../pipeline_run_20260420_144857.log
RUN  population                   section_1_population.export_popdynamics
DONE population                      3.19s | output=Bangladesh_Chittagong_popdynamics.csv | rows=5 | scenarios=5 | year_columns=17
```

This is the same console style you have already tested successfully. fileciteturn12file0

## Outputs

Outputs are written under `<base_dir>/02-process-output/`.

Key subfolders are:

- `logs/`: detailed log files and per-run CSV and JSON summaries
- `tables/`: main tabular outputs for each module
- `rasters/`: clipped or processed raster outputs
- `maps/`: saved figures and maps
- `shapefiles/`: vector outputs created by some modules

The runner also writes per-run summary files to `logs/`:

- `pipeline_run_summary_<run_id>.json`
- `pipeline_run_summary_<run_id>.csv`

## Troubleshooting

### 1. CCKP steps fail with xarray backend errors

If you see an error saying xarray found `netcdf4` or `h5netcdf` backends but their dependencies are missing, your environment is incomplete.

Fix it with:

```bash
conda install -c conda-forge netcdf4 h5netcdf h5py
```

Then rerun the pipeline. Your earlier console logs showed exactly this issue in an incomplete environment. fileciteturn12file0

### 2. Flood population exposure fails while infrastructure exposure still runs

This usually means stale flood intermediates from a previous run are still present, or the wrong code branch was used.

Recommended fix:

1. delete temporary flood output folders from `02-process-output/`
2. confirm you are using one canonical pipeline package, not a mixed folder copied from earlier branches
3. rerun the full flood sequence

### 3. Shapefile path problems

Check that `AOI_path` and `AOI_path_countries` point to real `.shp` files and that the associated sidecar files such as `.dbf`, `.shx`, and `.prj` are present in the same folder.

### 4. A step is skipped

A skipped step means the runner detected missing inputs and moved on safely. Review the log file and the final summary CSV or JSON to identify the missing dataset.

### 5. Plain `pip` installation fails on Windows

Switch to Conda. This pipeline uses compiled geospatial dependencies and Conda is the reliable installation path.

## Good practice for production use

- Keep one canonical pipeline folder and avoid maintaining multiple loosely named copies such as `adjusted`, `cleaned`, and `final`.
- Store project data outside the code folder and point to it through `fcs_menue.yaml`.
- Keep the YAML under version control alongside the code.
- Use the run summary CSV and JSON as your audit trail.
- When changing code, validate with one known city before applying the same code to others.

## Quick start

If you want the shortest correct setup path:

```bash
conda env create -f environment.yml
conda activate fcs-pipeline
python run_fcs_pipeline.py --config fcs_menue.yaml
```

## Package versions

This README was generated for the canonical Future City Scan package rebuilt from the last known-good configurable branch, rather than from later mixed variants.
