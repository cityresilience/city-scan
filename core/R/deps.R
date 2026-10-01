# deps.R — city-agnostic setup: packages + map layer parameters.
#
# Sourced by setup.R (before init_env/init_scan), and directly by ad hoc
# multi-AOI / comparison scripts that need the packages + helper fns +
# layer_params but NOT a scan context (no scan_id, no 01/02/03 dirs, no GCS).
# Assumes core/R/fns.R is already sourced (helper functions available).

# 2A. Load packages ------------------------------------------------------------
# Install packages from CRAN using librarian

if (!"librarian" %in% installed.packages()) install.packages("librarian")
librarian::shelf( # remove quiet = T because it seems failures are silenced
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
  here,

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
  terra,
  tidyterra,
  leaflet,
  leafem,
  paleolimbot/ggspatial,
  jsonlite,
  geojsonsf,
  exactextractr,
  h3o,

  # Web
  curl,
  rvest,

  # GCS access
  googleCloudStorageR,
  gargle,
  
  cran_repo = "https://cran.r-project.org"
)

librarian::stock(quiet = T,
  ggnewscale, # 4.10 or higher
  prettymapr,
  cran_repo = "https://cran.r-project.org"
)

if (packageVersion("ggplot2") < "4.0.0") {
  message("Updating ggplot2 to 4.0+...")
  install.packages("ggplot2")
  library(ggplot2)
}

# 3. Load map layer parameters -------------------------------------------------
# this should be a local file
layer_params_file <- here('source/layers.yml') # Also used by fns.R
layer_params <- read_yaml(layer_params_file)
