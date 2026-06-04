# Generating City Scan Maps

# if ("frontend" %in% list.files()) setwd("frontend")
if (!require("here", quietly = TRUE)) install.packages("here")
library(here)

# WARNING: Some raster plotting breaks with terra 1.8+, when reprojected, such
# as to EPSG: 3857. It results in the following error. Would upgrading tidyterra
# also solve this?
# Caused by error:
# ! [spatSample] at least one of 'values', 'cells', or 'xy' must be TRUE; or 'as.points' must be TRUE 
# 2: No shared levels found between `names(values)` of the manual scale and the data's fill values.

# Set static map visualization parameters
layer_alpha <- 0.7
map_width <- 8.77 # Width of the map itself, excluding legend
map_height <- 7.55
aspect_ratio <- map_width / map_height
map_portions <- c(7, 2) # First number is map width, second is legend width
include_captions <- FALSE

# Load libraries and pre-process rasters
source(here("core/R/setup.R"), local = T)
if (!exists("render_tasks")) source(here("core/R/pre-mapping.R"), local = T)

# Define map extent and zoom level adjustment
# static_map_bounds <- aspect_buffer(aoi, aspect_ratio, buffer_percent = 0.05)

# Task-specific rendering: if render_tasks is set (from CLI), load maps.yml per task
# and filter to only those layers/custom scripts
render_layers <- NULL
render_custom <- NULL
if (exists("render_tasks") && length(render_tasks) > 0) {
  .rt <- resolve_render_targets(render_tasks)
  render_layers <- .rt$layers
  render_custom <- .rt$custom
  message("Rendering maps for tasks: ", paste(render_tasks, collapse = ", "))
  if (length(render_layers)  > 0) message("  Layers: ", paste(render_layers, collapse = ", "))
  if (length(.rt$dep_layers) > 0) message("  Dependency layers: ", paste(.rt$dep_layers, collapse = ", "))
  if (length(render_custom)  > 0) message("  Custom: ", paste(render_custom, collapse = ", "))
}

message("\n=== Generating City Scan Static Maps ===")

# Autozoom (disabled for now): see autozoom_bounds() in fns.R — centers on the
# built-up core when urban pixels cover <10% of the AOI, else frames full AOI.
# static_map_bounds <- autozoom_bounds(aoi, aspect_ratio)
static_map_bounds <- aspect_buffer(aoi, aspect_ratio, buffer_percent = 0.05)

zoom_adjustment <- 0

# Static maps

# Initiate plots list ----------------------------------------------------------
plots <- list()

# Plot AOI & wards -------------------------------------------------------------
plots$aoi <- plot_static_layer(aoi_only = T, plot_aoi = T, plot_wards = !is.null(wards),
  expansion = 1.5, zoom_adj = zoom_adjustment, aoi_stroke = list(color = "yellow", linewidth = 0.4),
  baseplot = "https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/${z}/${y}/${x}.jpg",
  captions = include_captions)
  
plots$wards     <- plot_wards_overview()
plots$landmarks <- plot_landmarks_overview()

# Aggregation config -----------------------------------------------------------
aggregate_mode <- city_params$aggregate_mode %||% "none"
aggregate_size <- city_params$aggregate_size %||% 1000

# Per-layer lookups resolved from each tasks/{name}/maps.yml. See
# build_aggregate_lookups() in fns.R for the YAML schema (mixed-list with
# optional per-layer overrides).
.lookups <- build_aggregate_lookups()
aggregate_fun_lookup      <- .lookups$fun
aggregate_mode_lookup     <- .lookups$mode
aggregate_size_lookup     <- .lookups$size
aggregate_coverage_lookup <- .lookups$cov
smoothing_lookup          <- .lookups$smoothing

# Standard plots ---------------------------------------------------------------
standard_layers <- unlist(lapply(layer_params, \(x) x$fuzzy_string)) %>%
  discard_at(c("fluvial", "pluvial", "coastal", "combined_flooding", "burnt_area", "elevation",
               "coastal_erosion_baseline", "transect_coastline", "seismic_hazard"))

# Filter to task-specific layers if render_tasks is set
# (check render_tasks not render_layers — c() collapses to NULL, so a task with
# only custom: and no layers: would otherwise fall through and render everything)
if (exists("render_tasks") && length(render_tasks) > 0) {
  standard_layers <- standard_layers[names(standard_layers) %in% render_layers]
}

standard_layers %>%
  map2(names(.), \(fuzzy_string, yaml_key) {
    tryCatch_named(yaml_key, {
      data <- fuzzy_read(spatial_dir, fuzzy_string)
      if (!inherits(data, c("SpatRaster", "SpatVector"))) {
        message(paste("No data for:", yaml_key))
        return(NULL)
      }
      # Select data_variable band for multi-band rasters (e.g. air quality)
      dv <- layer_params[[yaml_key]]$data_variable
      if (!is.null(dv) && inherits(data, "SpatRaster") && nlyr(data) > 1) data <- data[dv]
      # Clip raster to AOI (GEE/XEE rasters may only be bbox-clipped)
      # if (inherits(data, "SpatRaster")) data <- crop(data, aoi, mask = TRUE)

      # Downsample too-fine rasters to keep plot memory bounded. Multi-band
      # rasters without a data_variable selector default to band 1 (otherwise
      # plotting takes Nx memory). Factor rasters use modal aggregation,
      # continuous rasters use mean.
      if (inherits(data, "SpatRaster")) {
        if (nlyr(data) > 1) {
          message(paste("  Multi-band raster (", nlyr(data), "bands), taking first band only"))
          data <- data[[1]]
        }
        afun_agg <- if (isTRUE(layer_params[[yaml_key]]$factor)) "modal" else "mean"
        data <- aggregate_if_too_fine(data, threshold = 5e5, fun = afun_agg)
      }

      # Normal raster plot (always from the untouched original)
      raster_data <- vectorize_if_coarse(data)
      if (nrow(raster_data) > 0) {
        plot <- plot_static_layer(
          data = raster_data, yaml_key = yaml_key,
          plot_aoi = T, plot_wards = !is.null(wards), zoom_adj = zoom_adjustment)
        plots[[yaml_key]] <<- plot
        message(paste("Success:", yaml_key))
      }

      # Smoothing (per-task, optional). Produces {layer}_smooth and feeds the
      # smoothed raster into the hex path below. Helper handles tryCatch so a
      # focal crash / OOM skips gracefully without breaking the rest of the render.
      smooth_res <- apply_smoothing(data, yaml_key, smoothing_lookup[[yaml_key]], zoom_adjustment)
      data_smoothed <- smooth_res$smoothed
      if (!is.null(smooth_res$plot)) plots[[paste0(yaml_key, "_smooth")]] <<- smooth_res$plot

      # Hex aggregation (per-task, optional). Single helper handles both the
      # raster (run_aggregate) and points (points_hex_count) paths internally.
      # When smoothing is active, hex is computed from the smoothed raster.
      layer_agg_mode <- aggregate_mode_lookup[[yaml_key]] %||% aggregate_mode
      layer_agg_size <- aggregate_size_lookup[[yaml_key]] %||% aggregate_size
      if (layer_agg_mode != "none") {
        hex_plot <- aggregate_hex(
          data, data_smoothed, yaml_key, layer_agg_mode, layer_agg_size,
          aggregate_coverage_lookup[[yaml_key]] %||% 0,
          aggregate_fun_lookup[[yaml_key]] %||% "mean",
          zoom_adjustment)
        if (!is.null(hex_plot)) {
          plots[[paste0(yaml_key, "_hex")]] <<- hex_plot
          message(paste("Success:", yaml_key, "(hex)"))
        }
      }
      
    })
  }) %>% unlist() -> plot_log

# Built-up hatch overlays for hazard maps --------------------------------------
for (layer_name in c("landslides", "liquefaction")) {
  if (!is.null(plots[[layer_name]])) {
    plots[[paste0(layer_name, "_builtup")]] <- add_builtup_hatch(plots[[layer_name]])
  }
}
# Infrastructure has points — hatch goes underneath
if (!is.null(plots[["infrastructure"]])) {
  plots[["infrastructure_builtup"]] <- add_builtup_hatch(plots[["infrastructure"]], underlay = TRUE)
}

# Non-standard static plots ----------------------------------------------------

message("\nCustom maps:")
if (is.null(render_custom) && !exists("render_tasks")) {
  # No task filter — discover all custom scripts from maps.yml files
  render_custom <- c()
  task_dirs <- list.dirs(here("tasks"), recursive = FALSE, full.names = FALSE)
  for (td in task_dirs) {
    yml <- here("tasks", td, "maps.yml")
    if (file.exists(yml)) {
      task_maps <- yaml::read_yaml(yml)
      if (!is.null(task_maps$custom)) render_custom <- c(render_custom, task_maps$custom)
    }
  }

}
for (script in render_custom) {
  message("  ", basename(script))
  source(here(script), local = T)
}

# Save plots -------------------------------------------------------------------
# Switched to for loop because walk required too much memory; uncertain if helps
# For Algeria, reduced time from 1,100 seconds to 1,000 seconds
message(glue("\nSaving {length(plots)} maps to {styled_maps_dir}..."))
for (name in names(plots)) {
  message(glue("  Saving: {name}.png"), appendLF = FALSE)
  tryCatch({
    save_plot(plots[[name]], filename = glue("{name}.png"), directory = styled_maps_dir,
      map_height = map_height + ifelse(include_captions, .2, 0), map_width = map_width, dpi = 200, rel_widths = map_portions)
    message(" ✔")
  },
    error = function(e) message(glue(" ✗ {e$message}"))
  )
}

# See which layers weren't successfully mapped (only show for full renders)
if (!exists("render_tasks")) {
  unmapped <- setdiff(c(names(layer_params), "aoi", "forest_deforest", "burnt_area"), names(plots))
  if (length(unmapped) > 0) warning(paste(length(unmapped), "layers not mapped (not counting flood overlays):\n-", paste(unmapped, collapse = "\n- ")))
}
