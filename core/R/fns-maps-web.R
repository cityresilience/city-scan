# =========================================================
# WEB MAPPING FUNCTIONS
# =========================================================

prepare_parameters <- function(yaml_key, ...) {
  # Override the layers.yaml parameters with arguments provided to ...
  # Parameters include bins, breaks, center, color_scale, domain, labFormat, and palette
  layer_params <- read_yaml(layer_params_file)
  if (yaml_key %ni% names(layer_params)) stop(paste(yaml_key, "is not a key in", layer_params_file))
  yaml_params <- layer_params[[yaml_key]]
  new_params <- list(...)
  kept_params <- yaml_params[!names(yaml_params) %in% names(new_params)]
  params <- c(new_params, kept_params)

  # If labels are not null, convert literal \n to actual line breaks
  if (!is.null(params$labels)) {
    params$labels <- params$labels %>%
      str_replace_all("\\\\n", "\n")
  }

  params$breaks <- unlist(params$breaks) # Necessary for some color scales
  if (is.null(params$bins)) {
    params$bins <- if(is.null(params$breaks)) 0 else length(params$breaks)
  }
  if (is.null(params$stroke)) params$stroke <- NA
  if (exists_and_true(params$factor) & is.null(params$breaks)) {
    params$breaks <- params$labels
  }

  # Apply layer transparency to palette
  params$palette <- sapply(params$palette, \(p) {
    # If palette has no alpha, add
    layer_alpha <- params$alpha %||% layer_alpha
    if (p == "transparent") return("#FFFFFF00")
    if (nchar(p) == 7 | substr(p, 1, 1) != "#") return(scales::alpha(p, layer_alpha))
    # If palette already has alpha, multiply
    if (nchar(p) == 9) {
      alpha_hex <- as.hexmode(substr(p, 8, 9))
      new_alpha_hex <- as.character(alpha_hex * layer_alpha)
      # At one point I used the following; what was I trying to solve for? This
      # could make colors with alpha < 1 more opaque than colors with alpha = 1
      # new_alpha_hex <- as.character(as.hexmode("ff") - (as.hexmode("ff") - alpha_hex) * layer_alpha)
      if (nchar(new_alpha_hex) == 1) new_alpha_hex <- paste0(0, new_alpha_hex)
      new_p <- paste0(substr(p, 1, 7), new_alpha_hex)
      return(new_p)
    }
    warning(paste("Palette value", p, "is not of length 6 or 8"))
  }, USE.NAMES = F)

  return(params)
}



create_layer_function <- function(data, yaml_key = NULL, params = NULL, color_scale = NULL, message = F, fuzzy_string = NULL, ...) {  
  if (message) message("Check if data is in EPSG:3857; if not, raster is being re-projected")
  if (is.null(params)) {
    params <- prepare_parameters(yaml_key, ...)
  }
  if (!is.null(params$data_variable)) data <- data[params$data_variable]
  
  if (nrow(data) == 0) stop("Data object has no rows (0 geometries or 0 cells)")
  if (inherits(data, "SpatVector") && all(is.na(values(data)))) stop("Data object has no rows (0 geometries or 0 cells)")
  
  if (exists_and_true(params$factor)) {
    layer_values <- ordered(
      get_layer_values(data),
      levels = params$breaks,
      labels = params$labels)
    data <- 
      set_layer_values(
        data = data,
        values = layer_values)
  } else {
    layer_values <- get_layer_values(data)
    if(params$bins > 0 && is.null(params$breaks)) {
      vals <- get_layer_values(data)
      if (!is.null(params$center)) {
        vals <- c(vals, params$center - vals)
      }
      params$breaks <- break_pretty2(
                  data = vals, n = params$bins + 1, FUN = signif,
                  method = params$binning_method %>% {if(is.null(.)) "quantile" else .})
    }
    if (!is.null(params$breaks)) {
      # sig_digits <- max(nchar(str_replace_all(as.character(abs(breaks)), c("^[0\\.]*|\\." = ""))))
      # round_digits <- max(nchar(str_extract(params$breaks %>% {. - floor(params$breaks)}, "(?<=\\.).*")), na.rm = T)
      round_digits <- max(nchar(str_replace(params$breaks %>% {. - floor(params$breaks)}, "^.*\\.", "")), na.rm = T)
      layer_values <- round(layer_values, round_digits)
    } else {
      layer_values <- round(layer_values, 2)
    }
    data <- set_layer_values(data, values = layer_values)
  }
  labels <- label_maker(x = layer_values,
                        levels = params$breaks,
                        labels = params$labels,
                        suffix = params$suffix)

  if (is.null(color_scale) & length(params$palette) > 0) {
    domain <- set_domain(layer_values, domain = params$domain, center = params$center, factor = params$factor)
    color_scale <- create_color_scale(
      domain = domain,
      palette = params$palette,
      center = params$center,
      # bins = if (is.null(params$breaks)) params$bins else params$breaks
      bins = params$bins,
      breaks = params$breaks,
      factor = params$factor,
      levels = levels(layer_values))
  }

  # if (length(params$stroke$palette) > 0) {
  #   stroke_color_scale <- create_color_scale(
  #     domain = range(data)[,params$stroke$variable],
  #     palette = params$stroke$palette,
  #     bins = params$bins,
  #     breaks = params$breaks
  #   )
  # }

if (inherits(data, "SpatRaster")) v <- as.polygons(data, digits = 4)
if (inherits(data, "SpatVector")) v <- data

v_styled <- v %>%
  rename(value = 1) %>%
  mutate(
    fillColor = color_scale(value),
    label = label_maker(
      x = value,
      levels = params$breaks,
      labels = params$labels,
      suffix = params$suffix))
fgb_path <- file.path(fgb_dir, paste0(yaml_key, ".fgb"))
writeVector(v_styled, fgb_path, overwrite = T, filetype = "FlatGeobuf")


# Where did this come from? Appeared 2025-06-02??
  # # If the data is a raster, we need to set the domain to the range of the values
  # # in the raster. If it is a vector, we can use the values in the first column.
  # if (class(data)[1] %in% c("SpatRaster", "RasterLayer")) {
  #   domain <- if (is.null(params$domain)) range(layer_values, na.rm = T) else params$domain
  # } else {
  #   domain <- if (is.null(params$domain)) range(layer_values, na.rm = T) else params$domain
  # }
  # legend_opacity <- params$legend_opacity %||% 0.8

# I have moved the formerly-present note on lessons from the CRC Workshop code to my `Week of 2023-11-26` note in Obsidian.

### !!! I need to pull labels out because not always numeric so can't be signif

layer_function <- function(maps, show = T) {
    if (class(data)[1] %in% c("SpatRaster", "RasterLayer")) {
    # RASTER
      # maps <- maps %>% 
      #   addRasterImage(data, opacity = 1,
      #     colors = color_scale,
      #     # For now the group needs to match the section id in the text-column
      #     # group = params$title %>% str_replace_all("\\s", "-") %>% tolower(),
      #     group = params$group_id)
      maps <- maps %>% 
        addFgb(
          file = fgb_path,
          color = NULL,
          fill = T,
          label = "label",
          fillOpacity = 0.9,
          group = params$group_id)
    } else if (class(data)[1] %in% c("SpatVector", "sf")) {
      # VECTOR
      if ( # Add circle markers if geometry type is "points"
        (class(data)[1] == "SpatVector" && geomtype(data) == "points") |
        (class(data)[1] == "sf" && "POINTS" %in% st_geometry_type(data))) {
        maps <- maps %>%
          addCircles(
            data = data,
            color = params$palette,
            weight = params$weight,
            # opacity = 0.9,
            group = params$group_id,
            # label = ~ signif(pull(data[[1]]), 6)) # Needs to at least be 4 
            label = labels)
      } else { # Otherwise, draw the geometries
        maps <- maps %>%
          addPolygons(
            data = data,
            fill = if(is.null(params$fill) || params$fill) T else F,
            fillColor = ~color_scale(layer_values),
            fillOpacity = 0.9,
            stroke = if(!is.null(params$stroke) && !is.na(params$stroke) && params$stroke != F) T else F,
            color = if(!is.null(params$stroke) && !is.na(params$stroke) && params$stroke == T) ~color_scale(layer_values) else params$stroke,
            weight = params$weight,
            opacity = 0.9,
            group = params$group_id,
            # label = ~ signif(pull(data[[1]]), 6)) # Needs to at least be 4 
            label = labels)
    }} else {
      stop("Data is not spatRaster, RasterLayer, spatVector or sf")
    }
    # See here for formatting the legend: https://stackoverflow.com/a/35803245/5009249
    # Check if data is points (for circular legend icons)
    is_points <- (class(data)[1] == "SpatVector" && geomtype(data) == "points") |
                 (class(data)[1] == "sf" && "POINTS" %in% st_geometry_type(data))

    legend_args <- list(
      map = maps,
      # data = data,
      position = 'bottomright',
      values = domain,
      # values = if (is.null(params$breaks)) domain else params$breaks,
      # pal = if (is.null(params$labels) | is.null(params$breaks)) color_scale else NULL,
      pal = if (diff(lengths(list(params$labels, params$breaks))) == 1) NULL else color_scale,
      # colors = if (is.null(params$labels) | is.null(params$breaks)) NULL else if (diff(lengths(list(params$labels, params$breaks))) == 1) color_scale(head(params$breaks, -1)) else color_scale(params$breaks),
      colors = if (diff(lengths(list(params$labels, params$breaks))) == 1) color_scale(tail(params$breaks, -1)) else NULL,
      opacity = legend_opacity,
      # bins = params$bins,
      # bins = 3,  # legend color ramp does not render if there are too many bins
      labels = params$labels,
      title = format_title(params$title, params$subtitle),
      # labFormat = params$labFormat,
      # labFormat = labelFormat(transform = function(x) label_maker(x = x, levels = params$breaks, labels = params$labels)),
      # labFormat = function(type, breaks, labels) {
      # }
      # group = params$title %>% str_replace_all("\\s", "-") %>% tolower())
      group = params$group_id,
      className = if (is_points) "info legend legend-circle" else "info legend")
    legend_args <- Filter(Negate(is.null), legend_args)
    # Using do.call so I can conditionally include args (i.e., pal and colors)
    maps <- do.call(addLegend, legend_args)
    # if (!show) maps <- hideGroup(maps, group = layer_id)
    return(maps)
  }

  return(layer_function)
}

# Making the static map, given the dynamic map
mapshot_styled <- function(map_dynamic, file_suffix, return) {
  mapview::mapshot(map_dynamic,
          remove_controls = c('zoomControl'),
          file = paste0(styled_maps_dir, city_string, '-', file_suffix, '.png'),
          vheight = vheight, vwidth = vwidth, useragent = useragent)
  # return(map_static)
}

