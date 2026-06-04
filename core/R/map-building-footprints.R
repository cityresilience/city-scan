#!/usr/bin/env Rscript
# Plot building footprints
# Reads clipped buildings from 02-process-output/spatial/

if (!exists("aoi")) source(here::here("core/R/setup.R"))

message("\n=== Building Footprints Plot ===")

# Read clipped buildings
buildings_path <- list.files(spatial_dir, pattern = "building_footprints\\.(fgb|gpkg)$", full.names = TRUE)[1]

if (is.null(buildings_path) || length(buildings_path) == 0 || !file.exists(buildings_path)) {
  message("No building footprints found in spatial_dir — skipping plot")
} else {
  buildings <- vect(buildings_path)
  message("Loaded ", nrow(buildings), " buildings")

  # Roads (optional)
  roads <- tryCatch(
    fuzzy_read(spatial_dir, "edges-edit\\.gpkg$"),
    error = function(e) NULL
  )
  if (inherits(roads, "SpatVector")) {
    roads <- crop(roads, aoi)
    message("Loaded ", nrow(roads), " road segments")
  }

  # Plot
  p <- ggplot() +
    geom_spatvector(data = buildings, color = NA, fill = "#FF9C28") +
    theme_void() +
    theme(panel.background = element_rect(fill = "black"))

  if (inherits(roads, "SpatVector")) {
    p <- p + geom_spatvector(data = roads, color = "white", linewidth = 0.1)
  }

  # Save
  output_file <- file.path(styled_maps_dir, "building_footprints.png")
  ggsave(filename = output_file, plot = p, width = 8.77, height = 7.55, dpi = 200)
  message("Saved: ", output_file)
}

message("=== Building footprints plot complete ===\n")
