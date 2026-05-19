# Orchestration

> For a visual diagram of the orchestration flow, see [orchestration-graph.md](../reference/orchestration-graph.md).

## Prerequisites

1. Activate the conda environment:
   ```bash
   conda activate cityscan
   ```

2. Navigate to the project root:
   ```bash
   cd city-scan-automation
   ```

3. Install the `scan` command (first time only):
   ```bash
   pip install -e .
   ```

## `scan` vs `python -m tasks`

Both commands do the same thing. `scan` is a shell alias installed via `pip install -e .`.

| | `scan` | `python -m tasks` |
|---|---|---|
| Runs from | repo root only | repo root or city folder |
| Needs `--scan-id` | always (for existing cities) | only from repo root |

> **Key difference:** `scan` always resolves to the repo root, so it requires `--scan-id` even if you're inside a city folder. To run without `--scan-id`, use `python -m tasks` directly from the city folder — this resolves paths relative to the local `tasks/__main__.py`.

```bash
# These are equivalent:
scan fathom --multianalysis --scan-id 2026-03-moldova-chisinau

cd mnt/2026-03-moldova-chisinau
python -m tasks fathom --multianalysis
```

---

## Single City

### Setup

1. Edit `inputs/city_inputs.yml` with city name, year range, flood config, etc.
2. Place AOI shapefile in `inputs/AOI/` (e.g., `tunis.shp`, `.dbf`, `.prj`, `.shx`)
3. If the city has wards, place wards shapefile in the same `inputs/AOI/` folder (any file with "wards" in the name)
4. Edit `inputs/menu.yml` to enable/disable tasks

### Run

```bash
# First run (creates city folder from inputs/)
scan --all

# Existing city
scan --all --scan-id 2026-04-namibia-windhoek

# Specific tasks
scan wsf
scan wsf population forest
scan wsf --collect
scan wsf --analyze
```

### Flow

1. Reads `inputs/city_inputs.yml` + `inputs/AOI/`
2. Auto-generates scan_id (e.g., `2026-04-namibia-windhoek`)
3. Creates `mnt/{scan_id}/`
4. Copies inputs to `01-user-input/`:
   - `city_inputs.yml`, `menu.yml` → `01-user-input/`
   - AOI files (no "wards" in name) → `01-user-input/AOI/`
   - Wards files ("wards" in name) → `01-user-input/wards/`
5. Copies `tasks/`, `core/`, `source/` to city folder
6. Runs collect → analyze for each enabled task

---

## Multiple Cities

### Setup — Option A: separate AOI folders

1. Edit `inputs/multi_inputs.yml` with a `cities:` list and shared settings.

2. Place each city's AOI in its own subfolder under `inputs/AOI/`:
   ```
   inputs/AOI/
     Windhoek/
       Windhoek_geoboundaries.shp (+ .dbf, .prj, .shx)
     Windhoek_wards/
       Windhoek_wards_geoboundaries.shp (+ .dbf, .prj, .shx)
     Swakopmund/
       Swakopmund.shp
   ```

3. Wards are auto-detected from `{city_name}_wards/` sibling folder (if exists).

### Setup — Option B: multipolygon file

Use a single vector file (GPKG, SHP, GeoJSON) where each row is a city. AOI shapefiles are auto-extracted to `inputs/AOI/{city_slug}/`.

```yaml
multipolygon:
  file: inputs/AOI/lobito_corridor_cities.gpkg
  name_column: GC_UCN_MAI_2025
```

To run only specific cities from the multipolygon file, add a `cities:` list — only those cities will be processed (all AOIs are still extracted):

```yaml
multipolygon:
  file: inputs/AOI/lobito_corridor_cities.gpkg
  name_column: GC_UCN_MAI_2025

# Only run these (must exist in the multipolygon file)
cities:
  - city_name: Sakania
  - city_name: Lukuni
```

If a city name in `cities:` is not found in the multipolygon file, an error is raised.

### Run

```bash
scan --all --multicity
scan elevation --multicity
scan --all --multicity --parallel
```

### Example `multi_inputs.yml` (Option A)

```yaml
cities:
  - city_name: Windhoek
  - city_name: Swakopmund
  - city_name: Walvis Bay

first_year: 2015
last_year: 2026

flood:
  threshold: 15
  year: [2020]
  return_period: [10, 100, 1000]
```

Per-city overrides are supported:
```yaml
cities:
  - city_name: Windhoek
    first_year: 2010
  - city_name: Aus
```

### Flow

For each city:

1. Extracts AOI (from multipolygon file or finds AOI subfolder)
2. Generates `city_inputs.yml` with shared settings + city-specific overrides
3. Creates city folder in `mnt/`, copies code + inputs
4. Runs tasks as subprocess
5. Moves to next city

Cities always run sequentially; `--parallel` applies to tasks within each city. `city_inputs.yml` is always updated from `multi_inputs.yml` to keep config in sync.

---

## Rendering

```bash
# Static maps — all layers
scan --render maps --scan-id 2026-04-namibia-windhoek

# Static maps — task-specific (only renders layers + custom scripts from that task's maps.yml)
scan fathom --render maps --scan-id 2026-04-namibia-windhoek
scan gdp_gridded --render maps --scan-id 2026-04-namibia-windhoek

# Scan calculations (generates index.qmd + quarto render)
scan --render scan-calculations --scan-id 2026-04-namibia-windhoek

# Single task charts (renders tasks/{task}/charts/index.qmd)
scan elevation --render charts --scan-id 2026-04-namibia-windhoek

# Render for all cities
scan --render maps --multicity
scan --render scan-calculations --multicity

# Sync code before rendering (useful if code was updated in repo root)
scan --render maps --sync --scan-id 2026-04-namibia-windhoek
```

Each task can define its map layers and custom R scripts in `tasks/{task}/maps.yml`:
```yaml
layers:
  - fluvial
  - pluvial
  - combined_flooding
custom:
  - core/R/map-flooding.R
```

---

## Multianalysis

Cross-task R/Python analysis scripts (e.g., fathom flood exposure).

```bash
scan --multianalysis --scan-id 2026-04-namibia-windhoek
scan fathom --multianalysis --scan-id 2026-04-namibia-windhoek
```

---

## Syncing

Update code in an existing city folder from the repo root without re-running setup.

```bash
# Sync everything (tasks, source, core, scan-calculations)
scan --sync --scan-id 2026-04-namibia-windhoek

# Sync specific targets
scan --sync tasks --scan-id 2026-04-namibia-windhoek
scan --sync tasks core --scan-id 2026-04-namibia-windhoek

# -t is shortcut for --sync tasks
scan -t --scan-id 2026-04-namibia-windhoek
```

---

## Flags

| Flag | Description |
|---|---|
| `--all` | Run all tasks enabled in menu.yml |
| `--scan-id {id}` | Target an existing city folder in mnt/ |
| `--multicity` | Batch run from inputs/multi_inputs.yml |
| `--collect` | Collection step only |
| `--analyze` | Analysis step only |
| `--multianalysis` | Run multianalysis scripts |
| `--render {target}` | Render: `maps`, `scan-calculations`, or `charts` |
| `--sync {targets}` | Sync code to city folder: `tasks`, `source`, `core`, `scan-calculations` |
| `-t` | Shortcut for `--sync tasks` |
| `-k` / `--keep` | Keep existing city folder as-is (no sync prompt) |
| `-e` | Use existing city folder (same as providing sync targets) |
| `--parallel` | Run tasks concurrently with TUI |
| `--upload` | Upload outputs to GCS after each step |
| `--auto-exit` | Skip confirmation prompts |
| `--list` | Show available tasks (`--list tasks`), cities (`--list cities`), or flags (`--list flags`) |
