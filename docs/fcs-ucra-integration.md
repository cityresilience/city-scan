# FCS and UCRA inside City Scan

Two sibling pipelines are integrated as ordinary City Scan tasks. Both are
**vendored** — the code is in this repo, so a fresh clone has everything it
needs except the bulk input data.

| | `fcs` | `ucra` |
|---|---|---|
| What | Future City Scan — SSP projections | Urban Climate Risk Assessment |
| Code | `tasks/fcs/` | `tasks/ucra/pipeline/` |
| Adapter | `tasks/fcs/__init__.py` | `tasks/ucra/__init__.py` |
| Conda env | `fcs-pipeline` | `ucra` |
| Shape | **per city** — one run, one city | **country batch** — one run, all cities |
| Data root | `$CITYSCAN_FCS_DIR` | `$CITYSCAN_UCRA_DIR` |
| Bucket prefix | `gs://city-scan-global-data/fcs-data/` | `.../ucra-data/` |
| Output tag | `_fsca` | `_ucra` (+ `_ucra_cmip6`) |
| Render dir | `03-render-output/fcs/` | `03-render-output/ucra/` |
| Map style | City Scan's own (see below) | Burundi report |

Both run like any other task:

```bash
scan fcs --multicity -e
```

```bash
scan ucra --multicity -e
```

and both are off by default in `inputs/menu.yml` (`fcs: False`, `ucra: False`),
so `scan --all` does not pull them in until you ask for them.

---

## Why UCRA is a batch and FCS is not

This is the single most important thing to understand before changing either.

FCS is genuinely per-city: one config, one AOI, one set of outputs. The adapter
writes a config per city and runs the pipeline once per city.

UCRA is not. Its `bootstrap` discovers **every** shapefile in
`<data root>/shapefiles_received/` and each module loops all of them, writing
cross-city tables (`stats/avg_temp.csv`, `stats/CCKP/*.csv`, …) with **one row
per city**. Its 26 plots consume those tables as peer comparisons. Running UCRA
once per city would produce one-row "comparison" tables and single-point
comparison charts — silently destroying their meaning.

So the `ucra` adapter:

1. runs the batch **once**, triggered only when this city's output folder is
   missing (the batch creates every city's folder, so in a multicity pass the
   first city triggers it and the rest reuse it);
2. exports this city's slice **plus** the cross-city stats tables, so per-city
   charts can still place the city against its peers;
3. copies the figures UCRA's R scripts drew into the city's render tree.

**The one exception** is `tasks/ucra/cmip6.py`. Downscaled NEX-GDDP-CMIP6
projections are reduced over a single AOI's extent, so that module really is
per-city and runs inside the normal loop. It is slow (~1,450 GEE calls per city
at the default 1980–2100 window) and therefore opt-in via `ucra_cmip6: True`.

---

## Configuration

Everything lives in `inputs/menu.yml`. Neither pipeline's own config file is
read during a `scan` run — the adapters **generate** one per run into
`tasks/*/configs_generated/` (gitignored) from the menu values. That is
deliberate: the pipelines' shipped configs carry absolute paths, an Earth Engine
project and an Rscript location, none of which should ever be committed.

`tasks/fcs/fcs_menue.yaml` and `tasks/ucra/pipeline/configs/ucra_menu.yaml`
remain only as examples for driving the vendored pipelines standalone.

### Data roots

The code is vendored; the data is not (60–160 GB). Each root resolves:

1. `fcs_base_dir` / `ucra_project_dir` in `menu.yml`
2. `$CITYSCAN_FCS_DIR` / `$CITYSCAN_UCRA_DIR`
3. `<repo parent>/FCS` and `<repo parent>/ucra-data`

Blank in the committed `menu.yml`, so no machine paths ship. A missing tree
fails with a message naming all three options.

Expected layout:

```
<CITYSCAN_FCS_DIR>/           <CITYSCAN_UCRA_DIR>/
  data/                         data/
  01-inputs/shapefiles/         shapefiles_received/
  02-process-output/            <City>/            (created by the batch)
                                stats/  plots/     (created by the batch)
```

### Pulling data from GCS

Neither pipeline can stream from `/vsigs/` the way City Scan's R code does —
that works only because `core/R/gcs-overrides.R` monkeypatches City Scan's *own*
readers. These are separate codebases launched through `conda run`, doing plain
`os.path.exists` and `rasterio.open` on absolute local paths. So the data is
**downloaded before the run** (`core/py/global_data.py`), which is what City
Scan already does for scan folders in `gcs_module.download_scan_folder()`.

```yaml
fcs_data_source: 'gcs'     # or leave 'local'
ucra_data_source: 'gcs'
```

or per-run, without touching config:

```bash
scan fcs --multicity --sync-data
```

Downloads are skip-if-present (compared by relative path + size) and land as
`<name>.part` until complete, so interrupting is safe. FCS pulls **only the
folders its enabled `fcs_layers` need** (`LAYER_DATA` in `tasks/fcs/__init__.py`);
UCRA takes the whole tree, because the batch runs every module over every city.

---

## Map styling

FCS and UCRA maps are drawn in Python but deliberately follow **different**
house styles, because they serve different documents:

- **`tasks/fcs/style.py`** reproduces City Scan's own R cartography
  (`core/R/fns-maps-static.R`) so FCS and City Scan maps are indistinguishable
  side by side: `cartolight` basemap, unclipped raster, solid grey AOI, legend
  panel on the right at the 7:2 `map_portions` split, ticks scale bar, minimal
  north arrow. The constants are read from the R source, not eyeballed.
- **`tasks/ucra/style.py`** follows the CRP *Urban Climate Risk Analysis —
  Burundi* report: clipped raster, dashed AOI, colourbar underneath.

Shared plumbing — reprojection, basemap, scale bar, north arrow, percentile
stretch — is in `core/py/map_base.py`. Only the styling differs.

Two raster quirks are handled there and are easy to reintroduce by accident:

- `keep_zero=True` — the urban-heat-island grids declare `nodata=0`, but zero is
  a real measurement ("no projected increase"). Masking it blanks the layer.
- `mask_values=(0,)` — WSF evolution stores `0` for "never built up". Left in,
  the colour ramp runs 0–2015 instead of 1985–2015 and flattens the map.

---

## Reading the FCS failure report

For the Pakistan MCs, FCS reports **9 succeeded, 2 skipped, 6 failed** and that
is the correct result, not breakage. The adapter prints a plain-English summary
instead of the raw tracebacks:

```
  FCS — Rajanpur: 9 succeeded, 2 skipped, 6 failed
  OK       population, urbanland, heatflux, urbanheatisland, ...
  SKIPPED  (input data not present)
    flood_population_exposure      Missing Fathom flood input folder
  FAILED   (expected for this city — data limitation, not a defect)
    population_rescaling   city is not in the IIASA Global Cities database, ...
    erosion                inland city — no shoreline inside the AOI ...
```

Failures whose signature isn't recognised appear under
`** UNEXPECTED — worth investigating **` and are logged at ERROR, so a real
regression can't hide among the routine ones. Raw tracebacks stay in
`<fcs data root>/02-process-output/logs/`; `fcs_verbose: True` echoes them.

The six expected failures all trace to two facts: these 13 municipal committees
are **absent from the IIASA Global Cities database** (`GC_PAK.csv` holds only 9
major cities), so nothing can be downscaled to them; and they are **inland**, so
erosion has no shoreline to measure.

---

## Report integration

Both tasks contribute a section to the Quarto report via
`scan-calculations/sections.yml` → `tasks/<name>/charts/index.qmd`. The UCRA
section renders three galleries (Maps / Peer comparisons + R indices / CMIP6)
and shows any figure it finds, captioning unknown ones by file stem — so new
output appears without editing the `.qmd`.

```bash
scan --render scan-calculations --multicity
```

---

## Environments

Three conda environments, kept separate because their dependency sets conflict:

| Env | Used by | Spec |
|---|---|---|
| `cityscan` | City Scan + both adapters + all rendering | `requirements.txt` |
| `fcs-pipeline` | the vendored FCS pipeline | `tasks/fcs/environment.yml` |
| `ucra` | the vendored UCRA pipeline | `tasks/ucra/pipeline/requirements.txt` |

The adapters call the other two through `conda run -n <env>`, so only `cityscan`
needs to be active. Change the names with `fcs_env` / `ucra_env` in `menu.yml`.

`xgboost` is optional — the CMIP6 bias correction skips that one comparison and
logs a line if it is absent.
