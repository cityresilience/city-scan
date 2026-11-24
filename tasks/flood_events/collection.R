# Flood Events data collection
# Source: Dartmouth Flood Observatory from GCS private bucket

if (!exists("aoi")) source(here::here("core/R/setup.R"))
aoi <- aoi %>% st_as_sf() %>% st_transform("EPSG:4326")

# flood_archive_file is set by core/R/global-data-paths.R based on USE_GCS

flood_archive <- tryCatch({
  fa <- read_sf(flood_archive_file) %>% st_transform("EPSG:4326")

  if (nrow(fa) > 0) {
    # Repair under planar GEOS — S2 can't fix self-intersecting polygons
    # (e.g. DRC 2014-10-04 in Lobito corridor) and would drop them.
    s2_prev <- sf_use_s2()
    sf_use_s2(FALSE)
    fa <- st_make_valid(fa)
    sf_use_s2(s2_prev)
    fa <- fa[st_is_valid(fa),] %>% st_transform(st_crs(aoi))
    intersections <- which(apply(st_intersects(fa, aoi, sparse = F), 1, any))
    fa[intersections,]
  } else {
    fa
  }
}, error = function(e) { message("Flood archive not available: ", e$message); NULL })

if (!is.null(flood_archive) && nrow(flood_archive) > 0) {
  floods <- st_drop_geometry(flood_archive) %>%
    select(BEGAN, ENDED, DEAD, DISPLACED, MAINCAUSE, SEVERITY)

  flood_text_all <- floods %>% mutate(
    severity = ordered(SEVERITY, levels = c(1, 1.5, 2), labels = c("Large event", "Very large event", "Extreme event")),
    duration = paste(ENDED - BEGAN, "days"),
    fatalities = paste(scales::label_comma()(DEAD), "fatalities"),
    displaced = paste(scales::label_comma()(DISPLACED), "displaced"),
    line1 = toupper(paste(lubridate::month(BEGAN, label = T, abbr = F), lubridate::year(BEGAN))),
    line2 = paste(severity, (MAINCAUSE), sep = ", "),
    line3 = paste(as.character(duration), fatalities, displaced, sep = ", "),
    text = paste0(line1, ": ", line2, "\n", line3),
    mag = normalize(DEAD) * normalize(DISPLACED) * SEVERITY,
    begin_day = lubridate::yday(BEGAN),
    end_day = lubridate::yday(ENDED),
    begin_month = lubridate::month(BEGAN),
    end_month = lubridate::month(ENDED),
    begin_year = lubridate::year(BEGAN) + begin_day/1000,
    end_year = lubridate::year(ENDED))

  flood_text_all[which(rank(-flood_text_all$mag) > 10),"text"] <- NA

  write_csv(flood_text_all, file.path(tabular_dir, paste0(city_string, "_flood_events.csv")))
} else {
  floods <- tibble(BEGAN = as.Date(character()), ENDED = as.Date(character()),
                   DEAD = numeric(), DISPLACED = numeric(), MAINCAUSE = character(), SEVERITY = numeric())
  flood_text_all <- tibble()
}
