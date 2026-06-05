# Fathom flooding multianalysis
# Equivalent of Caroline's clean.py — clean_flood()
# Reads raw backend CSVs, produces cleaned flood CSVs in tabular/
# Sources: tabular/flood_wsf.csv, tabular/wsf*.csv
#          tabular/flood_osm*.csv, tabular/flood_road*.csv, tabular/flood_pop*.csv

if (!exists("aoi")) source(here::here("core/R/setup.R"))

# Read WSF data (needed for flood exposure calculations)
# Prefer harmonized (filtered to "WSF Harmonized" source), fall back to evolution
wsf_harm_file <- str_subset(list.files(tabular_dir, full.names = T), "wsf_harmonized\\.csv$")
wsf_evo_file <- str_subset(list.files(tabular_dir, full.names = T), "wsf_evolution\\.csv$")

if (length(wsf_harm_file) > 0) {
  wsf_flood_base <- read_csv(wsf_harm_file[1], show_col_types = FALSE) %>%
    filter(source == "WSF Harmonized") %>%
    select(year, cumulative_sq_km)
} else if (length(wsf_evo_file) > 0) {
  wsf_flood_base <- read_csv(wsf_evo_file[1], col_types = "dd") %>%
    rename(year = 1, cumulative_sq_km = 2)
} else {
  wsf_flood_base <- NULL
}

# Read flood_wsf and join with wsf
wsf_flood <- tryCatch({
  if (is.null(wsf_flood_base)) stop("No WSF data")
  flood_file <- str_subset(list.files(tabular_dir, full.names = T), "flood_wsf.csv")
  inner_join(wsf_flood_base, read_csv(flood_file, show_col_types = FALSE), by = "year")
}, error = function(e) { message("wsf_flood not available: ", e$message); NULL })

# Flood OSM data
flood_osm <- tryCatch({
  flood_osm_file <- list.files(tabular_dir, full.names = T) %>% str_subset("flood_osm")
  if (length(flood_osm_file) != 1) stop("flood_osm file not found or ambiguous")
  read_csv(flood_osm_file, col_types = "fcfdddc") %>% data.frame()
}, error = function(e) { message("flood_osm not available: ", e$message); NULL })

# Flood Road data
flood_road <- tryCatch({
  flood_road_file <- list.files(tabular_dir, full.names = T) %>% str_subset("flood_road")
  if (length(flood_road_file) != 1) stop("flood_road file not found or ambiguous")
  read_csv(flood_road_file, col_types = "fdd") %>%
    mutate(type = forcats::fct_relabel(type, \(x) str_replace(x, "_2020", ""))) %>%
    data.frame()
}, error = function(e) { message("flood_road not available: ", e$message); NULL })

# Flood Population data
flood_pop <- tryCatch({
  flood_pop_file <- list.files(tabular_dir, full.names = T) %>% str_subset("flood_pop")
  if (length(flood_pop_file) != 1) stop("flood_pop file not found or ambiguous")
  read_csv(flood_pop_file, col_types = "fd") %>%
    mutate(type = forcats::fct_relabel(type, \(x) str_replace(x, "_2020", ""))) %>%
    data.frame()
}, error = function(e) { message("flood_pop not available: ", e$message); NULL })

# Helper: flood string (roads + OSM facilities in flood zone)
flood_string <- function(flood_type) {
  stopifnot(flood_type %in% c("fluvial", "pluvial", "coastal", "comb"))
  if (!is.null(flood_road)) {
    roads_pct <- flood_road %>% .[.$type == flood_type, "percentage_in_flood_zones"] %>%
      round(1) %>% paste0("%")
    roads_string <- paste(roads_pct, "of major roads,")
    if (roads_pct == "0%" && flood_road %>% .[.$type == flood_type, "total_major_road_meter"] == 0) {
      roads_string <- "NO ROADS RECORDED IN AOI     "
    }
  } else roads_string <- "NO ROADS FLOOD FILE     "
  if (!is.null(flood_osm)) {
    police_count <- flood_osm %>% .[.$poi == "police" & .$type == flood_type, "string"] %>%
      { if (length(.) > 0) paste(., "police stations") else NULL }
    health_count <- flood_osm %>% .[.$poi == "health" & .$type == flood_type, "string"] %>%
      { if (length(.) > 0) paste(., "health facilities") else NULL }
    schools_count <- flood_osm %>% .[.$poi == "schools" & .$type == flood_type, "string"] %>%
      { if (length(.) > 0) paste(., "schools") else NULL }
    fire_count <- flood_osm %>% .[.$poi == "fire" & .$type == flood_type, "string"] %>%
      { if (length(.) > 0) paste(., "fire stations") else NULL }
    osm_string <- paste_and(c(schools_count, health_count, fire_count, police_count))
  } else osm_string <- "NO OSM FLOOD FILE     "

  flood_type_long <- str_replace_all(flood_type, c(
    fluvial = "riverine",
    pluvial = "surface water",
    coastal = "coastal",
    comb = "riverine, surface water, or coastal"))

  paste(paste_bold(roads_string), ',', paste_bold(osm_string), "are located in a", paste_bold(flood_type_long), "flood risk zone with a minimum depth of 15 cm")
}

# Helper: flood population area
flood_pop_area <- function(flood_type) {
  stopifnot(flood_type %in% c("fluvial", "pluvial", "coastal", "comb"))
  if (!is.null(flood_pop) && nrow(flood_pop) > 0) {
    pop_pct <- flood_pop %>% .[.$type == flood_type, "exposed_dense_pop_pct"] %>%
      round(1) %>% paste0("%")
    paste("Percentage of population dense areas (>60th percentile density) in flood zone:", paste_bold(pop_pct))
  } else "Pop flood file not found or empty"
}

# Gather flood data by type — uses raw column names from flood_wsf.csv
gather_flood_data <- function(flood_type) {
  if (is.null(wsf_flood)) return(NULL)
  col_name <- paste0(flood_type, "_2020")
  if (flood_type == "combined") col_name <- "comb_2020"
  if (!col_name %in% names(wsf_flood)) return(tibble(year = wsf_flood_base$year, exposed_km2 = 0))
  wsf_flood %>%
    select(year, cumulative_sq_km, exposed_km2 = all_of(col_name)) %>%
    filter(!is.na(exposed_km2)) %>%
    mutate(percent_exposed = scales::percent(exposed_km2 / cumulative_sq_km, accuracy = 0.01))
}

# Create flood data variables
if (!is.null(wsf_flood)) {
  fu <- gather_flood_data("fluvial")
  pu <- gather_flood_data("pluvial")
  cu <- gather_flood_data("coastal")
  comb <- gather_flood_data("combined")
  pufu <- bind_rows(
    if (any(fu$exposed_km2 > 0)) fu %>% mutate(type = "River") else NULL,
    if (any(pu$exposed_km2 > 0)) pu %>% mutate(type = "Rainwater") else NULL,
    if (any(cu$exposed_km2 > 0)) cu %>% mutate(type = "Coastal") else NULL,
    comb %>% mutate(type = "Combined")) %>%
    mutate(type = factor(type, levels = c("Combined", "River", "Rainwater", "Coastal")))

  # Save flood CSVs for OJS
  if (!is.null(fu) && nrow(fu) > 0) write_csv(fu, file.path(tabular_dir, paste0(city_string, "_fu.csv")))
  if (!is.null(pu) && nrow(pu) > 0) write_csv(pu, file.path(tabular_dir, paste0(city_string, "_pu.csv")))
  if (!is.null(cu) && nrow(cu) > 0) write_csv(cu, file.path(tabular_dir, paste0(city_string, "_cu.csv")))
  if (!is.null(comb) && nrow(comb) > 0) write_csv(comb, file.path(tabular_dir, paste0(city_string, "_comb.csv")))
  if (nrow(pufu) > 0) write_csv(pufu, file.path(tabular_dir, paste0(city_string, "_pufu.csv")))
}

# =============================================================================
# Flood exposure by return period (probability) and total — from WSF + flood rasters
# =============================================================================

calculate_flood_by_prob <- function(flood_tif, wsf_tif, output_file = NULL) {
  flood_r <- rast(flood_tif)
  wsf_r <- rast(wsf_tif)

  # Map RP bands to output columns (nested: each includes all higher-severity pixels)
  # Band 1 = max_probability, Band 2+ = r{rp} binary (0/1)
  # r10 = flooded at 1-in-10yr → also flooded at 1-in-100 and 1-in-1000
  # r100 = flooded at 1-in-100yr → also flooded at 1-in-1000
  # r1000 = flooded at 1-in-1000yr
  # rp_col_map <- c(
  #   "r10" = ">10%",
  #   "r100" = "1-10%",
  #   "r1000" = "0.1-1%"
  # )
  rp_col_map <- c(
    "r10" = "1-in-10 year",
    "r100" = "1-in-100 year",
    "r1000" = "1-in-1,000 year"
  )

  # return_period_map <- c(
  #   `>10%` = "1-in-10 year",
  #   `1-10%` = "1-in-100 year",
  #   `0.1-1%` = "1-in-1,000 year"
  # )
  return_period_map <- c(
    `>10%` = "1-in-10 year",
    `1-10%` = "1-in-100 year",
    `0.1-1%` = "1-in-1,000 year"
  )

  # Check if multi-band TIF with RP bands
  n_bands <- nlyr(flood_r)
  if (n_bands < 2) stop("Flood TIF must be multi-band with RP layers (band 1=max_prob, band 2+=r{rp}). Re-collect fathom data.")

  flood_r <- crop(flood_r, aoi, mask = TRUE)
  wsf_r <- crop(wsf_r, aoi, mask = TRUE)
  utm_crs <- paste0("+proj=utm +zone=", floor((mean(ext(wsf_r)[1:2]) + 180) / 6) + 1, " +datum=WGS84")
  flood_r <- project(flood_r, utm_crs, method = "near")
  wsf_r <- project(wsf_r, flood_r, method = "near")

  wsf_vals <- values(wsf_r)[, 1]
  pixel_area_sqkm <- prod(res(flood_r)) / 1e6

  # Read each RP band by matching band name
  band_names <- names(flood_r)
  rp_vals <- list()
  for (rp_name in names(rp_col_map)) {
    idx <- which(band_names == rp_name)
    if (length(idx) > 0) {
      rp_vals[[rp_col_map[[rp_name]]]] <- values(flood_r)[, idx[1]]
    }
  }

  wsf_max <- max(wsf_vals, na.rm = TRUE)
  years <- 1985:floor(wsf_max)
  results <- list()

  for (yr in years) {
    built_mask <- wsf_vals <= yr & !is.na(wsf_vals)
    row_data <- list(year = yr - 1984, yearName = yr)

    for (col_name in names(rp_vals)) {
      band_v <- rp_vals[[col_name]]
      exposed_mask <- built_mask & band_v > 0 & !is.na(band_v)
      row_data[[col_name]] <- round(sum(exposed_mask, na.rm = TRUE) * pixel_area_sqkm, 2)
    }

    # Total = same as 1-in-1000 (widest net)
    # if (!is.null(rp_vals[["0.1-1%"]])) {
    #   total_v <- rp_vals[["0.1-1%"]]
    if (!is.null(rp_vals[["1-in-1,000 year"]])) {
      total_v <- rp_vals[["1-in-1,000 year"]]
      total_mask <- built_mask & total_v > 0 & !is.na(total_v)
      row_data[["total"]] <- round(sum(total_mask, na.rm = TRUE) * pixel_area_sqkm, 2)
    } else {
      row_data[["total"]] <- 0
    }

    results[[length(results) + 1]] <- row_data
  }

  result_df <- bind_rows(results)
  for (old_name in names(return_period_map)) {
    new_name <- return_period_map[[old_name]]
    if (old_name %in% names(result_df)) result_df[[new_name]] <- result_df[[old_name]]
  }

  if (!is.null(output_file)) {
    write_csv(result_df, output_file)
    message("Saved to: ", output_file)
  }
  return(result_df)
}

calculate_flood_total <- function(flood_tif, wsf_tif, output_file = NULL) {
  flood_r <- rast(flood_tif)
  wsf_r <- rast(wsf_tif)
  flood_r <- crop(flood_r, aoi, mask = TRUE)
  wsf_r <- crop(wsf_r, aoi, mask = TRUE)
  utm_crs <- paste0("+proj=utm +zone=", floor((mean(ext(wsf_r)[1:2]) + 180) / 6) + 1, " +datum=WGS84")
  flood_r <- project(flood_r, utm_crs, method = "near")
  wsf_r <- project(wsf_r, flood_r, method = "near")

  flood_vals <- values(flood_r)[, 1]
  wsf_vals <- values(wsf_r)[, 1]
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

# Find WSF TIF — prefer harmonized, fall back to evolution
wsf_tif <- list.files(spatial_dir, pattern = "wsf_harmonized\\.tif$", full.names = TRUE)[1]
if (is.null(wsf_tif) || length(wsf_tif) == 0)
  wsf_tif <- list.files(spatial_dir, pattern = "wsf.*evolution.*\\.tif$", full.names = TRUE)[1]
if (is.null(wsf_tif) || length(wsf_tif) == 0)
  wsf_tif <- list.files(spatial_dir, pattern = "wsf.*\\.tif$", full.names = TRUE)[1]

if (!is.null(wsf_tif) && length(wsf_tif) > 0) {
  message("Using WSF: ", wsf_tif)

  flood_types <- list(
    fluvial = list(pattern = "fluvial_2020\\.tif$", prob_out = "fu_prob.csv", total_out = "fu_total.csv"),
    pluvial = list(pattern = "pluvial_2020\\.tif$", prob_out = "pu_prob.csv", total_out = "pu_total.csv"),
    coastal = list(pattern = "coastal_2020\\.tif$", prob_out = "cu_prob.csv", total_out = "cu_total.csv"),
    combined = list(pattern = "_comb_2020\\.tif$", prob_out = "comb_prob.csv", total_out = "comb_total.csv")
  )

  flood_total_data <- list()
  flood_type_labels <- c(fluvial = "River", pluvial = "Rainwater", coastal = "Coastal", combined = "Combined")

  for (ft_name in names(flood_types)) {
    ft <- flood_types[[ft_name]]
    flood_tif <- list.files(spatial_dir, pattern = ft$pattern, full.names = TRUE, ignore.case = TRUE)[1]

    if (!is.null(flood_tif) && length(flood_tif) > 0 && !is.na(flood_tif) && file.exists(flood_tif)) {
      message("\n=== Processing ", ft_name, " ===")

      tryCatch({
        calculate_flood_by_prob(flood_tif, wsf_tif, file.path(tabular_dir, ft$prob_out))
      }, error = function(e) message("Error processing ", ft_name, " prob: ", e$message))

      tryCatch({
        d <- calculate_flood_total(flood_tif, wsf_tif, file.path(tabular_dir, ft$total_out))
        flood_total_data[[flood_type_labels[[ft_name]]]] <- d %>% mutate(type = flood_type_labels[[ft_name]])
      }, error = function(e) message("Error processing ", ft_name, " total: ", e$message))
    } else {
      message("Skipping ", ft_name, " - TIF not found")
    }
  }

  if (length(flood_total_data) > 0) flood_total <- bind_rows(flood_total_data)
} else {
  message("WSF TIF not found — skipping flood probability analysis")
  flood_total_data <- list()
}

# Probability colors and linetypes
prob_colors <- c("1-in-1,000 year" = "#9ECAE1", "1-in-100 year" = "#3182BD", "1-in-10 year" = "#08306B")
prob_linetypes <- c("1-in-1,000 year" = "solid", "1-in-100 year" = "dashed", "1-in-10 year" = "dotted")
