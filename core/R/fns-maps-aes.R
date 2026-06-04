
# =========================================================
# SCALE BREAKS HELPERS
# =========================================================

set_domain <- function(values, domain = NULL, center = NULL, factor = NULL) {
  if (!is.null(factor) && factor) {
    # Necessary for keeping levels in order
    domain <- ordered(levels(values), levels = levels(values))
  }
  if (is.null(domain)) {
    # This is a very basic way to set domain. Look at toolbox for more robust layer-specific methods
    min <- min(values, na.rm = T)
    max <- max(values, na.rm = T)
    domain <- c(min, max)
  }
  if (!is.null(center) && center == 0) {
    extreme <- max(abs(domain))
    domain <- c(-extreme, extreme)
  }
  return(domain)
}


get_layer_values <- function(data) {
  if (class(data)[1] %in% c("SpatRaster")) {
      values <- values(data)
      # if (!is.null(levels(data))) values <- factor(values, levels = levels(data)[[1]]$value, labels = levels(data)[[1]]$label)
    } else if (class(data)[1] %in% c("SpatVector")) {
      values <- pull(values(data))
    } else if (class(data)[1] == "sf") {
      values <- data$values
    } else stop("Data is not of class SpatRaster, SpatVector or sf")
  return(values)
}

set_layer_values <- function(data, values) {
  if (class(data)[1] %in% c("SpatRaster")) {
      values(data) <- values
    } else if (class(data)[1] %in% c("SpatVector")) {
      values(data)[[1]] <- values
    } else if (class(data)[1] == "sf") {
      data$values <- values
    } else stop("Data is not of class SpatRaster, SpatVector or sf")
  return(data)
}


breaks_midpoints <- \(breaks, rescaler = scales::rescale, ...) {
  scaled_breaks <- rescaler(breaks, ...)
  midpoints <- head(scaled_breaks, -1) + diff(scaled_breaks)/2
  midpoints[length(midpoints)] <- midpoints[length(midpoints)] + .Machine$double.eps
  return(midpoints)
}


# Alternatively could be two separate functions: pretty_interval() and pretty_quantile()
break_pretty2 <- function(data, n = 6, method = "quantile", FUN = signif,
                          digits = NULL, threshold = 1/(n-1)/4,
                          quantiles = NULL, min_value = NULL) {
  # Filter to values >= min_value before computing breaks
  if (!is.null(min_value)) data <- data[data >= min_value & !is.na(data)]
  divisions <- if (!is.null(quantiles)) as.numeric(unlist(quantiles)) else seq(from = 0, to = 1, length.out = n)
  n <- length(divisions)
  threshold <- 1/(n-1)/4

  if (method == "quantile") breaks <- unname(stats::quantile(data, divisions, na.rm = T))
  if (method == "interval") breaks <- divisions *
    (max(data, na.rm = T) - min(data, na.rm = T)) +
    min(data, na.rm = T)
  if (method == "log") {
    pos_data <- data[data > 0 & !is.na(data)]
    if (length(pos_data) == 0) return(rep(0, n))
    log_range <- log10(range(pos_data))
    breaks <- c(0, 10^seq(log_range[1], log_range[2], length.out = n - 1))
  }

  # Skip prettification when min_value is set — return exact breaks
  if (!is.null(min_value)) return(round(breaks))

  if (is.null(digits)) {
    digits <- if (all.equal(FUN, signif)) 1 else if (all.equal(FUN, round)) 0
  }

  distribution <- ecdf(data)
  discrepancies <- 100
  while (any(abs(discrepancies) > threshold) & digits < 6) {
    if (all.equal(FUN, signif) == TRUE) {
      pretty_breaks <- FUN(breaks, digits = digits)
      if(all(is.na(str_extract(tail(pretty_breaks, -1), "\\.[^0]*$")))) pretty_breaks[1] <- floor(pretty_breaks[1])
    }
    if (all.equal(FUN, round) == TRUE) {
      pretty_breaks <- c(
        floor(breaks[1] * 10^digits) / 10^digits,
        FUN(tail(head(breaks, -1), -1), digits = digits),
        ceiling(tail(breaks, 1) * 10^digits) / 10^digits)
    }
    if (method == "quantile") discrepancies <- distribution(pretty_breaks) - divisions
    # if (method == "interval) discrepancies <- distribution(pretty_breaks) - distribution(breaks)
    if (method == "interval") {
      discrepancies <- (pretty_breaks - breaks)/ifelse(breaks != 0, breaks, pretty_breaks)
      discrepancies[breaks == 0 & pretty_breaks == 0] <- 0
    }
    digits <- digits + 1
  }
  return(pretty_breaks)
}



# =========================================================
# SCALE COLORS AND LINES HELPERS
# =========================================================

fill_scale <- function(data_type, params) {
  # data_type <- if (data_type %ni% c("raster", "points", "lines", "polygons")) type_data(data_type))
  if (length(params$palette) == 0 | data_type %in% c("points", "line")) {
    NULL 
  } else if (exists_and_true(params$factor)) {
    # Switched to na.translate = F because na.value = "transparent" includes
    # NA in legend for forest. Haven't tried with non-raster.
    scale_fill_manual(
      values = params$palette,
      name = format_title(params$title, params$subtitle),
      na.translate = F,
      na.value = "transparent")
  } else if (params$bins == 0) {
    # Labels: year-range integers (1900-2100) render without thousands separator;
    # anything else gets the standard comma separator. Override per-layer via
    # `big_mark` in layers.yml if auto-detection misfires.
    .smart_labels <- if (!is.null(params$big_mark)) {
      scales::label_number(big.mark = params$big_mark)
    } else {
      function(x) {
        is_year <- all(is.finite(x)) && all(x >= 1900 & x <= 2100) && all(x == floor(x))
        if (is_year) format(x, scientific = FALSE, trim = TRUE)
        else scales::label_number(big.mark = ",")(x)
      }
    }
    scale_fill_gradientn(
      colors = params$palette,
      limits = if (is.null(params$domain)) NULL else params$domain,
      rescaler = if (!is.null(params$center)) ~ scales::rescale_mid(.x, mid = params$center) else scales::rescale,
      labels = .smart_labels,
      na.value = "transparent",
      name = format_title(params$title, params$subtitle))
  } else if (params$bins > 0) {
    .smart_labels <- if (!is.null(params$big_mark)) {
      scales::label_number(big.mark = params$big_mark)
    } else {
      function(x) {
        is_year <- all(is.finite(x)) && all(x >= 1900 & x <= 2100) && all(x == floor(x))
        if (is_year) format(x, scientific = FALSE, trim = TRUE)
        else scales::label_number(big.mark = ",")(x)
      }
    }
    scale_fill_stepsn(
      colors = params$palette,
      # Length of labels is one less than breaks when we want a discrete legend
      breaks = if (is.null(params$breaks)) waiver() else if (diff(lengths(list(params$labels, params$breaks))) == 1) params$breaks[-1] else params$breaks,
      # breaks_midpoints() is important for getting the legend colors to match the specified colors
      values = if (is.null(params$breaks)) NULL else breaks_midpoints(params$breaks, rescaler = if (!is.null(params$center)) scales::rescale_mid else scales::rescale, mid = params$center),
      labels = if (is.null(params$labels)) .smart_labels else params$labels,
      limits = if (is.null(params$breaks)) NULL else range(params$breaks),
      rescaler = if (!is.null(params$center)) scales::rescale_mid else scales::rescale,
      na.value = "transparent",
      oob = list(squish = scales::oob_squish, censor = scales::oob_censor, squish_any = scales::oob_squish_any, censor_any = scales::oob_censor_any)[[params$oob %||% "squish"]],
      name = format_title(params$title, params$subtitle),
      guide = if (diff(lengths(list(params$labels, params$breaks))) == 1) "legend" else "colorsteps")
  }
}

color_scale <- function(data_type, params) {
  if (data_type == "points") {
    scale_color_manual(values = params$palette, name = format_title(params$title, params$subtitle))
  } else if (length(params$stroke) < 2 || is.null(params$stroke$palette)) {
    NULL
  } else {
    scale_color_stepsn(
      colors = params$stroke$palette,
      # Length of labels is one less than breaks when we want a discrete legend
      breaks = if (is.null(params$stroke$breaks)) waiver() else if (diff(lengths(list(params$stroke$labels, params$stroke$breaks))) == 1) params$stroke$breaks[-1] else params$stroke$breaks,
      # breaks_midpoints() is important for getting the legend colors to match the specified colors
      values = if (is.null(params$stroke$breaks)) NULL else breaks_midpoints(params$stroke$breaks, rescaler = if (!is.null(params$stroke$center)) scales::rescale_mid else scales::rescale, mid = params$stroke$center),
      labels = if (is.null(params$stroke$labels)) waiver() else params$stroke$labels,
      limits = if (is.null(params$stroke$breaks)) NULL else range(params$stroke$breaks),
      rescaler = if (!is.null(params$stroke$center)) scales::rescale_mid else scales::rescale,
      na.value = "transparent",
      oob = list(squish = scales::oob_squish, censor = scales::oob_censor, squish_any = scales::oob_squish_any, censor_any = scales::oob_censor_any)[[params$stroke$oob %||% "squish"]],
      name = format_title(params$stroke$title, params$stroke$subtitle))
  }
}

create_color_scale <- function(domain, palette, center = NULL, bins = 5, reverse = F, breaks = NULL, factor = NULL, levels = NULL) {
  # List of shared arguments
  args <- list(
    palette = palette,
    domain = domain,
    na.color = 'transparent',
    alpha = T)
  # if (!is.null(breaks)) bins <- length(breaks)
  if (!is.null(factor) && factor) {
      color_scale <- rlang::inject(colorFactor(
        !!!args,
        levels = levels,
        ordered = TRUE))
  } else if (bins == 0) {
    color_scale <- rlang::inject(colorNumeric(
      # Why did I find it necessary to use colorRamp previously? For setting "linear"?
      # palette = colorRamp(palette, interpolate = "linear"),
      !!!args,
      reverse = reverse))
  } else {
    color_scale <- rlang::inject(colorBin(
      !!!args,
      bins = if (!is.null(breaks)) breaks else bins,
      # Might want to turn pretty back on
      pretty = FALSE,
      right = TRUE,  # Important for matching ggplot2 scale_fill_stepsn
      reverse = reverse))       
  }
  return(color_scale)
}


linewidth_scale <- function(data_type, params) {
  if (length(params$weight) < 2 || is.null(params$weight$range)) {
    NULL
  } else if (params$weight$factor) {
    scale_linewidth_manual(
      name = format_title(params$weight$title, params$weight$subtitle),
      values = unlist(setNames(params$weight$palette, params$weight$labels)))
  } else {
    scale_linewidth(
      range = c(params$weight$range[[1]], params$weight$range[[2]]),
      name = format_title(params$weight$title, params$weight$subtitle))
  }
}


# =========================================================
# THEME HELPERS
# =========================================================

theme_legend <- function(data, params) {
  layer_values <- get_layer_values(data)
  is_legend_text <- function() {
    !is.null(params$labels) && is.character(params$labels) | is.character(layer_values)
  }
  legend_text_alignment <- if (is_legend_text()) 0 else 1

  legend_theme <- theme(
    legend.title = ggtext::element_markdown(),
    legend.text = element_text(hjust = legend_text_alignment))
  return(legend_theme)
}

theme_custom <- function(...) {
  theme(
  # legend.key = element_rect(fill = "#FAFAF8"),
  legend.justification = c("left", "bottom"),
  legend.box.margin = margin(0, 0, 0, 12, unit = "pt"),
  legend.margin = margin(4,0,4,0, unit = "pt"),
  axis.title = element_blank(),
  axis.text = element_blank(),
  axis.ticks = element_blank(),
  axis.ticks.length = unit(0, "pt"),
  plot.margin = margin(0,0,0,0),
  ...)
}


save_plot <- function(
    plot = NULL, filename, directory,
    map_height = map_height, map_width = map_width, dpi = 300,
    rel_widths = c(3, 1)) {
  # Saves plots with set legend widths
  plot_layout <- plot_grid(
    plot + theme(legend.position = "none"),
    # Before ggplot2 3.5 was get_legend(plot); still works but with warning;
    # there are now multiple guide-boxes
    get_plot_component(plot, "guide-box-right"),
    rel_widths = rel_widths,
    nrow = 1) +
    theme(plot.background = element_rect(fill = "white", colour = NA))
  cowplot::save_plot(
    plot = plot_layout,
    filename = file.path(directory, filename),
    dpi = dpi,
    base_height = map_height, base_width = sum(rel_widths)/rel_widths[1] * map_width)
}
