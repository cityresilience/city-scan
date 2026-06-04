USE_GCS <<-TRUE # Use GCS if available
source(here("core/R/setup.R"))

# Output directory
processed_dir <- file.path(tabular_dir, "processed")


calculate_flood_by_prob <- function(flood_tif, wsf_tif, output_file = NULL) {

  # Read rasters, crop to AOI, and project both to UTM for area calculation
  flood_r <- rast(flood_tif)
  wsf_r <- rast(wsf_tif)
  flood_r <- crop(flood_r, aoi, mask = TRUE)
  wsf_r <- crop(wsf_r, aoi, mask = TRUE)
  utm_crs <- paste0("+proj=utm +zone=", floor((mean(ext(wsf_r)[1:2]) + 180) / 6) + 1, " +datum=WGS84")
  flood_r <- project(flood_r, utm_crs, method = "near")
  wsf_r <- project(wsf_r, flood_r, method = "near")

  flood_vals <- values(flood_r)[, 1]
  wsf_vals <- values(wsf_r)[, 1]

  # Pixel area in sq km (UTM res is in meters)
  pixel_area_sqkm <- prod(res(flood_r)) / 1e6


  # Probability bins (matching layers.yml labels)
  bins <- list(
    `0.1-1%` = list(min = 0.1, max = 1),
    `1-10%` = list(min = 1, max = 10),
    `>10%` = list(min = 10, max = Inf)
  )

  # Calculate for each year — auto-detect range from WSF values
  wsf_max <- max(wsf_vals, na.rm = TRUE)
  years <- 1985:floor(wsf_max)
  results <- list()

  for (yr in years) {
    # Pixels built by this year
    built_mask <- wsf_vals <= yr & !is.na(wsf_vals)

    # Count exposed area in each probability bin
    row_data <- list(year = yr - 1984, yearName = yr)

    for (bin_name in names(bins)) {
      bin <- bins[[bin_name]]
      if (is.infinite(bin$max)) {
        exposed_mask <- built_mask & flood_vals >= bin$min & !is.na(flood_vals)
      } else {
        exposed_mask <- built_mask & flood_vals >= bin$min & flood_vals < bin$max & !is.na(flood_vals)
      }
      exposed_sqkm <- sum(exposed_mask, na.rm = TRUE) * pixel_area_sqkm
      row_data[[bin_name]] <- round(exposed_sqkm, 2)
    }

    # Also calculate total
    total_exposed_mask <- built_mask & flood_vals >= 0.1 & !is.na(flood_vals)
    row_data[["total"]] <- round(sum(total_exposed_mask, na.rm = TRUE) * pixel_area_sqkm, 2)

    results[[length(results) + 1]] <- row_data
  }

  result_df <- bind_rows(results)

  if (!is.null(output_file)) {
    write_csv(result_df, output_file)
    message("Saved to: ", output_file)
  }

  return(result_df)
}

# Simple total exposed area per year (no probability bins)
calculate_flood_total <- function(flood_tif, wsf_tif, output_file = NULL) {
  flood_r <- rast(flood_tif)
  wsf_r <- rast(wsf_tif)

  # Crop to AOI
  flood_r <- crop(flood_r, aoi, mask = TRUE)
  wsf_r <- crop(wsf_r, aoi, mask = TRUE)

  # Project both to UTM for simple area calculation
  utm_crs <- paste0("+proj=utm +zone=", floor((mean(ext(wsf_r)[1:2]) + 180) / 6) + 1, " +datum=WGS84")
  flood_r <- project(flood_r, utm_crs, method = "near")
  wsf_r <- project(wsf_r, flood_r, method = "near")

  flood_vals <- values(flood_r)[, 1]
  wsf_vals <- values(wsf_r)[, 1]

  # Pixel area in sq km (UTM res is in meters)
  pixel_area_sqkm <- prod(res(flood_r)) / 1e6

  wsf_max <- max(wsf_vals, na.rm = TRUE)
  years <- 1985:floor(wsf_max)
  results <- list()

  for (yr in years) {
    built_mask <- wsf_vals <= yr & !is.na(wsf_vals)
    total_built_sqkm <- sum(built_mask, na.rm = TRUE) * pixel_area_sqkm
    exposed_mask <- built_mask & flood_vals > 0 & !is.na(flood_vals)
    exposed_sqkm <- sum(exposed_mask, na.rm = TRUE) * pixel_area_sqkm

    results[[length(results) + 1]] <- list(
      Year = yr,
      uba_km2 = round(total_built_sqkm, 2),
      uba_km2_exposed = round(exposed_sqkm, 2),
      percent_uba_exposed = scales::percent(exposed_sqkm / total_built_sqkm, accuracy = 0.01)
    )
  }

  result_df <- bind_rows(results)

  if (!is.null(output_file)) {
    write_csv(result_df, output_file)
    message("Saved to: ", output_file)
  }

  return(result_df)
}

# Run for each flood type
run_all <- function() {
  
  # Find WSF TIF — prefer harmonized, fall back to evolution
  wsf_tif <- list.files(spatial_dir, pattern = "wsf_harmonized\\.tif$", full.names = TRUE)[1]
  if (is.null(wsf_tif) || length(wsf_tif) == 0) {
    wsf_tif <- list.files(spatial_dir, pattern = "wsf.*evolution.*\\.tif$", full.names = TRUE)[1]
  }
  if (is.null(wsf_tif) || length(wsf_tif) == 0) {
    wsf_tif <- list.files(spatial_dir, pattern = "wsf.*\\.tif$", full.names = TRUE)[1]
  }

  if (is.null(wsf_tif) || length(wsf_tif) == 0) {
    stop("WSF TIF not found")
  }
  message("Using WSF: ", wsf_tif)

  flood_types <- list(
    pluvial = list(pattern = "pluvial_2020\\.tif$", output = "pu_prob.csv"),
    fluvial = list(pattern = "fluvial_2020\\.tif$", output = "fu_prob.csv"),
    coastal = list(pattern = "coastal_2020\\.tif$", output = "cu_prob.csv")
    # combined = list(pattern = "combined.*2020\\.tif$|comb.*2020\\.tif$", output = "comb_prob.csv")
  )

  for (ft_name in names(flood_types)) {
    ft <- flood_types[[ft_name]]
    flood_tif <- list.files(spatial_dir, pattern = ft$pattern, full.names = TRUE, ignore.case = TRUE)[1]

    if (!is.null(flood_tif) && length(flood_tif) > 0 && file.exists(flood_tif)) {
      message("\n=== Processing ", ft_name, " ===")
      message("Flood TIF: ", flood_tif)

      tryCatch({
        calculate_flood_by_prob(
          flood_tif = flood_tif,
          wsf_tif = wsf_tif,
          output_file = file.path(processed_dir, ft$output)
        )
      }, error = function(e) {
        message("Error processing ", ft_name, ": ", e$message)
      })
    } else {
      message("Skipping ", ft_name, " - TIF not found")
    }
  }

  # Also calculate total exposed (no probability bins) for each flood type
  flood_types_total <- list(
    fluvial = list(pattern = "fluvial_2020\\.tif$", output = "fu_total.csv"),
    pluvial = list(pattern = "pluvial_2020\\.tif$", output = "pu_total.csv"),
    coastal = list(pattern = "coastal_2020\\.tif$", output = "cu_total.csv")
  )

  for (ft_name in names(flood_types_total)) {
    ft <- flood_types_total[[ft_name]]
    flood_tif <- list.files(spatial_dir, pattern = ft$pattern, full.names = TRUE, ignore.case = TRUE)[1]

    if (!is.null(flood_tif) && length(flood_tif) > 0 && file.exists(flood_tif)) {
      message("\n=== Processing ", ft_name, " (total) ===")
      tryCatch({
        calculate_flood_total(
          flood_tif = flood_tif,
          wsf_tif = wsf_tif,
          output_file = file.path(processed_dir, ft$output)
        )
      }, error = function(e) {
        message("Error processing ", ft_name, " total: ", e$message)
      })
    }
  }
}

# Run
run_all()
