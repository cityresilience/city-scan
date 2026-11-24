# Benchmark population assembly
# Sourced at render time (scan-calculations) when all sibling cities have data
# Requires: setup.R, benchmark-helper.R already sourced
# Saves: {city}_pop_benchmark.csv, {city}_density_benchmark.csv, {city}_pop_growth.csv

message("\n=== Benchmark population assembly ===")

# Oxford/benchmark data requires GCS
if (!exists("USE_GCS") || !USE_GCS) {
  USE_GCS <<- TRUE
  source(here::here("core/R/gcs-auth.R"))
}

if (!exists("in_oxford")) source(here::here("core/R/benchmark-helper.R"))
if (!exists("get_oxford_pop")) source(here::here("tasks/oxford/collection.R"))
source(here::here("core/R/pop-backup.R"))

# Manual population data if exists
pop_manual <- tryCatch({readr::read_csv("./manual-data-entry/pop.csv", col_types = "ccddc") %>%
  mutate(Method = "Manual")}, error = function(e) tibble())

# AOI area
aoi_area <- tryCatch(
  round(sum(expanse(aoi %>% st_as_sf() %>% vect(), unit = "km")), 2),
  error = function(e) { message("Could not compute AOI area: ", e$message); NA_real_ })

# WorldPop growth for main city (from own task's CSVs)
wpop_growth <- tryCatch({
  fuzzy_read(tabular_dir, "worldpop_2015_2030.csv", read_csv) %>%
    rename_with(str_to_title) %>%
    mutate(
      Year = as.numeric(str_extract(Year, "\\d{4}")),
      Location = city,
      Country = country,
      Group = city,
      Area_km = aoi_area
    )
}, error = function(e) { message("WorldPop G2 CSV not found: ", e$message); tibble() })

wpop_growth_g1 <- tryCatch({
  fuzzy_read(tabular_dir, "worldpop_2000_2020.csv", read_csv) %>%
    rename_with(str_to_title) %>%
    mutate(
      Year = as.numeric(str_extract(Year, "\\d{4}")),
      Location = city,
      Country = country,
      Group = city,
      Area_km = aoi_area
    )
}, error = function(e) { message("WorldPop G1 CSV not found: ", e$message); tibble() })


# =============================================================================
# Assemble population for city + benchmark cities
# =============================================================================

pop_longitude <- tibble()

# Check if WorldPop Global2 available for main city (prioritize over Oxford)
use_wpop_for_city <- nrow(wpop_growth) > 0

# Add WorldPop Global2 for main city if available (priority over Oxford)
if (use_wpop_for_city) {
    message("Using WorldPop Global2 population data for ", city)
    pop_longitude <- pop_longitude %>%
        bind_rows(wpop_growth %>% mutate(Source = "WorldPop Global 2", Method = "WorldPop Global2", Group = city))
}

# Add WorldPop Global1 for main city (separate line on chart)
if (nrow(wpop_growth_g1) > 0) {
    message("Adding WorldPop Global1 population data for ", city)
    pop_longitude <- pop_longitude %>%
        bind_rows(wpop_growth_g1 %>% mutate(Source = "WorldPop Global 1", Method = "WorldPop Global1", Group = city))
}

# Sibling scan for benchmark cities
bm_cities_no_city <- setdiff(bm_cities, city)
wp_found_cities <- character()
sibling_cities <- character()

if (benchmark_mode != "oxford" && length(bm_cities_no_city) > 0) {
    message("Looking for WorldPop CSVs in sibling scan directories...")
    # G2 (2015-2030)
    wp_siblings <- pop_sibling_scan(bm_cities_no_city, country)
    if (nrow(wp_siblings$data) > 0) {
        pop_longitude <- pop_longitude %>%
            bind_rows(wp_siblings$data %>% mutate(Group = "Benchmark - sibling"))
        wp_found_cities <- wp_siblings$found_cities
        sibling_cities <- wp_siblings$found_cities
    }
    # G1 (2000-2020)
    wp_siblings_g1 <- pop_sibling_scan(bm_cities_no_city, country,
        dataset_pattern = "worldpop_2000_2020", source_label = "WorldPop Global 1")
    if (nrow(wp_siblings_g1$data) > 0) {
        pop_longitude <- pop_longitude %>%
            bind_rows(wp_siblings_g1$data %>% mutate(Group = "Benchmark - sibling"))
    }
}

# Oxford population for remaining benchmarks
remaining_bm <- setdiff(bm_cities_no_city, wp_found_cities)
oxford_found_cities <- character()

if (benchmark_mode != "sibling" && length(remaining_bm) > 0) {
    if (in_oxford && !use_wpop_for_city) {
        # City is in Oxford but no WorldPop — use Oxford for city + remaining benchmarks
        oxford_pop_subset <- get_oxford_pop(c(city, remaining_bm))
        if (!is.null(oxford_pop_subset) && nrow(oxford_pop_subset) > 0) {
            oxford_pop_subset <- oxford_pop_subset %>%
                mutate(Group = ifelse(Location == city, city, "Benchmark - Oxford"))
            pop_longitude <- pop_longitude %>% bind_rows(oxford_pop_subset)
            oxford_found_cities <- setdiff(unique(oxford_pop_subset$Location), city)
        }
    } else {
        # Try Oxford for remaining benchmarks
        oxford_pop_subset <- get_oxford_pop(remaining_bm)
        if (!is.null(oxford_pop_subset) && nrow(oxford_pop_subset) > 0) {
            oxford_pop_subset <- oxford_pop_subset %>% mutate(Group = "Benchmark - Oxford")
            pop_longitude <- pop_longitude %>% bind_rows(oxford_pop_subset)
            oxford_found_cities <- unique(oxford_pop_subset$Location)
        }
    }
}

# Backup for cities not found via sibling or Oxford
still_remaining <- setdiff(remaining_bm, oxford_found_cities)

if (length(still_remaining) > 0 && !is.null(benchmark_backup)) {
    if (benchmark_backup == "citypopulation") {
        message("Using citypopulation.de backup for: ", paste(still_remaining, collapse = ", "))
        backup_pop <- still_remaining %>%
            lapply(function(x) {
                data <- get_de_pop_growth(x, country = country)
                if (nrow(data) > 0) data$Group <- "Benchmark - backup"
                return(data)
            }) %>%
            bind_rows()
        if (nrow(backup_pop) > 0) {
            backup_pop <- backup_pop %>%
                mutate(Location = str_extract(tolatin(Location), tolatin(still_remaining) %>%
                    paste(collapse = "|")))
            pop_longitude <- pop_longitude %>% bind_rows(backup_pop)
        }
    } else if (benchmark_backup == "worldpop_ucdb") {
        message("Using WorldPop + UCDB backup for: ", paste(still_remaining, collapse = ", "))
        wpop_bm <- tryCatch(
            get_benchmark_worldpop(still_remaining, oxford_pop),
            error = function(e) { message("WorldPop benchmark download failed: ", e$message); tibble() }
        )
        if (nrow(wpop_bm) > 0) {
            pop_longitude <- pop_longitude %>%
                bind_rows(wpop_bm %>% mutate(Group = "Benchmark - backup"))
        }
    }
}


# Final assembly + save -----------------------------------------------------------------------
if (nrow(pop_longitude) > 0 && "Year" %in% names(pop_longitude)) {

  # add manual data if exists
  if (nrow(pop_manual) > 0) pop_longitude <- bind_rows(pop_longitude, pop_manual) %>%
    filter(!is.na(Population))

  if (!"Area_km" %in% names(pop_longitude)) pop_longitude$Area_km <- NA_real_
  pop_longitude <- pop_longitude %>%
    mutate(Area_km = case_when(
           Area_km == 0 ~ NA_real_,
           T ~ Area_km
         )) %>%
    group_by(Year, Location) %>%
    fill(Area_km, Population, Country, .direction = "updown") %>%
    ungroup() %>%
    distinct(Location, Year, Source, .keep_all = T)

  write_csv(pop_longitude, file.path(tabular_dir, paste0(city_string, "_pop_benchmark.csv")))
  message("Saved: _pop_benchmark.csv")

  # Population Density
  target_year <- as.numeric(format(Sys.Date(), "%Y"))
  density <- pop_longitude %>%
      filter(Area_km != 0 & !is.na(Area_km)) %>%
      slice_min(order_by = abs(Year - target_year), by = Location, with_ties = FALSE)
  density$Density <- density$Population/density$Area_km
  density <- density %>% arrange(desc(Density))
  write_csv(density, file.path(tabular_dir, paste0(city_string, "_density_benchmark.csv")))
  message("Saved: _density_benchmark.csv")

  # Population growth (main city only)
  pop_growth <- pop_longitude %>% filter(Group == city) %>% select(-Area_km)
  pop_growth <- arrange(pop_growth, Year)
  write_csv(pop_growth, file.path(tabular_dir, paste0(city_string, "_pop_growth.csv")))
  message("Saved: _pop_growth.csv")

} else {
  message("No population data available — skipping benchmark assembly")
}

message("=== Benchmark population assembly complete ===\n")
