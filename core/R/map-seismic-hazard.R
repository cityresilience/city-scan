# Seismic Hazard ----------------------------------------------------------------
# Non-standard because uses larger extent (like burnt_area)
tryCatch_named("seismic_hazard", {
  seismic_hazard <- fuzzy_read(spatial_dir, layer_params$seismic_hazard$fuzzy_string)
  if (inherits(seismic_hazard, c("SpatVector", "SpatRaster"), which = F)) {
    seismic_extent <- aspect_buffer(
      vect(ext(seismic_hazard), crs = crs(seismic_hazard)),
      aspect_ratio, buffer_percent = 0.05)
    plots$seismic_hazard <- plot_static_layer(
      seismic_hazard, "seismic_hazard",
      static_map_bounds = seismic_extent,
      plot_aoi = T)
  }
})
