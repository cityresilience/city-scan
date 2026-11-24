# WorldPop analysis: city's own population data only

if (!exists("aoi")) source(here::here("core/R/setup.R"))

message("\n=== WorldPop analysis ===")

# Population density distribution (ridge plot data)
tryCatch({
  pop_file <- list.files(spatial_dir, pattern = "_population\\.tif$", full.names = TRUE) %>%
    str_subset("dense", negate = TRUE)
  wpop_df <- rast(pop_file[1]) %>%
    as_tibble() %>%
    rename(pop = 1) %>%
    filter(!is.na(pop), pop > 0)
  write_csv(wpop_df, file.path(tabular_dir, paste0(city_string, "_pop_density_pixels.csv")))
  message("Saved: _pop_density_pixels.csv")
}, error = function(e) message("Population raster not available for ridge plot: ", e$message))

message("=== WorldPop analysis complete ===\n")
