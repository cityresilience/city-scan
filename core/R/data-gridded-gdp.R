# Gridded GDP — clip global rasters to AOI
# Source: Zenodo (Downscaled gridded GDP 1990-2022)
# Run AFTER setup.R
if (!exists("aoi")) source(here("core/R/setup.R"))

message("\n=== Gridded GDP ===")

gdp_dir <- file.path(local_materials, "Gridded_GDP_1990_2022")

# --- Total GDP (30 arc-sec, ~1km) ---
gdp_tot_out <- file.path(spatial_dir, paste0(city_string, "_gdp_total.tif"))
if (!file.exists(gdp_tot_out)) {
  message("Clipping total GDP...")
  gdp_tot <- rast(file.path(gdp_dir, "rast_gdpTot_1990_2020_30arcsec.tif"))
  gdp_tot <- crop(gdp_tot, aoi, mask = TRUE)
  gdp_tot <- gdp_tot / 1e6  # Convert to million USD
  writeRaster(gdp_tot, gdp_tot_out, overwrite = TRUE)
  message("Saved: ", gdp_tot_out)
} else {
  message("Total GDP already exists, skipping.")
}

# --- GDP per capita (5 arc-min, ~10km) ---
gdp_pc_out <- file.path(spatial_dir, paste0(city_string, "_gdp_per_capita.tif"))
if (!file.exists(gdp_pc_out)) {
  message("Clipping GDP per capita...")
  gdp_pc <- rast(file.path(gdp_dir, "rast_adm2_gdp_perCapita_1990_2022.tif"))
  gdp_pc <- crop(gdp_pc, aoi, mask = TRUE)
  writeRaster(gdp_pc, gdp_pc_out, overwrite = TRUE)
  message("Saved: ", gdp_pc_out)
} else {
  message("GDP per capita already exists, skipping.")
}

message("Gridded GDP complete.")
