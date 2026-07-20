# Set up session for running maps.R
# Uses `here` package for project-root-relative paths (like Python's config/paths.py)

# 0. Initialize Scan
# 1. Set here & directories 
# 2. Load packages & authenticate GCS if needed
# 3. Load map layer parameters
# 4. Load city parameters
# 5. Read AOI & wards

# 0. Initialize Scan-ID -----------------------------------------------------------
if (!"here" %in% installed.packages()) install.packages("here")
library(here)
source(here("core/R/fns.R"), local = T)
auto_root_here()

message("\n=== Starting Setup ===")
message("Project root: ", here())

# Derive + validate scan_id BEFORE creating any dirs. If auto_root_here()
# didn't land us in a city folder, bail loudly here so we don't pollute
# canonical with empty 01-/02-/03- folders.
scan_id <- Sys.getenv("SCAN_ID", "")
if (scan_id == "") scan_id <- basename(here())
if (!grepl("^[0-9]{4}-[0-9]{2}-[a-z0-9_-]+$", tolower(scan_id)) ||
    scan_id == "" || is.na(scan_id)) {
  stop("\nCannot determine valid scan_id from here() = ", here(),
       "\nDid auto_root_here() find a .here marker?")
}
message("\nInitializing for ", scan_id)
invisible(NULL)

if (!exists("USE_GCS", where = .GlobalEnv)) {
    USE_GCS <<- Sys.getenv("USE_GCS", "false") == "true"
  }

# USE_GCS <<- TRUE

# 1 Set directories -----------------------------------------------------------
city_dir <- here()

# subdirectorie pattern
user_input_dir <-     here("01-user-input")
process_output_dir <- here("02-process-output")
output_dir <-         here("03-render-output")

spatial_dir <- here("02-process-output/spatial")
fgb_dir <- here("02-process-output/spatial-fgb")
tabular_dir <- here("02-process-output/tabular")

styled_maps_dir <- here("03-render-output/maps")
charts_dir <- here("03-render-output/plots")

if (!dir.exists(user_input_dir)) dir.create(user_input_dir, recursive = T)
if (!dir.exists(spatial_dir)) dir.create(spatial_dir, recursive = T)
if (!dir.exists(tabular_dir)) dir.create(tabular_dir, recursive = T)
if (!dir.exists(fgb_dir)) dir.create(fgb_dir, recursive = T)
if (!dir.exists(styled_maps_dir)) dir.create(styled_maps_dir, recursive = T)
if (!dir.exists(charts_dir)) dir.create(charts_dir, recursive = T)

# If USE GCS, authenticate and use gcs-overrides
message(paste('USE GCS:', USE_GCS))

message("spatial_dir: ", spatial_dir)
message("spatial files count: ", length(list.files(spatial_dir)))

# 2A. Load packages -------------------------------------------------------------
# Install packages from CRAN using librarian

if (!"librarian" %in% installed.packages()) install.packages("librarian")
librarian::shelf(quiet = T,
  # Read-in
  readxl,
  readr,
  yaml, 

  # Basic
  stringr,
  glue,
  tidyr,
  purrr,
  forcats,
  units,
  dplyr,
  zoo,
  lubridate,

  # Plots
  ggplot2, # 4.0+
  ggrepel,
  directlabels,
  ggh4x,
  ggtext,
  plotly, 
  cowplot,
  ggpackets,
  ggridges,
  ggpattern,

  # Spatial
  sf,
  rspatial/terra, # Only the github version of leaflet supports terra, in place of raster, which is now required as sp (on which raster depends) is being deprecated
  tidyterra,
  leaflet,
  leafem,
  ggspatial,
  jsonlite,
  geojsonsf,
  exactextractr,
  h3o,


  # Web
  curl,
  rvest,

  # GCS access
  googleCloudStorageR, 
  gargle
  )

librarian::stock(quiet = T,
  ggnewscale, # 4.10 or higher
  prettymapr
)

if (packageVersion("ggplot2") < "4.0.0") {
  message("Updating ggplot2 to 4.0+...")
  install.packages("ggplot2")
  library(ggplot2)
}

# Note: auto-switching to GCS removed — USE_GCS must be explicitly set in the Rmd


# 2B. Setting up GCS ----------------------------------------------------------
if(USE_GCS) { 
  
  source(here("core/R/gcs-auth.R"))

  } else  {
  # Paths already absolute via here() — no reassignment needed
}

# setup directories for global data path
source(here("core/R/global-data-paths.R"))


# 3. Load map layer parameters -------------------------------------------------
# this should be a local file 
layer_params_file <- here('source/layers.yml') # Also used by fns.R
layer_params <- read_yaml(layer_params_file)


# 4. Load city parameters ------------------------------------------------------
city_params <- read_yaml(file.path(user_input_dir, "city_inputs.yml"))
city <- str_to_title(city_params$city_name)
message(glue("City set to {city} (City directory: {city_dir})"))
city_string <- tolower(city) %>% stringr::str_replace_all(" ", "_")
country <- str_to_title(city_params$country_name)
if (length(country) == 0 || is.null(country) || country == "") {
  country <- str_match(scan_id, "\\d{4}-\\d{2}-([a-z]+)-")[1, 2] %>% str_to_title()
}

bm_cities_manual <- c(city_params$bm_cities_manual)
nearby_countries_string <- city_params$nearby_countries

basic_info <- fuzzy_read(tabular_dir, "basic_info.yml", read_yaml)
if (length(country) == 0 && is.list(basic_info)) country <- basic_info$country


# 5. Read AOI & wards ----------------------------------------------------------
message("\nReading AOI and wards data...")
# Defining layer because of bug where AOI always includes South Jakarta shapefile;
# ideally would not need to specify like this, for greater flexibility
aoi <- fuzzy_read(user_input_dir, "AOI", layer = city_params$AOI_shp_name) %>%
  project("epsg:4326")
message("AOI Ready!")

wards <- tryCatch(fuzzy_read(user_input_dir, "wards") %>% project("epsg:4326"), error = \(e) NULL)

# Major roads — used by add_roads_underlay() to overlay the road network on
# each map. From accessibility/filter_major_roads output. Loaded as terra
# SpatVector to match the rest of the plotting pipeline (geom_spatvector).
road_network <- tryCatch(
  vect(file.path(spatial_dir, paste0(city_string, "_major_roads.gpkg")),
       layer = "major_roads") %>%
    project("epsg:4326"),
  error = function(e) { message("road_network not loaded: ", e$message); NULL })

writeVector(aoi, file.path(fgb_dir, "aoi.fgb"), overwrite = T, filetype = "FlatGeobuf")

message("Setup complete.\n")