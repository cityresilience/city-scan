# =========================================================
# CHARTING FUNCTIONS & HELPERS
# =========================================================

ggdonut <- function(data, category_column, quantities_column, colors, title = NULL, show_legend = FALSE) {
  data <- as.data.frame(data) # tibble does weird things with data frame, not fixing now
  data <- data[!is.na(data[,quantities_column]),]
  data <- data[data[,quantities_column] > 0,]
  # data <- data[rev(order(data[,quantities_column])),]
  data$decimal <- data[,quantities_column]/sum(data[,quantities_column], na.rm = T)
  data$max <- cumsum(data$decimal) 
  data$min <- lag(data$max)
  data$min[1] <- 0
  data$label <- paste(scales::label_percent(0.1)(data$decimal))
  data$label[data$decimal < .02] <- "" 
  data$label_position <- (data$max + data$min) / 2
  data[,category_column] <- factor(data[,category_column], levels = data[,category_column])
  breaks <- data[data[,"decimal"] > 0.2,] %>%
    { setNames(.$label_position, .[,category_column]) }

  donut_plot <- ggplot(data) +
    geom_rect(
      aes(xmin = .data[["min"]], xmax = .data[["max"]], fill = .data[[category_column]],
      ymin = 0, ymax = 1),
      color = "white") +
    geom_text(y = 0.5, aes(x = label_position, label = label)) +
    scale_y_continuous(guide = "none", name = NULL) +
    scale_fill_manual(values = colors, guide = if (show_legend) "legend" else "none") +
    scale_x_continuous(guide = "none", name = NULL) +
    coord_radial(expand = F, inner.radius = 0.3) +
    labs(title = title) +
    theme(axis.ticks = element_blank())
  return(donut_plot)
}


# Filled histogram — color bins match map, width bins match data
# Based on Ben's prototype. Reusable for RWI, air quality, LST, etc.
# x: numeric vector of values
# breaks: break points for color bins (from layers.yml)
# palette: color palette matching breaks (from layers.yml)
# labels: optional labels for color bins
# full_domain: if TRUE, x-axis spans full break range; if FALSE, spans data range
# domain: override x-axis limits (e.g., c(-2, 2) for RWI, c(0, 100) for PM2.5)
filled_histo <- function(x, breaks, palette, labels = NULL, full_domain = FALSE, domain = NULL) {
  fill_bins <- sort(c(Inf, -Inf, breaks, head(breaks, -1) + diff(breaks)/2)) %>%
    cut(breaks = breaks) %>% na.omit() %>% unique()
  if (is.null(labels)) labels <- fill_bins
  df <- tibble(x = x, fill_group = cut(x, breaks = breaks, labels = labels))
  if (is.null(domain)) {
    domain <- if (full_domain) c(min(breaks[is.finite(breaks)]), max(breaks[is.finite(breaks)])) else c(min(x, na.rm = TRUE), max(x, na.rm = TRUE))
  }
  df %>%
    ggplot() +
    geom_histogram(aes(x = x, fill = fill_group), show.legend = TRUE) +
    scale_x_continuous(breaks = c(breaks[is.finite(breaks)], domain), limits = domain) +
    scale_fill_manual(values = setNames(palette, labels), na.translate = TRUE, drop = FALSE, na.value = "transparent") +
    theme_minimal()
}