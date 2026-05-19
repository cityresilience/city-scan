# Multi-City Runs

## Single City

```bash
scan --all
```

### Setup

1. Edit `inputs/city_inputs.yml` with city name, year range, flood config, etc.
2. Place AOI shapefile in `inputs/AOI/` (e.g., `tunis.shp`, `.dbf`, `.prj`, `.shx`)
3. If the city has wards, place wards shapefile in the same `inputs/AOI/` folder (any file with "wards" in the name)
4. Edit `inputs/menu.yml` to enable/disable tasks

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

### Re-running

From root with existing city:
```bash
scan --all --scan-id 2026-04-namibia-windhoek
```

From city folder:
```bash
cd mnt/2026-04-namibia-windhoek
scan --all
```

> **Note:** The `scan` shell alias always resolves to the repo root, so it requires `--scan-id` even if you're inside a city folder. To run without `--scan-id`, use `python -m tasks` directly from the city folder — this resolves paths relative to the local `tasks/__main__.py`.

---

## Multiple Cities

```bash
scan --all --multicity
```

### Setup

1. Edit `inputs/multi_inputs.yml` — same structure as `city_inputs.yml` but with a `cities:` list at the top. Shared settings (flood, accessibility, year range) apply to all cities.

2. Place each city's AOI in its own subfolder under `inputs/AOI/`:
   ```
   inputs/AOI/
     Windhoek/
       Windhoek_geoboundaries.shp (+ .dbf, .prj, .shx)
     Windhoek_wards/
       Windhoek_wards_geoboundaries.shp (+ .dbf, .prj, .shx)
     Swakopmund/
       Swakopmund.shp
     Walvis_Bay/
       walvis_buffer_hull_1000m.shp
     Luderitz/
       Luderitz.shp
     Aus/
       Aus.shp
   ```

3. Wards are auto-detected from `{city_name}_wards/` sibling folder (if exists).

4. `inputs/menu.yml` is shared across all cities.

### Example `multi_inputs.yml`

```yaml
cities:
  - city_name: Windhoek
  - city_name: Swakopmund
  - city_name: Walvis Bay
  - city_name: Lüderitz
  - city_name: Aus

# Shared settings (same fields as city_inputs.yml)
first_year: 2015
last_year: 2026

flood:
  threshold: 15
  year: [2020]
  return_period: [10, 100, 1000]

# ... accessibility, FWI, etc.
```

Per-city overrides are supported:
```yaml
cities:
  - city_name: Windhoek
    first_year: 2010    # override shared setting for this city only
  - city_name: Aus
```

### Flow

For each city in the list:

1. Finds AOI subfolder in `inputs/AOI/` (case-insensitive, handles umlauts and spaces → underscores)
2. Auto-detects the `.shp` file (skips files with "wards" in the name)
3. Generates `city_inputs.yml` with:
   - Shared settings from `multi_inputs.yml`
   - City-specific overrides
   - `AOI_shp_name` auto-detected from subfolder
   - `bm_cities_manual` auto-populated with the other cities in the list
4. Writes `city_inputs.yml` to `inputs/`
5. Runs `scan` (with all passthrough flags) as subprocess
6. Normal single-city flow takes over:
   - Creates `mnt/{scan_id}/`
   - Copies only this city's AOI files flat → `01-user-input/AOI/`
   - Copies wards → `01-user-input/wards/` (if `{city}_wards/` exists)
   - Rewrites `AOI_shp_name` in copied `city_inputs.yml` to flat stem
   - Runs tasks
7. Moves to next city

### Result

```
mnt/
  2026-04-namibia-windhoek/      # has wards
  2026-04-namibia-swakopmund/
  2026-04-namibia-walvis_bay/
  2026-04-namibia-luderitz/
  2026-04-namibia-aus/
```

Each city is self-contained. Benchmark cities (`bm_cities_manual`) point to siblings for cross-city population comparison via the sibling scan in `worldpop/analysis.R`.

### Flags

All flags work with `--multicity`:

```bash
scan --all --multicity --parallel    # parallel tasks within each city
scan --all --multicity --collect     # collect only for all cities
scan wsf fathom --multicity          # specific tasks for all cities
scan --all --multicity --upload      # upload to GCS after each task
```

Cities always run sequentially; `--parallel` applies to tasks within each city.
