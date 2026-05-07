# Maps customization: `layers.yml` and `maps.yml`

Two YAML files drive every static map:

- **`source/layers.yml`** — registry of map layers. Per-layer styling, title, palette, breaks, source-file pattern, etc.
- **`tasks/{name}/maps.yml`** — per-task render config. Which layers this task contributes, custom map scripts, and dependency tasks.<!-- Experimental: hex/aggregate behavior and smoothing config (only consumed by `maps-static-experimental.R`). -->

Map render flow lives in `core/R/maps-static.R`; per-layer parameter resolution lives in `core/R/fns-maps-web.R::prepare_parameters`. Experimental smoothing + hex aggregation paths live in `core/R/maps-static-experimental.R` + `core/R/fns-aggregation.R`.

---

## `source/layers.yml`

Each top-level key (the **yaml_key**, e.g. `population`, `wsf`, `gdp_agriculture`) defines one map layer. Inside it:

### Required

| Key | Notes |
|---|---|
| `fuzzy_string` | Regex matching the spatial filename in `02-process-output/spatial/`. Used by `fuzzy_read()`. e.g. `population.tif$`, `(?<!flood_)wsf.*\.tif$`. |
| `title` | Map title (rendered in legend / panel). |
| `palette` | List of hex codes, e.g. `['#ECEB72', '#8E3933']`. 6-digit `#RRGGBB` or 8-digit `#RRGGBBAA` (alpha will be multiplied by `alpha`/`layer_alpha`). |

### Common

| Key | Notes |
|---|---|
| `subtitle` | Smaller text under title. HTML allowed (e.g. `Number of persons per 10,000 m<sup>2</sup>`). |
| `caption` | Attribution / source string. Only printed when `plot_static_layer(captions = TRUE)`. |
| `group_id` | Leaflet layer-control group name (interactive maps). |
| `data_variable` | Column or band name to extract before plotting. e.g. for `gdp_agriculture` the raster has band `gdp_agriculture_2020`. Static-map path subsets with `data[dv]`. <!-- Experimental hex path renames the aggregated `value` column to `data_variable` so plot_static_layer's lookup matches. --> |

### Binning / scale

| Key | Type | Allowed values | Notes |
|---|---|---|---|
| `bins` | integer | `0`, or any positive int | `0` (or omit) → continuous `scale_fill_gradientn`. `>0` → stepped `scale_fill_stepsn`. Auto-derived as `length(breaks)` when only `breaks` is set. |
| `breaks` | numeric list | any numeric vector | Explicit cut points. For `factor: true`, these are the factor levels. |
| `labels` | string list | any | Labels for each bin or factor level. Literal `\n` becomes a real newline. Length should be `length(breaks) - 1` for binned, or `length(breaks)` for factor. |
| `binning_method` | string | `"quantile"` (default), `"interval"`, `"log"` | Used when `bins > 0` and `breaks` is null. `quantile` cuts at equal-population intervals; `interval` cuts at equal-width; `log` distributes on a base-10 log scale (positive values only, with a `0` floor). Defined in `break_pretty2` (`fns-maps-aes.R`). |
| `quantiles` | numeric list (0–1) | any | Custom cut probabilities for `binning_method: quantile`, e.g. `[0, 0.1, 0.5, 0.9, 1]`. Overrides the default equal-spaced cuts. |
| `min_value` | number | any | Drop values `< min_value` before computing breaks. Useful for skewed data where rural/background noise should not influence break placement. Applied in `break_pretty2` (`fns-maps-aes.R`) before the `quantile`/`interval`/`log` step. |
| `factor` | boolean | `true` / `false` | `true` triggers categorical path: `ordered()` + `scale_fill_manual` with `na.translate = FALSE`. Requires both `breaks` (= levels) and `labels`. |
| `center` | number | any | Pivot for diverging palettes (e.g. `0` for change rasters). Triggers `scales::rescale_mid` so the middle palette color sits at `center`. |
| `domain` | `[min, max]` | any 2-element numeric | Fixed scale range; overrides auto-detected min/max. |
| `oob` | string | `"squish"` (default), `"censor"`, `"squish_any"`, `"censor_any"` | Out-of-bounds handler for stepped scales. `squish` clamps to nearest bin; `censor` replaces with `NA`; `*_any` variants apply to any out-of-range value (not just numeric). Resolved in `fns-maps-aes.R::fill_scale`. |

### Vector-only styling

| Key | Notes |
|---|---|
| `stroke` | `TRUE` → color by value; a hex/named color → constant; defaults to `NA` (no stroke). |
| `fill` | Defaults to `TRUE`. Set `FALSE` to draw outlines only. |
| `weight` | Stroke line weight. |
| `size` | Point size. |
| `alpha` | Per-layer transparency (0–1). Multiplied into palette alpha. |

### Display formatting

| Key | Notes |
|---|---|
| `suffix` | Appended to numeric labels (e.g. `" m"`, `"%"`). |

### Legacy / not wired in the static path

These appear in the layers.yml `template` block but the current `maps-static.R` path doesn't read them. Safe to leave for legacy parity:

- `basemap` (`"satellite"` / `"vector"`) — only consumed by the leaflet/interactive path (`plot_basemap` in `fns-maps-static.R`).
- `labFormat`, `legend_opacity`, `min`, `max`, `crop` — declared in template, no live static-map use.
- `title_fr`, `subtitle_fr` — read only by `core/R/map-deforestation.R` and `core/R/transparencies.R` for French labels.

### Minimal example

```yaml
population:
  fuzzy_string: (?<!dense_)population.tif$
  title: 'Population density'
  subtitle: 'Number of persons per 10,000 m<sup>2</sup>'
  palette: ['#ECEB72', '#8E3933']
  group_id: Population density
  bins: 5
  caption: 'Map data from WorldPop Global2.'
```

### Categorical example

```yaml
land_cover:
  fuzzy_string: lc.tif$
  title: 'Land cover'
  palette: ['#006400', '#FFBB22', '#FFFF4C', '#F096FF', '#FA0000', ...]
  factor: true
  breaks: [10, 20, 30, 40, 50, ...]
  labels: ['Trees', 'Shrubland', 'Grassland', 'Cropland', 'Built-up', ...]
  group_id: Land cover
```

---

## `tasks/{name}/maps.yml`

Per-task render config. Read in two places:

- `core/R/fns-util.R::resolve_render_targets()` — called from `maps-static.R` when `--render maps` is invoked with specific tasks; gathers `layers`, `custom`, and resolves `depends`.
<!-- - `core/R/fns-aggregation.R::build_aggregate_lookups()` — EXPERIMENTAL. Builds aggregate/smoothing lookups so per-task settings override the global defaults. Currently only called from `maps-static-experimental.R`. -->

### Top-level keys

| Key | Type | Notes |
|---|---|---|
| `layers` | list of yaml_keys | Layers from `layers.yml` this task contributes. Drives the standard render loop. |
| `depends` | list of task names | Other tasks whose layers should also render when this task's `--render maps` is invoked (NOT a collection-time dependency — those live in `source/tasks.yml`). |
| `custom` | list of R script paths | Custom map scripts (relative to repo root, e.g. `core/R/map-flooding.R`). Run after standard layers. |

<!-- ##### **EXPERIMENTAL**
| Key | Type | Notes |
|---|---|---|
| `aggregate_fun` | string | Function for hex/cell aggregation. `mean`, `sum`, `median`, `min`, `max`, `modal`, or quantile syntax `q25`/`q50`/`q90` (parsed by `parse_agg_fun` in `fns-aggregation.R`). Default `"mean"`. |
| `aggregate_mode` | string | `"none"` (default), `"hexbin"`, `"h3"`, or `"resample"`. Inherits `city_inputs.yml::aggregate_mode` when omitted. |
| `aggregate_size` | integer (m) | Hexbin flat-to-flat distance OR resample cell side. Inherits `city_inputs.yml::aggregate_size` (default 1000) when omitted. Ignored for `h3` (resolution auto-derived from AOI area). |
| `min_coverage` | float (0–1) | Drop hex cells whose AOI coverage is below this fraction. Default `0` (no filter). |
| `smoothing` | object (see below) | Optional pre-hex raster smoothing. Produces a `_smooth` map and feeds the smoothed raster into the hex pipeline. | -->

<!-- ### `smoothing:` block *EXPERIMENTAL*

```yaml
smoothing:
  method: gaussian   # gaussian | median | modal
  window: 3          # focal window in cells (default 3)
  sigma: 1           # only used by gaussian (default 1)
```

- **gaussian**: weighted kernel, continuous data only.
- **median**: uniform window, preserves peaks; continuous data.
- **modal**: most-common value; the only safe choice for categorical/temporal layers (e.g. WSF year-of-construction, land cover). Don't use gaussian/median on temporal data — produces fake fractional years. -->

### Examples

**Layers only:**
```yaml
layers:
  - wsf
  - wsf_tracker
  - wsf_harmonized
```

<!-- **Hex aggregation with quantile fun:**
```yaml
layers:
  - wsf
  - wsf_tracker
  - wsf_harmonized
aggregate_mode: hexbin
aggregate_fun: q25       # typical build year — between mode (biased old) and max (biased newest)
aggregate_size: 2400
min_coverage: 0.1
```

**Categorical with smoothing:**
```yaml
layers:
  - land_cover
aggregate_fun: modal
aggregate_mode: hexbin
aggregate_size: 2400
smoothing:
  method: modal
  window: 3
```

**Custom-only task (no standard layers):**
```yaml
custom:
  - core/R/map-building-footprints.R
``` -->

**Layers + dependency layers + custom script:**
```yaml
layers:
  - fluvial
  - pluvial
  - coastal
  - combined_flooding
depends:
  - worldpop
  - wsf
  - accessibility
custom:
  - core/R/map-flooding.R
```

