tryCatch_named("elevation", {
  elev_csv <- fuzzy_read(tabular_dir, "elevation.csv", read_csv, col_types = "cd")
  elevation_breaks <- (elev_csv$Bin %||% elev_csv$Elevation_Band) %>%
    str_extract_all("\\d+") %>% unlist() %>% unique() %>% as.numeric()
  elevation_data <- fuzzy_read(spatial_dir, layer_params$elevation$fuzzy_string) %>%
          crop(aoi, mask = TRUE) %>%
          # FABDEM water sentinels (rivers, lakes, sea) are exactly 0.0 — drop to NA
          subst(0, NA) %>%
          # aggregate_if_too_fine(threshold = 1e6, fun = \(x) Mode(x, na.rm = T)) %>%
          vectorize_if_coarse(threshold = 1e6)
  plots$elevation <- plot_static_layer(
    data = elevation_data, yaml_key = "elevation", breaks = elevation_breaks,
    plot_aoi = T, plot_wards = !is.null(wards), zoom_adj = zoom_adjustment)
})