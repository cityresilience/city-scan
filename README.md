# City Scan

A City Scan is a rapid geospatial assessment of a city's demographic, socioeconomic, climate, and risk conditions. It is a collection of maps and charts made from global and publicly available datasets that provide quick high-level insights into resilience-related topics for a city. These scans are especially useful for grounding early-stage conversations in geospatial data.

This repository provides automation tools for city scanning and analysis. The task-based structure organizes each topic and data source into its own module under `tasks/`, with standardized data collection, analysis, and visualization components.

---

## Getting Started

1. **Install prerequisites** — R, Python, Quarto, and gcloud. See [docs/getting-started/setup.md](docs/getting-started/setup.md) for full instructions per OS.

2. **Clone the repo and install the Command Line Interface (CLI)** — from the repo root, run:
   ```bash
   pip install -e .
   ```
   This installs the `scan` command. For details on the CLI and how the orchestration works, see [docs/getting-started/orchestration.md](docs/getting-started/orchestration.md).

3. **Verify your environment** — run:
   ```bash
   scan --check
   ```
   This runs a preflight on R, Python, GEE, GCS, Quarto, and inputs. Fix anything that fails before continuing.

4. **Run your first scan** — configure `inputs/city_inputs.yml` + `inputs/menu.yml`, drop an AOI shapefile in `inputs/AOI/`, then run `scan --all`. Step-by-step in [docs/getting-started/run-scan.md](docs/getting-started/run-scan.md).

For a longer guided tour (including modifying maps and creating charts), see [docs/getting-started/walkthrough.md](docs/getting-started/walkthrough.md).

---

## Structure

Top-level folders:

- **`inputs/`** — User config (`city_inputs.yml`, `multi_inputs.yml`, `menu.yml`, `AOI/`)
- **`tasks/`** — Scan topics, each with collection, analysis, and charts
- **`core/`** — Shared infrastructure (Python, R, config)
- **`source/`** — Canonical configs copied to each city (`layers.yml`, `tasks.yml`, `generic-text.yml`)
- **`scan-calculations/`** — Quarto project that compiles per-task charts into a single report
- **`mnt/`** — Auto-created per-city output folders (`YYYY-MM-country-city/`)
- **`templates/`** — Boilerplate files for new tasks and starter input configs
- **`docs/`** — Setup guides and reference (see [docs/README.md](docs/README.md))
- **`logs/`** — Auto-created log files

Each scan in `mnt/{scan_id}/` contains:
- `01-user-input/` — copy of the user's `inputs/`
- `02-process-output/` — spatial rasters and tabular CSVs
- `03-render-output/` — static maps and chart PNGs
- copies of `tasks/`, `core/`, `source/`, `scan-calculations/`

See [docs/reference/structure.md](docs/reference/structure.md) for a full breakdown.

---

## Workflow

The general workflow is:

1. **Configure** — set up AOI boundary and city parameters in `inputs/`
2. **Collect** — `scan --collect` downloads and clips global datasets to the AOI
3. **Analyze** — `scan --analyze` computes statistics and generates CSVs
4. **Multianalysis** — `scan --multianalysis` runs cross-task R/Python analysis (e.g. fathom flood exposure)
5. **Map** — `scan --render maps` generates static maps from spatial data using `layers.yml` styling
6. **Chart** — `scan --render charts {task}` renders per-topic Quarto charts
7. **Compile** — `scan --render scan-calculations` assembles the combined report

`scan --all` runs steps 2–3 for every task enabled in `menu.yml`. Step 4 runs only for tasks with a `multianalysis.R`/`.py` file. Steps 5–7 use the `--render` flag and can be run from the repo root (with `--scan-id`) or directly inside a city folder.

For a visual diagram of how data flows, see [docs/reference/workflow-graph.md](docs/reference/workflow-graph.md). For a hands-on walkthrough, see [docs/getting-started/walkthrough.md](docs/getting-started/walkthrough.md).

---

## Path Resolution

The CLI runs from two locations:

- **Repo root** (`city-scan-automation/`) — on first run, `scan --all` creates the city folder in `mnt/` and copies `tasks/`, `core/`, `source/` into it. Use `--scan-id` to target an existing city.
- **City folder** (`mnt/YYYY-MM-country-city/`) — run `python -m tasks` from here without needing `--scan-id`. All paths resolve relative to this folder.

> The `scan` shell alias always resolves to the repo root, so it requires `--scan-id` for existing cities. To run without `--scan-id`, use `python -m tasks` directly from the city folder.

R scripts use the `here` package (`.here` file) to resolve the project root. Python uses `core/config/paths.py` which auto-detects whether it's running from root or a city folder by looking for `01-user-input/`. Both approaches ensure the same code works from either location.

---

## Cache

City Scan uses a shared cache directory for some large downloads so repeated downloads can be reused across scans.

- Default location: `mnt/.cache/`
- Current namespaces: `worldpop/`, `osm-pbf/`
- Optional override: set `CITY_SCAN_CACHE_DIR` to use a different cache root

### Cache commands

```bash
scan --cache-ls
scan --cache-ls --cache-targets worldpop

scan --cache-purge                    # dry-run preview
scan --cache-purge --yes              # confirm purge
scan --cache-purge --yes --cache-targets worldpop,osm-pbf
```

Notes:

- `--cache-purge` is safe by default and only performs a dry run unless `--yes` is provided.
- `--cache-targets` accepts comma-separated targets (for example `worldpop,osm-pbf`) or `all`.
- For WorldPop direct downloads, cache writes are logged so users can see when a file is added to cache.
