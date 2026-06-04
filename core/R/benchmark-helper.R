# Benchmark city selection + Oxford availability check
# Sourced by: worldpop/analysis.R, oxford/collection.R
# Requires: setup.R already sourced (city, country, bm_cities_manual, nearby_countries_string, tabular_dir)

message("\n=== Benchmark city selection ===")

# Always authenticate for global reference data (Oxford CSVs live in GCS regardless of USE_GCS)
if (!googleAuthR::gar_has_token()) {
  adc_path <- Find(file.exists, c(
    Sys.getenv("GOOGLE_APPLICATION_CREDENTIALS"),
    file.path(Sys.getenv("HOME"), ".config", "gcloud", "application_default_credentials.json")))
  if (!is.null(adc_path))
    googleCloudStorageR::gcs_auth(token = gargle::credentials_app_default(
      scopes = "https://www.googleapis.com/auth/cloud-platform"))
}

# Download Oxford locations from GCS
if (!exists("oxford_location_file") || !file.exists(oxford_location_file)) {
  oxford_location_file <- tempfile(fileext = ".csv")
  googleCloudStorageR::gcs_get_object("oxford-economics/oxford-locations.csv", bucket = "city-scan-global-data", saveToDisk = oxford_location_file)
}

# Is city in Oxford Economics? --------------------------------------------------------------
oxford_locations <- read_csv(oxford_location_file, col_types = "c")
oxford_locations_in_country <- dplyr::filter(oxford_locations, Country == country)

# Match with or without diacritics (e.g. "Chișinău" == "Chisinau")
.strip_diacritics <- function(x) stringi::stri_trans_general(x, "Latin-ASCII")
city_ascii <- .strip_diacritics(city)
oxford_ascii <- .strip_diacritics(oxford_locations_in_country$Location)
in_oxford <- city_ascii %in% oxford_ascii

# If city matched only via ASCII normalization, use the Oxford spelling for lookups
if (in_oxford && !(city %in% oxford_locations_in_country$Location)) {
  oxford_city_name <- oxford_locations_in_country$Location[oxford_ascii == city_ascii][1]
  message(glue("Matched '{city}' → Oxford name '{oxford_city_name}'"))
  city <- oxford_city_name
}

message(glue("{city} in Oxford Economics: {in_oxford}"))

# Read only population indicator from Oxford for size-matching ---------------------------------
if (!exists("oxford_file") || !file.exists(oxford_file)) {
  oxford_file <- tempfile(fileext = ".csv")
  googleCloudStorageR::gcs_get_object("oxford-economics/Oxford Global Cities Data.csv", bucket = "city-scan-global-data", saveToDisk = oxford_file)
}
oxford_pop <- tryCatch({
  read_csv(oxford_file,
    col_types = "cccccccccdddddddddddddddddddddddddddddddddddddddddcllldlcclcc") %>%
  mutate(Location = case_when(Location == "Lom\u00e9" ~ "Lomé",
                              Location == "Yaound\u00e9" ~ "Yaoundé",
                              T ~ Location)) %>%
  subset(Indicator == "Total population") %>%
  select(Location, Country, `2021`)
}, error = function(e) {
  message(glue("Could not read Oxford data for size-matching: {e$message}"))
  tibble()
})

# Get population estimate for benchmark size-matching ----------------------------------------
# Need a pop estimate to filter benchmark cities to similar size (±50%)
pop <- tryCatch({
  if (in_oxford) {
    oxford_pop %>%
      subset(Location == city) %>%
      pull(`2021`)
  } else {
    # Try WorldPop
    wpop_csv <- fuzzy_read(tabular_dir, "worldpop_2015_2030.csv", read_csv)
    if (!is.null(wpop_csv) && nrow(wpop_csv) > 0) {
      wpop_csv %>% slice_max(year, n = 1) %>% pull(population) / 1000  # Oxford is in thousands
    } else NULL
  }
}, error = function(e) NULL)

if (is.null(pop)) message("Warning: could not get population estimate for benchmark size-matching")

# Benchmark countries auto-detect if not specified -------------------------------------------
if (is.null(nearby_countries_string) || nearby_countries_string == "") {
  tryCatch({
    # Load economic classification
    econ_class <- read_csv(here::here("source/countries_economies_classification.csv"))

    # Find focus country's region and income group
    focus_row <- econ_class %>%
      filter(Economy == country | str_detect(Economy, fixed(country)))

    if (nrow(focus_row) > 0) {
      focus_region <- focus_row$Region[1]
      focus_income <- focus_row$`Income group`[1]

      # Get countries with same region AND income group
      similar_countries <- econ_class %>%
        filter(Region == focus_region,
                `Income group` == focus_income,
                Economy != country) %>%
        pull(Economy)

      if (length(similar_countries) > 0) {
        nearby_countries_string <- paste(tolower(similar_countries), collapse = "|")
        message(glue("Auto-detected similar countries ({focus_region}, {focus_income}):
{paste(similar_countries, collapse = ', ')}"))
      }
    }
  }, error = function(e) {
    message(glue("Could not auto-detect similar countries: {e$message}"))
  })
}

# Benchmark city selection -------------------------------------------------------------------

nearby_cities <- if (is.null(nearby_countries_string)) NULL else {
    oxford_locations %>%
        subset(str_detect(tolower(Country), nearby_countries_string)) %>%
        subset(Location != Country & !str_detect(Location, "Total")) %>%
        pull(Location)
}

bm_cities_oxford <- if (is.null(nearby_countries_string) || is.null(pop) || nrow(oxford_pop) == 0) NULL else {
    oxford_pop %>%
    subset(str_detect(tolower(Country), nearby_countries_string)) %>%
    subset(Location %in% nearby_cities) %>%
    subset((between(`2021`, pop*.5, pop*1.5) | Country == country) & Location != city) %>%
    pull(Location)
}

# Benchmark mode and backup (from city_inputs.yml)
benchmark_mode <- city_params$benchmark_mode %||% "auto"  # sibling, oxford, auto
benchmark_backup <- city_params$benchmark_backup  # null, citypopulation, worldpop_ucdb

# Benchmark cities: merge based on mode
bm_cities <- if (benchmark_mode == "sibling") {
  bm_cities_manual %>% unique() %>% which_not(city)
} else if (benchmark_mode == "oxford") {
  c(bm_cities_manual, bm_cities_oxford) %>% unique() %>% which_not(city)
} else {
  # auto — both
  c(bm_cities_manual, bm_cities_oxford) %>% unique() %>% which_not(city)
}

has_manual_benchmarks <- length(bm_cities_manual) > 0

message(glue("\nBenchmark mode: {benchmark_mode}"))
message(glue("Benchmark backup: {if (is.null(benchmark_backup)) 'none' else benchmark_backup}"))
message(glue("In Oxford: {in_oxford}"))
message(glue("Manual cities: {if (length(bm_cities_manual) > 0) paste(bm_cities_manual, collapse = ', ') else 'none'}"))
message(glue("Oxford auto-detect: {if (length(bm_cities_oxford) > 0) paste(bm_cities_oxford, collapse = ', ') else 'none'}"))
message(glue("All benchmark cities ({length(bm_cities)}): {paste(bm_cities, collapse = ', ')}"))


# Generic sibling scan -----------------------------------------------------------------------
# Scans sibling scan directories for CSV data matching a dataset pattern
# Used by worldpop and ghs tasks to find benchmark city data
#
# dataset_pattern: regex for the CSV filename, e.g. "worldpop_2015_2030" or "ghs_pop"
# year_col / pop_col: column names in the sibling CSV
pop_sibling_scan <- function(cities, country, dataset_pattern = "worldpop_2015_2030",
                             source_label = "WorldPop Global 2",
                             year_col = "year", pop_col = "population") {
  parent_dir <- dirname(here::here())
  sibling_dirs <- list.dirs(parent_dir, full.names = TRUE, recursive = FALSE)

  results <- list()
  found_cities <- character()

  for (ct in cities) {
    # Normalize city name the same way setup.R creates city_string
    ct_normalized <- tolatin(ct) %>% tolower() %>% str_replace_all(" ", "-")
    ct_underscore <- str_replace_all(ct_normalized, "-", "_")

    # Find matching sibling directory (ends with the city string)
    match_dir <- sibling_dirs[str_detect(basename(sibling_dirs),
      paste0("(", ct_normalized, "|", ct_underscore, ")$"))]

    if (length(match_dir) == 0) next
    match_dir <- match_dir[1]

    # Look for CSV matching dataset_pattern
    tabular_path <- file.path(match_dir, "02-process-output", "tabular")
    if (!dir.exists(tabular_path)) next

    csv_files <- base::list.files(tabular_path, pattern = paste0(dataset_pattern, "\\.csv$"), full.names = TRUE)
    if (length(csv_files) == 0) next

    # Get area from sibling's AOI shapefile
    area_km <- tryCatch({
      sibling_yml <- yaml::read_yaml(file.path(match_dir, "01-user-input", "city_inputs.yml"))
      aoi_shp <- file.path(match_dir, "01-user-input", "AOI", paste0(sibling_yml$AOI_shp_name, ".shp"))
      sibling_aoi <- st_read(aoi_shp, quiet = TRUE) %>% vect()
      round(sum(expanse(sibling_aoi, unit = "km")), 2)
    }, error = function(e) NA_real_)

    result <- tryCatch({
      read.csv(csv_files[1]) %>%
        as_tibble() %>%
        mutate(
          Year = as.numeric(str_extract(as.character(.data[[year_col]]), "\\d{4}")),
          Population = .data[[pop_col]],
          Location = ct,
          Country = country,
          Area_km = area_km,
          Source = source_label,
          Method = paste0(source_label, " (sibling)"),
          .keep = "none"
        )
    }, error = function(e) { message("  sibling read error for ", ct, ": ", e$message); NULL })

    if (!is.null(result) && nrow(result) > 0) {
      results[[ct]] <- result
      found_cities <- c(found_cities, ct)
      message("  ", source_label, " from sibling: ", ct, " (", basename(match_dir), ")")
    }
  }

  list(data = bind_rows(results), found_cities = found_cities)
}

# Benchmark WorldPop: get WorldPop G2 population for benchmark cities
# Uses GHS Urban Centre Database (UCDB) for city boundaries

# GCS paths (supports /vsicurl/ windowed reads)
UCDB_URL <- "/vsicurl/https://storage.googleapis.com/city-scan-global-public/Urban_Centre_Database/GHS_STAT_UCDB2015MT_GLOBE_R2019A_V1_2.gpkg"
G2_GCS_BASE <- "/vsicurl/https://storage.googleapis.com/city-scan-global-public/world_population/WorldPop-Global-2"

# Direct WorldPop URL (does NOT support range requests — must download full file)
G2_WP_TEMPLATE <- "https://data.worldpop.org/GIS/Population/Global_2015_2030/R2025A/{year}/{ISO}/v1/100m/constrained/{iso}_pop_{year}_CN_100m_R2025A_v1.tif"


get_ucdb_boundary <- function(city_name, country_name = NULL) {
  # Get all cities for the country, then fuzzy match by name in R
  # This handles UCDB using local names (e.g. "Homel" instead of "Gomel")

  if (!is.null(country_name)) {
    query <- glue::glue("SELECT * FROM \"GHS_STAT_UCDB2015MT_GLOBE_R2019A_V1_2\" WHERE CTR_MN_NM = '{country_name}'")
  } else {
    # No country — try exact name match globally
    query <- glue::glue("SELECT * FROM \"GHS_STAT_UCDB2015MT_GLOBE_R2019A_V1_2\" WHERE UC_NM_MN = '{city_name}'")
  }

  all_cities <- tryCatch(
    st_read(UCDB_URL, query = query, quiet = TRUE),
    error = function(e) NULL
  )

  if (is.null(all_cities) || nrow(all_cities) == 0) {
    message("  UCDB: no results for country '", country_name, "'")
    return(NULL)
  }

  # Exact match first
  result <- all_cities %>% filter(UC_NM_MN == city_name)

  # Partial match (city name contained in UCDB name or vice versa)
  if (nrow(result) == 0) {
    city_lower <- tolower(tolatin(city_name))
    result <- all_cities %>%
      filter(str_detect(tolower(tolatin(UC_NM_MN)), fixed(city_lower)) |
             str_detect(city_lower, tolower(tolatin(UC_NM_MN))))
  }

  # Fuzzy match by string distance (handles Gomel→Homel, etc.)
  if (nrow(result) == 0) {
    city_lower <- tolower(tolatin(city_name))
    all_cities <- all_cities %>%
      mutate(.dist = stringdist::stringdist(city_lower, tolower(tolatin(UC_NM_MN)), method = "jw"))
    best <- all_cities %>% slice_min(.dist, n = 1)
    if (best$.dist[1] < 0.25) {
      result <- best %>% select(-.dist)
      message("  UCDB: fuzzy matched '", city_name, "' -> '", result$UC_NM_MN[1],
              "' (dist=", round(best$.dist[1], 3), ")")
    } else {
      all_cities <- all_cities %>% select(-.dist)
    }
  }

  if (nrow(result) == 0) {
    message("  UCDB: no match for '", city_name, "' in ", country_name)
    return(NULL)
  }

  # If multiple matches, pick largest by population
  if (nrow(result) > 1) {
    message("  UCDB: multiple matches for ", city_name, " — using largest")
    result <- result %>% slice_max(P15, n = 1)
  }

  message("  UCDB: matched '", city_name, "' -> '", result$UC_NM_MN[1], "'")
  result
}


get_worldpop_g2_for_city <- function(city_boundary, iso3, years = 2015:2030) {
  # Get WorldPop G2 population for a city boundary
  # Try GCS first (windowed reads), fallback to full download from WorldPop
  iso_lower <- tolower(iso3)
  iso_upper <- toupper(iso3)
  city_vect <- vect(city_boundary)
  results <- list()

  for (yr in years) {
    fname <- paste0(iso_lower, "_pop_", yr, "_CN_100m_R2025A_v1.tif")

    pop <- tryCatch({
      # Try GCS (supports /vsicurl/ windowed reads)
      r <- rast(file.path(G2_GCS_BASE, fname))
      r_crop <- crop(r, city_vect, mask = TRUE)
      sum(values(r_crop), na.rm = TRUE)
    }, error = function(e) {
      # Fallback: download full file from WorldPop (no range request support)
      tryCatch({
        url <- glue::glue(G2_WP_TEMPLATE, year = yr, ISO = iso_upper, iso = iso_lower)
        tmp <- tempfile(fileext = ".tif")
        download.file(url, tmp, mode = "wb", quiet = TRUE)
        r <- rast(tmp)
        r_crop <- crop(r, city_vect, mask = TRUE)
        pop_val <- sum(values(r_crop), na.rm = TRUE)
        unlink(tmp)
        pop_val
      }, error = function(e2) {
        message("    Failed year ", yr, ": ", e2$message)
        NA_real_
      })
    })

    results[[as.character(yr)]] <- pop
  }

  tibble(
    Year = as.numeric(names(results)),
    Population = round(unlist(results))
  ) %>% filter(!is.na(Population))
}


get_benchmark_worldpop <- function(cities, oxford_pop_df = NULL) {
  # For each benchmark city:
  #   1. Look up country from Oxford data
  #   2. Get UCDB boundary
  #   3. Download WorldPop G2 and sum population per year
  # Returns tibble matching pop_longitude format

  all_results <- list()

  for (ct in cities) {
    message("  Processing benchmark: ", ct)

    # Get country from Oxford data
    ct_country <- NULL
    if (!is.null(oxford_pop_df) && nrow(oxford_pop_df) > 0) {
      ct_row <- oxford_pop_df %>% filter(Location == ct)
      if (nrow(ct_row) > 0) ct_country <- ct_row$Country[1]
    }

    # Get UCDB boundary
    boundary <- get_ucdb_boundary(ct, ct_country)
    if (is.null(boundary)) next

    iso3 <- boundary$CTR_MN_ISO[1]
    area_km <- boundary$AREA[1]
    ct_country <- if (!is.null(ct_country)) ct_country else boundary$CTR_MN_NM[1]

    message("    ISO3: ", iso3, " | Area: ", area_km, " km²")

    # Get WorldPop G2 population
    pop_data <- tryCatch(
      get_worldpop_g2_for_city(boundary, iso3),
      error = function(e) {
        message("    WorldPop G2 failed for ", ct, ": ", e$message)
        tibble()
      }
    )

    if (nrow(pop_data) == 0) next

    pop_data <- pop_data %>%
      mutate(
        Location = ct,
        Country = ct_country,
        Area_km = area_km,
        Source = "WorldPop Global 2",
        Method = "WorldPop G2 (UCDB AOI)",
        Group = "Benchmark"
      )

    all_results[[ct]] <- pop_data
    message("    OK: ", nrow(pop_data), " years, latest pop = ",
            scales::comma(tail(pop_data$Population, 1)))
  }

  if (length(all_results) == 0) return(tibble())
  bind_rows(all_results)
}

