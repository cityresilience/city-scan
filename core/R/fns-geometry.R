# =========================================================
# GEOM / RASTER HELPERS
# =========================================================

rast_as_vect <- function(x, digits = 8, ...) {
  if (class(x) == "SpatVector") return(x)
  if (is.character(x)) x <- rast(x, ...)
  out <- as.polygons(x, digits = digits)
  return(out)
}

# Build a kernel-density "heat map" raster from a SpatVector of points. Used by
# pre-mapping.R for road-intersection density and historical-fire density.
density_rast <- \(points, n = 100, aoi = NULL) {
  crs <- crs(points)
  data_extent <- ext(points)
  if (!is.null(aoi)) {
    data_extent <- terra::union(data_extent, ext(project(aoi, crs)))
  }
  density_extent <- ext(aspect_buffer(vect(data_extent, crs = crs), aspect_ratio = aspect_ratio))
  points_df <- as_tibble(mutate(points, x = geom(points, df = T)$x, y = geom(points, df = T)$y))
  density <-  MASS::kde2d(points_df$x, points_df$y, n = n, lims = as.vector(density_extent))
  dimnames(density$z) <- list(x = density$x, y = density$y)
  # Rotate density, because top left is lowest x and lowest y, instead of lowest x and highest y
  density$z <- rotate_ccw(density$z)
  rast(scales::rescale((density$z)), crs = crs, extent = density_extent)
}

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

center_max_circle <- \(x, simplify = T, tolerance = 0.0001) {
  if (simplify) s <- simplifyGeom(x, tolerance = tolerance) else s <- x
  p <- as.points(s)
  v <- voronoi(p)
  vp <- as.points(v)
  vp <- vp[is.related(vp, s, "within")]
  # Using vp[which.max(nearest(vp, p)$distance)] is 60x slower
  vppd <- distance(vp, p)

  center <- vp[which.max(apply(vppd, 1, min))]
  radius <- vppd[which.max(apply(vppd, 1, min))]
  return(list(center = center, radius = radius))
}

site_labels <- function(x, simplify = T, tolerance = 0.0001) {
  sites <- list()
  for (i in 1:nrow(x)) {
    sites[i] <- center_max_circle(x[i], simplify = simplify, tolerance = tolerance)["center"]
  }
  label_sites <- Reduce(rbind, unlist(sites))
  return(label_sites)
}
