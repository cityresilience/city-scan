# Benchmark population assembly - tasks/benchmark/collection.R
# Runs AFTER oxford + worldpop (see source/tasks.yml dependencies).
# Merges each task's outputs; does NOT recompute bm_cities or re-run oxford -
# it reads oxford's _benchmark-cities-pop.csv and worldpop's CSVs.
# Saves: {city}_pop_benchmark.csv, {city}_density_benchmark.csv, {city}_pop_growth.csv
#
# Sources benchmark-helper.R for FUNCTIONS only (pop_sibling_scan,
# get_benchmark_worldpop) and pop-backup.R (get_de_pop_growth).

if (!exists("aoi")) source(here::here("core/R/setup.R"))
source(here::here("core/R/benchmark-helper.R"))
source(here::here("core/R/pop-backup.R"))

message("\n=== Benchmark population assembly ===")

benchmark_mode <- city_params$benchmark_mode %||% "auto"   # sibling | oxford | auto
benchmark_backup <- city_params$benchmark_backup           # null | citypopulation | worldpop_ucdb

# Manual population data if exists
pop_manual <- tryCatch({readr::read_csv("./manual-data-entry/pop.csv", col_types = "ccddc") %>%
  mutate(Method = "Manual")}, error = function(e) tibble())

# AOI area
aoi_area <- tryCatch(
  round(sum(expanse(aoi %>% st_as_sf() %>% vect(), unit = "km")), 2),
  error = function(e) { message("Could not compute AOI area: ", e$message); NA_real_ })

# Oxford benchmark pop written by the oxford task (pop_benchmark shape: has
# Population + Country + Area_km). Group is the city (main) or "Benchmark - Oxford".
oxford_bench <- tryCatch(
  fuzzy_read(tabular_dir, "benchmark-cities-pop.csv", read_csv),
  error = function(e) tibble())
# fuzzy_read returns NA (not a data frame) when the oxford CSV is missing -
# coerce so nrow() works and we degrade to "no oxford peers" instead of crashing.
if (!is.data.frame(oxford_bench)) oxford_bench <- tibble()
oxford_main  <- if (nrow(oxford_bench) > 0) oxford_bench %>% filter(Group != "Benchmark - Oxford") else tibble()
oxford_peers <- if (nrow(oxford_bench) > 0) oxford_bench %>% filter(Group == "Benchmark - Oxford") else tibble()
in_oxford <- nrow(oxford_main) > 0

# Benchmark cities = manual + Oxford-auto peers (from oxford output, NOT recomputed)
oxford_peer_names <- if (nrow(oxford_peers) > 0) unique(oxford_peers$Location) else character()
bm_cities <- c(bm_cities_manual, oxford_peer_names) %>% unique() %>% which_not(city)

# WorldPop growth for main city (from worldpop task's CSVs)
wpop_growth <- tryCatch({
  fuzzy_read(tabular_dir, "worldpop_2015_2030.csv", read_csv) %>%
    rename_with(str_to_title) %>%
    mutate(Year = as.numeric(str_extract(Year, "\\d{4}")),
           Location = city, Country = country, Group = city, Area_km = aoi_area)
}, error = function(e) { message("WorldPop G2 CSV not found: ", e$message); tibble() })

wpop_growth_g1 <- tryCatch({
  fuzzy_read(tabular_dir, "worldpop_2000_2020.csv", read_csv) %>%
    rename_with(str_to_title) %>%
    mutate(Year = as.numeric(str_extract(Year, "\\d{4}")),
           Location = city, Country = country, Group = city, Area_km = aoi_area)
}, error = function(e) { message("WorldPop G1 CSV not found: ", e$message); tibble() })


# =============================================================================
# Assemble population for city + benchmark cities
# =============================================================================
pop_longitude <- tibble()

# Main city: WorldPop Global 2 (priority) + Global 1
use_wpop_for_city <- nrow(wpop_growth) > 0
if (use_wpop_for_city) {
    message("Using WorldPop Global2 population data for ", city)
    pop_longitude <- pop_longitude %>%
        bind_rows(wpop_growth %>% mutate(Source = "WorldPop Global 2", Method = "WorldPop Global2", Group = city))
}
if (nrow(wpop_growth_g1) > 0) {
    pop_longitude <- pop_longitude %>%
        bind_rows(wpop_growth_g1 %>% mutate(Source = "WorldPop Global 1", Method = "WorldPop Global1", Group = city))
}

# Main city has no WorldPop but is in Oxford -> use its Oxford pop
if (!use_wpop_for_city && in_oxford) {
    message("Using Oxford population data for ", city)
    pop_longitude <- pop_longitude %>% bind_rows(oxford_main %>% mutate(Group = city))
}

# Sibling scan for benchmark cities (WorldPop from sibling scan dirs)
bm_cities_no_city <- setdiff(bm_cities, city)
wp_found_cities <- character()
sibling_cities <- character()

if (benchmark_mode != "oxford" && length(bm_cities_no_city) > 0) {
    message("Looking for WorldPop CSVs in sibling scan directories...")
    wp_siblings <- pop_sibling_scan(bm_cities_no_city, country)
    if (nrow(wp_siblings$data) > 0) {
        pop_longitude <- pop_longitude %>%
            bind_rows(wp_siblings$data %>% mutate(Group = "Benchmark - sibling"))
        wp_found_cities <- wp_siblings$found_cities
        sibling_cities <- wp_siblings$found_cities
    }
    wp_siblings_g1 <- pop_sibling_scan(bm_cities_no_city, country,
        dataset_pattern = "worldpop_2000_2020", source_label = "WorldPop Global 1")
    if (nrow(wp_siblings_g1$data) > 0) {
        pop_longitude <- pop_longitude %>%
            bind_rows(wp_siblings_g1$data %>% mutate(Group = "Benchmark - sibling"))
    }
}

# Oxford pop for remaining benchmarks (from oxford task's CSV, NOT re-fetched)
remaining_bm <- setdiff(bm_cities_no_city, wp_found_cities)
oxford_found_cities <- character()

if (benchmark_mode != "sibling" && length(remaining_bm) > 0 && nrow(oxford_peers) > 0) {
    oxford_remaining <- oxford_peers %>% filter(Location %in% remaining_bm)
    if (nrow(oxford_remaining) > 0) {
        pop_longitude <- pop_longitude %>%
            bind_rows(oxford_remaining %>% mutate(Group = "Benchmark - Oxford"))
        oxford_found_cities <- unique(oxford_remaining$Location)
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
            get_benchmark_worldpop(still_remaining, oxford_bench),
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
    mutate(Area_km = case_when(Area_km == 0 ~ NA_real_, T ~ Area_km)) %>%
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
  message("No population data available - skipping benchmark assembly")
}

message("=== Benchmark population assembly complete ===\n")
