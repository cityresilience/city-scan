#  Defining the UN Data and citypopulation.de pop function because it is used as backup in Oxford and in Density


get_un_pop_growth <- function(city, country = country) {
  # UN Data — download from GCS if not already available
  if (!exists("undata_file") || !file.exists(undata_file)) {
    undata_file <- tempfile(fileext = ".csv")
    tryCatch(
      googleCloudStorageR::gcs_get_object("Population/undata-pop.csv", bucket = "city-scan-global-data", saveToDisk = undata_file),
      error = function(e) { warning(paste0("Could not download undata: ", e$message)); return(NULL) }
    )
  }
  if (!file.exists(undata_file)) {
    warning("undata_file not available")
    return(NULL)
  } else {
    pop_growth_undata <- read_csv(undata_file,
                                  col_types = "cdccccccddc", n_max = 69490) %>%
      filter(`Country or Area` == country) %>%
      filter(Sex == "Both Sexes") %>%
      filter(str_detect(tolower(tolatin(City)), tolower(tolatin(city)))) %>%
      select(Location = City, Year, Population = Value) %>%
      mutate(Source = "UN Data") %>%
      arrange(Year)
    return(pop_growth_undata)
  }
}  


get_de_pop_growth <- function(city, country = country) {
  tryCatch({
    # citypopulation.de
    if (tolower(tolatin(country)) == "sao tome and principe") country <- "saotome"

    url <- paste0("https://www.citypopulation.de/en/", str_replace_all(tolower(country), " ", ""), "/cities/")
    table_ids = c("adminareas", "largecities", "citysection")


    de <- read_html(url) %>%
          html_node(paste0("section#", "citysection")) %>%
          html_node("table") %>%
          html_table()

    nomatim <- paste0(
      "https://nominatim.openstreetmap.org/search?",
      "city=", URLencode(city),
      "&country=", URLencode(country),
      "&format=json&polygon_geojson=1&limit=1"
    ) %>%
      fromJSON() %>%
      filter(
        class == 'boundary',
        type == 'administrative',
        addresstype %in% c('city', 'town')
      )

    if (nrow(nomatim) == 0) {
      geo <- list(area = NA, addresstype = NA)
    } else {
      area <- nomatim %>%
        pull(geojson) %>%
        toJSON(auto_unbox = TRUE) %>%
        geojson_sfc() %>%
        st_make_valid() %>%
        st_sf(crs = 4326) %>%
        st_transform(32628) %>%
        st_area()

      geo <- list(area = as.numeric(area) / 1e6, addresstype = nomatim$addresstype[1])
    }

    pop_growth_de <- de %>%
      select(Location = Name, contains("Population")) %>%
      filter(str_detect(tolower(tolatin(Location)), tolower(tolatin(city)))) %>%
      pivot_longer(cols = contains("Population"), values_to = "Population", names_to = "Year") %>%
      mutate(
        Location = Location,
        Country = country,
        Year = str_extract(Year, "\\d{4}") %>% as.numeric(),
        Population = str_replace_all(Population, ",", "") %>% as.numeric(),
        Source = "citypopulation.de / OSM",
        OSM_Address_type = if(!is.null(geo$addresstype)) geo$addresstype else NA,
        Area_km = if(!is.null(geo$area)) geo$area else NA,
        .keep = "unused") %>%
      arrange(Year)

    if (nrow(pop_growth_de) == 0) warning("No population data detected in citypopulation.de table<br><br>")
    if (length(unique(pop_growth_de$Location)) > 1) warning("More than one city name in citypopulation.de table\n")

    return(pop_growth_de)
  }, error = function(e) {
    warning(paste0("Error in get_de_pop_growth: ", e$message))
    return(tibble(
      Location = character(),
      Country = character(),
      Year = numeric(),
      Population = numeric(),
      Source = character(),
      OSM_Address_type = character(),
      Area_km = numeric()
    ))
  })
}

un_de_pop_growth <- function(city, country) {
  # Select whether to use citypopulation.de or UN data based on which has more data
  # Alternatively, can plot both, coloring each line by Source column
  pop_growth <- bind_rows(get_un_pop_growth(city, country),
                          get_de_pop_growth(city, country))
  return(pop_growth)
}


# GHS Population Growth Data (yearly totals)
get_ghs_pop_growth <- function(city = city, country = country, aoi) {
  # GHS-POP years: every 5 years from 1975 to 2030
  ghs_years <- seq(1975, 2030, 5)

  pop_growth_ghs <- bind_rows(
    Filter(Negate(is.null), lapply(ghs_years, function(year) {
      tryCatch({
        # Read GHS population raster for this year
        pattern <- paste0("ghs_pop_E", year, ".*.tif$")
        ghs_raster <- fuzzy_read(spatial_dir, pattern)

        # Clip raster to AOI before summing
        ghs_clipped <- terra::crop(ghs_raster, aoi %>% vect(), mask = TRUE)

        # Calculate total population (sum of all pixel values)
        total_pop <- sum(values(ghs_clipped), na.rm = TRUE)

        # Calculate area in km² (convert from m² to km²)
        aoi_area <- sum(expanse(aoi %>% vect(),, unit = "km"))

        tibble(
          Location = city,
          Country = country,
          Year = year,
          Population = round(total_pop),
          Area_km = round(aoi_area, 2),
          Source = "GHS-POP",
          Method = "GHS-POP R2023A"
        )
      }, error = function(e) {
        # Print error for debugging
        warning(paste0("Error processing year ", year, ": ", e$message))
        NULL
      })
    }))
  )

  if (nrow(pop_growth_ghs) == 0) {
    warning("No GHS population data found in spatial_dir")
    return(NULL)
  }

  return(pop_growth_ghs %>% arrange(Year))
}


# get WorldPop 
get_worldpop <- function() {
  tryCatch({
    fuzzy_read(spatial_dir, "population.*.tif$")
  }, error = function(e) NULL)
}


get_worldpop_total <- function(year = 2020, aoi = aoi) {
    wp_raster <- get_worldpop()
    if (is.null(wp_raster)) return(NULL)

    # Clip to AOI and calculate total population
    wp_clipped <- terra::crop(wp_raster, aoi %>% vect(), mask = TRUE)
    total_pop <- sum(values(wp_clipped), na.rm = TRUE)
    
    return(total_pop)

    # tibble(
    #   Location = city,
    #   Country = country,
    #   Year = year,
    #   Population = round(total_pop),
    #   Area_km = round(sum(expanse(aoi, unit = "km")), 2),
    #   Source = "WorldPop",
    #   Method = "WorldPop CIC 2020"
    # )
  }


# Read WorldPop CSVs from sibling scan directories for benchmark cities
get_worldpop_from_siblings <- function(cities, country) {
  parent_dir <- dirname(getwd())
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

    # Look for WorldPop CSV
    tabular_path <- file.path(match_dir, "02-process-output", "tabular")
    if (!dir.exists(tabular_path)) next

    csv_files <- list.files(tabular_path, pattern = "worldpop_2015_2030\\.csv$", full.names = TRUE)
    if (length(csv_files) == 0) next

    # Get area from sibling's AOI shapefile
    area_km <- tryCatch({
      sibling_yml <- yaml::read_yaml(file.path(match_dir, "01-user-input", "city_inputs.yml"))
      aoi_shp <- file.path(match_dir, "01-user-input", "AOI", paste0(sibling_yml$AOI_shp_name, ".shp"))
      sibling_aoi <- st_read(aoi_shp, quiet = TRUE) %>% vect()
      round(sum(expanse(sibling_aoi, unit = "km")), 2)
    }, error = function(e) NA_real_)

    wp <- tryCatch({
      read.csv(csv_files[1]) %>%
        as_tibble() %>%
        mutate(
          Year = as.numeric(str_extract(year, "\\d{4}")),
          Population = population,
          Location = ct,
          Country = country,
          Area_km = area_km,
          Source = "WorldPop Global 2",
          Method = "WorldPop G2 (scan-tabular)",
          .keep = "none"
        )
    }, error = function(e) NULL)

    if (!is.null(wp) && nrow(wp) > 0) {
      results[[ct]] <- wp
      found_cities <- c(found_cities, ct)
      message("  WorldPop from sibling: ", ct, " (", basename(match_dir), ")")
    }
  }

  list(data = bind_rows(results), found_cities = found_cities)
}