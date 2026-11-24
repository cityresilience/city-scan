# Sectoral GDP Flood Exposure
# Reads: spatial/{city}_gdp_{sector}.tif (3 bands: 2010, 2015, 2020)
#        spatial/*_2020.tif (flood rasters)
# Writes: tabular/flood_gdp_sectoral.csv

if (!exists("aoi")) source(here::here("core/R/setup.R"))

message("\n=== Sectoral GDP Flood Exposure ===")

sectors <- c("agriculture", "industry", "service", "combined")
years <- c(2010, 2015, 2020)
percentile_threshold <- 0.60

flood_types <- list(
  fluvial  = "fluvial_2020\\.tif$",
  pluvial  = "pluvial_2020\\.tif$",
  coastal  = "coastal_2020\\.tif$"
)
flood_type_labels <- c(fluvial = "River", pluvial = "Rainwater", coastal = "Coastal")

results <- list()

for (sector in sectors) {
  gdp_tif <- list.files(spatial_dir, pattern = paste0("gdp_", sector, "\\.tif$"), full.names = TRUE)[1]
  if (is.na(gdp_tif) || !file.exists(gdp_tif)) {
    message("  ", sector, ": TIF not found, skipping")
    next
  }

  gdp_r <- rast(gdp_tif)
  message("  ", sector, ": ", nlyr(gdp_r), " bands")

  for (band_idx in seq_along(years)) {
    yr <- years[band_idx]
    gdp_band <- crop(gdp_r[[band_idx]], aoi, mask = TRUE)

    # Compute 60th percentile threshold
    gdp_vals <- values(gdp_band)[!is.na(values(gdp_band)) & values(gdp_band) > 0]
    if (length(gdp_vals) == 0) {
      message("    ", yr, ": no valid GDP values")
      next
    }
    threshold <- quantile(gdp_vals, percentile_threshold)
    high_gdp_mask <- gdp_band > threshold & !is.na(gdp_band)
    n_high <- sum(values(high_gdp_mask) == 1, na.rm = TRUE)

    for (ft_name in names(flood_types)) {
      flood_tif <- list.files(spatial_dir, pattern = flood_types[[ft_name]], full.names = TRUE, ignore.case = TRUE)[1]
      if (is.na(flood_tif) || !file.exists(flood_tif)) next

      tryCatch({
        flood_r <- rast(flood_tif)
        flood_max <- flood_r[[1]]
        flood_max <- crop(flood_max, aoi, mask = TRUE)

        # Resample high GDP mask to flood resolution
        high_gdp_resampled <- resample(high_gdp_mask, flood_max, method = "near")
        flood_mask <- flood_max > 0 & !is.na(flood_max)

        # High GDP pixels in flood zone
        n_high_flood <- sum(values(high_gdp_resampled) == 1 & values(flood_mask) == 1, na.rm = TRUE)
        n_high_total <- sum(values(high_gdp_resampled) == 1, na.rm = TRUE)
        pct <- if (n_high_total > 0) round(n_high_flood / n_high_total * 100, 2) else 0

        # Also compute total GDP exposed
        gdp_resampled <- resample(gdp_band, flood_max, method = "bilinear")
        total_gdp <- sum(values(gdp_resampled), na.rm = TRUE)
        exposed_gdp <- sum(values(gdp_resampled)[values(flood_mask) == 1], na.rm = TRUE)

        results[[length(results) + 1]] <- tibble(
          year = yr,
          sector = str_to_title(sector),
          flood_type = flood_type_labels[[ft_name]],
          total_gdp_M = round(total_gdp, 2),
          exposed_gdp_M = round(exposed_gdp, 2),
          pct_gdp_exposed = round(exposed_gdp / total_gdp * 100, 2),
          high_gdp_pixels = n_high_total,
          high_gdp_in_flood = n_high_flood,
          pct_high_gdp_in_flood = pct
        )
      }, error = function(e) message("    Error: ", sector, "/", yr, "/", ft_name, " - ", e$message))
    }

    # Combined = sum of individual flood types
    ft_results <- Filter(\(r) r$year == yr && r$sector == str_to_title(sector), results)
    if (length(ft_results) > 0) {
      ft_df <- bind_rows(ft_results)
      results[[length(results) + 1]] <- tibble(
        year = yr,
        sector = str_to_title(sector),
        flood_type = "Combined",
        total_gdp_M = ft_df$total_gdp_M[1],
        exposed_gdp_M = sum(ft_df$exposed_gdp_M),
        pct_gdp_exposed = round(sum(ft_df$exposed_gdp_M) / ft_df$total_gdp_M[1] * 100, 2),
        high_gdp_pixels = ft_df$high_gdp_pixels[1],
        high_gdp_in_flood = sum(ft_df$high_gdp_in_flood),
        pct_high_gdp_in_flood = round(sum(ft_df$high_gdp_in_flood) / ft_df$high_gdp_pixels[1] * 100, 2)
      )
    }
  }

  message("  ", sector, ": done")
}

if (length(results) > 0) {
  flood_gdp_sectoral <- bind_rows(results) %>% arrange(sector, year, flood_type)
  write_csv(flood_gdp_sectoral, file.path(tabular_dir, "flood_gdp_sectoral.csv"))
  message("Saved: ", file.path(tabular_dir, "flood_gdp_sectoral.csv"))
}
