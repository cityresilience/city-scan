plot_flooding <- function(flood_type) {
  tryCatch_named(flood_type, {
    file <- fuzzy_read(spatial_dir, glue("{flood_type}_2020.tif$"), paste)
    if (is.na(file)) return(NULL)
    flood_data <- terra::crop(rast(file)[[1]], static_map_bounds)
    # Temporary fix for if layer is all NAs
    if (all(is.na(values(flood_data)))) values(flood_data)[1] <- 0
    plots[[flood_type]] <<- plot_static_layer(
      flood_data, yaml_key = flood_type,
      plot_aoi = T, plot_wards = !is.null(wards))

    # Population overlays — covers population, population_2030, etc.
    for (pop_key in grep("^population", names(plots), value = TRUE)) {
      plots[[glue("{flood_type}_{pop_key}")]] <<-
        plot_static_layer(flood_data, yaml_key = flood_type, baseplot = plots[[pop_key]])
    }

    # WSF overlay with legend ordering (WSF underneath, flood on top)
    wsf_base <- if (!is.null(plots$wsf_harmonized)) plots$wsf_harmonized else plots$wsf
    if (!is.null(wsf_base)) {
      wsf_ordered <- wsf_base + guides(fill = guide_legend(order = 2))
      p_flood_wsf <- plot_static_layer(flood_data, yaml_key = flood_type, baseplot = wsf_ordered) +
        guides(fill = guide_legend(order = 1))
      plots[[glue("{flood_type}_wsf")]] <<- p_flood_wsf
    }

    # Infrastructure overlay
    if (!is.null(plots$infrastructure)) plots[[glue("{flood_type}_infrastructure")]] <<-
      plot_static_layer(flood_data, yaml_key = flood_type, baseplot = plots$infrastructure)

    # Built-up area 2025 hatch overlay on flood maps
    if (exists("builtup_extent_2025") && !is.null(builtup_extent_2025)) {
      builtup_clipped <- sf::st_intersection(sf::st_as_sf(builtup_extent_2025), sf::st_as_sf(aoi))
      plots[[glue("{flood_type}_builtup")]] <<- plots[[flood_type]] +
        ggpattern::geom_sf_pattern(
          data = builtup_clipped, color = NA, fill = NA,
          aes(pattern = "2025 built-up area"),
          pattern_spacing = 0.0125, pattern_fill = NA,
          pattern_density = 0.5, pattern_size = 0.25) +
        ggpattern::scale_pattern_manual(values = "stripe", name = "") +
        coord_3857_bounds(static_map_bounds)
    }
  })
}

flooding_yaml_keys <- c("fluvial", "pluvial", "coastal", "combined_flooding")
walk(flooding_yaml_keys, plot_flooding)
