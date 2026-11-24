# Earthquake data collection
# Sources: USGS FDSN (comprehensive catalog) + NOAA NCEI (curated damage metadata).
# Merged into a single CSV using NCEI's column schema (see core/R/pre-charting.R).
# USGS-only events have NA in NCEI-specific columns (damage, deaths, intensity, tsunami).
# Dedup rule: same date ±1 day + within 50 km + |mag diff| ≤ 0.8 → NCEI row kept (richer metadata).

if (!exists("aoi")) source(here::here("core/R/setup.R"))

EQ_RADIUS_KM <- 500
EQ_MIN_MAG <- 1

city_point <- aoi %>% st_as_sf() %>% st_transform("EPSG:4326") %>%
  st_combine() %>% st_centroid()
coords <- st_coordinates(city_point)

get_usgs <- function(lat, lon) {
  library(httr2)
  resp <- request("https://earthquake.usgs.gov/fdsnws/event/1/query") %>%
    req_url_query(
      format = "geojson",
      starttime = "1900-01-01",
      latitude = lat, longitude = lon,
      maxradiuskm = EQ_RADIUS_KM,
      minmagnitude = EQ_MIN_MAG,
      orderby = "time"
    ) %>%
    req_perform()
  features <- resp_body_json(resp)$features
  if (length(features) == 0) return(tibble())
  map_dfr(features, function(f) {
    p <- f$properties
    g <- f$geometry$coordinates
    t <- as.POSIXct(p$time / 1000, origin = "1970-01-01", tz = "UTC")
    tibble(
      id = f$id,
      year = lubridate::year(t),
      month = lubridate::month(t),
      day = lubridate::day(t),
      hour = lubridate::hour(t),
      minute = lubridate::minute(t),
      second = lubridate::second(t),
      locationName = p$place %||% NA_character_,
      latitude = g[[2]],
      longitude = g[[1]],
      eqDepth = g[[3]],
      eqMagnitude = p$mag
    )
  })
}

get_ncei <- function() {
  library(httr2)
  resps <- request("http://www.ngdc.noaa.gov/hazel/hazard-service/api/v1/earthquakes") %>%
    req_url_query(minYear = 1900, maxYear = lubridate::year(Sys.Date())) %>%
    req_perform_iterative(iterate_with_offset("page"))
  resps %>% resps_successes() %>%
    resps_data(\(resp) bind_rows(resp_body_json(resp)$items)) %>% bind_rows()
}

usgs <- tryCatch(get_usgs(coords[, "Y"], coords[, "X"]),
  error = function(e) { message("USGS unavailable: ", e$message); tibble() })
ncei <- tryCatch(get_ncei(),
  error = function(e) { message("NCEI unavailable: ", e$message); tibble() })

# Spatial filter NCEI to within radius
if (nrow(ncei) > 0) {
  ncei_sf <- ncei %>%
    subset(!is.na(latitude) & !is.na(longitude)) %>%
    st_as_sf(coords = c("longitude", "latitude"), crs = st_crs(city_point), remove = FALSE)
  ncei_dist_km <- as.numeric(st_distance(ncei_sf, city_point) %>% units::set_units(km))
  ncei <- ncei_sf[ncei_dist_km <= EQ_RADIUS_KM, ] %>% st_drop_geometry()
}

# drop USGS rows that match any NCEI row. NCEI keeps the row (it carries damage metadata).
if (nrow(ncei) > 0 && nrow(usgs) > 0) {
  ncei_sf <- st_as_sf(ncei, coords = c("longitude", "latitude"), crs = 4326, remove = FALSE)
  usgs_sf <- st_as_sf(usgs, coords = c("longitude", "latitude"), crs = 4326, remove = FALSE)
  near <- st_is_within_distance(usgs_sf, ncei_sf, dist = units::set_units(50, km))

  usgs_to_drop <- integer(0)
  for (i in seq_along(near)) {
    if (length(near[[i]]) == 0) next
    u_date <- as.Date(paste(usgs$year[i], usgs$month[i], usgs$day[i], sep = "-"))
    for (j in near[[i]]) {
      n_date <- as.Date(paste(ncei$year[j],
                              coalesce(ncei$month[j], 1L),
                              coalesce(ncei$day[j], 1L), sep = "-"))
      date_ok <- !is.na(u_date) && !is.na(n_date) &&
        abs(as.numeric(difftime(u_date, n_date, units = "days"))) <= 1
      mag_ok <- !is.na(usgs$eqMagnitude[i]) && !is.na(ncei$eqMagnitude[j]) &&
        abs(usgs$eqMagnitude[i] - ncei$eqMagnitude[j]) <= 0.8
      if (date_ok && mag_ok) {
        usgs_to_drop <- c(usgs_to_drop, i)
        break
      }
    }
  }
  if (length(usgs_to_drop) > 0) usgs <- usgs[-usgs_to_drop, ]
}

# Union with `source` label. bind_rows fills NA for columns missing in either side, so
# USGS-only rows automatically get NA in damageAmountOrder, deaths, intensity, etc.
# id coerced to character — NCEI returns integer ids, USGS returns string ids.
eq <- bind_rows(
  if (nrow(ncei) > 0) ncei %>% mutate(source = "NCEI", id = as.character(id)) else NULL,
  if (nrow(usgs) > 0) usgs %>% mutate(source = "USGS", id = as.character(id)) else NULL
)

if (!is.null(eq) && nrow(eq) > 0) {
  write_csv(eq, file.path(tabular_dir, paste0(city_string, "_earthquake.csv")))
}
