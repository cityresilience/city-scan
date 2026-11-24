# USE_GCS <<- TRUE
# source(here("core/R/setup.R"))  # already sourced in scan-calculations.Rmd
# source(here("core/R/fns.R"))    # already sourced in scan-calculations.Rmd
source(here("core/R/pop-backup.R"))


aoi <- aoi %>% st_as_sf()

message("\nstarting pre-charting")
# Is city in Oxford Economics? --------------------------------------------------------------
oxford_locations <- readr::read_csv(oxford_location_file, col_types = "c")
oxford_locations_in_country <- dplyr::filter(oxford_locations, Country == country)
in_oxford <- city %in% oxford_locations_in_country$Location

# if so -> check oxford data path exists

# Reading in Oxford Economics data if available
if (!exists("oxford_full")) oxford_full <- read_csv(oxford_file,
    col_types = "cccccccccdddddddddddddddddddddddddddddddddddddddddcllldlcclcc") %>%
  # To rename a city (e.g., we did a scan for "Sarbagita" which is "Denpasar" in Oxford)
  # or to replace missing characters (e.g. "Lom�" ~ "Lomé") 
  mutate(Location = case_when(Location == "Lom�" ~ "Lomé", 
                              Location == "Yaound�" ~ "Yaoundé", 
                              T ~ Location))



# Set Fallback to manual or getting from GHS ---------------------------------------------------------------
pop_manual <- tryCatch({readr::read_csv("./manual-data-entry/pop.csv", col_types = "ccddc") %>% 
  mutate(Method = "Manual")}, error = function(e) tibble())

# GHS population data
pop_ghs <- tryCatch({get_ghs_pop_growth(city, country, aoi)}, error = function(e) tibble(Group = city))

# Population raster (worldpop) for ridges plot
tryCatch({
  wpop_df <- fuzzy_read(spatial_dir, "population.*.tif$") %>%
    as_tibble() %>%
    rename(pop = 1) %>%
    filter(!is.na(pop), pop > 0)
}, error = function(e) message("wpop_df not available"))
 
wpop_growth <- tryCatch({
  aoi_area <- sum(expanse(aoi %>% vect(), unit = "km"))
  fuzzy_read(tabular_dir, "worldpop_2015_2030.csv", read_csv) %>%
    rename_with(str_to_title) %>%
    mutate(
      Year = as.numeric(str_extract(Year, "\\d{4}")),
      Location = city,
      Country = country,
      Group = city,
      Area_km = round(aoi_area, 2)
    )
}, error = function(e) tibble(Group = city, Location = city))




# Check Population Data availability ---------------------------------------------------------------
 if (in_oxford) {

    pop <- oxford_full %>%
      subset(Location == city & Indicator == "Total population", select = '2021') %>%
      pull()

    pop_source <- "Oxford Economics"

  } else {

    sources <- list(
      `WorldPop Global 2 (2025)` = function() tryCatch(wpop_growth %>% slice_min(abs(Year - 2025), n = 1) %>%
                                 pull(Population), error = function(e) NULL),
      `GHS-POP` = function() tryCatch(get_ghs_pop_growth(city, country, aoi) %>% slice_min(abs(Year - 2021), n = 1) %>%
                                 pull(Population), error = function(e) NULL),
      `UN/DE` = function() tryCatch(un_de_pop_growth(city, country) %>% slice_max(Year) %>% summarize(Population = mean(Population)) %>% pull(Population), error = function(e) NULL)
    )

    pop <- NULL
    for (src in names(sources)) {
      pop <- sources[[src]]()
      if (!is.null(pop)) {
        pop_source <- src
        break
      }
    }
  }

# Benchmark cities if empty ---------------------------------------------------------------
# Auto-detect benchmark countries if not specified
if (is.null(nearby_countries_string) || nearby_countries_string == "") {
  tryCatch({
    # Load economic classification
    econ_class <- read_csv("source/countries_economies_classification.csv")

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

# Benchmark city selection -------------------------------------------------------------------------

nearby_cities <- if (is.null(nearby_countries_string)) NULL else {
    oxford_locations %>%
        subset(str_detect(tolower(Country), nearby_countries_string)) %>%
        subset(Location != Country & !str_detect(Location, "Total")) %>%
        pull(Location)
}

bm_cities_oxford <- if (is.null(nearby_countries_string)) NULL else { oxford_full %>%
    select(Location, Country, Indicator, `2021`) %>%
    subset(str_detect(tolower(Country), nearby_countries_string)) %>%
    subset(Location %in% nearby_cities & Indicator == "Total population") %>%
    subset((between(`2021`, pop*.5, pop*1.5) | Country == country) & Location != city) %>%
    pull(Location)
  
}

# Benchmark cities: use manual selection if defined, otherwise auto-detect from Oxford
bm_cities <- if (length(bm_cities_manual) > 0) {
  bm_cities_manual %>% unique() %>% which_not(city)
} else {
  bm_cities_oxford %>% unique() %>% which_not(city)
}


# Building Population Data -------------------------------------------------------------------------
oxford <- subset(oxford_full, Location %in% c(city, bm_cities)) %>%
    mutate(Group = case_when(Location == city ~ Location, 
                             T ~ "Benchmark") %>% factor(levels = c(city, "Benchmark"))
                             )


# DUMMY DF
pop_longitude <- tibble() # dummy df

# Check if WorldPop Global2 available for main city (prioritize over Oxford)
use_wpop_for_city <- !is.null(wpop_growth) && nrow(wpop_growth) > 1

# Add WorldPop Global2 for main city if available (priority over Oxford)
if (use_wpop_for_city) {
    message("Using WorldPop Global2 population data for ", city)
    pop_longitude <- pop_longitude %>%
        bind_rows(wpop_growth %>% mutate(Source = "WorldPop Global 2", Method = "WorldPop Global2", Group = city))
}

# WorldPop from sibling scan directories for ALL benchmark cities (priority over Oxford)
bm_cities_no_city <- setdiff(bm_cities, city)
wp_found_cities <- character()
if (length(bm_cities_no_city) > 0) {
    message("Looking for WorldPop CSVs in sibling scan directories...")
    wp_siblings <- get_worldpop_from_siblings(bm_cities_no_city, country)
    if (nrow(wp_siblings$data) > 0) {
        pop_longitude <- pop_longitude %>%
            bind_rows(wp_siblings$data %>% mutate(Group = "Benchmark"))
        wp_found_cities <- wp_siblings$found_cities
    }
}

# Oxford as fallback for benchmarks not found via WorldPop; also main city if in_oxford and no WorldPop
oxford_pop_subset <- if (in_oxford && !use_wpop_for_city) {
    subset(oxford, Indicator == "Total population" & !Location %in% wp_found_cities)
} else {
    subset(oxford, Indicator == "Total population" & Location != city & !Location %in% wp_found_cities)
}

if (nrow(oxford_pop_subset) > 0) {
    pop_longitude <- pop_longitude %>% bind_rows(
        oxford_pop_subset %>%
        select(Group, Location, Country, Indicator, matches('\\d')) %>%
        pivot_longer(cols = matches('^\\d'), names_to = "Year", values_to = "Value") %>%
        pivot_wider(values_from = Value, names_from = Indicator) %>%
        mutate(
        Year = as.numeric(Year),
        Population = `Total population` * 1000,
        Source = "Oxford",
        Method = "Oxford",
        .keep = "unused") %>%
        arrange(Group) %>%
        subset(Year <= 2021 & !is.na(Population))
        )

    # Get Area data for oxford pop
    oxford_areas <- read_csv(oxford_areas_file, col_types = "ccd") %>%
        mutate(Location = str_to_title(Location)) %>%
        filter(Location %in% str_to_title(pop_longitude$Location)) %>%
        select(-Country)

    if (any(duplicated(oxford_areas$Location))) stop("Multiple Oxford Economics cities have been matched with the same name")

    pop_longitude <- left_join(pop_longitude, oxford_areas, by = "Location")
    if ("Area_km.x" %in% names(pop_longitude)) {
        pop_longitude <- pop_longitude %>%
            mutate(Area_km = coalesce(Area_km.x, Area_km.y)) %>%
            select(-Area_km.x, -Area_km.y)
    }
}

# Remaining cities not yet in pop_longitude
non_oxford_cities <- setdiff(c(city, bm_cities_manual), pop_longitude$Location %>% unique()) %>% .[!duplicated(.)]

# Use GHS for main city if not yet added
if (city %in% non_oxford_cities && !is.null(pop_ghs) && nrow(pop_ghs) > 0) {
    message("Using GHS population data for ", city)
    pop_longitude <- pop_longitude %>%
        bind_rows(pop_ghs) %>% mutate(Group = city)
    non_oxford_cities <- setdiff(non_oxford_cities, city)
}

# for the rest, use citypopulation.DE / UN data
if (length(non_oxford_cities) > 0) {
    non_oxford_pop <- non_oxford_cities %>%
        lapply(function(x) {
            country_temp <- non_oxford_cities[(non_oxford_cities == x)][1] %>% names()
            if (length(country_temp) != 0) if (country_temp != "") country <- country_temp
            data <- get_de_pop_growth(x, country = country)
            return(data)
            }) %>%
        bind_rows() %>%
        mutate(Location = str_extract(tolatin(Location), tolatin(c(city, bm_cities)) %>% 
            paste(collapse = "|")),
                Method = "get_de_pop_growth()",
            Group = case_when(Location == city ~ city, T ~ "Benchmark"))

    pop_longitude <- pop_longitude %>%
        bind_rows(non_oxford_pop)
}


# Final Population data assembly -----------------------------------------------------------------------
# add manual data if exists
if (nrow(pop_manual) > 0) pop_longitude <- bind_rows(pop_longitude, pop_manual) %>%
  filter(!is.na(Population))

# Final Populatin data
if (!"Area_km" %in% names(pop_longitude)) pop_longitude$Area_km <- NA_real_
pop_longitude <- pop_longitude %>%
  mutate(Area_km = case_when(
         Area_km == 0 ~ NA_real_,
         T ~ Area_km
       )) %>%
  group_by(Year, Location) %>%
  fill(Area_km, Population, Country, .direction = "updown") %>%
  ungroup() %>%
  distinct(Location, Year, Population, .keep_all = T) 


# message('pop_longitude - Ready')
# print(pop_longitude %>% names())
# print(pop_longitude %>% head(2))

# Indicators selection &  helpers  -----------------------------------------------------------------------
countries <- oxford$Country %>% unique()
oxford_countries <- subset(oxford_full, Country %in% countries) %>%
  subset(str_detect(Location, "- Total") | Location %in% countries, select = -Location)

indicators <- select(oxford, Indicator) %>% distinct()
pop_dist_inds <- subset(indicators, str_detect(Indicator, "Population") & 
                          Indicator %ni% c("Population 0-14", "Population 15-64", "Population 65+")) %>% pull()
emp_inds <- subset(indicators, str_detect(Indicator, "Employment")) %>% pull()
gva_inds <- subset(indicators, str_detect(tolower(Indicator), "gross value added, real, us")) %>% pull()
extra_inds <- c("Total population", "Employment - Total", "GDP, real, US$ - Total")


# POPULATION ANALYSIS
# Population growth ----------------------------------------------------------------------------------
pop_growth <- pop_longitude %>% filter(Group == city) %>% select(-Area_km)
pop_growth <- arrange(pop_growth, Year) 
write_csv(pop_growth, file.path(tabular_dir,"population-growth.csv"))




# not sure what below is for...
# pop_capital <- read_xls("/Users/bennotkin/Documents/world-bank/crp/city-scans/03-multi-scan-materials/WUP2018-F13-Capital_Cities.xls", skip = 16)
# pop_capital %>% filter(str_detect(`Country or area`, nearby_countries_string))

# Population Density ------------------------------------------------------------------------------------
target_year <- as.numeric(format(Sys.Date(), "%Y"))

density <- pop_longitude %>%
    filter(Area_km != 0 & !is.na(Area_km)) %>%
    # For each location, pick the year closest to current year for fair comparison
    slice_min(order_by = abs(Year - target_year), by = Location, with_ties = FALSE)

density$Density <- density$Population/density$Area_km
density <- density %>% arrange(desc(Density))
# density <- density %>% mutate(Location = str_replace(Location, "Nur-Sultan", "Astana")) 

city_pop_density <- density[which(density$Location == city), "Density"]

# Population Distirbution --------------------------------------------------------------------------------
if (in_oxford) {
    pop_dist_long <- subset(oxford, Location %in% c(city, bm_cities) & Indicator %in% pop_dist_inds) %>%
        select(Location, Indicator, `2021`, Group) %>%
        # group_by(Group, Indicator) %>%
        # summarize(`2021` = mean(`2021`)) %>%
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
        mutate(Group = factor(Group, levels  = c(city, "Benchmark"))) %>%
        mutate(order = case_when(Group == city ~ 1, T ~ 2)) %>%
        arrange(order) %>%
        mutate(Group = reorder(Group, order)) %>%
        ungroup() %>% mutate(cumpct = cumsum(Percentage))
    } 


# WorldPop Age Structure --------------------------------------------------------------------------------

age_file <- list.files(tabular_dir)[!is.na(str_match(list.files(tabular_dir), ".*_demographics.csv"))]


if (length(age_file) > 0) {
    pop_dist_group_wp <- read_csv(file.path(tabular_dir, age_file), col_types = "ffd") %>% 
        rename(Age_Bracket = age_group, Sex = sex, Count = population) %>%
        mutate(Sex = fct_recode(Sex, "Female" = "f", "Male" = "m")) %>%
        mutate(Age_Bracket = forcats::fct_collapse(Age_Bracket, "0-4" = c("0-1", "1-4"))) %>%
        group_by(Age_Bracket, Sex) %>% summarize(Count = sum(Count), .groups = "drop") %>%
        # mutate(Age_Bracket = factor(Age_Bracket, levels = unique(Age_Bracket))) %>%
        mutate(Percentage = Count/sum(Count)) %>%
        group_by(Sex) %>%
        mutate(
        Sexed_Percent = Count/sum(Count),
        Sexed_Percent_cum = cumsum(Sexed_Percent)) %>% 
        ungroup()
}

# Oxford Economics Age Structure --------------------------------------------------------------------------------
if (in_oxford) {
  # Using age groups 0-14, 15-64, 65+
  # https://databank.worldbank.org/metadataglossary/world-development-indicators/series/SP.POP.DPND.YG
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
}


# ECONOMIC ANALYSIS
# Share of GDP, Employment, Population ---------------------------------------------------------------------------------
if (in_oxford) {
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
}

# GDP, Pop, Emp Growth ---------------------------------------------------------------------------------
if (in_oxford) {
    pop_growth_years <- oxford %>% subset(Indicator == "Total population") %>%
        pivot_longer(cols = contains("20"), values_to = "Value", names_to = "Year") %>%
        mutate(Group, Location, Year = as.numeric(Year), Value, .keep = "used") %>%
        subset(between(Year, 2000, 2021)) %>%
        group_by(Group, Location) %>%
        mutate(Growth = Value / lag(Value) - 1) %>% 
        slice_max(Year, n = 20)

    pop_growth2 <- pop_growth_years %>%
        summarize(`Population Growth` = mean(Growth, na.rm = T), .groups = "drop") %>%
        arrange(desc(`Population Growth`))
 
    emp_growth <- oxford %>% subset(Indicator == "Employment - Total") %>%
        pivot_longer(cols = contains("20"), values_to = "Value", names_to = "Year") %>%
        mutate(Group, Location, Year = as.numeric(Year), Value, .keep = "used") %>%
        subset(between(Year, 2000, 2021)) %>%
        group_by(Group, Location) %>%
        mutate(Growth = Value / lag(Value) - 1) %>%
        # slice_max(Year, n = 20) %>%
        subset(between(Year, 2000, 2021)) %>%
        summarize(`Employment Growth` = mean(Growth, na.rm = T), .groups = "drop") %>%
        arrange(desc(`Employment Growth`))
  
    emp_growth_years <- oxford %>% subset(Indicator == "Employment - Total") %>%
        pivot_longer(cols = contains("20"), values_to = "Value", names_to = "Year") %>%
        mutate(Group, Location, Year = as.numeric(Year), Value, .keep = "used") %>%
        subset(between(Year, 2000, 2021)) %>%
        group_by(Group, Location) %>%
        mutate(Growth = Value / lag(Value) - 1) # %>%
        # slice_max(Year, n = 10) %>%
        # filter(between(Year, 2000, 2021)) %>%
        # summarize(`Employment Growth` = mean(Growth, na.rm = T), .groups = "drop") %>%
        # arrange(desc(`Employment Growth`))
    
    gdp_growth <- oxford %>% subset(Indicator == "GDP, real, US$ - Total") %>%
        pivot_longer(cols = contains("20"), values_to = "Value", names_to = "Year") %>%
        mutate(Group, Location, Year = as.numeric(Year), Value, .keep = "used") %>%
        subset(between(Year, 2000, 2021)) %>%
        group_by(Group, Location) %>%
        mutate(Growth = Value / lag(Value) - 1) %>%
        # slice_max(Year, n = 10) %>%
        filter(between(Year, 2000, 2021)) %>%
        summarize(`GDP Growth` = mean(Growth, na.rm = T), .groups = "drop") %>%
        arrange(desc(`GDP Growth`))
    
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
    
}

# GDP Per Capita ---------------------------------------------------------------------------------
if (in_oxford) {
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
  
}

# Share of Employment by Sector ----------------------------------------------------------------
if (in_oxford) {
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
        mutate(Share = case_when(Indicator == "Other" & Group == "Benchmark" ~ Share * 2 / 6, T ~ Share))
    
    # Gross value added, by sector ----
    # Data is with employment above
  
    # emp_shares3 <- bind_rows(emp_shares, emp_shares2)
    
    gva_shares <- subset(oxford, Indicator %in% gva_inds) %>% 
        subset(str_detect(Indicator, "Total", negate = T)) %>%
        select(Group, Location, Indicator, Value = `2021`) %>%
        group_by(Location, Group) %>% 
        mutate(Indicator = str_replace(Indicator, ".*- ", "")) %>%
        mutate(Indicator = str_replace(Indicator, "Transport, storage, information & communication services", "Transport & ICT")) %>%
        mutate(Indicator = factor(Indicator, levels = sector_order)) %>%
        mutate(Share = Value / sum(Value)) %>%
        select(-Value) #%>%
    # pivot_wider(names_from = Indicator, values_from = Share) %>%
    # arrange(Group) %>% View()
    
    gva_shares2 <- gva_shares %>% 
        ungroup() %>%
        group_by(Group, Indicator) %>%
        summarize(Share = median(Share), .groups = "drop") %>%
        arrange(Group, Indicator)
    
    ylims_shares <- c(0, ceiling(max(emp_shares$Share, gva_shares$Share) * 10) /10)
}
# Economic Inequality ---------------------------------------------------------------------------------
if (in_oxford) {
  # subset(oxford, !is.na(`Income Band`)) %>% select(`Income Band`) %>% unique() %>% subset(str_detect(`Income Band`, "PPP constant 20"))
  
    incomes <- oxford %>% subset(str_detect(Indicator, "PPP constant 2015 prices")) %>%
        select(Location, `Income Band`, Group, starts_with("20")) %>% 
        mutate(Band = str_extract(`Income Band`, "^[^\\s]*") %>% str_replace("�", "-") %>% str_replace_all(",000", "K") %>% str_replace_all(",500", ".5K"),
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
    
    # "$35K-70K", "$70K-100K", "$100K-150K", "$150K-200K", "$200K-$250K", "Over $250K"
    upper_income_bands <- c("$70K-100K", "$100K-150K", "$150K-200K", "$200K-$250K", "Over $250K")
    upper_income <- subset(incomes_city, Band %in% upper_income_bands) %>%
        ungroup() %>%
        group_by(Year) %>%
        summarize(Households = sum(Households), Percent = sum(Percent), sum = sum[[1]], .groups = "drop") %>%
        mutate(Location = city, Group = city, Band = "Over $70K")
    
    # "Up to $1,000", "$1K-2K" ,"$2K-5K", "$5K-7.5K", "$7.5K-10K"
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
  

}

# WSF
# Urban Built-up Area -----------------------------------------------------------------------------

wsf_file <- str_subset(list.files(tabular_dir, full.names = T), "(?<!flood_)wsf(?!.*(tracker|stats|harmonized)).*\\.csv$")

if (length(wsf_file) > 0)  {
    wsf_file <- wsf_file[1]
    wsf <- read_csv(wsf_file, col_types = "dd")
    wsf <- wsf %>%
        rename(Year = 1) %>%
        select(Year, uba_km2 = any_of(c("AREA_sq_km", "cumulative sq km", "cumulative_sq_km"))) %>%
        mutate(growth_pct = (uba_km2 / lag(uba_km2) - 1), growth_km2 = uba_km2 - lag(uba_km2))
}

# WSF Tracker ---------------------------------------------------------------------------------
wsf_tracker_file <- str_subset(list.files(tabular_dir, full.names = T), "wsf_tracker.*\\.csv$")

if (length(wsf_tracker_file) > 0)  {
    wsf_tracker_file <- wsf_tracker_file[1]
    wsf_tracker <- read_csv(wsf_tracker_file)

    wsf_tracker <- wsf_tracker %>%
        mutate(date = if ("month" %in% names(.)) zoo::as.yearmon(paste(.data$year, .data$month, sep = "-")) else zoo::as.yearmon(.data$year)) %>%
        select(date, uba_km2 = any_of(c("AREA_sq_km", "cumulative sq km", "cumulative_sq_km"))) %>%
        mutate(growth_pct = (uba_km2 / lag(uba_km2) - 1), growth_km2 = uba_km2 - lag(uba_km2))
}
    
# Landcover ----------------------------------------------------------------------------------
tryCatch({
  lc <- read_csv(str_subset(list.files(tabular_dir, full = T), "lc.csv"), col_types = "cd") %>%
    rename(`Land Cover` = `Land Cover Type`, Count = `Pixel Count`) %>%
    filter(!is.na(`Land Cover`)) %>%
    mutate(Percent = Count/sum(Count)) %>%
    arrange(desc(Percent)) %>%
    mutate(`Land Cover` = factor(`Land Cover`, levels = `Land Cover`)) %>%
    mutate(Percent = round(Percent, 4))
}, error = function(e) message("lc not available"))

# Elevation ----------------------------------------------------------------------------------
tryCatch({
  elevation <- read_csv(str_subset(list.files(tabular_dir, full = T), "elevation.csv"), col_types = "cd") %>%
    subset(!is.na(Bin)) %>%
    mutate(Elevation = as.numeric(str_replace(Bin, "-.*", "")),
           Bin = factor(Bin, levels = Bin),
           percent = Count/sum(Count))
}, error = function(e) message("elevation not available"))

# Slope ----------------------------------------------------------------------------------
tryCatch({
  slope <- read_csv(str_subset(list.files(tabular_dir, full = T), "slope.csv"), col_types = "cd") %>%
    subset(!is.na(Bin)) %>%
    mutate(Slope = as.numeric(str_replace(Bin, "[-+].*", "")),
           Bin = factor(Bin, levels = Bin),
           percent = Count/sum(Count))
}, error = function(e) message("slope not available"))




# FLOOD ANLAYSIS 
# Flood OSM data ------------------------------------------------------------------
flood_osm_file <- list.files(tabular_dir, full.names = T) %>% str_subset("flood_osm")

if (length(flood_osm_file) == 1) {
  flood_osm <- read_csv(flood_osm_file, col_types = "cfddd") %>%
    mutate(
      type = forcats::fct_relabel(type, \(x) str_replace(x, "_2020", "")),
      string = paste(pois_in_flood_zone, "in", total_pois)) %>%
           # string = case_when(
           #   # total_pois == 0 ~ "NONE EXIST",
           #   pois_in_flood_zone == 0 ~ "no",
           #   T ~ string)) %>%
    data.frame()
} else {
  if (length(flood_osm_file) == 0) {
    warning("Flood OSM file does not exist. Is it named differently?<br><br>")
  }
  if (length(flood_osm_file) > 1) {
    warning("Too many files in tabular/ match flood_osm pattern")
  }
}

# Flood Road data ------------------------------------------------------------------
flood_road_file <- list.files(tabular_dir, full.names = T) %>% str_subset("flood_road")

if (length(flood_road_file) == 1) {
  flood_road <- read_csv(flood_road_file, col_types = "fdd") %>%
    mutate(type = forcats::fct_relabel(type, \(x) str_replace(x, "_2020", ""))) %>%
    data.frame()
} else {
  if (length(flood_road_file) == 0) {
    warning("Flood road file does not exist. Is it named differently?<br><br>")
  }
  if (length(flood_road_file) > 1) {
    warning("Too many files in tabular/ match flood_road pattern")
  }
}

# Flood String Fixes ------------------------------------------------------------------
flood_string <- function(flood_type) {
  stopifnot(flood_type %in% c("fluvial", "pluvial", "coastal", "comb"))
  if (exists("flood_road")) {
    roads_pct <- flood_road %>% .[.$type == flood_type, "percentage_in_flood_zones"] %>%
      round(1) %>% paste0("%")
    roads_string <- paste(roads_pct, "of major roads,")
    if (roads_pct == "0%" && flood_road %>% .[.$type == flood_type, "total_major_road_meter"] == 0) {
      roads_string <- "NO ROADS RECORDED IN AOI     "
    }
  } else roads_string <- "NO ROADS FLOOD FILE     "
  if (exists("flood_osm")) {
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

# Flood WSF ------------------------------------------------------------------
tryCatch({
  flood_file <- str_subset(list.files(tabular_dir, full.names = T), "flood_wsf.csv")
  wsf_flood <- full_join(select(wsf, -starts_with("growth")), read_csv(flood_file), by = c("Year" = "year")) %>%
    rename(combined_2020 = comb_2020)
}, error = function(e) message("wsf_flood not available"))

# Gather Flood Data ------------------------------------------------------------------
gather_flood_data <- function(flood_type) {
  if (!exists("wsf_flood")) return(NULL)
  df <- select(wsf_flood, Year, uba_km2, uba_km2_exposed = contains(flood_type))
  if ("uba_km2_exposed" %ni% names(df)) {
    no_data_df <- tibble(Year = wsf$Year, uba_km2_exposed = 0)
    return(no_data_df)
  }
  df <- 
      mutate(df,
        growth_pct = scales::percent(uba_km2_exposed / lag(uba_km2_exposed) - 1, accuracy = 0.01),
        percent_uba_exposed = scales::percent(uba_km2_exposed/uba_km2, accuracy = 0.01))
  return(df)
}

# Flood Population Data ------------------------------------------------------------------
flood_pop_file <- list.files(tabular_dir, full.names = T) %>% str_subset("flood_pop")
if (length(flood_pop_file) == 1) {
  flood_pop <- read_csv(flood_pop_file, col_types = "fd") %>%
    mutate(type = forcats::fct_relabel(type, \(x) str_replace(x, "_2020", ""))) %>%
    data.frame()
} else {
  if (length(flood_pop_file) == 0) {
    warning("Flood pop file does not exist. Is it named differently?<br><br>")
  }
  if (length(flood_pop_file) > 1) {
    warning("Too many files in tabular/ match flood_pop pattern")
  }
}

# Flood Population Area ------------------------------------------------------------------
flood_pop_area <- function(flood_type) {
  stopifnot(flood_type %in% c("fluvial", "pluvial", "coastal", "comb"))
  if (exists("flood_pop") && nrow(flood_pop) > 0) {
    pop_pct <- flood_pop %>% .[.$type == flood_type, "exposed_dense_pop_pct"] %>%
      round(1) %>% paste0("%")
    paste("Percentage of population dense areas (>60th percentile density) in flood zone:", paste_bold(pop_pct))
  } else "Pop flood file not found or empty"
}

# Flood data - only create if wsf_flood exists
if (exists("wsf_flood")) {
  # Fluvial
  fu <- gather_flood_data("fluvial")
  # Pluvial
  pu <- gather_flood_data("pluvial")
  # Coastal
  cu <- gather_flood_data("coastal")
  # Combined
  comb <- gather_flood_data("combined")
  pufu <- bind_rows(
      if (any(fu$uba_km2_exposed > 0)) fu %>% mutate(type = "River") else NULL,
      if (any(pu$uba_km2_exposed > 0)) pu %>% mutate(type = "Rainwater") else NULL,
      if (any(cu$uba_km2_exposed > 0)) cu %>% mutate(type = "Coastal") else NULL,
      comb %>% mutate(type = "Combined")) %>%
    mutate(type = factor(type, levels = c("Combined", "River", "Rainwater", "Coastal")))
}

# Flood Events ----------------------------------------------------------------------------------
# Dartmouth Flood Observatory - read from GCP flood-archive folder
flood_archive <- read_sf(flood_archive_file) %>%
  st_transform("EPSG:4326")

if (nrow(flood_archive) > 0) {
  flood_archive <- st_make_valid(flood_archive)
  flood_archive <- flood_archive[st_is_valid(flood_archive),] %>% st_transform(st_crs(aoi))

  intersections <- which(apply(st_intersects(flood_archive, aoi, sparse = F), 1, any))

  flood_archive <- flood_archive[intersections,]

  floods <- st_drop_geometry(flood_archive) %>%
    select(BEGAN, ENDED, DEAD, DISPLACED, MAINCAUSE, SEVERITY)

  flood_text_all <- floods %>% mutate(
    severity = ordered(SEVERITY, levels = c(1, 1.5, 2), labels = c("Large event", "Very large event", "Extreme event")),
    duration = paste(ENDED - BEGAN, "days"),
    fatalities = paste(scales::label_comma()(DEAD), "fatalities"),
    displaced = paste(scales::label_comma()(DISPLACED), "displaced"),
    line1 = toupper(paste(lubridate::month(BEGAN, label = T, abbr = F), lubridate::year(BEGAN))),
    line2 = paste(severity, (MAINCAUSE), sep = ", "),
    line3 = paste(as.character(duration), fatalities, displaced, sep = ", "),
    text = paste0(line1, ": ", line2, "\n", line3),
    mag = normalize(DEAD) * normalize(DISPLACED) * SEVERITY,
    begin_day = lubridate::yday(BEGAN),
    end_day = lubridate::yday(ENDED),
    begin_month = lubridate::month(BEGAN),
    end_month = lubridate::month(ENDED),
    begin_year = lubridate::year(BEGAN) + begin_day/1000, # The /1000 helps keep labels in proper vertical order
    end_year = lubridate::year(ENDED))

  # flood_text_all2[which(order(flood_text_all2$mag, decreasing = TRUE) > 10),"text"] <- NA
  flood_text_all[which(rank(-flood_text_all$mag) > 10),"text"] <- NA
  # flood_text_all2[order(flood_text_all2$mag, decreasing = T)[1:10],"text"]
} else {
  warning("Flood archive data not available - skipping flood events analysis")
  floods <- tibble(BEGAN = as.Date(character()), ENDED = as.Date(character()),
                   DEAD = numeric(), DISPLACED = numeric(), MAINCAUSE = character(), SEVERITY = numeric())
  flood_text_all <- tibble()
}


# EARTHQUAKE ----------------------------------------------------------------------------------
get_earthquake_data <- function() {
  library(httr2)
  # Previously, in httr, used set_cookies(`csrftoken` = "CJOWAoXjdFb7fL1Xf3asS9mj6GVJmbvvIKj365nRxupF27lO5UfkZECjtZoHLuuD")
  resps <- request("http://www.ngdc.noaa.gov/hazel/hazard-service/api/v1/earthquakes") %>%
    req_url_query(minYear = 1900, maxYear = lubridate::year(Sys.Date())) %>%
    req_perform_iterative(iterate_with_offset("page"))
  eq <- resps %>%
    resps_successes() %>%
    resps_data(\(resp) bind_rows(resp_body_json(resp)$items)) %>%
    bind_rows()
    return(eq)
}

eq <- get_earthquake_data()

# # CYCLONES ----------------------------------------------------------------------------------
# # Read cyclones from https://www.ncei.noaa.gov/products/international-best-track-archive
# # Haven't investigated why this isn't working
# # cyclones <- curl_and_delete(
# #     "https://www.ncei.noaa.gov/data/international-best-track-archive-for-climate-stewardship-ibtracs/v04r00/access/shapefile/IBTrACS.since1980.list.v04r00.lines.zip",
# #     FUN = read_sf) %>%
# #   st_transform("EPSG:4326")
cyclones <- read_sf(cyclone_archive_file) %>%
  st_transform("EPSG:4326")
# plot(cyclones)

cyclones_near_index <- st_is_within_distance(aoi, cyclones, as_units(250, "km"))
cyclones_near <- cyclones[cyclones_near_index[[1]],]
cyclones_near$distance_km <- drop_units(st_distance(st_centroid(aoi), cyclones_near)[1,])/1000
cyclones_near <- cyclones_near %>% st_shift_longitude()

# cyclones_near$LON <- cyclones_near %>% st_coordinates() %>% .[,"X"]



# PHOTOVOLTAIC POTENTIAL (PV)
aoi_largest <- aoi %>% vect() %>% .[which.max(expanse(.)),,] %>% project("EPSG:4326")

setGDALconfig("GS_NO_SIGN_REQUEST=YES")
monthly_pv <- rast("/vsigs/city-scan-global-data/globalsolar/PVOUT-monthly.tif") %>%
  terra::extract(aoi_largest, include_area = T) %>%
  .[,-1] %>% as.matrix() %>%
  { data.frame(
    month = 1:12,
    max = matrixStats::colMaxs(.),
    min = matrixStats::colMins(.),
    mean = colMeans(.)
    )}




tryCatch({
  fwi_file <- str_subset(list.files(tabular_dir, full = T), "fwi")
  fwi <- read_csv(fwi_file, col_types = "dd")
}, error = function(e) message("fwi not available"))
# PLOT CHECKS