# =========================================================
# STATIC MAPPING FUNCTION
# =========================================================

create_geom <- function(data, params) {
  data_type <- type_data(data)
  layer_values <- get_layer_values(data)
  if (data_type == "points") {
    geom_spatvector(data = data, aes(color = layer_values), size = params$size %||% 1)
  } else if (data_type == "polygons") {
    geom_spatvector(data = data, aes(fill = layer_values), color = params$stroke)
  } else if (data_type == "lines") {
    stroke_variable <- if (length(params$stroke) > 1) params$stroke$variable else NULL
    weight_variable <- if (length(params$weight) > 1) params$weight$variable else NULL
    # I could use aes_list in a safer way
    # aes_list2 <- c(
    #   aes(color = .data[[stroke_variable]]))
    #   aes(linewidth = (.data[[weight_variable]])))
    aes_list <- aes(color = .data[[stroke_variable]], linewidth = (.data[[weight_variable]]))
    if (is.null(weight_variable)) aes_list <- aes_list[-2]
    if (is.null(stroke_variable)) aes_list <- aes_list[-1]
    geom_spatvector(data = data, aes_list)
  } else if (data_type == "raster") {
    geom_spatraster(data = data, maxcell = 5e6) #, show.legend = T)
  }
}


plot_static_layer <- function(
    data, yaml_key, baseplot = NULL, static_map_bounds, zoom_adj = 0,
    expansion, aoi_stroke = list(color = "grey30", linewidth = 0.4),
    plot_aoi = T, aoi_only = F, plot_wards = F, captions = F, packet = F, ...) {
  if (aoi_only) {
    layer <- NULL
  } else { 
    # Create geom and scales
    params <- prepare_parameters(yaml_key = yaml_key, ...)
    if (!is.null(params$data_variable)) data <- data[params$data_variable]
    if (exists_and_true(params$factor)) {
      data <- 
        set_layer_values(
          data = data,
          values = ordered(get_layer_values(data),
                          levels = params$breaks,
                          labels = params$labels))
      params$palette <- setNames(params$palette, params$labels)
    }
    if(params$bins > 0 && is.null(params$breaks)) {
      vals <- get_layer_values(data)
      if (!is.null(params$center)) {
        vals <- c(vals, params$center - vals)
      }
      params$breaks <- break_pretty2(
        data = vals, n = params$bins + 1, FUN = signif,
        method = params$binning_method %>% {if(is.null(.)) "quantile" else .},
        quantiles = params$quantiles)
      # Sparse data can collapse multiple quantile cut points onto the same value
      # (e.g. AOI with a single feature). Dedupe and shrink bins so scale_fill_stepsn
      # doesn't error with "replacement has N rows, data has 1".
      params$breaks <- unique(params$breaks)
      if (length(params$breaks) < 2) {
        params$bins <- 0
        params$breaks <- NULL
      } else {
        params$bins <- length(params$breaks) - 1
      }
    }
    geom <- create_geom(data, params)
    data_type <- type_data(data)
    scales <- list(
      fill_scale(data_type, params),
      color_scale(data_type, params),
      linewidth_scale(data_type, params)) %>%
      .[lengths(.) > 1]
    lab <- if (captions) labs(caption = params$caption %||% "") else NULL
    theme <- theme_legend(data, params)
    layer <- list(geom = geom, scale = scales, labs = lab, theme = theme)
  }

  # I should make all these functions into a package and then define city_dir,
  # map_width, static_map_bounds, etc., as package level variables that get set
  # with set_.*() variables

  if ("static_map_bounds" %in% ls() && missing(static_map_bounds)) remove(static_map_bounds, inherits = F)
  if (!exists("static_map_bounds")) {
    warning(paste("static_map_bounds does not exist. Define one globally or as an",
      "argument to plot_static_layer. A plot extent will be defined using `aoi`."))
    if (exists("aoi")) {
      static_map_bounds <- aspect_buffer(aoi, aspect_ratio, buffer_percent = 0.05)
  } else stop("No object `aoi` exists.")
  }

  if (!missing(expansion)) {
    aspect_ratio <- as.vector(ext(project(static_map_bounds, "epsg:3857"))) %>%
      { diff(.[1:2])/diff(.[3:4]) }
    static_map_bounds <- aspect_buffer(static_map_bounds, aspect_ratio, buffer_percent = expansion - 1)
  }

  if (packet) {
    p <- ggpacket() +
      ggnewscale::new_scale_fill() + ggnewscale::new_scale_color() +
      layer +
      theme_custom()
  } else {
  # Plot geom and scales on baseplot
  baseplot <- if (is.null(baseplot) || identical(baseplot, "vector")) {
    ggplot() +
      geom_spatvector(data = static_map_bounds, fill = NA, color = NA) +
      annotation_map_tile(type = "cartolight", zoom = get_zoom_level(static_map_bounds) + zoom_adj, progress = "none")
  } else if (is.character(baseplot)) {
    ggplot() +
      geom_spatvector(data = static_map_bounds, fill = NA, color = NA) +
      annotation_map_tile(type = baseplot, zoom = get_zoom_level(static_map_bounds) + zoom_adj, progress = "none")
  } else { baseplot + ggnewscale::new_scale_fill() }
  p <- baseplot +
    layer + 
    annotation_north_arrow(style = north_arrow_minimal, location = "br", height = unit(1, "cm")) +
    annotation_scale(style = "ticks", aes(unit_category = "metric", width_hint = 0.33), height = unit(0.25, "cm")) +        
    theme_custom()
  }
  if (captions) p <- p + theme(legend.box.margin = margin(0, 0, 18, 12, unit = "pt"), plot.caption = element_text(hjust = 0, size = 8, color = "grey40"))
  if (plot_aoi) p <- p + geom_spatvector(data = aoi, color = aoi_stroke$color, fill = NA, linetype = "solid", linewidth = 0.6)
  if (plot_wards) p <- p + geom_spatvector(data = wards, color = "grey40", fill = NA, linetype = "solid", linewidth = 0.25)
  p <- p + coord_3857_bounds(static_map_bounds)
  return(p)
}



# =========================================================
# WARDS / LANDMARKS OVERVIEW PLOTS
# =========================================================

# Plot AOI + ward boundaries with labels over satellite imagery. Returns a
# ggplot, or NULL when wards are missing or have no usable label column.
# Reads `wards`, `zoom_adjustment`, `include_captions` from the global env.
plot_wards_overview <- function() {
  if (is.null(wards)) return(NULL)
  ward_names_col <- intersect(names(wards), c("shapeName", "WARD_NO", "NAME", "name", "Name", "WARD", "ADM2_EN", "ADM2_NAME"))[1]
  if (is.na(ward_names_col)) return(NULL)
  ward_centroids <- centroids(wards)
  ward_centroids$label <- as.data.frame(wards)[[ward_names_col]]
  ward_df <- data.frame(
    x = geom(ward_centroids)[, "x"],
    y = geom(ward_centroids)[, "y"],
    label = ward_centroids$label
  )
  plot_static_layer(aoi_only = T, plot_aoi = T, plot_wards = F,
    expansion = 1.5, zoom_adj = zoom_adjustment, aoi_stroke = list(color = "yellow", linewidth = 0.4),
    baseplot = "https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/${z}/${y}/${x}.jpg",
    captions = include_captions) +
    geom_spatvector(data = wards, color = "white", fill = NA, linetype = "solid", linewidth = 0.25) +
    geom_spatial_text_repel(data = ward_df, crs = "epsg:4326",
      aes(x = x, y = y, label = label),
      size = 2.5, fontface = "bold", color = "white",
      segment.size = 0.2, box.padding = 0.3, max.overlaps = 20)
}

# Plot landmarks (italic labels) with ward labels (bold) and ward perimeter
# points used as obstacles to reduce text overlap. Returns a ggplot, or NULL
# when no landmarks file is found in `user_input_dir`. Side effect: writes
# landmarks.png into `styled_maps_dir`.
# Reads `user_input_dir`, `wards`, `ward_labels`, `styled_maps_dir` from globals.
plot_landmarks_overview <- function() {
  landmarks <- fuzzy_read(user_input_dir, "Landmark")
  if (!inherits(landmarks, "SpatVector")) return(NULL)
  landmarks <- landmarks %>% project("epsg:4326") %>% select(Name)
  landmarks_df <- mutate(landmarks, x = geom(landmarks)[,"x"], y = geom(landmarks)[,"y"])

  # Combine landmark labels, ward labels, and ward lines, to reduce text overlaps
  landmarks_and_points_to_avoid <-
    rbind(
      mutate(landmarks, label = Name, type = "landmark", fface = "italic", fsize = 1.5),
      mutate(ward_labels, label = WARD_NO, type = "ward", fface = "bold", fsize = 2),
      mutate(as.points(wards) %>% .[rep(c(T, F, F), nrow(.))], label = "", type = "perimeter")
      ) %>%
    mutate(x = geom(.)[,"x"], y = geom(.)[,"y"])
  plot <- plot_static_layer(aoi_only = T, plot_aoi = F, plot_wards = T) +
    geom_spatial_point(data = landmarks_df, crs = "epsg:4326", aes(x = x, y = y), size = 0.25) +
    geom_spatial_text_repel(data = landmarks_and_points_to_avoid, crs = "epsg:4326",
      aes(
        x = x, y = y, fontface = fface, size = fsize,
        label = break_lines(label, width = 12, newline = "\n")),
      segment.size = 0.1, box.padding = 0.1, min.segment.length = 0.2, max.time = 2,
      force_pull = 0.8, max.overlaps = 40,
      lineheight = 0.9) +
    scale_size(range = c(1.5, 2), guide = "none")
  save_plot(plot = plot, filename = "landmarks.png",
            directory = styled_maps_dir)
  plot
}


# =========================================================
# AOI AND ZOOM EXTENT HELPERS
# =========================================================


coord_3857_bounds <- function(extent, expansion = 1, ...) {
  if (!inherits(extent, "SpatExtent")) {
    if (inherits(extent, "SpatVector")) extent <- ext(project(extent, "epsg:3857"))
    if (inherits(extent, "sfc")) extent <- ext(vect(st_transform(extent, crs = "epsg:3857")))
    extent <- ext(extent)
  }
  coord_sf(
    crs = "epsg:3857",
    expand = F,
    default = T,
    xlim = extent[1:2] %>% { (. - mean(.)) * expansion + mean(.)},
    ylim = extent[3:4] %>% { (. - mean(.)) * expansion + mean(.)},
    ...)
}

get_zoom_level <- \(bounds, cap = 6) {
  area <- sum(expanse(project(bounds, "epsg:3857")))
  sq_area <- if (aspect_ratio >= 1) area * aspect_ratio else area / aspect_ratio
  zoom <- round(28.10592 - .77015 * log(sq_area))
  if (is.na(cap)) return(zoom)
  max(zoom, cap)
}

aspect_buffer <- function(x, aspect_ratio, buffer_percent = 0, to_crs = "epsg:3857", keep_crs = T) {
  if (!inherits(x, "SpatVector")) {
    if (inherits(x, "sfc")) x <- vect(x) else stop("Input must be a terra SpatVector object")
  }
  
  from_crs <- crs(x)
  x <- project(x, y = to_crs)
  bounds_proj <- ext(x)
  center_coords <- crds(centroids(vect(bounds_proj)))
  corners <- vect(matrix(
    c(bounds_proj$xmin, bounds_proj$ymin,  # bottom left
      bounds_proj$xmax, bounds_proj$ymin,  # bottom right
      bounds_proj$xmin, bounds_proj$ymax,  # top left
      bounds_proj$xmax, bounds_proj$ymax), # top right
    ncol = 2, byrow = TRUE), crs = to_crs)

  distance_matrix <- as.matrix(distance(corners))
  x_distance <- max(distance_matrix[1,2], distance_matrix[3,4])
  y_distance <- max(distance_matrix[1,3], distance_matrix[2,4])

  if (x_distance/y_distance < aspect_ratio) x_distance <- y_distance * aspect_ratio
  if (x_distance/y_distance > aspect_ratio) y_distance <- x_distance/aspect_ratio

  new_bounds <- terra::ext(
    x = center_coords[1] + c(-1, 1) * x_distance/2 * (1 + buffer_percent),
    y = center_coords[2] + c(-1, 1) * y_distance/2 * (1 + buffer_percent))
  new_bounds <- vect(new_bounds, crs = to_crs)
  if (!keep_crs) return(new_bounds)
  project(new_bounds, y = from_crs)
}



grow_extent <- \(x, amount) {
  # Given a SpatExtent object, grow (or shrink) it by a given multiplier
  # amount can be length 1 (applied to all sides), 2 (applied to x and y) or 4 (applied to each side)
  stopifnot(inherits(x, "SpatExtent"))
  stopifnot(length(amount) %in% c(1, 2, 4))
  if (length(amount) == 1) amount <- rep(amount, 4)
  if (length(amount) == 2) amount <- c(rep(amount[1], 2), rep(amount[2], 2))
  growth <- amount * c(rep(diff(x[1:2]), 2), rep(diff(x[3:4]), 2))
  x + growth
}

change_zoom <- function(p, zoom) {
  # Update, not the best method (better to use ggproto) but we have a way for 
  # separating q from p!
  
  # This is a bad solution because it changes the zoom level of all plots. 
  # p <- change_zoom(plot) changes the zoom on both plot (output) and p (input).
  # Need to learn how to either 1) create a distinct copy (neither ggplot_build
  # nor rlang::duplicate seem to do this), or 2) create a ggproto (?) that can
  # be used with `+`

  q <- unserialize(serialize(p, NULL))

  # p_copy <- ggplot2::ggplot_build(p)$plot
  tile_layer_index <- detect_index(p$layers, \(x) inherits(x$geom, "GeomMapTile"))
  q$layers[[tile_layer_index]]$mapping$zoom <- zoom
  q
}

zoom_on_extent <- function(p, extent_vect, aspect_ratio, buffer_percent = 0.05, zoom_adj = 0) {
  bounds <- aspect_buffer(extent_vect, aspect_ratio, buffer_percent = buffer_percent)
  (p + theme(legend.position = "none") +
    coord_3857_bounds(bounds)) %>%
    change_zoom(get_zoom_level(bounds) + zoom_adj)
}


# Compute static map bounds with autozoom: when built-up pixels (LC class 50)
# cover less than `built_up_threshold` of the AOI, center on the built-up core;
# otherwise frame the full AOI. Falls back to the AOI bounds on any error
# (missing LC raster, etc.). Reads `spatial_dir` from global env.
autozoom_bounds <- function(aoi, aspect_ratio, built_up_threshold = 0.10,
                            zoom_buffer = 0.15, full_buffer = 0.05) {
  tryCatch({
    lc <- fuzzy_read(spatial_dir, "_lc\\.tif$")
    if (!inherits(lc, "SpatRaster")) stop("No LC raster")
    urban_mask <- lc == 50
    ratio <- sum(values(urban_mask) == 1, na.rm = TRUE) / sum(!is.na(values(lc)))
    cat(sprintf("\nBuilt-up ratio: %.2f\n", ratio))
    if (ratio < built_up_threshold) {
      message("Centering on built-up core")
      urban_extent <- get_built_extent(urban_mask)
      aspect_buffer(vect(urban_extent, crs = crs(lc)), aspect_ratio, buffer_percent = zoom_buffer)
    } else {
      message(sprintf("Using full AOI (built-up > %d%%)", round(built_up_threshold * 100)))
      aspect_buffer(aoi, aspect_ratio, buffer_percent = full_buffer)
    }
  }, error = function(e) {
    message("Using full AOI (fallback: ", e$message, ")")
    aspect_buffer(aoi, aspect_ratio, buffer_percent = full_buffer)
  })
}

get_built_extent <- function(urban_mask) {
    # Apply opening morphological operation to remove thin lines (roads)
    kernel <- matrix(1, 5, 5) 
    eroded <- focal(urban_mask, w = kernel, fun = "min", na.rm = TRUE)
    # Then dilate
    opened <- focal(eroded, w = kernel, fun = "max", na.rm = TRUE)

    # Now get extent of remaining urban area
    urban_cells <- cells(opened, 1)[[1]]
    urban_coords <- xyFromCell(opened, urban_cells)
    urban_extent <- ext(
        min(urban_coords[,1]), max(urban_coords[,1]),
        min(urban_coords[,2]), max(urban_coords[,2])
    )

    return(urban_extent)
}


# =========================================================
# ADDITIONAL LAYER COMPONENT HELPERS
# =========================================================

# Functions for making the maps
plot_basemap <- function(basemap_style = "vector") {
  aoi_bounds <- st_bbox(aoi)
  basemap <-
    leaflet(
      data = aoi,
      # Need to probably do this with javascript
      height = "calc(100vh - 2rem)",
      width = "100%",
      options = leafletOptions(zoomControl = F, zoomSnap = 0.1)) %>% 
    fitBounds(
      lng1 = unname(aoi_bounds$xmin - (aoi_bounds$xmax - aoi_bounds$xmin)/20),
      lat1 = unname(aoi_bounds$ymin - (aoi_bounds$ymax - aoi_bounds$ymin)/20),
      lng2 = unname(aoi_bounds$xmax + (aoi_bounds$xmax - aoi_bounds$xmin)/20),
      lat2 = unname(aoi_bounds$ymax + (aoi_bounds$ymax - aoi_bounds$ymin)/20))
  if (basemap_style == "satellite") { 
    basemap <- basemap %>% addProviderTiles(., providers$Esri.WorldImagery,
                      options = providerTileOptions(opacity = basemap_opacity))
  } else if (basemap_style == "vector") {
    # addProviderTiles(., providers$Wikimedia,
    basemap <- basemap %>%
      addProviderTiles(providers$CartoDB.Positron)
      # addProviderTiles(., providers$Stadia.AlidadeSmooth,
      #  options = providerTileOptions(opacity = basemap_opacity))
  }
  return(basemap)
}


add_aoi <- function(map, data = aoi, color = 'black', weight = 2, fill = F, dashArray = '12', ...) {
  addPolygons(map, data = data, color = color, weight = weight, fill = fill, dashArray = dashArray, ...)
}

# Helper: overlay the major-road network on a map. Reads `road_network` from
# global env (loaded in setup.R as a SpatVector from {city}_major_roads.gpkg,
# layer "major_roads"). Drawn as an underlay so roads sit above the basemap
# tiles but beneath the data layer.
add_roads_underlay <- function(p, underlay = TRUE, color = "grey65") {
  if (!exists("road_network") || is.null(road_network)) return(p)
  roads_sf <- sf::st_as_sf(road_network)
  roads_sf$highway <- ifelse(is.na(roads_sf$highway), "primary", roads_sf$highway)
  width_map <- c(
    "motorway" = 0.45, "trunk" = 0.35, "primary" = 0.25,
    "connector" = 0.3,
    "secondary" = 0.2, "tertiary" = 0.15, "unclassified" = 0.1,
    "motorway_link" = 0.175, "trunk_link" = 0.15, "primary_link" = 0.125,
    "secondary_link" = 0.1, "tertiary_link" = 0.075
  )
  roads_layer <- ggplot2::geom_sf(
    data = roads_sf, inherit.aes = FALSE,
    aes(linewidth = highway),
    color = color, fill = NA
  )
  p <- p + roads_layer +
    ggplot2::scale_linewidth_manual(values = width_map, guide = "none") +
    coord_3857_bounds(static_map_bounds)
  if (underlay) {
    n <- length(p$layers)
    tile_idx <- which(vapply(p$layers[-n], function(l) {
      inherits(l$geom, "GeomMapTile") || inherits(l$stat, "StatMapTile")
    }, logical(1)))
    insert_after <- if (length(tile_idx) > 0) max(tile_idx) else 2
    new_order <- c(seq_len(insert_after), n, seq(insert_after + 1, n - 1))
    p$layers <- p$layers[new_order]
  }
  p
}


# Helper: overlay ward labels on a map. Reads `ward_labels` and
# `ward_label_column` from global env. No-ops if either is missing.
add_wards_labels <- function(p) {
  if (!exists("ward_labels") || !exists("ward_label_column")) return(p)
  p + geom_text_repel(
    data = ward_labels,
    aes(label = ward_label_column, geometry = geometry),
    stat = "sf_coordinates", size = 2, fontface = "bold")
}

# Helper: add built-up area 2025 hatch overlay to a plot
# underlay = TRUE inserts hatch beneath data layers (for point/line maps)
add_builtup_hatch <- function(p, underlay = FALSE) {
  if (!exists("builtup_extent_2025") || is.null(builtup_extent_2025)) return(p)
  builtup_clipped <- sf::st_intersection(sf::st_as_sf(builtup_extent_2025), sf::st_as_sf(aoi))
  hatch_layer <- ggpattern::geom_sf_pattern(
    data = builtup_clipped, color = NA, fill = NA,
    aes(pattern = "2025 built-up area"),
    pattern_spacing = 0.0125, pattern_fill = NA,
    pattern_density = 0.5, pattern_size = 0.25)
  if (underlay) {
    # Add the hatch via `+` so ggplot registers it properly, then move it to position 3
    # (above basemap, below all data layers). Direct insertion into $layers bypasses
    # ggplot's compute-layer setup and errors with "Problem while computing layer data".
    p <- p + hatch_layer +
      ggpattern::scale_pattern_manual(values = "stripe", name = "") +
      coord_3857_bounds(static_map_bounds)
    n <- length(p$layers)
    p$layers <- append(p$layers[-n], list(p$layers[[n]]), after = 2)
  } else {
    p <- p + hatch_layer +
      ggpattern::scale_pattern_manual(values = "stripe", name = "") +
      coord_3857_bounds(static_map_bounds)
  }
  p
}




