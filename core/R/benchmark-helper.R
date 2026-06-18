# Benchmark city selection + Oxford availability — FUNCTION LIBRARY.
# Pure definitions: sourcing this file runs NOTHING. Callers call the functions
# and assign the results themselves (in_oxford, bm_cities, ...).
# Requires helpers from setup.R: fuzzy_read, which_not, glue, %||%

# check_in_oxford() — is the city in Oxford Economics?
# Returns list(in_oxford, city, oxford_locations):
#   - in_oxford: logical
#   - city: the Oxford spelling if matched only via ASCII (else unchanged)
#   - oxford_locations: the locations table (reused for nearby-city selection)
check_in_oxford <- function(city, country) {
  oxford_location_file <- tempfile(fileext = ".csv")
  googleCloudStorageR::gcs_get_object("oxford-economics/oxford-locations.csv",
    bucket = "city-scan-global-data", saveToDisk = oxford_location_file)
  oxford_locations <- read_csv(oxford_location_file, col_types = "c")
  oxford_locations_in_country <- dplyr::filter(oxford_locations, Country == country)

  # Match with or without diacritics (e.g. "Chisinau" with/without diacritics)
  strip_diacritics <- function(x) stringi::stri_trans_general(x, "Latin-ASCII")
  city_ascii <- strip_diacritics(city)
  oxford_ascii <- strip_diacritics(oxford_locations_in_country$Location)
  in_oxford <- city_ascii %in% oxford_ascii

  # If matched only via ASCII normalization, return the Oxford spelling
  if (in_oxford && !(city %in% oxford_locations_in_country$Location)) {
    city <- oxford_locations_in_country$Location[oxford_ascii == city_ascii][1]
  }

  list(in_oxford = in_oxford, city = city, oxford_locations = oxford_locations)
}

# load_oxford_data() — read the big Oxford Global Cities CSV ONCE.
# Returns oxford_full (all indicators). Callers derive oxford_pop, economics, etc.
load_oxford_data <- function() {
  oxford_file <- tempfile(fileext = ".csv")
  googleCloudStorageR::gcs_get_object("oxford-economics/Oxford Global Cities Data.csv",
    bucket = "city-scan-global-data", saveToDisk = oxford_file)
  read_csv(oxford_file,
    col_types = "cccccccccdddddddddddddddddddddddddddddddddddddddddcllldlcclcc") %>%
    mutate(Location = case_when(Location == "Lom\u00e9" ~ "Lomé",
                                Location == "Yaound\u00e9" ~ "Yaoundé",
                                T ~ Location))
}

# get_nearby_countries() — auto-detect peers' countries from the economic
# classification (same region + income group). Returns a pipe-string or NULL.
get_nearby_countries <- function(country) {
  tryCatch({
    econ_class <- read_csv(here::here("source/countries_economies_classification.csv"))
    focus_row <- econ_class %>%
      filter(Economy == country | str_detect(Economy, fixed(country)))
    if (nrow(focus_row) == 0) return(NULL)

    focus_region <- focus_row$Region[1]
    focus_income <- focus_row$`Income group`[1]
    similar_countries <- econ_class %>%
      filter(Region == focus_region, `Income group` == focus_income, Economy != country) %>%
      pull(Economy)
    if (length(similar_countries) == 0) return(NULL)

    paste(tolower(similar_countries), collapse = "|")
  }, error = function(e) {
    message(glue("Could not auto-detect similar countries: {e$message}"))
    NULL
  })
}

# get_pop_estimate() — main-city population for +/-50% peer size-matching.
# Oxford 2021 if in_oxford, else latest WorldPop (Oxford is in thousands).
get_pop_estimate <- function(city, in_oxford, oxford_pop, tabular_dir) {
  tryCatch({
    if (in_oxford) {
      oxford_pop %>% subset(Location == city) %>% pull(`2021`)
    } else {
      wpop_csv <- fuzzy_read(tabular_dir, "worldpop_2015_2030.csv", read_csv)
      if (!is.null(wpop_csv) && nrow(wpop_csv) > 0) {
        wpop_csv %>% slice_max(year, n = 1) %>% pull(population) / 1000
      } else NULL
    }
  }, error = function(e) NULL)
}

# get_oxford_benchmark_cities() — size-matched Oxford cities in nearby countries.
get_oxford_benchmark_cities <- function(city, country, nearby_countries, pop, oxford_pop, oxford_locations) {
  if (is.null(nearby_countries)) return(NULL)

  nearby_cities <- oxford_locations %>%
    subset(str_detect(tolower(Country), nearby_countries)) %>%
    subset(Location != Country & !str_detect(Location, "Total")) %>%
    pull(Location)

  if (is.null(pop) || nrow(oxford_pop) == 0) return(NULL)
  oxford_pop %>%
    subset(str_detect(tolower(Country), nearby_countries)) %>%
    subset(Location %in% nearby_cities) %>%
    subset((between(`2021`, pop * .5, pop * 1.5) | Country == country) & Location != city) %>%
    pull(Location)
}

# select_benchmark_cities() — the composer. Merges manual + Oxford-auto by mode.
#   sibling -> manual only;  oxford/auto -> manual + Oxford-auto.
# oxford_pop / oxford_locations are passed in so Oxford is loaded once upstream.
select_benchmark_cities <- function(city, country, bm_cities_manual, nearby_countries,
                                    benchmark_mode, in_oxford, oxford_pop, oxford_locations,
                                    tabular_dir) {
  if (is.null(nearby_countries) || nearby_countries == "")
    nearby_countries <- get_nearby_countries(country)

  pop <- get_pop_estimate(city, in_oxford, oxford_pop, tabular_dir)
  bm_oxford <- get_oxford_benchmark_cities(city, country, nearby_countries, pop, oxford_pop, oxford_locations)

  if (benchmark_mode == "sibling") {
    bm_cities_manual %>% unique() %>% which_not(city)
  } else {
    c(bm_cities_manual, bm_oxford) %>% unique() %>% which_not(city)
  }
}


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

