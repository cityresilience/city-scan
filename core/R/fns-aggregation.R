
# =========================================================
# AGGREGATION FUNCTIONS
# =========================================================


count_aoi_cells <- function(data, aoi) {
  aoi_area <- if ("sf" %in% class(aoi)) {
    units::drop_units(sum(st_area(aoi)))
  } else if ("SpatVector" %in% class(aoi)) {
    sum(expanse(aoi)) # sum to account for multiple geometries
  }
  cell_count <- (aoi_area / cellSize(data)[1,1])[[1]]
  return(cell_count)
}

vectorize_if_coarse <- function(data, threshold = 7000) {
  if (class(data)[1] %in% c("sf", "SpatVector")) return(data)
  cell_count <- count_aoi_cells(data, aoi)
  if (cell_count < threshold) data <- rast_as_vect(data)
  return(data)
}

aggregate_if_too_fine <- function(data, threshold = 1e5, fun = "modal") {
  if (class(data)[1] %in% c("sf", "SpatVector")) return(data)
  cell_count <- count_aoi_cells(data, aoi)
  if (cell_count > threshold) {
    factor <- round(sqrt(cell_count / threshold))
    if (factor > 1) data <- terra::aggregate(data, fact = factor, fun = fun)
  }
  return(data)
}

# Parse a fun spec that may be "q{N}" (e.g. "q25", "q10", "q90") into a weighted
# quantile function compatible with exactextractr::exact_extract. Anything else
# is returned unchanged so the built-in exactextractr stats (mean, median, min,
# max, mode, sum, ...) still work.
parse_agg_fun <- function(fun) {
  if (is.function(fun)) return(fun)
  if (is.character(fun) && grepl("^q[0-9]+(\\.[0-9]+)?$", fun)) {
    q <- as.numeric(sub("^q", "", fun)) / 100
    if (q < 0 || q > 1) stop("quantile out of range: ", fun)
    return(function(values, coverage_fractions) {
      ok <- !is.na(values)
      if (!any(ok)) return(NA_real_)
      as.numeric(stats::quantile(values[ok], probs = q, na.rm = TRUE, type = 7))
    })
  }
  fun
}

run_aggregate <- function(data, aoi, mode, size, fun, gpkg_path, min_coverage = 0) {
  current_params <- paste(mode, size, fun, min_coverage)

  # Check cache
  if (file.exists(gpkg_path)) {
    tryCatch({
      cached_meta <- readLines(paste0(gpkg_path, ".params"), warn = FALSE)
      if (length(cached_meta) > 0 && cached_meta[1] == current_params) {
        message("  Loaded cached hex")
        return(vect(gpkg_path))
      }
    }, error = function(e) NULL)
  }

  # Generate
  hd <- if (mode == "hexbin") {
    hexbin_aggregate(data, aoi, hex_size_m = size, fun = fun, min_coverage = min_coverage)
  } else if (mode == "h3") {
    h3_aggregate(data, aoi, fun = fun)
  } else if (mode == "resample") {
    cell_aggregate(data, target_m = size, fun = fun)
  }

  message(paste("  Hex result:", if (is.null(hd)) "NULL" else paste(nrow(hd), "hexes")))

  # Save cache (hexbin/h3 only — resample stays as raster)
  if (!is.null(hd) && mode %in% c("hexbin", "h3")) {
    writeVector(hd, gpkg_path, overwrite = TRUE)
    writeLines(current_params, paste0(gpkg_path, ".params"))
    message(paste("  Saved:", gpkg_path))
  }

  hd
}

cell_aggregate <- function(data, target_m = 1000, fun = "mean") {
  fun <- parse_agg_fun(fun)
  if (class(data)[1] %in% c("sf", "SpatVector")) return(data)
  if (nlyr(data) > 1) data <- data[[1]]
  cell_m <- as.numeric(sqrt(cellSize(data, unit = "m")[1, 1]))
  if (cell_m >= target_m) return(data)
  fact <- round(target_m / cell_m)
  if (fact > 1) {
    if (is.function(fun)) {
      data <- terra::aggregate(data, fact = fact,
        fun = function(x, ...) fun(x, rep(1, length(x))))
    } else {
      data <- terra::aggregate(data, fact = fact, fun = fun)
    }
  }
  return(data)
}

# Smooth a raster in-place without mutating the input. Three methods:
#   gaussian: weighted kernel via terra::focalMat(..., "Gauss") — for continuous data
#   median:   uniform window, preserves peaks — for continuous data
#   modal:    most-common value — for categorical/temporal (e.g. WSF year, landcover)
# max_cells caps pre-focal raster size: terra::focal segfaults on rasters with
# tens of millions of cells (seen on Lobito's ~1000km AOI at native WSF resolution).
# Pre-aggregation reduces cells to a safe range before focal runs.
smooth_raster <- function(data, method = "gaussian", window = 3, sigma = 1, max_cells = 5e5) {
  if (!inherits(data, "SpatRaster")) {
    stop("smooth_raster requires a SpatRaster; got ", class(data)[1])
  }
  original_names <- names(data)  # preserve across aggregate + focal so plot_static_layer's data_variable lookup still works
  n <- terra::ncell(data)
  if (n > max_cells) {
    factor <- round(sqrt(n / max_cells))
    if (factor > 1) {
      # For categorical/temporal rasters (modal), "max" preserves the urban
      # signal in sparse blocks better than string "modal", which can collapse
      # NA-heavy blocks to NA and wipe the map. max = "latest year any pixel
      # was built in this block", same year semantics as the input.
      pre_fun <- if (method == "modal") "max" else "mean"
      message(paste0("  Pre-aggregating ", n, " cells by ", factor, "x before smoothing (fun=", pre_fun, ")"))
      data <- terra::aggregate(data, fact = factor, fun = pre_fun, na.rm = TRUE)
    }
  }
  result <- if (method == "gaussian") {
    w <- terra::focalMat(data, sigma, "Gauss")
    terra::focal(data, w = w, fun = "sum", na.rm = TRUE, na.policy = "omit")
  } else if (method == "median") {
    terra::focal(data, w = window, fun = "median", na.rm = TRUE, na.policy = "omit")
  } else if (method == "modal") {
    terra::focal(data, w = window, fun = "modal", na.rm = TRUE, na.policy = "omit")
  } else {
    stop("Unknown smoothing method: ", method, " (expected gaussian, median, or modal)")
  }
  names(result) <- original_names
  result
}

hexbin_aggregate <- function(data, aoi, hex_size_m = 1000, fun = "mean", min_coverage = 0) {
  fun <- parse_agg_fun(fun)
  aoi_sf <- sf::st_as_sf(aoi)

  # Project AOI to UTM for metric hex sizing
  if (sf::st_is_longlat(aoi_sf)) {
    centroid <- sf::st_coordinates(sf::st_centroid(sf::st_union(aoi_sf)))
    utm_zone <- floor((centroid[1] + 180) / 6) + 1
    utm_crs <- sf::st_crs(paste0("+proj=utm +zone=", utm_zone,
      if (centroid[2] < 0) " +south" else "", " +datum=WGS84"))
    aoi_utm <- sf::st_transform(aoi_sf, utm_crs)
  } else {
    aoi_utm <- aoi_sf
  }

  # Create hex grid over AOI
  hex_grid <- sf::st_make_grid(aoi_utm, cellsize = hex_size_m, square = FALSE)
  hex_grid <- sf::st_sf(geometry = hex_grid)
  message(paste("  hex grid cells:", nrow(hex_grid)))
  hex_grid <- sf::st_intersection(hex_grid, sf::st_union(aoi_utm))
  # st_intersection can produce mixed geometries (lines/points at edges) — keep only polygons
  hex_grid <- hex_grid[sf::st_is(hex_grid, c("POLYGON", "MULTIPOLYGON")), ]
  message(paste("  hex after intersection:", nrow(hex_grid)))

  # Extract raster values per hex
  hex_wgs <- sf::st_transform(hex_grid, sf::st_crs(data))
  message(paste("  raster CRS:", sf::st_crs(data)$input))
  message(paste("  hex CRS:", sf::st_crs(hex_wgs)$input))
  message(paste("  raster ext:", paste(as.vector(ext(data)), collapse=", ")))
  message(paste("  hex bbox:", paste(round(sf::st_bbox(hex_wgs), 4), collapse=", ")))

  r <- if (inherits(data, "SpatRaster")) data else rast(data)
  vals <- exactextractr::exact_extract(r, hex_wgs, fun, progress = FALSE)
  message(paste("  extracted values: n=", length(vals), "NAs=", sum(is.na(vals)), "zeros=", sum(vals == 0, na.rm=T)))
  hex_wgs$value <- vals

  # Remove hexes with no data
  hex_wgs <- hex_wgs[!is.na(hex_wgs$value), ]
  if (min_coverage > 0) {
    cov_frac <- exactextractr::exact_extract(r, hex_wgs,
      function(values, cov) sum(cov[!is.na(values)]) / sum(cov), progress = FALSE)
    hex_wgs <- hex_wgs[cov_frac >= min_coverage, ]
    message(paste("  after coverage filter (>=", min_coverage, "):", nrow(hex_wgs), "hexes"))
  }
  message(paste("  after filter:", nrow(hex_wgs), "hexes"))

  if (nrow(hex_wgs) == 0) return(NULL)

  vect(hex_wgs)
}

# Count points per hex cell. Mirrors hexbin_aggregate's grid construction
# (UTM hex grid intersected with AOI) but joins points instead of extracting
# raster values. Returns SpatVector with `count` column; drops empty hexes.
points_hex_count <- function(points, aoi, hex_size_m = 1000) {
  pts_sf <- sf::st_as_sf(points)
  aoi_sf <- sf::st_as_sf(aoi)

  if (sf::st_is_longlat(aoi_sf)) {
    centroid <- sf::st_coordinates(sf::st_centroid(sf::st_union(aoi_sf)))
    utm_zone <- floor((centroid[1] + 180) / 6) + 1
    utm_crs <- sf::st_crs(paste0("+proj=utm +zone=", utm_zone,
      if (centroid[2] < 0) " +south" else "", " +datum=WGS84"))
    aoi_utm <- sf::st_transform(aoi_sf, utm_crs)
  } else {
    aoi_utm <- aoi_sf
  }

  hex_grid <- sf::st_make_grid(aoi_utm, cellsize = hex_size_m, square = FALSE)
  hex_grid <- sf::st_sf(geometry = hex_grid)
  hex_grid <- sf::st_intersection(hex_grid, sf::st_union(aoi_utm))
  hex_grid <- hex_grid[sf::st_is(hex_grid, c("POLYGON", "MULTIPOLYGON")), ]
  message(paste("  hex grid cells:", nrow(hex_grid)))

  pts_utm <- sf::st_transform(pts_sf, sf::st_crs(aoi_utm))
  joined <- sf::st_intersects(hex_grid, pts_utm)
  hex_grid$count <- lengths(joined)

  hex_grid <- hex_grid[hex_grid$count > 0, ]
  message(paste("  hexes with points:", nrow(hex_grid)))

  if (nrow(hex_grid) == 0) return(NULL)

  hex_wgs <- sf::st_transform(hex_grid, 4326)
  vect(hex_wgs)
}

build_aggregate_lookups <- function() {
  fun_lookup <- list(); mode_lookup <- list(); size_lookup <- list()
  cov_lookup <- list(); smoothing_lookup <- list()
  task_dirs <- list.dirs(here("tasks"), recursive = FALSE, full.names = FALSE)
  for (td in task_dirs) {
    yml <- here("tasks", td, "maps.yml")
    if (!file.exists(yml)) next
    task_maps <- yaml::read_yaml(yml)
    task_afun   <- task_maps$aggregate_fun %||% "mean"
    task_amode  <- task_maps$aggregate_mode
    task_asize  <- task_maps$aggregate_size
    task_acov   <- task_maps$min_coverage
    task_smooth <- task_maps$smoothing
    for (entry in task_maps$layers) {
      if (is.character(entry)) { lyr <- entry; ovr <- list() }
      else                     { lyr <- names(entry)[[1]]; ovr <- entry[[1]] }
      fun_lookup[[lyr]] <- ovr$aggregate_fun %||% task_afun
      amode      <- ovr$aggregate_mode %||% task_amode
      asize      <- ovr$aggregate_size %||% task_asize
      acov       <- ovr$min_coverage   %||% task_acov
      smooth_cfg <- ovr$smoothing      %||% task_smooth
      if (!is.null(amode))      mode_lookup[[lyr]]      <- amode
      if (!is.null(asize))      size_lookup[[lyr]]      <- asize
      if (!is.null(acov))       cov_lookup[[lyr]]       <- acov
      if (!is.null(smooth_cfg)) smoothing_lookup[[lyr]] <- smooth_cfg
    }
  }
  list(fun = fun_lookup, mode = mode_lookup, size = size_lookup,
       cov = cov_lookup, smoothing = smoothing_lookup)
}

# Smooth a raster per smooth_cfg (a list with $method, $window, $sigma) and
# build a corresponding ggplot. Returns list(smoothed = SpatRaster|NULL,
# plot = ggplot|NULL). No-op (both NULL) when smooth_cfg is NULL or data
# isn't a SpatRaster.
apply_smoothing <- function(data, yaml_key, smooth_cfg, zoom_adj = 0) {
  if (is.null(smooth_cfg)) return(list(smoothed = NULL, plot = NULL))
  if (!inherits(data, "SpatRaster")) {
    message(paste("  Smoothing skipped (non-raster):", yaml_key))
    return(list(smoothed = NULL, plot = NULL))
  }
  method <- smooth_cfg$method %||% "gaussian"
  message(paste("  Smoothing:", yaml_key, "|", method))
  smoothed <- tryCatch(
    smooth_raster(
      data, method = method,
      window = smooth_cfg$window %||% 3,
      sigma  = smooth_cfg$sigma  %||% 1),
    error = function(e) {
      message(paste("  Smooth error:", yaml_key, "-", e$message))
      NULL
    })
  if (is.null(smoothed)) return(list(smoothed = NULL, plot = NULL))
  smooth_plot_data <- vectorize_if_coarse(smoothed)
  plot <- if (nrow(smooth_plot_data) > 0) {
    plot_static_layer(
      data = smooth_plot_data, yaml_key = yaml_key,
      plot_aoi = TRUE, plot_wards = !is.null(wards), zoom_adj = zoom_adj)
  } else NULL
  if (!is.null(plot)) message(paste("Success:", yaml_key, "(smooth)"))
  list(smoothed = smoothed, plot = plot)
}

# Aggregate a layer to hex polygons and return a ggplot. Handles both
# SpatRaster (run_aggregate) and SpatVector points (points_hex_count).
# Writes {yaml_key}_hex.gpkg. When the aggregated values are counts (sum/count
# for raster, always for points), overrides the layer's factor/breaks/labels
# with a sequential gradient since the original styling no longer applies.
aggregate_hex <- function(data, data_smoothed, yaml_key, layer_agg_mode,
                          layer_agg_size, layer_min_cov, afun, zoom_adj = 0) {
  is_raster <- inherits(data, "SpatRaster")
  is_points <- inherits(data, "SpatVector") && terra::geomtype(data) == "points"
  if (!(is_raster || (is_points && layer_agg_mode == "hexbin"))) return(NULL)

  gpkg_path <- file.path(spatial_dir, paste0(yaml_key, "_hex.gpkg"))

  if (is_raster) {
    message(paste("  Hexbin:", yaml_key, "| mode:", layer_agg_mode, "| size:", layer_agg_size))
    hex_input <- if (!is.null(data_smoothed)) data_smoothed else data
    hex_data <- tryCatch(
      run_aggregate(hex_input, aoi, layer_agg_mode, layer_agg_size, afun, gpkg_path,
                    min_coverage = layer_min_cov),
      error = function(e) { message(paste("  Hex error:", e$message)); NULL })
  } else {
    message(paste("  Points hex:", yaml_key, "| size:", layer_agg_size))
    hex_data <- tryCatch(
      points_hex_count(data, aoi, hex_size_m = layer_agg_size),
      error = function(e) { message(paste("  Points hex error:", e$message)); NULL })
    if (!is.null(hex_data)) writeVector(hex_data, gpkg_path, overwrite = TRUE)
  }
  if (is.null(hex_data) || nrow(hex_data) == 0) return(NULL)

  # Hex cell area for the subtitle.
  # hexbin: cellsize is flat-to-flat d, so area = (sqrt(3)/2) * d^2
  # resample: square cell of side d, so area = d^2
  # h3:      read area directly from the geometry (varies by resolution)
  hex_label <- if (layer_agg_mode == "hexbin") {
    paste0(signif((sqrt(3) / 2) * (layer_agg_size / 1000)^2, 2), " km²")
  } else if (layer_agg_mode == "resample") {
    paste0(signif((layer_agg_size / 1000)^2, 2), " km²")
  } else if (layer_agg_mode == "h3") {
    paste0(signif(mean(terra::expanse(hex_data, unit = "km"), na.rm = TRUE), 2), " km²")
  } else {
    paste0(layer_agg_size, " m")
  }
  yaml_sub <- layer_params[[yaml_key]]$subtitle
  bin_note <- paste0(hex_label, " hexbins")
  hex_subtitle <- if (!is.null(yaml_sub) && nzchar(yaml_sub)) {
    paste0(yaml_sub, " (", bin_note, ")")
  } else if (is_points) {
    paste0("Per ", hex_label, " hexbin")
  } else {
    paste0(afun, " per ", hex_label, " hex")
  }

  hex_extra <- list()
  if (is_points || afun %in% c("sum", "count")) {
    base_cols <- unlist(layer_params[[yaml_key]]$palette)
    base_color <- if (length(base_cols) > 1) "#009E73" else base_cols[[1]]
    light_end <- {
      m <- grDevices::col2rgb(base_color) / 255 * 0.35 + 0.65
      grDevices::rgb(m[1, 1], m[2, 1], m[3, 1])
    }
    hex_extra <- list(
      factor = FALSE, breaks = NULL, labels = NULL,
      palette = c(light_end, base_color),
      bins = 4, binning_method = "interval")
    if (is_points) hex_extra$data_variable <- "count"
  }

  do.call(plot_static_layer, c(
    list(data = hex_data, yaml_key = yaml_key,
         subtitle = hex_subtitle,
         plot_aoi = TRUE, plot_wards = !is.null(wards), zoom_adj = zoom_adj),
    hex_extra))
}

h3_aggregate <- function(data, aoi, fun = "mean") {
  fun <- parse_agg_fun(fun)
  aoi_sf <- sf::st_as_sf(aoi)

  # Auto-detect H3 resolution from AOI area
  aoi_area_km2 <- as.numeric(sf::st_area(sf::st_union(aoi_sf))) / 1e6
  # Target ~3000 hexes, find res where hex area ≈ aoi_area / 3000
  target_hex_area_km2 <- aoi_area_km2 / 3000
  h3_areas <- c(4250546, 607221, 86745, 12393, 1770, 252, 36, 5.16, 0.74, 0.11)  # km² per res 0-9
  res <- which.min(abs(h3_areas - target_hex_area_km2)) - 1  # 0-indexed
  res <- max(3, min(res, 9))  # clamp to 3-9
  message(glue("H3: using resolution {res} (~{round(h3_areas[res + 1])} km² per hex) for {round(aoi_area_km2)} km² AOI"))

  # Get H3 cell indices covering the AOI
  aoi_wgs <- sf::st_transform(aoi_sf, 4326)
  h3_cells <- h3o::polygon_to_cells(sf::st_union(aoi_wgs), res = res)
  hex_polys <- h3o::cell_to_polygon(h3_cells)
  hex_sf <- sf::st_sf(h3_index = h3_cells, geometry = hex_polys, crs = 4326)

  # Extract raster values per hex
  hex_sf$value <- exactextractr::exact_extract(rast(data), hex_sf, fun)

  # Remove empty hexes
  hex_sf <- hex_sf[!is.na(hex_sf$value) & hex_sf$value != 0, ]

  if (nrow(hex_sf) == 0) return(NULL)

  vect(hex_sf)
}
