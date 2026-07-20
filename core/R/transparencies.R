# Generating City Scan maps for transparencies

if ("frontend" %in% list.files()) setwd("frontend")

# This file is currently set to use layers-with-french.yml instead of layers.yml.
# Change in R/setup.R

# Set static map visualization parameters --------------------------------------

# Frequently used parameters:
# For a single legend per map, use
#   map_width <- 12.56; map_height <- 9.7; map_portions <- c(map_width, 2.6)
# For two columns of legends (and captions), use
#   map_width <- 11.2; map_height <- 9.7; map_portions <- c(map_width, 4.06)

layer_alpha <- 0.7
map_width <- 11.2 # 15.16 is total width (map_width + legend width)
map_height <- 9.7
aspect_ratio <- map_width / map_height
map_portions <- c(map_width, 4.06) # First number is map width, second is legend width

# Specify, as vector, the languages to use for titles and subtitles.
# Currently, options are "english" and "french"
languages <- "english"

# Load libraries and pre-process rasters
source(here("core/R/setup.R"), local = T)
source(here("core/R/pre-mapping.R"), local = T)

# If you want to change the layers.yml file, change it here
# layer_params_file <- 'source/layers-uzbek.yml' # Also used by fns.R
# layer_params <- read_yaml(layer_params_file)

# Define map extent and zoom level adjustment

# Rotate CRS to maximize AOI space in map frame
crs_rot <- rotate_crs_to_short_axis(aoi)

# static_map_bounds <- aspect_buffer(aoi, aspect_ratio, buffer_percent = 0.05)
static_map_bounds <- aspect_buffer(aoi, aspect_ratio, buffer_percent = 0.05, to_crs = crs_rot, keep_crs = F)
zoom_adjustment <- 1

# Custom themes
theme_title <- \(...) theme(plot.title = element_text(size = 20, margin = margin(6, 0, 3.5, 40)), ...)

# Static maps
message("Creating standard maps...")
# Initiate plots list ----------------------------------------------------------
plots <- list()
packets <- list()

# Plot AOI boundary, vector basemap, and aerial basemap  -----------------------
plots$aoi <- plot_static_layer(aoi_only = T, plot_aoi = T, plot_wards = !is.null(wards),
  baseplot = ggplot(),
  zoom_adj = zoom_adjustment,
  aoi_stroke = list(color = "black", linewidth = 0.4)) +
  labs(title = paste(c(
    english = "Area of interest",
    french = "Zone d'intérêt")[languages],
    collapse = "   /   ")) +
  theme_title()

plots$vector <- plot_static_layer(aoi_only = T, plot_aoi = F, plot_wards = !is.null(wards),
  zoom_adj = zoom_adjustment,
  # , aoi_stroke = list(color = "black", linewidth = 0.4)
  ) +
  labs(title = "   ") +
  theme_title()

# Plot aerial imagery ----------------------------------------------------------
plots$aerial <- plot_static_layer(aoi_only = T, plot_aoi = F, plot_wards = !is.null(wards),
    zoom_adj = zoom_adjustment,
    #  aoi_stroke = list(color = "yellow", linewidth = 0.4),
    baseplot = "https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/${z}/${y}/${x}.jpg") +
  labs(title = "   ") +
  theme_title()

# Plot blank map for scale bar only --------------------------------------------
plots$scale_bar <- plot_static_layer(aoi_only = T, plot_aoi = F, plot_wards = F,
  baseplot = ggplot()) +
  theme_title() +
  annotation_scale(style = "ticks", aes(unit_category = "metric", width_hint = 0.33), height = unit(0.25, "cm"))

fake_layers <- c()

# Standard plots ---------------------------------------------------------------
unlist(lapply(layer_params, \(x) x$fuzzy_string)) %>%
  discard_at(c("burnt_area", "elevation")) %>%
  map2(names(.), \(fuzzy_string, yaml_key) {
    tryCatch_named(yaml_key, {
      file_path <- fuzzy_read(spatial_dir, fuzzy_string, FUN = paste)
      if (is.na(file_path)) stop(glue("File {file_path} does not exist"))
      variables_to_use <- c(
        layer_params[[yaml_key]]$data_variable,
        layer_params[[yaml_key]]$stroke$variable,
        layer_params[[yaml_key]]$weight$variable)  %||% 1
      data <- fuzzy_read(spatial_dir, fuzzy_string)
      data <- aggregate_if_too_fine(data, threshold = 5e5, fun = "modal")
      data <- vectorize_if_coarse(select(data, any_of(variables_to_use)), 70000)
      # Can disregard following, unless have other reasons to use. Instead, made forest use bins: 1
      # # Check if data is a SpatRaster with all NA values; only causes problems for factor data as we drop the unused factors
      # if (exists_and_true(layer_params[[yaml_key]]$factor) && inherits(data, "SpatRaster") && all(is.na(data[,,variables_to_use]))) {
      #   file_path <- fuzzy_read(file.path(spatial_dir, "fake"), fuzzy_string, FUN = paste)
      #   data <- fuzzy_read(file.path(spatial_dir, "fake"), fuzzy_string)
      #   if (inherits(data, "SpatRaster") && all(is.na(data[,,variables_to_use]))) {
      #     warning("No valid data found even in fake folder. Legend will not be created.")
      #   }
      # }
      if (length(variables_to_use) == 1) data <- data %>%
        select(all_of(variables_to_use))
      if (nrow(data) == 0) {
        message(paste("No data for:", yaml_key))
        return(NULL)
      }
      if (inherits(data, "SpatRaster")) data <- vectorize_if_coarse(data)
      titles <- unlist(layer_params[[yaml_key]][c("title", "title_fr")])
      subtitles <- unlist(layer_params[[yaml_key]][c("subtitle", "subtitle_fr")])
      packet <- plot_static_layer(
        title = paste(titles, collapse = "<br>"),
        subtitle = paste(subtitles, collapse = "<br>"),
        data = data, yaml_key = yaml_key, zoom_adj = zoom_adjustment,
        packet = T, plot_aoi = T, plot_wards = !is.null(wards)) +
        labs(title = paste(titles, collapse = "   /   ")) +
        theme_title()
      packets[[yaml_key]] <<- packet
      plots[[yaml_key]] <<- ggplot() + packet
      if (str_detect(file_path, "/fake/")) {
        fake_layers <<- unique(c(fake_layers, yaml_key))
        message(paste("Fake!:  ", yaml_key))
      } else {
        message(paste("Success:", yaml_key))
      }
    })
  }) %>% unlist() -> plot_log

if (length(fake_layers) > 0) {
  fake_log <- file.path(city_dir, "missing-layers.txt")
  fake_message <- sprintf(
    "%s is missing data for %d layers. Fake data has been used to ensure correct legend placement.\n - %s",
    city, length(fake_layers), paste(fake_layers, collapse = "\n - "))
  warning(fake_message)
  writeLines(fake_message, fake_log)
}

# Non-standard static plots ----------------------------------------------------
message("Creating non-standard maps...")
source(here("core/R/map-isochrones.R"), local = T) # Could be standard if layers.yml included baseplot # nolint: line_length_linter.
source(here("core/R/map-elevation.R"), local = T) # Could be standard if we wrote city-specific breakpoints to layers.yml
if ("zoom" %in% names(plots$elevation$layers[[2]]$mapping)) {
  plots$elevation$layers[[2]] <- NULL
}
source(here("core/R/map-deforestation.R"), local = T) # Could be standard if layers.yml included baseplot and source data had 2000 added
source(here("core/R/map-historical-burnt-area.R"), local = T)
# plots$infrastructure <- plots$infrastructure + theme(legend.text = element_markdown())

message("Adjusting plots for use as transparencies...")
# Rotate, remove grey background, add titles, remove scale bar and north arrow
for (name in names(plots)) {
  if (name != "scale_bar") {
    # Remove scale bar and north arrow
    plots[[name]]$layers <- plots[[name]]$layers %>%
      discard(\(x) inherits(x$geom, c("GeomNorthArrow", "GeomScaleBar")))
    # Draw AOI on all maps
    plots[[name]] <- plots[[name]] +
      geom_spatvector(data = aoi, fill = NA, linewidth = 0.4)
  }
  # Rotate maps to maximize AOI space in map frame (see crs_rot above)
  plots[[name]] <- plots[[name]] +
    coord_sf(
      crs = sf::st_crs(crs_rot),
      default_crs = sf::st_crs(crs_rot),
      xlim = ext(static_map_bounds)[1:2] %>% { (. - mean(.)) * 1 + mean(.)},
      ylim = ext(static_map_bounds)[3:4] %>% { (. - mean(.)) * 1 + mean(.)},
      expand = F
      )
  if (name == "vector") next
  if (name == "aerial") next
  # Remove grey background
  plots[[name]] <- plots[[name]] +
    theme(
      panel.background = element_rect(fill = "white"),
      legend.box.margin = margin(0, 0, 60, 12, unit = "pt")
      ) +
    theme_title()
  if (name == "aoi") next
  title <- paste(c(
      english = layer_params[[name]]$title,
      french =layer_params[[name]]$title_fr)[languages],
      collapse = "   /   ")
  if (length(title) > 0) {
    plots[[name]] <- plots[[name]] +
      labs(title = title)
  }
}

if (!is.null(plots$school_proximity)) plots$school_proximity <- plots$school_proximity +
  labs(title = paste(c(
    english = layer_params[["school_zones"]]$title,
    french = layer_params[["school_zones"]]$title_fr)[languages],
    collapse = "   /   "))
if (!is.null(plots$health_proximity)) plots$health_proximity <- plots$health_proximity +
  labs(title = paste(c(
    english = layer_params[["health_zones"]]$title,
    french = layer_params[["health_zones"]]$title_fr)[languages],
    collapse = "   /   "))
if (!is.null(plots$roads)) plots$roads <- plots$roads +
  labs(title = paste(c(
    english = layer_params[["roads"]]$stroke$title,
    french = layer_params[["roads"]]$stroke$title_fr)[languages],
    collapse = "   /   "))

# Save plots -------------------------------------------------------------------
message("Saving maps...")
transparencies_dir <- file.path(output_dir, "transparent-maps")
if (!dir.exists(transparencies_dir)) dir.create(transparencies_dir)
  discard_at(fake_layers %||% "") %>%
  walk2(names(.), \(plot, name) {
  # if (name != "aoi") return(NULL)
  save_plot(plot, filename = glue("{name}.png"), directory = transparencies_dir,
    map_height = map_height + .3, map_width = map_width, dpi = 200, rel_widths = map_portions)
})

# Save columns of legends by themselves ----------------------------------------
message("Creating legends...")
# First, create fake flood plot that combines fluvial, pluvial, and coastal flood legend titles
packets$sample_flood <-
  plot_static_layer(
    fuzzy_read(spatial_dir, layer_params$fluvial$fuzzy_string),
    "fluvial", packet = T,
    title = paste(collapse = "\n", c(
      english = "Flood Return Period",
      french = "Période de retour des inondations")[languages]),
    subtitle = paste(collapse = "\n", c(
      english = "15-cm or deeper flood event (global model)",
      french = "Probabilité d'un événement d'inondation de 15 centimètres ou plus dans une zone de 3 secondes d'arc au cours d’une année donnée")[languages]))

# First column
message("Assembling first legend column...")

# Create plot with all legends
leg1 <-
  ggplot() +
    packets$forest +
    packets$deforest +
    packets$vegetation +
    packets$sample_flood +
    packets$landslide +
    packets$summer_lst +
    packets$school_points +
    packets$health_points +
    theme(
      panel.background = element_rect(fill = "white"),
      legend.box.margin = margin(0, 0, 0, 0, unit = "pt"),
      legend.box.spacing = unit(0, "pt"),
      legend.justification = c("left", "top"))

map(leg1$scales$scales, function(s) tibble(name = s$name, aes = s$aesthetics[[1]])) %>% bind_rows()

# Specify guides for each legend and put in order (manual)
leg1$scales$scales[[1]]$guide <- guide_legend(    order = 1, theme = theme(legend.text = element_text(hjust = 0), legend.title = element_blank()))
leg1$scales$scales[[2]]$guide <- guide_colorsteps(order = 2, theme = theme(legend.text = element_text(hjust = 0)),                                 title = "Year of deforestation<br>", available_aes = c("fill_ggnewscale_3", "colour_ggnewscale_3"))
leg1$scales$scales[[3]]$guide <- guide_legend(    order = 3, theme = theme(legend.text = element_text(hjust = 0)),                                 title = "Vegetation (NDVI)<br>")
leg1$scales$scales[[4]]$guide <- guide_legend(    order = 4, theme = theme(legend.text = element_text(hjust = 0)))
leg1$scales$scales[[5]]$guide <- guide_legend(    order = 5, theme = theme(legend.text = element_text(hjust = 0)))
leg1$scales$scales[[6]]$guide <- guide_colourbar( order = 6, theme = theme(legend.text = element_text(hjust = 0)),                                                                      available_aes = c("fill_ggnewscale_7"))
leg1$scales$scales[[7]]$guide <- guide_legend(    order = 7, theme = theme(legend.text = element_text(hjust = 0), legend.title = element_blank()))
leg1$scales$scales[[8]]$guide <- guide_legend(    order = 8, theme = theme(legend.text = element_text(hjust = 0), legend.title = element_blank()))

leg1 %>%
  get_plot_component("guide-box-right") %>%
  ggsave(
    filename = file.path(transparencies_dir, glue("legend-col1.png")),
    height = map_height + 2, width = 2.3, dpi = 300, bg = "white")

# Second column
message("Assembling second legend column...")
 
# Create plot with all legends
leg2_order <- c(
  "population",
  "economic_activity",
  "gdp_combined",
  "wsf_harmonized",
  "roads")

leg2 <- ggplot() +
  packets[leg2_order] +
    theme(
      panel.background = element_rect(fill = "white"),
      legend.box.margin = margin(0, 0, 0, 0, unit = "pt"),
      legend.box.spacing = unit(0, "pt"),
      legend.justification = c("left", "top"))

map(leg2$scales$scales, function(s) tibble(name = s$name, aes = s$aesthetics[[1]])) %>% bind_rows()

# Specify guides for each legend and put in order (manual)
leg2$scales$scales[[1]]$guide <- guide_colorsteps(order = 1, theme = theme(legend.text = element_text(hjust = 1)), title = "People per 10,000 m<sup>2</sup>", available_aes = c("fill_ggnewscale_2", "colour_ggnewscale_2"), )
leg2$scales$scales[[2]]$guide <- guide_colorsteps(order = 2, theme = theme(legend.text = element_text(hjust = 1)),                                            available_aes = c("fill_ggnewscale_3", "colour_ggnewscale_3"), )
leg2$scales$scales[[3]]$guide <- guide_colorsteps(order = 3, theme = theme(legend.text = element_text(hjust = 1)),                                            available_aes = c("fill_ggnewscale_4", "colour_ggnewscale_4"), )
leg2$scales$scales[[4]]$guide <- guide_legend(    order = 6, theme = theme(legend.text = element_text(hjust = 1)), title = "Era of urban expansion")
leg2$scales$scales[[5]]$guide <- guide_colorsteps(order = 7, theme = theme(legend.text = element_text(hjust = 0)),                                            available_aes = c("colour"),                                   )
leg2$scales$scales[[6]]$guide <- guide_legend(    order = 8, theme = theme(legend.text = element_text(hjust = 0)), title = "Road type")

# Save legend
leg2 %>%
  get_plot_component("guide-box-right") %>%
  ggsave(
    filename = file.path(transparencies_dir, glue("legend-col2.png")),
    height = map_height + 2, width = 2.3, dpi = 300, bg = "white")
