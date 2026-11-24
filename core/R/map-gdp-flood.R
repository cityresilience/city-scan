# GDP + Flood overlay maps
# Renders: gdp_total + combined flood, gdp_per_capita + combined flood

plot_gdp_flood <- function(gdp_key) {
  if (is.null(plots[[gdp_key]])) return()

  for (flood_key in c("combined_flooding", "fluvial", "pluvial", "coastal")) {
    tryCatch_named(glue("{gdp_key}_{flood_key}"), {
      file <- fuzzy_read(spatial_dir, glue("{flood_key}_2020.tif$"), paste)
      if (is.na(file)) return(NULL)
      flood_data <- terra::crop(rast(file)[[1]], static_map_bounds)
      if (all(is.na(values(flood_data)))) values(flood_data)[1] <- 0
      plots[[glue("{gdp_key}_{flood_key}")]] <<- plot_static_layer(
        flood_data, yaml_key = flood_key, baseplot = plots[[gdp_key]])
    })
  }
}

walk(c("gdp_total", "gdp_per_capita"), plot_gdp_flood)
