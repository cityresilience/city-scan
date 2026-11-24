# COG web maps -------------------------------------------------------------
# Counterpart to fns-maps-web.R. Instead of polygonising each raster to a
# FlatGeobuf, this renders the delivered Cloud-Optimized GeoTIFFs directly on the
# leaflet web map via leafem::addCOG (the browser range-reads the COG), coloured
# straight from layers.yml so the styling matches the static + FGB maps exactly.
#
#   build_cog_sections(layers, keys)  reads layers.yml and returns one section
#     entry per raster layer — the "sections.yml"-style config (see
#     scan-calculations/sections.yml) that drives the COG maps. Optionally writes
#     it to cog-sections.yml.
#   add_cog_layer(map, url, entry)    adds one COG to a leaflet map, styled from
#     a section entry via leafem::colorOptions.
#
# NOTE ON AUTH: addCOG runs client-side (the browser fetches the COG), so the URL
# must be reachable without server credentials — a public object or a signed URL.
# A server-side .env/service account does NOT help here.

`%||%` <- function(a, b) if (is.null(a)) b else a

# Turn one layers.yml entry into a COG section config. Mirrors the param prep in
# create_layer_function() (fns-maps-web.R:16-31): unlist labels/breaks/palette,
# derive breaks from labels for factors, and resolve a numeric domain.
cog_section_from_layer <- function(key, params) {
  labels  <- if (!is.null(params$labels)) unlist(params$labels) else NULL
  breaks  <- if (!is.null(params$breaks)) unlist(params$breaks) else NULL
  factor  <- isTRUE(params$factor)
  if (factor && is.null(breaks)) breaks <- labels
  palette <- unlist(params$palette)

  domain <-
    if (!is.null(params$domain)) unlist(params$domain)
    else if (!is.null(params$min) && !is.null(params$max)) c(params$min, params$max)
    else if (!is.null(breaks)) range(suppressWarnings(as.numeric(breaks)), na.rm = TRUE)
    else NULL

  list(
    key           = key,
    title         = params$title %||% key,
    group_id      = params$group_id %||% key,
    palette       = as.list(palette),
    breaks        = if (!is.null(breaks)) as.list(breaks) else NULL,
    domain        = if (!is.null(domain) && all(is.finite(domain))) as.list(domain) else NULL,
    factor        = factor,
    labels        = if (!is.null(labels)) as.list(labels) else NULL,
    # band to display for a multi-band COG (air_quality, flood, worldpop, ...)
    data_variable = params$data_variable,
    suffix        = params$suffix)
}

# Read layers.yml and build the COG section config. `keys` defaults to every
# layer that carries a palette (i.e. is drawable); pass an explicit vector to
# restrict to the raster layers actually delivered as COGs.
build_cog_sections <- function(layers, keys = NULL, out_path = NULL) {
  if (is.null(keys)) {
    keys <- names(layers)[vapply(
      layers, \(p) is.list(p) && !is.null(p$palette), logical(1))]
  }
  sections <- lapply(keys, \(k) cog_section_from_layer(k, layers[[k]]))
  names(sections) <- keys
  if (!is.null(out_path)) {
    yaml::write_yaml(list(cog_sections = sections), out_path)
    message("Wrote ", out_path, " (", length(sections), " layers)")
  }
  sections
}

# Data-driven domain from the COG itself — a robust quantile range (like the
# static maps' set_domain / break_pretty2), read server-side with GDAL auth.
# Used for palette-only layers that have no breaks/domain in layers.yml. `url` is
# the plain https URL; needs GDAL_HTTP_HEADERS set with a bearer token in R.
cog_domain <- function(url, probs = c(0.02, 0.98), sample_n = 2e4) {
  # Sample from an overview, not full res — a decimated read over /vsicurl. The
  # 30 m national COGs are billions of px, so full-res na.rm sampling drags the
  # whole raster across the network (minutes). 2-98% quantiles survive decimation.
  r <- tryCatch(read_cog_overview(url), error = function(e) NULL)
  if (is.null(r)) return(NULL)
  s <- tryCatch(terra::spatSample(r, sample_n, method = "regular", na.rm = TRUE, warn = FALSE),
                error = function(e) NULL)
  if (is.null(s)) return(NULL)
  v <- s[[1]]; v <- v[is.finite(v)]
  if (length(v) < 10) return(NULL)
  unname(as.numeric(stats::quantile(v, probs, na.rm = TRUE)))
}

# Read a COG at a display resolution using its overviews (a decimated, streamed
# read via /vsicurl — NOT a full download). Needs GDAL_HTTP_HEADERS set with a
# bearer token in R. Falls back to full res for small rasters / missing overview.
read_cog_overview <- function(url, target = 1300) {
  vsi <- if (startsWith(url, "/vsicurl/")) url else paste0("/vsicurl/", url)
  r0 <- terra::rast(vsi)
  N <- terra::ncol(r0)
  if (N <= target * 1.5) return(r0)
  lvl <- max(0, round(log2(N / target)) - 1)
  tryCatch(terra::rast(vsi, opts = paste0("OVERVIEW_LEVEL=", lvl)),
           error = function(e) r0)
}

# Build the leaflet colour function for a layer (same colorFactor / colorBin /
# colorNumeric logic as the static maps), for use as addRasterImage(colors=).
cog_color_scale <- function(entry) {
  palette <- unlist(entry$palette)
  domain  <- if (!is.null(entry$domain)) as.numeric(unlist(entry$domain)) else NULL
  breaks  <- if (!is.null(entry$breaks)) suppressWarnings(as.numeric(unlist(entry$breaks))) else NULL
  factor  <- isTRUE(entry$factor)
  if (is.null(domain) && !is.null(breaks)) domain <- range(breaks, na.rm = TRUE)
  if (is.null(domain) && !factor) return(NULL)
  if (factor && !is.null(breaks))
    leaflet::colorFactor(palette, levels = breaks, na.color = "transparent", ordered = TRUE)
  else if (!is.null(breaks))
    leaflet::colorBin(palette, domain = domain, bins = breaks, na.color = "transparent", right = TRUE)
  else
    leaflet::colorNumeric(palette, domain = domain, na.color = "transparent")
}

# Build a JS pixelValuesToColorFn that maps a pixel value to its EXACT layers.yml
# colour. leafem::colorOptions only interpolates the palette into a generic ramp
# (ignoring factor/bin semantics), so instead we build the real leaflet colour
# scale (colorFactor / colorBin / colorNumeric — same as the static + FGB maps),
# sample it, and bake the lookup into a JS function georaster applies per pixel.
cog_pixel_fn <- function(entry) {
  palette <- unlist(entry$palette)
  domain  <- if (!is.null(entry$domain)) as.numeric(unlist(entry$domain)) else NULL
  breaks  <- if (!is.null(entry$breaks)) suppressWarnings(as.numeric(unlist(entry$breaks))) else NULL
  factor  <- isTRUE(entry$factor)
  if (is.null(domain) && !is.null(breaks)) domain <- range(breaks, na.rm = TRUE)
  if (is.null(domain) && !factor) return(NULL)   # no range -> can't colour

  vec <- function(x) paste0("[", paste(x, collapse = ","), "]")
  cvec <- function(x) paste0("[", paste0('"', x, '"', collapse = ","), "]")

  if (factor && !is.null(breaks)) {
    cs <- leaflet::colorFactor(palette, levels = breaks, na.color = "transparent", ordered = TRUE)
    cols <- cs(breaks)
    # leaflet turns the CSS keyword 'transparent' into white; restore it so
    # nodata / class-0 stays see-through (palette aligns 1:1 with breaks here).
    if (length(palette) == length(cols)) cols[palette == "transparent"] <- "rgba(0,0,0,0)"
    js <- sprintf(
      'function(x){var v=Array.isArray(x)?x[0]:x; if(v==null||isNaN(v))return null; var b=%s,c=%s,bi=0,bd=Infinity; for(var i=0;i<b.length;i++){var d=Math.abs(v-b[i]); if(d<bd){bd=d;bi=i;}} return c[bi];}',
      vec(breaks), cvec(cols))
  } else {
    cs <- if (!is.null(breaks))
            leaflet::colorBin(palette, domain = domain, bins = breaks, na.color = "transparent", right = TRUE)
          else leaflet::colorNumeric(palette, domain = domain, na.color = "transparent")
    vals <- seq(domain[1], domain[2], length.out = 256)
    cols <- cs(vals)
    js <- sprintf(
      'function(x){var v=Array.isArray(x)?x[0]:x; if(v==null||isNaN(v))return null; var d0=%.8g,d1=%.8g,c=%s; var i=Math.round((v-d0)/(d1-d0)*(c.length-1)); i=Math.max(0,Math.min(c.length-1,i)); return c[i];}',
      domain[1], domain[2], cvec(cols))
  }
  htmlwidgets::JS(js)
}

# Add one delivered COG to a leaflet map, styled from layers.yml.
#   crop = TRUE  : read the COG at overview res, crop + mask to `aoi` (a terra
#                  SpatVector) server-side, and draw the actual cropped data
#                  (leaflet::addRasterImage). No browser auth / streaming.
#   crop = FALSE : stream the COG in the browser (leafem::addCOG) with the exact
#                  layers.yml colours via pixelValuesToColorFn.
add_cog_layer <- function(map, url, entry, crop = FALSE, aoi = NULL, opacity = 0.85) {
  if (crop) {
    pal <- cog_color_scale(entry)
    if (is.null(pal)) return(map)
    r <- tryCatch({
      x <- read_cog_overview(url)
      terra::crop(x[[1]], aoi, mask = TRUE)
    }, error = function(e) NULL)
    if (is.null(r)) return(map)
    # squish out-of-domain values into the end colours (like maps-static
    # oob=squish) so extremes (e.g. dense cities) aren't dropped as transparent
    if (!isTRUE(entry$factor) && !is.null(entry$domain)) {
      d <- as.numeric(unlist(entry$domain))
      r <- terra::clamp(r, d[1], d[2], values = TRUE)
    }
    return(leaflet::addRasterImage(map, r, colors = pal, opacity = opacity,
                                   group = entry$group_id, project = TRUE))
  }
  fn <- cog_pixel_fn(entry)
  if (!is.null(fn)) {
    leafem::addCOG(map, url = url, group = entry$group_id, layerId = entry$key,
                   opacity = opacity, pixelValuesToColorFn = fn)
  } else {
    leafem::addCOG(map, url = url, group = entry$group_id, layerId = entry$key,
                   opacity = opacity,
                   colorOptions = leafem::colorOptions(palette = unlist(entry$palette),
                                                       na.color = "transparent"))
  }
}
