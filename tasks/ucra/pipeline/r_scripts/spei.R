args <- commandArgs(trailingOnly = TRUE)

if (length(args) < 1) {
  stop("Project directory argument is required.")
}

countr_dir <- args[1]
setwd(countr_dir)
if (!dir.exists("plots")) dir.create("plots", recursive = TRUE)


library(tidyverse)
library(lubridate)

spei_plot <- function(spei_period, plot_height, plot_width = 1900) {
  df <- read_csv(paste0('stats/spei/spei', spei_period, '.csv'), show_col_types = FALSE) %>%
    mutate(date = ymd(date))

  city_levels <- df %>%
    group_by(city) %>%
    summarize(avg = mean(spei, na.rm = TRUE), .groups = "drop") %>%
    arrange(avg) %>%
    pull(city)

  df %>%
    mutate(city = factor(city, levels = city_levels)) %>%
    ggplot(aes(date, spei)) +
    geom_area(color = '#a6cee3', fill = '#a6cee3', alpha = 0.4, linewidth = 0.2) +
    facet_wrap('city') +
    theme_minimal() +
    theme(panel.grid.minor = element_blank(),
          axis.title = element_blank(),
          legend.position = 'none',
          axis.text.x = element_text(angle = 45, hjust = 1)) +
    labs(subtitle = paste0('SPEI ', as.numeric(spei_period), '-month accumulation period'))

  ggsave(file.path('plots', paste0('spei', spei_period, '.png')),
         width = plot_width, height = plot_height, units = 'px')
}

plot_height <- 1000
spei_plot('01', plot_height)
spei_plot('12', plot_height)
spei_plot('48', plot_height)
