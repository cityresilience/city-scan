# WSF Harmonization
# Combines WSF Evolution (1985-2015) with WSF Tracker (2016+)
# using morphological closing to bridge resolution differences.
#
# Run AFTER data-collection.R (needs wsf_tracker + wsf_evolution tifs)
# Requires: setup.R already sourced (aoi, city_string, spatial_dir, tabular_dir)
if (!exists("aoi")) source(here("core/R/setup.R"))

# Need stats_wsf_evolution from data-collection.R
if (!exists("stats_wsf_evolution")) source(here("core/R/data-collection.R"))

message("\n=== WSF Harmonization ===")

# Load WSF tracker
wsf_tracker_path <- list.files(spatial_dir, pattern = "wsf_tracker\\.tif$", full.names = TRUE)[1]
if (is.null(wsf_tracker_path) || length(wsf_tracker_path) == 0 || !file.exists(wsf_tracker_path)) {
  message("WSF Tracker not found, skipping harmonization.")
  return(invisible(NULL))
}

# Load WSF evolution
wsf_evo_path <- list.files(spatial_dir, pattern = "wsf_evolution\\.tif$", full.names = TRUE)[1]
if (is.null(wsf_evo_path) || length(wsf_evo_path) == 0 || !file.exists(wsf_evo_path)) {
  message("WSF Evolution not found, skipping harmonization.")
  return(invisible(NULL))
}

wsf_tracker <- rast(wsf_tracker_path)
wsf_evolution <- rast(wsf_evo_path)

# Ensure both are in EPSG:4326
if (crs(wsf_tracker, describe = TRUE)$code != "4326") wsf_tracker <- project(wsf_tracker, "EPSG:4326", method = "near")
if (crs(wsf_evolution, describe = TRUE)$code != "4326") wsf_evolution <- project(wsf_evolution, "EPSG:4326", method = "near")

# Floor tracker years (2016.5 → 2016)
wsf_tracker_floor <- floor(wsf_tracker$era)

# --- Morphological closing on tracker (per-year, 7x7 kernel) ---
message("Applying morphological closing to WSF Tracker...")
years <- unique(values(wsf_tracker_floor$era)) %>% na.omit()
k <- matrix(1, nrow = 7, ncol = 7)

wsf_tracker_closed <- wsf_tracker_floor$era

for (yr in years) {
  yr_mask <- wsf_tracker_floor$era == yr
  yr_mask[is.na(yr_mask)] <- FALSE

  yr_dilated <- focal(yr_mask, w = k, fun = "max", na.rm = TRUE)
  yr_closed <- focal(yr_dilated, w = k, fun = "min", na.rm = TRUE)

  fill_mask <- yr_closed == 1 & is.na(wsf_tracker_closed)
  wsf_tracker_closed[fill_mask] <- yr
}

# Downsample to evolution resolution
wsf_tracker_closed <- wsf_tracker_closed %>% resample(wsf_evolution, method = "near")

# --- Harmonize: evolution for pre-2016, tracker for 2016+ ---
message("Combining Evolution + Tracker...")

# Step 1: trim evolution to where tracker has 2016 data
wsf_2016_binary <- wsf_tracker_closed == 2016
wsf_2016_binary[is.na(wsf_2016_binary)] <- FALSE
evo_trimmed <- mask(wsf_evolution, wsf_2016_binary, maskvalues = FALSE)

# Step 2: tracker 2016 pixels not already in evolution
tracker_2016_only <- wsf_tracker_closed
tracker_2016_only[wsf_tracker_closed != 2016] <- NA
tracker_2016_only[!is.na(evo_trimmed)] <- NA

# Step 3: combine
wsf_harmonized <- cover(evo_trimmed, tracker_2016_only)
wsf_harmonized <- cover(wsf_harmonized, wsf_tracker_closed)  # add 2017+

# --- Save outputs ---
message("Saving harmonized WSF...")
# dir.create(file.path(tabular_dir, "processed"), showWarnings = FALSE)

# Raster
wsf_harmonized %>%
  writeRaster(filename = file.path(spatial_dir, paste0(city_string, "_wsf_harmonized.tif")), overwrite = TRUE)

# Stats CSV — ensure same CRS as AOI
aoi_crs <- crs(aoi)
if (crs(wsf_harmonized) != aoi_crs) wsf_harmonized <- project(wsf_harmonized, aoi_crs, method = "near")
if (crs(wsf_evolution) != aoi_crs) wsf_evolution <- project(wsf_evolution, aoi_crs, method = "near")
if (crs(wsf_tracker_closed) != aoi_crs) wsf_tracker_closed <- project(wsf_tracker_closed, aoi_crs, method = "near")
wsf_harmonized_stat <- wsf_harmonized %>% crop(aoi, mask = TRUE) %>% stats_wsf_evolution()
wsf_evolution_stat <- wsf_evolution %>% crop(aoi, mask = TRUE) %>% stats_wsf_evolution()
wsf_tracker_morphed_stats <- wsf_tracker_closed %>% crop(aoi, mask = TRUE) %>% stats_wsf_evolution()

wsf_combined_stats <- bind_rows(
  wsf_evolution_stat %>% mutate(source = "WSF Evolution"),
  wsf_harmonized_stat %>% filter(year <= 2015) %>% mutate(source = "WSF Evolution (masked)"),
  wsf_tracker_morphed_stats %>% mutate(source = "WSF Tracker")
) %>%
  arrange(source, year) %>%
  group_by(source) %>%
  mutate(growth_percentage = round((cumulative_sq_km - lag(cumulative_sq_km)) / lag(cumulative_sq_km) * 100, 3)) %>%
  ungroup() %>%
  write_csv(file.path(tabular_dir, "processed", paste0(city_string, "_wsf_harmonized.csv")))

message("WSF Harmonization complete.")
