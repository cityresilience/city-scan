# Oxford Economics data collection
# Reads oxford_full (the ONE place it's loaded)
# get_oxford_pop() is a function — called by worldpop/dataanalysis.R as fallback
# Everything else runs inline and saves CSVs to tabular/
#
# Requires: setup.R already sourced (city, country, tabular_dir)
#           benchmark-helper.R sourced for functions (check_in_oxford, select_benchmark_cities, load_oxford_data)

USE_GCS <<- TRUE
if (!exists("aoi")) source(here::here("core/R/setup.R"))
source(here::here("core/R/benchmark-helper.R"))

message("\n=== Oxford datacollection ===")

# Benchmark selection — functions from benchmark-helper.R (no longer globals)
io <- check_in_oxford(city, country)
in_oxford <- io$in_oxford
city <- io$city                       # Oxford spelling if matched only via ASCII
oxford_locations <- io$oxford_locations

# Load oxford_full ONCE; derive the size-matching pop table from it
oxford_full <- tryCatch(load_oxford_data(), error = function(e) {
  message(glue("Could not read Oxford Economics data: {e$message}"))
  tibble()
})
oxford_pop <- if (nrow(oxford_full) > 0) {
  oxford_full %>% subset(Indicator == "Total population") %>% select(Location, Country, `2021`)
} else tibble()

benchmark_mode <- city_params$benchmark_mode %||% "auto"
benchmark_backup <- city_params$benchmark_backup
bm_cities <- select_benchmark_cities(city, country, bm_cities_manual, nearby_countries_string,
                                     benchmark_mode, in_oxford, oxford_pop, oxford_locations, tabular_dir)

# Subset for city + non-sibling benchmarks with Group column
# Oxford charts only use cities in Oxford, not sibling cities
oxford_bm <- if (exists("sibling_cities")) setdiff(bm_cities, sibling_cities) else bm_cities
oxford <- if (nrow(oxford_full) > 0) {
  subset(oxford_full, Location %in% c(city, oxford_bm)) %>%
    mutate(Group = case_when(Location == city ~ Location,
                             T ~ "Benchmark - Oxford") %>% factor(levels = c(city, "Benchmark - Oxford")))
} else tibble()

# National-level data for share calculations
if (nrow(oxford) > 0) {
countries <- oxford$Country %>% unique()
oxford_countries <- subset(oxford_full, Country %in% countries) %>%
  subset(str_detect(Location, "- Total") | Location %in% countries, select = -Location)

# Indicator lists
indicators <- select(oxford, Indicator) %>% distinct()
pop_dist_inds <- subset(indicators, str_detect(Indicator, "Population") &
                          Indicator %ni% c("Population 0-14", "Population 15-64", "Population 65+")) %>% pull()
emp_inds <- subset(indicators, str_detect(Indicator, "Employment")) %>% pull()
gva_inds <- subset(indicators, str_detect(tolower(Indicator), "gross value added, real, us")) %>% pull()
extra_inds <- c("Total population", "Employment - Total", "GDP, real, US$ - Total")
}


# =============================================================================
# FUNCTION: get_oxford_pop() — called by worldpop as fallback
# =============================================================================
get_oxford_pop <- function(cities) {
  if (length(cities) == 0 || nrow(oxford_full) == 0) return(tibble())

  oxford_matched <- oxford_full %>%
    subset(Location %in% cities & Indicator == "Total population")

  if (nrow(oxford_matched) == 0) return(tibble())

  oxford_subset <- oxford_matched %>%
    select(Location, Country, Indicator, matches('\\d')) %>%
    pivot_longer(cols = matches('^\\d'), names_to = "Year", values_to = "Value") %>%
    pivot_wider(values_from = Value, names_from = Indicator) %>%
    mutate(
      Year = as.numeric(Year),
      Population = `Total population` * 1000,
      Source = "Oxford",
      Method = "Oxford",
      Group = case_when(Location == city ~ city, T ~ "Benchmark - Oxford")) %>%
    select(-any_of("Total population")) %>%
    arrange(Location) %>%
    subset(Year <= 2021 & !is.na(Population))

  # Get area data for Oxford cities
  if (nrow(oxford_subset) > 0) {
    oxford_areas <- tryCatch({
      read_csv("oxford-economics/oxford-economics-areas.csv", col_types = "ccd") %>%
        mutate(Location = str_to_title(Location)) %>%
        filter(Location %in% str_to_title(oxford_subset$Location)) %>%
        select(-Country)
    }, error = function(e) tibble())

    if (nrow(oxford_areas) > 0) {
      oxford_subset <- left_join(oxford_subset, oxford_areas, by = "Location")
      if ("Area_km.x" %in% names(oxford_subset)) {
        oxford_subset <- oxford_subset %>%
          mutate(Area_km = coalesce(Area_km.x, Area_km.y)) %>%
          select(-Area_km.x, -Area_km.y)
      }
    }
  }

  oxford_subset
}


# =============================================================================
# Benchmark-city POPULATION — written REGARDLESS of in_oxford so the benchmark
# task can reuse it (peers exist even when the main city is not in Oxford).
# get_oxford_pop() shape already has Population + Country + Area_km. Named
# _benchmark-cities-pop (NOT _oxford_) so it does not trip oxford/charts'
# "in_oxford = any _oxford_ CSV exists" check.
# =============================================================================
write_csv(get_oxford_pop(c(city, oxford_bm)),
          file.path(tabular_dir, paste0(city_string, "_benchmark-cities-pop.csv")))


# =============================================================================
# ECONOMICS — only if in_oxford, runs inline, saves CSVs
# =============================================================================

if (in_oxford) {

# Age distribution: city vs benchmark median (2021 snapshot) -----------------------------------
pop_dist_long <- subset(oxford, Location %in% c(city, bm_cities) & Indicator %in% pop_dist_inds) %>%
    select(Location, Indicator, `2021`, Group) %>%
    mutate(Age_Bracket = substr(Indicator, 12, 20),
        Age_Bracket = factor(Age_Bracket, levels = unique(Age_Bracket)),
        Count = `2021`) %>%
    select(Group, Location, Age_Bracket, Count) %>%
    group_by(Location) %>%
    mutate(Percentage = Count/sum(Count)) %>%
    ungroup()

pop_dist_group <- pop_dist_long %>%
    group_by(Location) %>%
    mutate(Percentage = Count/sum(Count)) %>%
    ungroup() %>%
    group_by(Group, Age_Bracket) %>%
    summarize(Percentage = median(Percentage), .groups = "keep") %>%
    mutate(Group = factor(Group, levels  = c(city, "Benchmark - Oxford"))) %>%
    mutate(order = case_when(Group == city ~ 1, T ~ 2)) %>%
    arrange(order) %>%
    mutate(Group = reorder(Group, order)) %>%
    ungroup() %>% mutate(cumpct = cumsum(Percentage))

write_csv(pop_dist_group, file.path(tabular_dir, paste0(city_string, "_oxford_pop_dist.csv")))
message("Saved: _oxford_pop_dist.csv")


# Age structure: Young/Working/65+ over time (city only) ----------------------------------------
pop_dist_structure <- oxford %>%
    subset(Location == city & Indicator %in% pop_dist_inds) %>%
    select(Location, Indicator, starts_with('20'), Group) %>%
    mutate(Age_Bracket = substr(Indicator, 12, 20),
        Age_Bracket = factor(Age_Bracket, levels = unique(Age_Bracket))) %>%
    pivot_longer(cols = starts_with("20"), names_to = "Year", values_to = "Count") %>%
    mutate(Year = as.numeric(Year)) %>%
    subset(Year < 2022) %>%
    mutate(Group = case_when(
    Age_Bracket %in% c("0-4", "5-9","10-14") ~ "Young",
    Age_Bracket %in% c("65-69", "70-74","75-79", "80+") ~ "65+",
    T ~ "Working"),
    Group = factor(Group, levels = c("Young", "Working", "65+"))) %>%
    group_by(Year, Group) %>%
    summarize(Count = sum(Count), .groups = "drop") %>%
    group_by(Year) %>%
    mutate(Percent = Count / sum(Count), pct_sum = cumsum(Percent))

write_csv(pop_dist_structure, file.path(tabular_dir, paste0(city_string, "_oxford_age_structure.csv")))
message("Saved: _oxford_age_structure.csv")


# National shares: city % of national pop/GDP/employment ----------------------------------------
national_shares <- left_join(
  oxford %>% subset(Indicator %in% extra_inds) %>%
    select(Group, Location, Country, Indicator, Value = `2021`) %>%
    pivot_wider(values_from = Value, names_from = Indicator),
  oxford_countries %>% subset(Indicator %in% extra_inds) %>%
    select(Country, Indicator, Value = `2021`) %>%
    pivot_wider(values_from = Value, names_from = Indicator),
  by = c("Country" = "Country"),
  suffix = c("", "_national")) %>%
  mutate(`Population Share` = `Total population` / `Total population_national`,
         `GDP Share` = `GDP, real, US$ - Total` / `GDP, real, US$ - Total_national`,
         `Employment Share` = `Employment - Total` / `Employment - Total_national`) %>%
  select(Group, Location, contains("Share")) %>%
  arrange(desc(Group), desc(`Population Share`)) %>%
  mutate(Location = factor(Location, levels = unique(Location)))

national_shares_long <- national_shares %>%
  pivot_longer(cols = contains("Share"), names_to = "Indicator", values_to = "Percentage") %>%
  mutate(Indicator = factor(Indicator, levels = c("GDP Share", "Employment Share", "Population Share")))

write_csv(national_shares_long, file.path(tabular_dir, paste0(city_string, "_oxford_national_shares.csv")))
message("Saved: _oxford_national_shares.csv")


# Growth: GDP, employment, population timeseries ------------------------------------------------
pop_growth_years <- oxford %>% subset(Indicator == "Total population") %>%
    pivot_longer(cols = contains("20"), values_to = "Value", names_to = "Year") %>%
    mutate(Group, Location, Year = as.numeric(Year), Value, .keep = "used") %>%
    subset(between(Year, 2000, 2021)) %>%
    group_by(Group, Location) %>%
    mutate(Growth = Value / lag(Value) - 1) %>%
    slice_max(Year, n = 20)

emp_growth_years <- oxford %>% subset(Indicator == "Employment - Total") %>%
    pivot_longer(cols = contains("20"), values_to = "Value", names_to = "Year") %>%
    mutate(Group, Location, Year = as.numeric(Year), Value, .keep = "used") %>%
    subset(between(Year, 2000, 2021)) %>%
    group_by(Group, Location) %>%
    mutate(Growth = Value / lag(Value) - 1)

gdp_growth_years <- oxford %>% subset(Indicator == "GDP, real, US$ - Total") %>%
    pivot_longer(cols = contains("20"), values_to = "Value", names_to = "Year") %>%
    mutate(Group, Location, Year = as.numeric(Year), Value, .keep = "used") %>%
    subset(between(Year, 2000, 2021)) %>%
    group_by(Group, Location) %>%
    mutate(Growth = Value / lag(Value) - 1)

emp_longitude <- oxford %>% subset(Indicator %in% extra_inds) %>%
    select(Group, Location, Country, Indicator, matches('\\d')) %>%
    pivot_longer(cols = matches('^\\d'), names_to = "Year", values_to = "Value") %>%
    pivot_wider(values_from = Value, names_from = Indicator) %>%
    mutate(
    Year = as.numeric(Year),
    `Total employed` = `Employment - Total` * 1000) %>%
    arrange(Group) %>%
    subset(Year <= 2021 & !is.na(`Total employed`))

gdp_longitude <- oxford %>% subset(Indicator %in% extra_inds) %>%
    select(Group, Location, Country, Indicator, matches('\\d')) %>%
    pivot_longer(cols = matches('^\\d'), names_to = "Year", values_to = "Value") %>%
    pivot_wider(values_from = Value, names_from = Indicator) %>%
    mutate(
    Year = as.numeric(Year),
    GDP = `GDP, real, US$ - Total` * 1e6) %>%
    arrange(Group) %>%
    subset(Year <= 2021 & !is.na(`GDP`))

write_csv(pop_growth_years, file.path(tabular_dir, paste0(city_string, "_oxford_pop_growth.csv")))
write_csv(emp_growth_years, file.path(tabular_dir, paste0(city_string, "_oxford_emp_growth.csv")))
write_csv(gdp_growth_years, file.path(tabular_dir, paste0(city_string, "_oxford_gdp_growth.csv")))
write_csv(emp_longitude, file.path(tabular_dir, paste0(city_string, "_oxford_emp.csv")))
write_csv(gdp_longitude, file.path(tabular_dir, paste0(city_string, "_oxford_gdp.csv")))
message("Saved: _oxford_pop_growth.csv, _oxford_emp_growth.csv, _oxford_gdp_growth.csv, _oxford_emp.csv, _oxford_gdp.csv")


# GDP per capita ---------------------------------------------------------------------------------
gdppc <- oxford %>% subset(Indicator %in% extra_inds) %>%
    select(Group, Location, Country, Indicator, Value = `2021`) %>%
    pivot_wider(values_from = Value, names_from = Indicator) %>%
    mutate(`GDP per capita` = `GDP, real, US$ - Total` * 1e6  / (`Total population` * 1000)) %>%
    arrange(Group, -`GDP per capita`)

gdppc_longitude <- oxford %>% subset(Indicator %in% extra_inds) %>%
    select(Group, Location, Country, Indicator, matches('\\d')) %>%
    pivot_longer(cols = matches('^\\d'), names_to = "Year", values_to = "Value") %>%
    pivot_wider(values_from = Value, names_from = Indicator) %>%
    group_by(Location) %>%
    mutate(
    Year = as.numeric(Year),
    `GDP per capita` = `GDP, real, US$ - Total` * 1e6  / (`Total population` * 1000),
    growth = `GDP per capita` - lag(`GDP per capita`),
    growth_pct = growth/lag(`GDP per capita`)) %>%
    arrange(Group) %>%
    subset(Year <= 2021 & !is.na(`GDP per capita`))

write_csv(gdppc, file.path(tabular_dir, paste0(city_string, "_oxford_gdppc.csv")))
write_csv(gdppc_longitude, file.path(tabular_dir, paste0(city_string, "_oxford_gdppc_timeseries.csv")))
message("Saved: _oxford_gdppc.csv, _oxford_gdppc_timeseries.csv")


# Employment + GVA by sector -------------------------------------------------------------------
emp_shares <- subset(oxford, Indicator %in% emp_inds) %>%
    subset(Indicator != "Employment - Total") %>%
    select(Group, Location, Indicator, Value = `2021`) %>%
    group_by(Location, Group) %>%
    mutate(Indicator = str_replace(Indicator, ".*- ", ""),
        Share = Value / sum(Value)) %>%
    mutate(Indicator = str_replace(Indicator, "Transport, storage, information & communication services", "Transport & ICT"))

emp_shares2 <- emp_shares %>%
    ungroup() %>%
    group_by(Group, Indicator) %>%
    summarize(Share = median(Share), .groups = "drop") %>%
    arrange(desc(Group), desc(Share))

sector_order <- emp_shares2 %>% subset(Group == city) %>% .$Indicator %>% unique()
sector_order <- c(sector_order[which(sector_order != "Other")], "Other")

emp_shares <- emp_shares %>%
    mutate(Indicator = factor(Indicator, levels = sector_order)) %>%
    arrange(Indicator)

emp_shares2 <- emp_shares2 %>%
    mutate(Indicator = factor(Indicator, levels = sector_order))

emp_shares2 <- emp_shares2 %>%
    mutate(Share = case_when(Indicator == "Other" & Group == "Benchmark - Oxford" ~ Share * 2 / 6, T ~ Share))

gva_shares <- subset(oxford, Indicator %in% gva_inds) %>%
    subset(str_detect(Indicator, "Total", negate = T)) %>%
    select(Group, Location, Indicator, Value = `2021`) %>%
    group_by(Location, Group) %>%
    mutate(Indicator = str_replace(Indicator, ".*- ", "")) %>%
    mutate(Indicator = str_replace(Indicator, "Transport, storage, information & communication services", "Transport & ICT")) %>%
    mutate(Indicator = factor(Indicator, levels = sector_order)) %>%
    mutate(Share = Value / sum(Value)) %>%
    select(-Value)

gva_shares2 <- gva_shares %>%
    ungroup() %>%
    group_by(Group, Indicator) %>%
    summarize(Share = median(Share), .groups = "drop") %>%
    arrange(Group, Indicator)

ylims_shares <- c(0, max(c(emp_shares2$Share, gva_shares2$Share), na.rm = T) * 1.1)

write_csv(emp_shares2, file.path(tabular_dir, paste0(city_string, "_oxford_emp_sectors.csv")))
write_csv(emp_shares, file.path(tabular_dir, paste0(city_string, "_oxford_emp_sectors_individual.csv")))
write_csv(gva_shares2, file.path(tabular_dir, paste0(city_string, "_oxford_gva_sectors.csv")))
write_csv(gva_shares, file.path(tabular_dir, paste0(city_string, "_oxford_gva_sectors_individual.csv")))
message("Saved: _oxford_emp_sectors.csv, _oxford_gva_sectors.csv")


# Household income distribution -----------------------------------------------------------------
incomes <- oxford %>% subset(str_detect(Indicator, "PPP constant 2015 prices")) %>%
    select(Location, `Income Band`, Group, starts_with("20")) %>%
    mutate(Band = str_extract(`Income Band`, "^[^\\s]*") %>% str_replace("\u00e9", "-") %>% str_replace_all(",000", "K") %>% str_replace_all(",500", ".5K"),
        Band = case_when(Band == "Up" ~ "Up to $1,000",
                            Band == "Over" ~ "Over $250K",
                            T ~ Band),
        Band = factor(Band, levels = unique(Band))) %>%
    pivot_longer(cols = starts_with("20"), names_to = "Year", values_to = "Households") %>%
    mutate(Households = 1000 * Households,
        Year = as.numeric(Year))

incomes_city <- incomes %>% subset(Location == city & Year < 2022 & Year >= 2002) %>%
    group_by(Year) %>%
    mutate(Percent = Households / sum(Households),
        sum = sum(Households),
        pct_sum = cumsum(Percent)) %>%
    ungroup()

upper_income_bands <- c("$70K-100K", "$100K-150K", "$150K-200K", "$200K-$250K", "Over $250K")
upper_income <- subset(incomes_city, Band %in% upper_income_bands) %>%
    ungroup() %>%
    group_by(Year) %>%
    summarize(Households = sum(Households), Percent = sum(Percent), sum = sum[[1]], .groups = "drop") %>%
    mutate(Location = city, Group = city, Band = "Over $70K")

lower_income_bands <- c("Up to $1,000", "$1K-2K" ,"$2K-5K", "$5K-7.5K")
lower_income <- subset(incomes_city, Band %in% lower_income_bands) %>%
    ungroup() %>%
    group_by(Year) %>%
    summarize(Households = sum(Households), Percent = sum(Percent), sum = sum[[1]], .groups = "drop") %>%
    mutate(Location = city, Group = city, Band = "Under $5K")

incomes_city2 <-
    lower_income %>%
    bind_rows(subset(incomes_city, Band %ni% c(upper_income_bands, lower_income_bands))) %>%
    bind_rows(upper_income) %>%
    group_by(Year) %>%
    mutate(pct_sum = cumsum(Percent),
        Band = factor(Band, levels = c(lower_income$Band %>% unique(), levels(incomes_city$Band) %>% subset(. %ni% c(lower_income_bands, upper_income_bands)), upper_income$Band %>% unique()))) %>%
    ungroup() %>%
    filter(!is.na(Percent))

write_csv(incomes_city2, file.path(tabular_dir, paste0(city_string, "_oxford_incomes.csv")))
write_csv(incomes, file.path(tabular_dir, paste0(city_string, "_oxford_incomes_all.csv")))
message("Saved: _oxford_incomes.csv, _oxford_incomes_all.csv")

} # end if (in_oxford)

message("=== Oxford datacollection complete ===\n")
