# Runbook — City Scan + FCS from scratch (Pakistan 13 MCs)

Every command assumes PowerShell. Run them in order. Snags/skips you should
*expect* are flagged at each stage — most "failures" in this pipeline are
benign and by design.

---

## 0. One-time prerequisites

```powershell
# Long runs: stop the machine sleeping mid-batch
powercfg /change standby-timeout-ac 0
```

Required, must already exist:

| Thing | Where / value | Used by |
|---|---|---|
| conda env `cityscan` | has the `scan` CLI (editable install) | City Scan + the `fcs` task wrapper |
| conda env `fcs-pipeline` | FCS geospatial deps | FCS pipeline (invoked via `conda run`) |
| R 4.4.1 | `C:\Program Files\R\R-4.4.1\bin` — **not on PATH by default** | maps render, report, several R task steps |
| Quarto | `C:\Users\pc\AppData\Local\Programs\Quarto` | `scan-calculations` report |
| GEE | project `ee-azizlums`, `earthengine authenticate` done | elevation, forest, landcover, lst, green, ndmi, nightlight, water_risk |
| GCS ADC | `gcloud auth application-default login` as the account with bucket access | wsf, fathom, basic_info, benchmark, oxford, coastal_erosion, sea_level_rise, elevation, landcover_burn |

R packages (once). The ~40 spatial packages plus **knitr + rmarkdown** (Quarto
needs the latter two or every report fails):

```powershell
& "C:\Program Files\R\R-4.4.1\bin\Rscript.exe" -e "install.packages(c('knitr','rmarkdown'), type='binary', repos='https://cloud.r-project.org')"
```

Inputs to configure before any run:
- `inputs\multi_inputs.yml` — the city list + shared settings (`fwi_first_year`/`fwi_last_year` control the longest task).
- `inputs\menu.yml` — task on/off, plus the FCS block (`fcs`, `fcs_layers`, `fcs_base_dir`, `fcs_env`).
- `inputs\AOI\<City>\<City>.shp` — one folder per city.

---

## 1. Session setup (every new terminal)

```powershell
conda activate cityscan
cd <your-checkout>\city-scan
$env:PATH = "C:\Program Files\R\R-4.4.1\bin;" + $env:PATH
$env:GEE_PROJECT = "ee-azizlums"

# Where the FCS and UCRA bulk data trees live on THIS machine. Only needed if
# they are not at <repo parent>\FCS and <repo parent>\ucra-data.
$env:CITYSCAN_FCS_DIR  = "D:\Aziz\GFDRR\CRP\FCS"
$env:CITYSCAN_UCRA_DIR = "D:\Aziz\GFDRR\CRP\UCRA and City Scan Ultra\Pakistan"
```

**Snag:** forgetting the `$env:PATH` line is the single most common failure —
maps render dies with `FileNotFoundError [WinError 2]` (Rscript not found) and
R-backed task steps fail.

**On the data paths.** The FCS and UCRA *code* is vendored in this repo
(`tasks/fcs/`, `tasks/ucra/pipeline/`), but their input data is 60–160 GB and
lives outside it. Each root resolves in this order — first hit wins:

1. `fcs_base_dir` / `ucra_project_dir` in `inputs/menu.yml`
2. `$CITYSCAN_FCS_DIR` / `$CITYSCAN_UCRA_DIR`
3. `<repo parent>/FCS` and `<repo parent>/ucra-data`

The committed `menu.yml` leaves both blank on purpose, so nobody's machine paths
are pushed. Use the environment variables (above) or, if you prefer, fill in
`menu.yml` locally and keep it out of your commits with:

```powershell
git update-index --skip-worktree inputs\menu.yml
```

To make the variables permanent instead of per-session:

```powershell
setx CITYSCAN_FCS_DIR "D:\Aziz\GFDRR\CRP\FCS"
```

---

## 2. City Scan — data collection

```powershell
scan --all --multicity --parallel -e
```

**Always pass `-e` on a re-run.** Once the month rolls over, `scan_init` asks
`[e] Use existing (2026-06-…) / [n] Create new (2026-07-…)` for *every* city.
Answering `n` starts a fresh empty folder set and orphans all the existing
outputs — the `_fsca`, `_ucra` and render trees stay behind in the old one.
`-e` pre-answers "use existing" (`cli.py`: `f['use_existing'] = "-e" in args …`),
so everything lands in one place. `--sync`/`-t` and `-k`/`--keep` imply it too.

~30–60 min per city. Expect:

- **`City <name> failed with return code 1` on most cities — usually fine.** The
  batch continues. It normally means one task errored (typically `accessibility`,
  an Overpass timeout) while 36/37 passed. Note the code is *not* derived from
  task results — a city can report `37 passed 0 failed` and still exit 1 (the
  non-zero comes from interpreter shutdown, after `logs\task_report.txt` is
  written). Judge each city by its `N passed / N failed` line and that report.
- **`fwi` is the long pole** (~20 min/city). Shorten `fwi_first_year..fwi_last_year` to speed up.
- Transient network skips you may see: `ghs_builtup` / `ghs_population` (JRC
  jeodpp DNS), `seismic_hazard` (OpenQuake incomplete read), `burned_area`, `cyclones`.
  Re-run the single task later to fill gaps.
- Concurrency is capped at 5 to avoid OOM.

Re-run one task for one city:
```powershell
scan wsf --scan-id 2026-06-pakistan-arifwala
```

---

## 3. City Scan — maps (separate pass)

`scan --all` does **not** make maps. This does:

```powershell
scan --render maps --multicity
```

Expect (all benign for these inland Punjab cities):
- `No data for: slr_*`, `coastal_erosion_snap` — no coastline.
- `water_risk_quantity ... need at least two non-NA values to interpolate` on a few cities.
- `Failure: coastal_erosion_baseline - argument is of length zero`.

---

## 4. City Scan — report

```powershell
scan --render scan-calculations --multicity
```

**Snag:** if knitr/rmarkdown are missing you get, for *every* city:
`Error executing Rscript.exe: The pipe is being closed. (os error 232)` +
"The knitr package is not available". Fix with the install in §0.

---

## 5. FCS — data (runs all 17 layers, exports `_fsca`)

Requires the FCS tree at `fcs_base_dir` (default `D:/Aziz/GFDRR/CRP/FCS/`) with
`data/` and `01-inputs/shapefiles/WB_countries_Admin0_10m.shp`.

```powershell
scan fcs --multicity
```

Writes `_fsca`-tagged outputs into each city's
`mnt\<id>\02-process-output\{tabular,spatial,images}\` (~103 files/city).

**Expected per city: 9 SUCCESS, 2 SKIPPED, 6 FAILED → `[fcs] collect: WARNING`.**

At the end of each city the task prints a plain-English account instead of
leaving you to read the tracebacks:

```
  FCS — Rajanpur: 9 succeeded, 2 skipped, 6 failed
  ──────────────────────────────────────────────────────────────────
  OK       population, urbanland, heatflux, urbanheatisland, ...

  SKIPPED  (input data not present — nothing to compute)
    flood_population_exposure      Missing Fathom flood input folder
    flood_infrastructure_exposure  Missing road network shapefile ...

  FAILED   (expected for this city — data limitation, not a defect)
    population_rescaling   city is not in the IIASA Global Cities database, ...
    erosion                inland city — no shoreline inside the AOI ...
```

Anything whose signature isn't recognised is listed separately under
**`** UNEXPECTED — worth investigating **`** and logged at ERROR, so a genuine
regression can't hide among the six routine failures. The raw pandas tracebacks
are suppressed (they are kept in `<fcs_base_dir>\02-process-output\logs\`);
set `fcs_verbose: True` in `menu.yml` to echo them.

The six failures are by design, not breakage:

| Layer | Outcome | Why |
|---|---|---|
| population, urbanland, heatflux, urbanheatisland, cckp_precipitation, cckp_temperature, cleanup, country_population_ratio | SUCCESS | data present |
| flood_population_exposure, flood_infrastructure_exposure | SKIP | no Pakistan Fathom data; no road-network shapefile |
| population_rescaling, gdp_rescaling, gdp, demographics, country_gdp_ratio | FAIL | the 13 MCs are **not in the IIASA Global Cities DB** (`GC_PAK.csv` has only 9 major cities), so national SSP pop/GDP can't be downscaled |
| cyclones, erosion | FAIL | inland — single wind value / no shoreline |

Turn any layer off in `inputs\menu.yml` → `fcs_layers:`.

---

## 6. FCS — maps + plots (second pass)

```powershell
scan fcs --analyze --multicity
```

Fast; reads the existing `_fsca` data. Produces **7 maps + 4 plots per city** in
a separate `mnt\<id>\03-render-output\fcs\{maps,plots}\`.

Maps are drawn in **City Scan's own cartography** (`tasks\fcs\style.py`), so an
FCS map and a City Scan map are indistinguishable side by side in the report:
`cartolight` basemap with labels, raster semi-transparent and **unclipped**,
solid grey AOI outline, extent = AOI + 5% at the 8.77 × 7.55 map aspect, ticks
scale bar bottom-left, minimal north arrow bottom-right, and the legend in its
own right-hand panel at the 7:2 `map_portions` split with a plain title over an
italic subtitle. The numbers come from `core\R\maps-static.R` and
`core\R\fns-maps-aes.R` rather than being eyeballed.

Note this is **not** the same look as the UCRA maps, which follow the Burundi
report (clipped raster, dashed AOI, colourbar underneath). Shared plumbing —
reprojection, basemap, scale bar, north arrow — lives in `core\py\map_base.py`;
only the styling differs, in each task's `style.py`.

**Caveat:** the two urban-heat-island maps are **flat zero for all 13 cities** —
the UHI signal genuinely is ~0 for small inland towns (the `_urbanheatisland_fsca.csv`
tables are all `0.0`). They are rendered for consistency; do not read variation into them.

---

## 7. UCRA — data + export + render

```powershell
scan ucra --multicity            # batch-if-needed + export this city's slice + render
scan ucra --analyze --multicity  # re-render maps/plots only
```

**Read this before running.** UCRA is a **country batch**, not a per-city pipeline:
one run processes *every* shapefile in `<ucra_project_dir>\shapefiles_received\`
and writes cross-city tables (`stats\avg_temp.csv`, `stats\avg_air_1998_2019.csv`,
`stats\CCKP\*.csv`, …) with **one row per city**, which its plots use as peer
comparisons. So the task:

- runs the batch **once**, auto-triggered only when this city's UCRA output folder
  is missing. The batch creates *all* city folders, so on a fresh setup **city 1
  triggers it (slow) and cities 2-13 reuse it**. It will not run 13 times.
- exports this city's `<project_dir>\<City>\` slice (47 files) **plus** the 76
  cross-city stats CSVs (prefixed `ucra_stats_`) into
  `mnt\<id>\02-process-output\`, tagged **`_ucra`**.
- copies the **26 figures the UCRA R scripts drew** (`r_scripts\*.R` → ggsave into
  `<project_dir>\plots\`) into `03-render-output\ucra\plots\`, prefixed `r_`.
- renders **up to 11 maps + 3 peer-context plots** into
  `mnt\<id>\03-render-output\ucra\`.

Expected: `[ucra] collect: OK | analyze: OK`, 77 tabular + 46 spatial `_ucra`
files per city, plus 26 `r_*` figures. Prerequisites: env `ucra`, the AOIs staged
in `shapefiles_received\`, and the global datasets in `<ucra_project_dir>\data\`.

Maps are drawn in the style of the CRP *Urban Climate Risk Analysis — Burundi*
report (`tasks\ucra\style.py`): washed-out basemap (satellite for the
temperature layers, pale street canvas for the rest), raster clipped to the AOI
and drawn semi-transparent, **black dashed AOI outline**, tick-marked scale bar
in kilometres, no axes or frame. Basemap tiles are fetched at render time — with
no network the map still draws, just on a plain background.

| Snag | What it means |
|---|---|
| City 1 takes far longer than the rest | **Expected** — it's running the whole country batch. |
| `No UCRA outputs for '<city>' … and ucra_run_batch_if_missing is False` | Turn the flag on, or run the batch manually (below). |
| `UCRA batch finished but no output folder matched this city` | The AOI isn't in `shapefiles_received\`, or the name didn't normalise — UCRA names folders `Title Case` from the shapefile stem. |
| Stale WSF mosaic after changing the city set | Known UCRA trap: move the old `data\WSF2019` / `data\WSFevolution` mosaics aside so they rebuild. Never delete. |

Module toggles (`run_cckp`, `run_environment`, `run_wsf_drought`, …) live in
**`UCRA\configs\ucra_menu.yaml`**, not `menu.yml`. Force a full re-run explicitly:

```powershell
conda run -n ucra python "D:\Aziz\GFDRR\CRP\UCRA and City Scan Ultra\UCRA\run_pipeline.py" --config "D:\Aziz\GFDRR\CRP\UCRA and City Scan Ultra\UCRA\configs\ucra_menu.yaml"
```

---

## 7b. UCRA / CMIP6 — the one PER-CITY UCRA module (opt-in)

Ported from `UCRA\scripts\UCRA_pipeline_cmip6_downscaling_debiasing_ai_plot.ipynb`
into `city-scan\tasks\ucra\cmip6.py`. Unlike every other UCRA module this one is
genuinely per-city: it reduces NASA NEX-GDDP-CMIP6 daily fields over **one AOI's
extent** and pairs them with the matching ERA5 observed series, so it runs inside
the normal per-city loop and never touches the country batch.

Turn it on in `inputs\menu.yml`:

```yaml
ucra_cmip6: True
```

then the usual command picks it up:

```powershell
scan ucra --multicity
```

Produces, per city:

| Where | What |
|---|---|
| `02-process-output\tabular\` | `Timeseries_<var>_<City>_EnsembleMean_<scenario>_<decade>s_ucra_cmip6.csv` |
| | `<city>_cmip6_summary_ucra_cmip6.csv` — 2025 / 2100 / delta per scenario |
| | `<city>_cmip6_bias_correction_ucra_cmip6.csv` |
| `03-render-output\ucra\cmip6\` | `<city>_<var>_projection.png` — ensemble curves, ±1 SE band, Δ labels |
| | `<city>_rx1day_boxplot.png` — annual daily maxima by period |
| | `<city>_<var>_monthly_heatmap.png` — ERA5 observed climatology |
| | `<city>_bias_correction.png` — raw vs linear vs Random Forest (vs XGBoost) |

**Read this before enabling.**

| Snag | What it means |
|---|---|
| It is *slow* | One GEE round trip per variable × scenario × year. The defaults (4 vars, 3 scenarios, 1980-2100) are ~1,450 calls per city — hours, not minutes, and ×13 for the full batch. |
| Interrupting is safe | Results are cached **per decade**; a re-run refetches only the decades that are missing. Ctrl+C and resume freely. |
| Only 3 scenarios exist | GEE's NEX-GDDP-CMIP6 mirror carries `historical`, `ssp245`, `ssp585` only. SSP1-2.6 and SSP3-7.0 cannot be produced here no matter what `ucra_cmip6_scenarios` says. |
| `xgboost not installed — skipping the XGB correction` | Benign; linear scaling + Random Forest still run. `pip install xgboost` inside the `cityscan` env to add it. |
| `overlap too short (N days)` | Bias correction needs ≥100 days where CMIP6 historical and ERA5 both exist — widen `ucra_cmip6_first_year`. |
| `CMIP6_Future` empty before 2015 | Correct, not a bug: the SSP runs start in 2015. |

To try it cheaply first, narrow the window:

```yaml
ucra_cmip6_first_year: 2010
ucra_cmip6_last_year: 2039
ucra_cmip6_vars: ['tas']
```

---

## 8. Report again — now including the FCS + UCRA sections

```powershell
scan --render scan-calculations --multicity
```

Report goes from 16 → **18 sections**, gaining labelled
**"Future City Scan (FCS)"** (4 plots + urban-land/population tables) and
**"Urban Climate Risk Assessment (UCRA)"** sections. The UCRA section is split
into *Maps*, *Peer-city comparisons and climate indices* (the 3 rendered
comparisons plus the 26 `r_*` figures from UCRA's R scripts) and, when enabled,
*CMIP6 downscaled projections*, followed by the built-up, CMIP6-summary and
cross-city LST tables. Figures with no entry in the caption map still appear,
titled by their file stem — so new output shows up without editing the `.qmd`.

**Snag:** `scan --render ... --scan-id <one city>` **skips sync**, so edits to
`tasks\*\charts\` or `scan-calculations\sections.yml` won't reach that city.
Use `--multicity` (which syncs), or copy the files into `mnt\<id>\` manually.

---

## 9. Optional — upload to GCS

```powershell
scan --upload --multicity
```

`--upload` alone backfills everything already on disk; combined with a task or
`--render` it only pushes newly-created files.

**Snag:** large rasters time out on a slow uplink — the standalone
`upload_*_to_gcs.py` helpers use 8 MiB resumable chunks + retries and skip
already-present files, so just re-run them to finish.

---

## 10. Global INPUT data in GCS (bootstrapping a fresh machine)

§9 pushes *outputs*. This section is about the *inputs* UCRA and FCS need — the
bulk rasters that otherwise have to be copied onto every machine by hand.

Both live in `gs://city-scan-global-data`, beside City Scan's own global data:

| Prefix | Contents | Size |
|---|---|---|
| `ucra-data/` | mirror of `Pakistan\data\` — **already uploaded and verified** (5,555 files, 0 missing, 0 size mismatches) | 61.7 GB |
| `fcs-data/` | the `FCS\data\` folders the pipeline actually reads | 36.9 GB working set |
| `fcs-inputs/shapefiles/` | `WB_countries_Admin0_10m.shp` etc. — outside `data\`, nothing runs without it | 0.3 GB |

### Push (FCS; UCRA is done)

```powershell
python upload_fcs_data_to_gcs.py --dry-run
```

```powershell
python upload_fcs_data_to_gcs.py
```

Only 8 of the 28 folders in `FCS\data\` are referenced anywhere in the canonical
pipeline's `src\*.py`; the default **working set** is narrower still — the
folders the steps that *succeed* for these MCs need (urbanland, popdynamics,
heatflux, demographic, urbanheatisland, CCKP). `--all` adds `gdp`, `fathom` and
`globalErosionProjections` (~121 GB) for countries that can use them. Resumable
and skip-if-present, so it can be stopped and restarted freely. Check with:

```powershell
python upload_fcs_data_to_gcs.py --verify
```

### Pull

Per-run, without touching config:

```powershell
scan fcs --multicity --sync-data
```

```powershell
scan ucra --multicity --sync-data
```

Or make it the default in `inputs\menu.yml`:

```yaml
fcs_data_source: 'gcs'
ucra_data_source: 'local'
```

FCS pulls **only the folders its enabled `fcs_layers` need** (`LAYER_DATA` in
`tasks\fcs\__init__.py`) — the Pakistan layer set is ~37 GB, all 17 layers ~121
GB. UCRA has no useful subset: the batch runs every module over every city, so
it takes the whole 62 GB tree.

**Why this downloads instead of streaming.** City Scan reads its global data
straight from the bucket via `/vsigs/`, because `core\R\gcs-overrides.R`
monkeypatches *its own* `rast` / `vect` / `read_sf` / `read_csv`. UCRA and FCS
are separate repos launched through `conda run` in their own envs, doing plain
`os.path.exists` and `rasterio.open` on absolute local paths — there is no
reader to patch without forking them. So `core\py\global_data.py` makes the
files exist first, which is also what City Scan already does for scan folders in
`gcs_module.download_scan_folder()`.

| Snag | What it means |
|---|---|
| Second run re-lists the bucket | Expected and cheap. Files are compared by (relative path, size); nothing already on disk is refetched. |
| Interrupted mid-download | Safe. Each file lands as `<name>.part` and is only renamed into place once complete, so a truncated file can never be mistaken for a good one. |
| `no objects under gs://…` | The prefix hasn't been uploaded yet — run the push above. |
| Running it during a `scan --all` | Both are network-bound; expect each to slow the other. |

---

## Prompts that used to hang unattended runs (now patched — don't re-break)

| Prompt | Where | Behaviour now |
|---|---|---|
| `Choose [t/o/a/k]` project-file sync | `core/config/sync.py` | auto-**override**; escape hatch `CITYSCAN_SYNC=keep\|tasks\|override` |
| `[e] Use existing / [n] Create new` | `core/config/scan.py::scan_init` | on EOF (non-interactive) defaults to the **existing** folder |

---

## Windows encoding (also patched — don't re-break)

Every file the pipeline writes that can contain a non-ASCII character **must**
pass `encoding='utf-8'` explicitly. Windows defaults to cp1252, and several
outputs carry box-drawing rules (`─`) or accented city names.

| Where | Fix |
|---|---|
| `tasks/__main__.py` task-report write **and** read-back | `open(..., encoding='utf-8')` |
| `core/py/log_module.py` file handler | `FileHandler(..., encoding='utf-8')` |
| `core/py/log_module.py` console | `_force_utf8_console()` reconfigures stdout/stderr with `errors='replace'` |

**The symptom this caused, in case it ever returns:** every task passes, then the
run dies at the very last line of `main()` with `UnicodeEncodeError` while
writing `logs/task_report.txt`. Because `open(...,'w')` truncates *before* it
writes, the report was left **0 bytes** and the city exited **return code 1** —
which is why cities reporting `37 passed 0 failed` still showed as failures.
Actual task outputs were never affected.

The console fix matters specifically under `--multicity`: each city runs through
`subprocess.run`, and Python falls back to the locale encoding when its output
isn't a TTY. Run directly in a terminal the console is already UTF-8 (CP 65001)
and none of this is visible.

If you want genuinely fresh output folders, run interactively and answer `n`
(creates a new `YYYY-MM-...` id). Nothing is ever deleted.
