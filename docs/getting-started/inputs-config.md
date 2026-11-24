# Input Configuration

The `inputs/` folder controls everything about a scan: which city, which AOI, which tasks run, and the parameters for each task.

Three YAML files drive the pipeline:

| File | Purpose |
|---|---|
| `city_inputs.yml` | Single-city config: city name, AOI, year ranges, flood/accessibility/benchmark params |
| `multi_inputs.yml` | Multi-city batch config: list of cities (or a multipolygon file) + shared settings |
| `menu.yml` | Per-task on/off toggles |

Templates live in `templates/`. Copy them to `inputs/` and edit before running.

---

## `city_inputs.yml`

### Identification

| Key | Type | Description |
|---|---|---|
| `city_name` | string | Display name. Spaces and accents OK (`Lobito Corridor`, `Lüderitz`). Used for outputs, labels, and slugified scan_id. |
| `AOI_shp_name` | string (optional) | Stem of the AOI shapefile in `inputs/AOI/` (no extension). If omitted, AOI is auto-detected from UCDB / OSM / 5km buffer around the city centroid. |
| `prev_run_date` | string `YYYY-MM` (optional) | Reuse a previous scan folder. Default: `null` (creates fresh `mnt/{YYYY-MM}-{country}-{city}/`). |

### Time ranges

| Key | Type | Description |
|---|---|---|
| `first_year` | int | Start year for LST and time-series tasks. Sentinel-2 / Landsat data available from 2013-03-18. |
| `last_year` | int | End year for the same. |
| `fwi_first_year` | int | Start year for Fire Weather Index. |
| `fwi_last_year` | int | End year for FWI. |
| `demographics_year` | int (optional) | WorldPop R2025A year (2015–2030). Default: current year. |

### Accessibility (`osm_query` + `isochrone`)

OSM POI categories to fetch and walking-distance buffers for each.

```yaml
osm_query:
  schools:
    amenity: [school, kindergarten, university, college]
  health:
    amenity: [clinic, hospital, health]
  police:
    amenity: [police]
  fire:
    amenity: [fire_station]

isochrone:  # meters
  schools: [800, 1600, 2400]
  health: [1000, 2000, 3000]

accessibility_buffer: 5   # % of AOI bounds to buffer for capturing amenities just outside the AOI
```

### Flood (`flood`)

Drives the Fathom flood analysis.

```yaml
flood:
  threshold: 15           # cm — minimum depth to count as flooded
  year: [2020, 2050, 2100]
  ssp: [2, 5]             # available: 1, 2, 3, 5
  return_period: [10, 100, 1000]   # available: 5, 10, 20, 50, 100, 200, 500, 1000
```

### Benchmarks (`benchmark_*`, `bm_cities_*`, `nearby_countries`)

Controls which cities to benchmark against for population/Oxford comparisons.

| Key | Values | Description |
|---|---|---|
| `benchmark_mode` | `sibling` / `oxford` / `auto` (default) | `sibling` = only sibling scans; `oxford` = only Oxford auto-detect; `auto` = both. |
| `bm_cities_manual` | list of city names | Explicit benchmark cities. Resolved as sibling → Oxford → backup, in that order. |
| `benchmark_backup` | `citypopulation` / `worldpop_ucdb` / `null` | Fallback for manual cities not found as sibling or Oxford. |
| `nearby_countries` | pipe-separated country names | Filter for Oxford auto-detect (only relevant when mode includes Oxford). |

---

## `multi_inputs.yml`

Same fields as `city_inputs.yml` plus the cities/multipolygon list. Two modes — use one (or combine, see below).

### Mode A: per-city AOI folders

Each city has its own `inputs/AOI/{city_name}/` folder with a `.shp`. Wards auto-detected from `inputs/AOI/{city_name}_wards/` if present.

```yaml
cities:
  - city_name: Windhoek
  - city_name: Swakopmund
  - city_name: Walvis Bay
  - city_name: Lüderitz
  - city_name: Aus
```

Per-city overrides supported:

```yaml
cities:
  - city_name: Windhoek
    first_year: 2010      # overrides the shared first_year for this city only
  - city_name: Aus
```

### Mode B: multipolygon file

A single vector file (GPKG, SHP, GeoJSON) where each row is a city. AOIs are auto-extracted to `inputs/AOI/{city_slug}/`.

```yaml
multipolygon:
  file: inputs/AOI/lobito_corridor_cities.gpkg
  name_column: GC_UCN_MAI_2025
```

### Mode B + filter

Combine `multipolygon:` with a `cities:` list to extract all AOIs but only run a subset.

```yaml
multipolygon:
  file: inputs/AOI/lobito_corridor_cities.gpkg
  name_column: GC_UCN_MAI_2025

cities:
  - city_name: Sakania
  - city_name: Lukuni
```

If a name in `cities:` isn't found in the multipolygon file, the run errors out.

### Shared settings

All other `city_inputs.yml` keys (flood, accessibility, FWI, year ranges, benchmark_*) work identically here and apply to every city in the list.

---

## `menu.yml`

Per-task on/off. Set `True` to run, `False` to skip. Tasks not listed default to `False`.

```yaml
accessibility: True
air_quality: True
basic_info: True
buildings: True
burned_area: True
coastal_erosion: True
cyclones: True
demographics: True
earthquake: True
elevation: True
flood_coastal: True
flood_fluvial: True
flood_pluvial: True
flood_comb: True
flood_events: True
forest: True
fwi: True
ghs_builtup: True
ghs_population: True
green: True
gdp_gridded: True
gdp_sectoral: True
groundwater: True
landcover: True
landcover_burn: True
landslide: True
liquefaction: True
lst_summer: True
lst_winter: True
ndmi: True
nightlight: True
oxford: True
population: True
rwi: True
sea_level_rise: True
seismic_hazard: True
slope: True
solar: True
water_risk: True
wsf: True

# Compilation
scan_calculations: True
```

**Notes:**
- `population` = WorldPop. To use GHSL instead, set `population: False` and `ghs_population: True`.
- `slope` is derived from `elevation`. If you toggle `slope: True`, also enable `elevation: True` (unless the elevation raster is already on GCS).
- `scan_calculations: True` triggers the combined HTML report after all tasks finish. The folder is auto-copied to the city directory.

See `templates/menu.yml` and `tasks/` for the canonical task list.
