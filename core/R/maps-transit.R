###############################################################################
################### GENERATE MAPS FOR TRANSIT EXPOSURE SCAN ###################
###############################################################################

#### WARNING: THIS IS CURRENTLY ONLY A SAMPLE SCRIPT; IT HAS NOT YET BEEN #####
#### GENERICIZED TO WORK WITH ALL TRANSIT SCANS. USE AS A BASIS.          #####
#### WRITTEN ORIGINALLY FOR BAKU TRANSIT SCAN.                            #####

# Add transit route data and other additional data (e.g. UTCI from heat team)
# to 01-user-input/additional-data. If external layers are included in
# layers.yml, they will automatically be included. (Not including transit data)

###############################################################################
########### USER PARAMETERS: All in-file parameters are set here.  ############
########### For layer-specific parameters, see source/layer.yml    ############
###############################################################################

# Set static map visualization parameters
layer_alpha <- 0.7
map_width <- 8.77 # Width of the map itself, excluding legend
map_height <- 6.2 # 7.55
aspect_ratio <- map_width / map_height
map_portions <- c(7, 2) # First number is map width, second is legend width
include_captions <- FALSE
zoom_adjustment <- 0
rotate_to_fit <- FALSE # Rotates CRS so short axis of the AOI aligns with the frame's short axis

##############################################################################
############# Standardized code begins here (no edits required) ##############
##############################################################################

# WARNING: Some raster plotting breaks with terra 1.8+, when reprojected, such
# as to EPSG: 3857. It results in the following error. Would upgrading tidyterra
# also solve this?
# Caused by error:
# ! [spatSample] at least one of 'values', 'cells', or 'xy' must be TRUE; or 'as.points' must be TRUE 
# 2: No shared levels found between `names(values)` of the manual scale and the data's fill values.

# Set project root
# If this is run from parent city-scan directory, auto_root_here() uses the
# function definition provided there, not that of the individual city
# Not broadly tested and maybe not very important
if (!require("here", quietly = TRUE)) install.packages("here")
library(here)
source("core/R/fns-util.R")
root <- auto_root_here()

# Load libraries and pre-process rasters
source(here("core/R/setup.R"), local = T)
if (!exists("render_tasks")) source(here("core/R/pre-mapping.R"), local = T)

# # Define map extent and zoom level adjustment ---------------------------------

# Rotate CRS to maximize AOI space in map frame
if (rotate_to_fit) crs_rot <- rotate_crs_to_short_axis(aoi) else crs_rot <- "EPSG:3857"
static_map_bounds <- aspect_buffer(aoi, aspect_ratio, buffer_percent = 0.00, to_crs = crs_rot, keep_crs = F)

# Autozoom (disabled for now; does not include rotation)
# see autozoom_bounds() in fns.R — centers on the built-up core when urban
# pixels cover <10% of the AOI, else frames full AOI.
# static_map_bounds <- autozoom_bounds(aoi, aspect_ratio)

###############################################################################
############################### Map generation ################################
###############################################################################

message("\n=== Generating City Scan Static Maps ===")

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

# Standard plots ---------------------------------------------------------------
standard_layers <- unlist(lapply(layer_params, \(x) x$fuzzy_string)) %>%
  discard_at(c("fluvial", "pluvial", "coastal", "combined_flooding", "burnt_area", "elevation",
               "coastal_erosion_baseline", "transect_coastline", "seismic_hazard"))

standard_layers %>%
  map2(names(.), \(fuzzy_string, yaml_key) {
    tryCatch_named(yaml_key, {
      data <- fuzzy_read(spatial_dir, fuzzy_string)
      # If data is not found, look in 01-user-input/additional-data
      if (!inherits(data, c("SpatRaster", "SpatVector"))) {
        data <- fuzzy_read(file.path(user_input_dir, "additional-data"), fuzzy_string)
      }
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
          plot_aoi = F, plot_wards = !is.null(wards), zoom_adj = zoom_adjustment)
        plots[[yaml_key]] <<- plot
        message(paste("Success:", yaml_key))
      }

    })
  }) %>% unlist() -> plot_log

# Multi-hazard -----------------------------------------------------------------
# Landslides, Flooding, Liquefaction, Heat

hazards <- layer_params %>%
  keep_at(c("landslides", "combined_flooding", "liquefaction")) %>%
  map(\(x) fuzzy_read(spatial_dir, x$fuzzy_string))
heat_hours <- rast(file.path(user_input_dir, "additional-data", "UTCI_20090803.tif"))
hazards$heat <- app(heat_hours, "max", filename = file.path(spatial_dir, "baku_UTCI_20090803_max.tif"), overwrite = TRUE)

mh <-
  hazards$combined_flooding$r100 +
  project(hazards$landslides >=4, hazards$combined_flooding, method = "max") +
  project(hazards$liquefaction >=4, hazards$combined_flooding, method = "max") +
  project(hazards$heat >= 32, hazards$combined_flooding, method = "max")

mh <- 0.5 * (
  hazards$combined_flooding$r100 +
  hazards$combined_flooding$r10 +
  project(hazards$landslides >= 3, hazards$combined_flooding, method = "max") +
  project(hazards$landslides >= 4, hazards$combined_flooding, method = "max") +
  project(hazards$liquefaction >= 3, hazards$combined_flooding, method = "max") +
  project(hazards$liquefaction >= 4, hazards$combined_flooding, method = "max") +
  project(hazards$heat >= 26, hazards$combined_flooding, method = "max") +
  project(hazards$heat >= 32, hazards$combined_flooding, method = "max")
)

mh_med <- ifel(hazards$combined_flooding$r100 >= 1, 1, 0)
mh_med$landslides_med <-  ifel(project(hazards$landslides, hazards$combined_flooding, method = "max") >= 4, 1, 0)
mh_med$liquefaction_med <-  ifel(project(hazards$liquefaction, hazards$combined_flooding, method = "max") >= 3, 1, 0)
mh_med$heat_med <-  ifel(project(hazards$heat >= 26, hazards$combined_flooding, method = "max") >= 26, 1, 0)
mh <- ifel(hazards$combined_flooding$r10 >= 1, 1, 0)
mh$landslides <-  ifel(project(hazards$landslides, hazards$combined_flooding, method = "max") >= 4, 1, 0)
mh$liquefaction <-  ifel(project(hazards$liquefaction, hazards$combined_flooding, method = "max") >= 4, 1, 0)
mh$heat <-  ifel(project(hazards$heat, hazards$combined_flooding, method = "max") >= 32, 1, 0)

mh <- sapp(mh, \(x) ifel(is.na(x), 0, x))
mh_med <- sapp(mh_med, \(x) ifel(is.na(x), 0, x))

plot(mh$liquefaction)


# multihazard <- (app(mh_med, "sum") + app(mh, "sum"))/2
multihazard <- app(mh, "sum")
heat_box <- vect(ext(hazards$heat), crs = crs(hazards$heat))
multihazard <-crop(multihazard, project(heat_box, multihazard), mask = T)
# plot(multihazard)
plots$multihazard <- plot_static_layer(
  data = multihazard, yaml_key = "multihazard",
  plot_aoi = F, plot_wards = !is.null(wards), zoom_adj = zoom_adjustment
)

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
message("\nStarting maps with layer-specific scripts:")
  # Discover all custom scripts from maps.yml files
render_custom <- c()
task_dirs <- list.dirs(here("tasks"), recursive = FALSE, full.names = FALSE)
for (td in task_dirs) {
  yml <- here("tasks", td, "maps.yml")
  if (file.exists(yml)) {
    task_maps <- yaml::read_yaml(yml)
    if (!is.null(task_maps$custom)) render_custom <- c(render_custom, task_maps$custom)
  }
}

for (script in render_custom) {
  message("  ", basename(script))
  source(here(script), local = T)
}

# Adjust plots ----------------------------------------------------------------
for (name in names(plots)) {
  if (rotate_to_fit) {
  # Rotate maps to maximize AOI space in map frame (see crs_rot above)
  plots[[name]] <- plots[[name]] +
    coord_sf(
      crs = sf::st_crs(crs_rot),
      default_crs = sf::st_crs(crs_rot),
      xlim = ext(static_map_bounds)[1:2] %>% { (. - mean(.)) * 1 + mean(.)},
      ylim = ext(static_map_bounds)[3:4] %>% { (. - mean(.)) * 1 + mean(.)},
      expand = F
      )
  }
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

### ADD TRANSIT ###############################################################

# Read in transit data (routes, stops, ridership)
if (!require("XML", quietly = TRUE)) install.packages("XML")
routes <- project(vect(file.path(user_input_dir, "additional-data", "Edited Tramway")), "epsg:4326")
ridership <- read_csv("01-user-input/additional-data/ridership.csv") %>% mutate(on_off = Boardings + Alightings)
stops <- project(vect(file.path(user_input_dir, "additional-data", "Mass Transit Preliminary.kmz"), layer = "T1 Stops"), "epsg:4326")
stops <- full_join(stops, ridership, by = c("Name" = "spatial_match"))

# Add transit layers to existing plots, and remove legends
plots_overview <- plots %>%
  purrr::map(\(p) {
    p +
      geom_spatvector(data = routes) +
      geom_spatvector(data = stops) +
      # geom_spatvector_text(data = routes, aes(label = Name)) +
      geom_text_repel(data = st_as_sf(routes), aes(label = paste0("T", Name), geometry = geometry), stat = "sf_coordinates") +
      coord_3857_bounds(static_map_bounds) +
      theme(legend.position = "none")
  })

# Save overview plots with transit layers
for (name in names(plots_overview)) {
  message(glue("  Saving: overview-{name}.png"), appendLF = FALSE)
  tryCatch({
    save_plot(plots_overview[[name]], filename = glue("overview-{name}.png"), directory = styled_maps_dir,
      map_height = map_height + ifelse(include_captions, .2, 0), map_width = map_width, dpi = 200, rel_widths = c(1, 0))
    message(" ✔")
  },
    error = function(e) message(glue(" ✗ {e$message}"))
  )
}

# Plot transit walksheds with flood overlays

walksheds <- buffer(stops, 400)
# ws_names <- as_tibble(walksheds)$Name 
# setdiff(ws_names, ridership$StopNo)
# setdiff(ridership$StopNo, ws_names)
# as_tibble(walksheds)

walksheds_list <- split(walksheds, "StopNo")

flood_data <- fuzzy_read(spatial_dir, layer_params$combined_flooding_2050_ssp2$fuzzy_string)

plot_static_layer(data = flood_data, yaml_key = "combined_flooding_2050_ssp2",
          plot_aoi = F, plot_wards = F, zoom_adj = 0, baseplot = "cartolight_nolabels")

# R WILL CRASH IF YOU TRY TO VIEW THESE PLOTS IN R. VIEW ONLY AS PNGS/JPGS
# Would probably be better to crop data first and re-run plot static layer for each
# but for non-standardized symbologies, this would result in inconsistent map appearances.
flood_walksheds <- map(walksheds_list, \(w) {
  # browser()
  tile_extent <- aspect_buffer(w, 1)
  # plots$combined_flooding_2050_ssp2 +
  plot_static_layer(data = crop(flood_data, tile_extent), yaml_key = "combined_flooding_2050_ssp2",
          plot_aoi = F, plot_wards = F, zoom_adj = 2, baseplot = "cartolight_nolabels") +
    geom_spatvector(data = w, fill = NA) +
    geom_spatvector(data = routes[1,]) +
    geom_spatvector(data = stops[tile_extent], size = 4, aes(color = on_off)) +
    # scale_color_gradient(low = "#ECEB72", high = "#8E3933", limits = c(0, max(stops$on_off, na.rm = TRUE))) +
    scale_color_stepsn(
      colors = c("#ECEB72", "#8E3933"),
      breaks = c(1300, 2700, 4200, 5900, 9500, 19000), limits = c(1300, 19000),
      values = breaks_midpoints( c(1300, 2700, 4200, 5900, 9500, 19000))
      ) +
    coord_3857_bounds(tile_extent) +
    labs(title = glue::glue("{w$Stop[1]}\n#{w$StopNo[1]}: {w$on_off[1]} on/off")) +
    theme(legend.position = "none", plot.title = element_text(size = rel(0.8)), plot.margin = unit(rep(0.2, 4), "lines"))
})

flood_walksheds_tiled <- cowplot::plot_grid(plotlist = flood_walksheds, nrow = 4)

# save_plot(flood_walksheds_tiled, filename = "flood_walksheds_tiled.png", directory = styled_maps_dir,
#   map_height = map_height + ifelse(include_captions, .2, 0), map_width = map_height * 1.7, dpi = 200)

cowplot::save_plot(
    plot = flood_walksheds_tiled,
    filename = file.path(styled_maps_dir, "flood_walksheds_tiled.jpg"),
    dpi = 300,
    base_height = map_height, base_width = map_width * 1.7)

# # thought this would work but dont think it does
# flood_walksheds_with_null <- list()
# # length(l2) <- length(flood_walksheds)
# for (i in seq_along(flood_walksheds)) {
#   flood_walksheds_with_null[[2*i - 1]] <- flood_walksheds[[i]]
# }

# flood_walksheds_tiled_spaced <- cowplot::plot_grid(plotlist = flood_walksheds_with_null, nrow = 4, rel_widths = rep(c(1, 0.1), length.out = length(flood_walksheds_with_null)/2))

# cowplot::save_plot(
#     plot = flood_walksheds_tiled_spaced,
#     filename = file.path(styled_maps_dir, "flood_walksheds_tiled_spaced.jpg"),
#     dpi = 200,
#     base_height = map_height, base_width = map_width * 1.7)

for (name in names(flood_walksheds)) {
  message(glue("  Saving: flood_walksheds-{name}.png"), appendLF = FALSE)
  tryCatch({
    save_plot(flood_walksheds[[name]], filename = glue("flood_walksheds-{name}.png"), directory = styled_maps_dir,
      map_height = map_height + ifelse(include_captions, .2, 0), map_width = map_width, dpi = 200, rel_widths = c(1, 0))
    message(" ✔")
  },
    error = function(e) message(glue(" ✗ {e$message}"))
  )
}