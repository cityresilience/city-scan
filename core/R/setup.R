# Set up session for running maps.R
# Uses `here` package for project-root-relative paths (like Python's config/paths.py)
#
# setup.R is the ORCHESTRATOR. The reusable pieces:
#   core/R/fns.R   — helper functions (sourced)
#   core/R/deps.R  — city-agnostic: packages + layer_params (no scan needed)
#   init_env()     — scan plumbing: root, scan_id, dirs, GCS connect  (defined below)
#   init_scan()    — scan data:     city params, AOI, wards           (defined below)
#
# Sourcing this file runs all of them in order, reproducing the exact globals
# every existing caller relies on. Ad hoc scripts that only need packages +
# helper fns + layer_params (e.g. multi-AOI folder comparisons) can source
# fns.R + deps.R directly and skip init_env()/init_scan().

if (!"here" %in% installed.packages()) install.packages("here")
library(here)

source(here("core/R/fns.R"), local = T)    # helper functions
source(here("core/R/deps.R"), local = T)   # packages + layer_params


# ---------- INIT SCAN ENVIRONMENT (root, scan_id, dirs, GCS) ----------
# Scan-specific plumbing that does NOT read city data: locate the project root,
# derive + validate scan_id, create the 01/02/03 subdirs, and (when USE_GCS)
# authenticate + install the GCS override functions. Writes results to the
# GLOBAL env so existing callers see the same vars.
#
# BAILS if auto_root_here() finds no .here marker above the caller — this
# prevents polluting canonical / the repo root with empty 01-/02-/03- folders
# when setup is sourced from somewhere that isn't a city folder.
init_env <- function() {

  # 1. Locate project root via .here. No marker -> refuse to proceed.
  root <- auto_root_here()
  if (is.null(root)) {
    stop("\ninit_env(): no .here marker found above the caller.\n",
         "Refusing to create 01-/02-/03- dirs (would pollute the repo root).\n",
         "Run from inside a city folder (one containing a .here marker).")
  }

  message("\n=== Starting Setup ===")
  message("Project root: ", here())

  # 2. Derive + validate scan_id.
  scan_id <- Sys.getenv("SCAN_ID", "")
  if (scan_id == "") scan_id <- basename(here())
  # Allow an optional one-level delivery-folder prefix (e.g.
  # "2026-06-pakistan/2026-06-pakistan-jampur") for grouped/nested scans.
  if (!grepl("^([0-9]{4}-[0-9]{2}-[a-z0-9_-]+/)?[0-9]{4}-[0-9]{2}-[a-z0-9_-]+$", tolower(scan_id)) ||
      scan_id == "" || is.na(scan_id)) {
    stop("\nCannot determine valid scan_id from here() = ", here(),
         "\nDid auto_root_here() find a .here marker?")
  }
  message("\nInitializing for ", scan_id)

  # 3. USE_GCS — honor a value the caller already set in global, else env.
  if (!exists("USE_GCS", where = .GlobalEnv)) {
    assign("USE_GCS", Sys.getenv("USE_GCS", "false") == "true", envir = .GlobalEnv)
  }
  USE_GCS <- get("USE_GCS", envir = .GlobalEnv)

  # 4. Directories (subdirectory pattern).
  city_dir <- here()
  user_input_dir <-     here("01-user-input")
  process_output_dir <- here("02-process-output")
  output_dir <-         here("03-render-output")
  spatial_dir <- here("02-process-output/spatial")
  fgb_dir <- here("02-process-output/spatial-fgb")
  tabular_dir <- here("02-process-output/tabular")
  styled_maps_dir <- here("03-render-output/maps")
  charts_dir <- here("03-render-output/plots")

  # Publish to global BEFORE the GCS connect — gcs-auth.R / gcs-overrides.R run
  # in the global env and read USE_GCS / scan_id / city_dir from there (both at
  # source time, to build the lookup, and at call time in the override fns).
  list2env(list(
    scan_id = scan_id, USE_GCS = USE_GCS, city_dir = city_dir,
    user_input_dir = user_input_dir, process_output_dir = process_output_dir,
    output_dir = output_dir, spatial_dir = spatial_dir, fgb_dir = fgb_dir,
    tabular_dir = tabular_dir, styled_maps_dir = styled_maps_dir,
    charts_dir = charts_dir), envir = .GlobalEnv)

  if (!dir.exists(user_input_dir)) dir.create(user_input_dir, recursive = T)
  if (!dir.exists(spatial_dir)) dir.create(spatial_dir, recursive = T)
  if (!dir.exists(tabular_dir)) dir.create(tabular_dir, recursive = T)
  if (!dir.exists(fgb_dir)) dir.create(fgb_dir, recursive = T)
  if (!dir.exists(styled_maps_dir)) dir.create(styled_maps_dir, recursive = T)
  if (!dir.exists(charts_dir)) dir.create(charts_dir, recursive = T)

  message(paste('USE GCS:', USE_GCS))
  message("spatial_dir: ", spatial_dir)
  message("spatial files count: ", length(list.files(spatial_dir)))

  # 5. GCS connect — authenticate + install overrides (gated on USE_GCS inside
  #    gcs-auth.R). Sourced with default local = FALSE so the override fns land
  #    in the global env and shadow base/terra/yaml for the rest of the session.
  if (USE_GCS) {
    source(here("core/R/gcs-auth.R"))
  }

  # 6. Read environment variables from .env file (if present).
  #    Used for reading API keys.
  #    (Is this the right location?)
  read_env <- function(x = ".env") {
    env_paths <- paste0(strrep("../", 0:4), x)
    found <- env_paths[file.exists(env_paths)]
    if (length(found)) readRenviron(found[1])
  }
  read_env()

  # setup directories for global data path
  source(here("core/R/global-data-paths.R"))

  invisible(scan_id)
}


# ---------- INIT SCAN DATA (city params, AOI, wards) ----------
# Scan-specific data reads. Requires init_env() to have run first (scan_id,
# *_dir, GCS overrides all in global). Writes city, country, aoi, wards, etc.
init_scan <- function() {

  # 4. Load city parameters ----------------------------------------------------
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

  # 5. Read AOI & wards --------------------------------------------------------
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

  list2env(list(
    city_params = city_params, city = city, city_string = city_string,
    country = country, bm_cities_manual = bm_cities_manual,
    nearby_countries_string = nearby_countries_string, basic_info = basic_info,
    aoi = aoi, wards = wards, road_network = road_network), envir = .GlobalEnv)

  message("Setup complete.\n")
  invisible(aoi)
}


# ---------- RUN ----------
init_env()    # auto-root (+ bail if no .here) + scan_id + dirs + GCS connect
init_scan()   # city params + AOI + wards
