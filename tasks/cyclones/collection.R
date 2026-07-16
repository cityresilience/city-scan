# Cyclones data collection
# Source: IBTrACS from GCS private bucket

if (!exists("aoi")) source(here::here("core/R/setup.R"))
aoi <- aoi %>% st_as_sf() %>% st_transform("EPSG:4326")

cyclone_archive_file <- "/vsigs/city-scan-global-public/cyclones/IBTrACS_since1980_list_v04r00_lines.fgb"

cyclones_near <- tryCatch({
  cyclones <- read_sf(cyclone_archive_file) %>%
    st_transform("EPSG:4326")
  cyclones_near_index <- st_is_within_distance(aoi, cyclones, as_units(250, "km"))
  cn <- cyclones[cyclones_near_index[[1]],]
  cn$distance_km <- drop_units(st_distance(st_centroid(aoi), cn)[1,])/1000
  cn %>% st_shift_longitude()
}, error = function(e) { message("Cyclone data not available: ", e$message); NULL })

if (!is.null(cyclones_near) && nrow(cyclones_near) > 0) {
  write_csv(st_drop_geometry(cyclones_near), file.path(tabular_dir, paste0(city_string, "_cyclones.csv")))
}
