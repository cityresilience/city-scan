# Coastal erosion baseline map: bars + grey transect coastline polygon
tryCatch_named("coastal_erosion_baseline", {
  baseline_data <- fuzzy_read(spatial_dir, layer_params$coastal_erosion_baseline$fuzzy_string)
  if (nrow(baseline_data) == 0) stop("No baseline data")

  # Plot the baseline bars
  plots$coastal_erosion_baseline <- plot_static_layer(
    data = baseline_data, yaml_key = "coastal_erosion_baseline",
    plot_aoi = F, plot_wards = F, zoom_adj = zoom_adjustment)

  # Overlay grey transect coastline polygon
  coastline_file <- fuzzy_read(spatial_dir, layer_params$transect_coastline$fuzzy_string, paste)
  if (!is.na(coastline_file)) {
    coastline_sf <- st_read(coastline_file, quiet = TRUE)
    plots$coastal_erosion_baseline <- plots$coastal_erosion_baseline +
      geom_sf(data = coastline_sf, fill = NA, color = "grey30", linewidth = 0.3)
  }
})
