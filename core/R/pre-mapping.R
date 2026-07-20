# pre-mapping.R
message('\nPre-Mapping starting... might take while')

# Combine infrastructure base points
combine_infrastructure_points <- function() {
  health_points <- fuzzy_read(spatial_dir, "osm_health(?=.shp$|.gpkg$|$)") %>% mutate(Feature = "Hospital or clinic") %>% tryCatch(error = \(e) {return(NULL)})
  school_points <- fuzzy_read(spatial_dir, "osm_schools(?=.shp$|.gpkg$|$)") %>% mutate(Feature = "School") %>% tryCatch(error = \(e) {return(NULL)})
  fire_points <- fuzzy_read(spatial_dir, "osm_fire(?=.shp$|.gpkg$|$)") %>% mutate(Feature = "Fire station") %>% tryCatch(error = \(e) {return(NULL)})
  police_points <- fuzzy_read(spatial_dir, "osm_police(?=.shp$|.gpkg$|$)") %>% mutate(Feature = "Police station") %>% tryCatch(error = \(e) {return(NULL)})
  # Convert to centroids before rbind (OSM may return mixed point/polygon geometries)
  to_points <- \(x) if (!is.null(x) && inherits(x, "SpatVector")) centroids(x) else x
  rbind_if_non_null <- \(...) Reduce(rbind, unlist(list(...)))
  infrastructure_points <- rbind_if_non_null(to_points(health_points), to_points(school_points), to_points(fire_points), to_points(police_points))
  if (!is.null(infrastructure_points)) {
    infrastructure_points <- crop(infrastructure_points, aoi)
    writeVector(select(infrastructure_points, !contains("fid")), filename = file.path(spatial_dir, "infrastructure.gpkg"), overwrite = T)
  }
}

message("Combining infrastructure points...")
if (!file.exists(file.path(spatial_dir, "infrastructure.gpkg"))) {
  combine_infrastructure_points()
} else {
  message("infrastructure.gpkg already exists, skipping...")
}

# Road network centrality
assign_road_types <- function() {
  roads <- fuzzy_read(spatial_dir, "centralities\\.gpkg$", layer = "edges")
  if (inherits(roads, "SpatVector")) {
    roads$primary <- roads$highway %in% c("motorway", "trunk", "primary")
    roads$road_type <- ifelse(roads$primary, "Primary", "Secondary")
    roads$edge_centrality <- roads$edge_centrality * 100
    roads <- roads[, c("edge_centrality", "road_type")]
    roads <- roads[order(roads$edge_centrality), ]
    writeVector(roads, filename = file.path(spatial_dir, "edges-edit.gpkg"), overwrite = T)
  }
}
message("Assigning road types...")
if (!file.exists(file.path(spatial_dir, "edges-edit.gpkg"))) {
  assign_road_types()
} else {
  message("edges-edit.gpkg already exists, skipping...")
}

# Isochrones arrive as overlapping polygons; this function erases the overlaps.
# It is more robust than the combine_*_zones functions below, but designed for
# isochrones built by Daniel for the Philippines and does not match the backend
# output
erase_isochrone_overlaps <- function(x, layer_key = NULL) {
  zones <- fuzzy_read(spatial_dir, paste0(x, "_isochrone"))
  if (!"distance" %in% names(zones)) return(NULL)
  if (is.null(layer_key)) layer_key <- paste0(x, "_zones")
  layer_distances <- layer_params[[layer_key]]$breaks
  # browser()
  zones <- filter(zones, distance %in% layer_distances)
  if (nrow(zones) == 0) {
    warning(paste("No zones for", x, "of distances specified in layers.yml"))
    return(NULL)
  }
  # If multiple distances have the same zone, the erase output gets inverted.
  # We remove the duplicate zones that have the longer distance
  zones <- zones %>% arrange(distance) %>%
    distinct(geometry, .keep_all = T) %>%
    arrange(desc(distance))
  if (any(!is.valid(zones))) zones <- makeValid(zones)
  # Using the sequential version of erase often caused geometries with no attribute data
  zones <- seq_along(zones) %>%
    map(\(i) {
      if (nrow(zones[i + 1]) == 0) return(zones[i,])
      erase(zones[i,], zones[i+1,])
    }) %>% reduce(rbind)
  writeVector(zones, filename = file.path(spatial_dir, paste0(x, "-journeys.gpkg")), overwrite = T)
}
# ******** flag above for further questions. ********

# Combine school zones
combine_school_zones <- function() {
  schools_800 <- fuzzy_read(spatial_dir, "schools_800m(?=.shp$|.gpkg$|$)", FUN = vect) %>% tryCatch(error = \(e) {return(NULL)})
  schools_1600 <- fuzzy_read(spatial_dir, "schools_1600m(?=.shp$|.gpkg$|$)", FUN = vect) %>% tryCatch(error = \(e) {return(NULL)})
  schools_2400 <- fuzzy_read(spatial_dir, "schools_2400m(?=.shp$|.gpkg$|$)", FUN = vect) %>% tryCatch(error = \(e) {return(NULL)})
  schools_2400_only <- if (inherits(schools_2400, "SpatVector") & inherits(schools_1600, "SpatVector")) erase(schools_2400, schools_1600) else NULL
  schools_1600_only <- if (inherits(schools_1600, "SpatVector") & inherits(schools_800, "SpatVector")) erase(schools_1600, schools_800) else NULL
  school_layers <- c(schools_800, schools_1600_only, schools_2400_only)
  if (!is.na(school_layers)) {
    school_zones <- reduce(school_layers, rbind) %>%
      select(-level_1, -nodez) %>%
      select(!contains("fid"))
    writeVector(school_zones, filename = file.path(spatial_dir, "school-journeys.gpkg"), overwrite = T)
  }
}
message("Combining school zones...")
if (!file.exists(file.path(spatial_dir, "school-journeys.gpkg"))) {
  # Try new format (Python isochrone) first, fall back to old format
  if (length(list.files(spatial_dir, pattern = "schools_isochrone")) > 0) {
    erase_isochrone_overlaps("schools", "school_zones")
  } else {
    combine_school_zones()
  }
} else {
  message("school-journeys.gpkg already exists, skipping...")
}

rename_school_points <- function() {
  school_points <- fuzzy_read(spatial_dir, "schools(?=.shp$|.gpkg$|$)", FUN = vect)
  if (inherits(school_points, "SpatVector")) {
    school_points <- centroids(school_points)
    school_points <- crop(school_points, aoi)
    school_points <- school_points %>%
    mutate(Feature = "School") %>%
    select(!contains("fid"))
  writeVector(school_points, filename = file.path(spatial_dir, "school-points.gpkg"), overwrite = T)
  }
}
message("Renaming school points...")
if (!file.exists(file.path(spatial_dir, "school-points.gpkg"))) {
  rename_school_points()
} else {
  message("school-points.gpkg already exists, skipping...")
}

combine_health_zones <- function() {
  health_1000 <- fuzzy_read(spatial_dir, "health_1000m(?=.shp$|.gpkg$|$)", FUN = vect) %>% tryCatch(error = \(e) {return(NULL)})
  health_2000 <- fuzzy_read(spatial_dir, "health_2000m(?=.shp$|.gpkg$|$)", FUN = vect) %>% tryCatch(error = \(e) {return(NULL)})
  health_3000 <- fuzzy_read(spatial_dir, "health_3000m(?=.shp$|.gpkg$|$)", FUN = vect) %>% tryCatch(error = \(e) {return(NULL)})
  health_3000_only <- if (inherits(health_3000, "SpatVector") & inherits(health_2000, "SpatVector")) erase(health_3000, health_2000) else NULL
  health_2000_only <- if (inherits(health_2000, "SpatVector") & inherits(health_1000, "SpatVector")) erase(health_2000, health_1000) else NULL
  health_layers <- c(health_1000, health_2000_only, health_3000_only)
  if (!is.na(health_layers)) {
    health_zones <- reduce(health_layers, rbind) %>%
      select(-level_1, -nodez) %>%
      select(!contains("fid"))
    writeVector(health_zones, filename = file.path(spatial_dir, "health-journeys.gpkg"), overwrite = T)
  }
}
message("Combining health zones...")
if (!file.exists(file.path(spatial_dir, "health-journeys.gpkg"))) {
  if (length(list.files(spatial_dir, pattern = "health_isochrone")) > 0) {
    erase_isochrone_overlaps("health", "health_zones")
  } else {
    combine_health_zones()
  }
} else {
  message("health-journeys.gpkg already exists, skipping...")
}

rename_health_points <- function() {
  health_points <- fuzzy_read(spatial_dir, "health(?=.shp$|.gpkg$|$)", FUN = vect)
  if (inherits(health_points, "SpatVector")) {
    health_points <- centroids(health_points)
    health_points <- crop(health_points, aoi)
    health_points <- health_points %>%
    mutate(Feature = "Health facility") %>%
    select(!contains("fid"))
  writeVector(health_points, filename = file.path(spatial_dir, "health-points.gpkg"), overwrite = T)
  }
}
message("Renaming health points...")
if (!file.exists(file.path(spatial_dir, "health-points.gpkg"))) {
  rename_health_points()
} else {
  message("health-points.gpkg already exists, skipping...")
}

message("Processing WSF data...")
if (!file.exists(file.path(spatial_dir, "wsf-edit.tif"))) {
  wsf <- fuzzy_read(spatial_dir, "wsf_evolution.tif$")
  if (inherits(wsf, "SpatRaster")) {
    # classify 0 → NA, write directly to disk (avoids loading full raster into RAM)
    out_path <- file.path(spatial_dir, "wsf-edit.tif")
    classify(wsf, cbind(0, NA), filename = out_path, overwrite = TRUE, NAflag = NA)
  }
} else {
  message("wsf-edit.tif already exists, skipping...")
}

if (!file.exists(file.path(spatial_dir, "wsf-tracker-edit.tif"))) {
  wsf_tracker <- fuzzy_read(spatial_dir, "wsf_tracker(?!.*utm).tif$")
  if (inherits(wsf_tracker, "SpatRaster")) {
    # New Python task already stores year values; old backend stored raw era values needing 2016 + val/2
    # Use global() instead of values() to avoid loading entire raster into RAM
    if (global(wsf_tracker, "max", na.rm = TRUE)[1,1] < 100) {
      out_path <- file.path(spatial_dir, "wsf-tracker-edit.tif")
      app(wsf_tracker, \(x) 2016 + x/2, filename = out_path, overwrite = TRUE)
    } else {
      writeRaster(wsf_tracker, file.path(spatial_dir, "wsf-tracker-edit.tif"), overwrite = TRUE)
    }
  }
} else {
  message("wsf-tracker-edit.tif already exists, skipping...")
}

message("Processing burn data...")
if (!file.exists(file.path(spatial_dir, "burn-edit.tif"))) {
  burn <- fuzzy_read(spatial_dir, "lc_burn.tif$")
  if (inherits(burn, "SpatRaster")) {
    # Set negative values to NA, write directly to disk
    classify(burn, cbind(-Inf, 0, NA), right = FALSE,
             filename = file.path(spatial_dir, "burn-edit.tif"), overwrite = TRUE)
  }
} else {
  message("burn-edit.tif already exists, skipping...")
}

if (!file.exists(file.path(spatial_dir, "intersection-density.tif"))) {
  intersection_nodes <- fuzzy_read(spatial_dir, "nodes_and_edges(?=.shp$|.gpkg$|$)", layer = "nodes")
  if (inherits(intersection_nodes, "SpatVector")) {
    intersection_density <- density_rast(intersection_nodes, n = 200)
    writeRaster(intersection_density, file.path(spatial_dir, "intersection-density.tif"), overwrite = T)
  }
} else {
  message("intersection-density.tif already exists, skipping...")
}

if (!file.exists(file.path(spatial_dir, "burnt-area-density.tif"))) {
  historical_fire_data <- fuzzy_read(spatial_dir, "globfire")
  if (inherits(historical_fire_data, c("SpatVector", "SpatRaster")) && length(historical_fire_data) > 0) {
    historical_fire_density <- density_rast(historical_fire_data, n = 200, aoi = aoi)
    writeRaster(historical_fire_density, file.path(spatial_dir, "burnt-area-density.tif"), overwrite = T)
  }
} else {
  message("burnt-area-density.tif already exists, skipping...")
}

adjust_deforstation_years <- function() {
  deforest <- fuzzy_read(spatial_dir, "deforestation.tif$", rast)
  if (inherits(deforest, c("SpatRaster"))) {
    # Use global() to check range without loading all values into RAM
    max_val <- global(deforest, "max", na.rm = TRUE)[1,1]
    out_path <- file.path(spatial_dir, "deforestation-edit.tif")
    if (!is.na(max_val) && max_val > 0 && max_val < 100) {
      # Preserve integer year semantics — without wopt datatype override, terra::app
      # writes FLT4S and the legend formats years as "2,020" via ggplot's default
      # thousands separator.
      app(deforest, \(x) x + 2000, filename = out_path, overwrite = TRUE,
          wopt = list(datatype = "INT2U"))
    } else {
      writeRaster(deforest, out_path, overwrite = TRUE, datatype = "INT2U")
    }
  }
}
adjust_deforstation_years()


# Pop edit — commented out: GHS task creates ghs_pop_E2025.tif, not pop_2025.tif
# TODO: update fuzzy pattern if population map is needed
# if (!file.exists(file.path(spatial_dir, "pop_2025-edit.tif"))) {
#   pop_2025 <- fuzzy_read(spatial_dir, "pop_2025\\.tif")
#   if (inherits(pop_2025, "SpatRaster")) {
#     values(pop_2025)[values(pop_2025) == 0] <- NA
#     NAflag(pop_2025) <- NA
#     writeRaster(pop_2025, file.path(spatial_dir, "pop_2025-edit.tif"), overwrite = T)
#   }
# } else {
#   message("pop_2025-edit.tif already exists, skipping...")
# }


# built over time edit 
if (!file.exists(file.path(spatial_dir, "built_2030-edit.tif"))) {
  built_2030 <- fuzzy_read(spatial_dir, "built_over_time\\.tif$")
  if (inherits(built_2030, "SpatRaster")) {
    built_2030 <- ifel(built_2030 == 2030, 2030, NA)
    NAflag(built_2030) <- NA
    writeRaster(built_2030, file.path(spatial_dir, "built_2030-edit.tif"), overwrite = T)
  }

} else {
  message("built_2030-edit.tif already exists, skipping...")
}


if (!file.exists(file.path(spatial_dir, "vegetation-edit.tif"))) {
  ndvi <- fuzzy_read(spatial_dir, "ndvi.seaso")
  if (inherits(ndvi, "SpatRaster")) {
    if (!"NDVI" %in% names(ndvi)) names(ndvi) <- "NDVI"
    # Classify: values < 0.18 → NA, write directly to disk
    classify(ndvi, cbind(-Inf, 0.18, NA), right = FALSE,
             filename = file.path(spatial_dir, "vegetation-edit.tif"), overwrite = TRUE)
    # Binary: >= 0.18 → 1, < 0.18 → NA
    classify(ndvi, matrix(c(-Inf, 0.18, NA, 0.18, Inf, 1), ncol = 3, byrow = TRUE),
             right = FALSE, filename = file.path(spatial_dir, "vegetation-binary-edit.tif"), overwrite = TRUE)
  }
} else {
  message("vegetation-edit.tif already exists, skipping...")
}

# Landslide edit (set 0 to NA)
if (!file.exists(file.path(spatial_dir, "landslide-edit.tif"))) {
  landslide <- fuzzy_read(spatial_dir, "landslide.*\\.tif$")
  if (inherits(landslide, "SpatRaster")) {
    NAflag(landslide) <- 0
    writeRaster(landslide, file.path(spatial_dir, "landslide-edit.tif"), overwrite = T)
  }
} else {
  message("landslide-edit.tif already exists, skipping...")
}

# Liquefaction edit (set 0 to NA)
if (!file.exists(file.path(spatial_dir, "liquefaction-edit.tif"))) {
  liquefaction <- fuzzy_read(spatial_dir, "liquefaction\\.tif$")
  if (inherits(liquefaction, "SpatRaster")) {
    NAflag(liquefaction) <- 0
    writeRaster(liquefaction, file.path(spatial_dir, "liquefaction-edit.tif"), overwrite = T)
  }
} else {
  message("liquefaction-edit.tif already exists, skipping...")
}


# Built-up area extent (2025) for overlay on accessibility/hazard maps
message("Processing built-up area extent for overlay...")
builtup_extent_2025 <- tryCatch({
  wsf_harm <- fuzzy_read(spatial_dir, "wsf_harmonized\\.tif$")
  if (!inherits(wsf_harm, "SpatRaster")) {
    wsf_harm <- fuzzy_read(spatial_dir, "wsf_evolution\\.tif$")
  }
  if (inherits(wsf_harm, "SpatRaster")) {
    wsf_harm <- crop(wsf_harm, aoi, mask = TRUE)
    # Classify: anything <= 2025 = 1 (built), everything else = NA
    built_binary <- classify(wsf_harm, cbind(c(-Inf, 2025.5), c(2025.5, Inf), c(1, NA)),
                             include.lowest = TRUE)
    built_binary <- aggregate_if_too_fine(built_binary)
    built_poly <- as.polygons(built_binary)
    message("Built-up extent 2025 polygon created")
    built_poly
  } else {
    message("No WSF raster found for built-up extent")
    NULL
  }
}, error = function(e) {
  message("Built-up extent processing failed: ", e$message)
  NULL
})

# Temporary fix as LST isn't properly NA flagged in python output
summer_lst_file <- fuzzy_read(spatial_dir, "summer.*", paste)
if (!is.na(summer_lst_file)) {
  summer_lst <- rast(summer_lst_file)
  NAflag(summer_lst) <- 0
  writeRaster(summer_lst, file.path(spatial_dir, "summer_lst-edit.tif"), overwrite = TRUE)
}

## done
message("Pre-mapping processing complete.")
