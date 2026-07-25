args <- commandArgs(trailingOnly = TRUE)

if (length(args) < 1) {
  stop("Project directory argument is required.")
}

countr_dir <- args[1]
setwd(countr_dir)
if (!dir.exists("plots")) dir.create("plots", recursive = TRUE)


library(tidyverse)
library(lubridate)

cities <- read_csv('centroids.csv', show_col_types = FALSE) %>% select(city)
cities$centroids <- 0:(nrow(cities)-1)
var_list <- c('twsan')
date_list <- c('01', '02', '03',
               '04', '05', '06',
               '07', '08', '09',
               '10', '11', '12')

drought_plot <- function(var, year_beg, year_end, lab_x1, lab_y1, lab1, lab_x2 = 2, lab_y2 = 0, lab2 = '', plot_width, plot_height) {
  subt0 <- case_when(var == 'rdria' ~ 'Risk of drought impacts for agriculture',
                     var == 'spg01' ~ 'SPI 1-month accumulation period',
                     var == 'spg12' ~ 'SPI 12-month accumulation period',
                     var == 'twsan' ~ 'Total water storage anomaly')

  subt1 <- paste(year_beg, year_end, sep = '-')
  df <- cities

  for (yr in year_beg:year_end) {
    for (i in date_list) {
      file_path <- paste0('output/drought/', var, '_', yr, i, '.csv')
      if (!file.exists(file_path)) next
      df1 <- read_csv(file_path, show_col_types = FALSE)
      df <- df %>%
        full_join(df1, by = c("city", "centroids"))
      if ("OID_" %in% names(df)) df <- df %>% select(-OID_)
    }
  }

  line_color <- case_when(str_detect(var, 'spg') ~ '#018571',
                          var == 'twsan' ~ '#a6611a',
                          var == 'rdria' ~ '#b30000')

  # value_cols <- names(df)[!(names(df) %in% c("city", "centroids"))]

  # df <- df %>%
  #   select(-centroids) %>%
  #   pivot_longer(cols = all_of(value_cols), names_to = 'month', values_to = 'value') %>%
  #   mutate(date = str_extract(month, "\\d{8}")) %>%
  #   mutate(date = ymd(date)) %>%
  #   select(-month) %>%
  #   filter(!is.na(value), !is.na(date)
  #   )
  value_cols <- names(df)[stringr::str_detect(names(df), paste0("^", var, "_\\d{8}$"))]
  df <- df %>%
    select(-centroids) %>%
    pivot_longer(cols = all_of(value_cols), names_to = "month", values_to = "value") %>%
    mutate(date = stringr::str_extract(month, "\\d{8}")) %>%
    mutate(date = ymd(date)) %>%
    select(-month) %>%
    filter(!is.na(value), !is.na(date))

  if (nrow(df) == 0) {
    message("No drought data available for plotting.")
    return(invisible(NULL))
  }

  df_levels <- df %>%
    group_by(city) %>%
    summarize(avg = mean(value, na.rm = TRUE), .groups = "drop") %>%
    arrange(avg) %>%
    pull(city)

  smallest_date <- min(df$date, na.rm = TRUE)

  p <- df %>%
    mutate(city = factor(city, levels = df_levels)) %>%
    ggplot() +
    geom_hline(yintercept = 0, linewidth = 0.5, color = 'grey') +
    geom_line(aes(date, value, group = city), color = line_color) +
    annotate("text", x = smallest_date + days(lab_x1), y = lab_y1, label = lab1,
             color = 'darkgrey', lineheight = 0.9, size = 2) +
    annotate("text", x = smallest_date + days(lab_x2), y = lab_y2, label = lab2,
             color = 'darkgrey', lineheight = 0.9, size = 2) +
    facet_wrap('city') +
    theme_minimal() +
    theme(panel.grid.minor = element_blank(),
          panel.spacing = unit(1, 'lines'),
          axis.title = element_blank(),
          axis.text.x = element_text(angle = 45, hjust = 1),
          legend.position = 'none',
          legend.title = element_blank()) +
    labs(subtitle = paste(subt0, subt1, sep = ' '))

  ggsave(file.path('plots', paste0(var, '.png')), plot = p,
         width = plot_width, height = plot_height, units = 'px')
}

drought_plot('twsan', 2011, 2020, 250, -2, 'drier\nthan\nnormal', 250, 2, 'wetter\nthan\nnormal', 1900, 2000)
