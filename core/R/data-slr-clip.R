# Sea Level Rise data clipping script
# Clips Climate Central SLR VRT files to city AOI

# Requires: setup.R already sourced (aoi, city_string, spatial_dir, local_materials)
# When run standalone: source(here("core/R/setup.R")) first
if (!exists("aoi")) source(here("core/R/setup.R"))

# Path to SLR data
# TODO: add to GCS city-scan-global-data bucket and update global-data-paths.R
slr_dir <- file.path(local_materials, "SLR")

message("\n=== Clipping SLR data to AOI ===")

# Get AOI extent with small buffer
aoi_ext <- ext(aoi) + 0.01

# ============================================
# PART 1: Combine 1-10m into single raster
# ============================================
message("\nCreating combined 1-10m SLR layer...")

# Load and crop all meter layers
meter_layers <- list()
for (m in 1:10) {
  vrt_path <- file.path(slr_dir, paste0(m, "m.vrt"))
  if (file.exists(vrt_path)) {
    r <- crop(rast(vrt_path), aoi_ext)
    meter_layers[[m]] <- r
    message(paste("  Loaded:", m, "m"))
  }
}

# Align all rasters to the first one's grid using resample
if (length(meter_layers) > 1) {
  ref_rast <- meter_layers[[1]]
  for (i in 2:length(meter_layers)) {
    meter_layers[[i]] <- resample(meter_layers[[i]], ref_rast, method = "near")
  }
}

# Set flooded cells to meter value, non-flooded to NA
for (m in seq_along(meter_layers)) {
  meter_layers[[m]] <- ifel(meter_layers[[m]] == 1, m, NA)
}

# Stack and take minimum (lowest flood level for each cell)
if (length(meter_layers) > 0) {
  meter_stack <- rast(meter_layers)
  slr_combined <- min(meter_stack, na.rm = TRUE)

  # Save combined raster
  out_path <- file.path(spatial_dir, paste0(city_string, "_slr_1_10m.tif"))
  writeRaster(slr_combined, out_path, overwrite = TRUE)
  message(paste("  Saved combined layer:", basename(out_path)))
}

# ============================================
# PART 2: AR6 SSP scenarios - Combined by year
# ============================================
message("\nProcessing AR6 SSP scenarios (combined by year)...")

# Define all combinations
ssps <- c("ssp245", "ssp585")
percentiles <- c("50.0", "83.3")
return_levels <- c("", "_RL1", "_RL10")  # "" = high tide (no RL suffix)
years <- c(2020, 2050, 2100)

# Return level labels for output filenames
rl_labels <- c("hightide", "RL1", "RL10")

for (ssp in ssps) {
  for (pct_idx in seq_along(percentiles)) {
    pct <- percentiles[pct_idx]

    for (rl_idx in seq_along(return_levels)) {
      rl <- return_levels[rl_idx]
      rl_label <- rl_labels[rl_idx]

      message(paste("\n  Combining:", ssp, pct, "percentile,", rl_label))

      year_layers <- list()

      # First pass: load and crop all years
      for (yr in years) {
        # Build VRT filename
        vrt_name <- paste0("AR6_", ssp, "_mediumconfidence_", pct, "_", yr, rl, ".vrt")
        vrt_path <- file.path(slr_dir, vrt_name)

        if (!file.exists(vrt_path)) {
          warning(paste("    VRT not found:", vrt_name))
          next
        }

        message(paste("    Loading:", yr))
        r <- crop(rast(vrt_path), aoi_ext)
        year_layers[[as.character(yr)]] <- r
      }

      # Align all rasters to the first one's grid using resample
      if (length(year_layers) > 1) {
        ref_rast <- year_layers[[1]]
        for (i in 2:length(year_layers)) {
          year_layers[[i]] <- resample(year_layers[[i]], ref_rast, method = "near")
        }
      }

      # Set flooded cells to year value
      for (yr_name in names(year_layers)) {
        yr <- as.numeric(yr_name)
        year_layers[[yr_name]] <- ifel(year_layers[[yr_name]] == 1, yr, NA)
      }

      # Combine: take minimum year (earliest flood)
      if (length(year_layers) > 0) {
        year_stack <- rast(year_layers)
        combined <- min(year_stack, na.rm = TRUE)

        # Output filename: city_slr_ssp245_83.3_hightide.tif
        out_name <- paste0(city_string, "_slr_", ssp, "_", pct, "_", rl_label, ".tif")
        out_path <- file.path(spatial_dir, out_name)

        writeRaster(combined, out_path, overwrite = TRUE)
        message(paste("    Saved:", out_name))
      }
    }
  }
}

message("\n=== SLR clipping complete ===")
