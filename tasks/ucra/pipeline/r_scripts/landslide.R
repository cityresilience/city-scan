args <- commandArgs(trailingOnly = TRUE)

if (length(args) < 1) {
  stop("Project directory argument is required.")
}

countr_dir <- args[1]
setwd(countr_dir)
if (!dir.exists("plots")) dir.create("plots", recursive = TRUE)


library(tidyverse)

options(scipen = 999)

ls <- read_csv('stats/landslide_avg.csv', show_col_types = FALSE)

ls %>%
  filter(avg != 0) %>%
  ggplot() +
  geom_segment(aes(x = 0.00000, xend = avg,
                   y = fct_reorder(city, avg), yend = fct_reorder(city, avg)),
               color = 'grey', linewidth = 0.3) +
  geom_point(aes(avg, fct_reorder(city, avg), color = avg), size = 2.5,
             show.legend = FALSE, color = '#fbc9ff') +
  theme_minimal() +
  theme(panel.grid.minor = element_blank(),
        panel.grid.major.y = element_blank(),
        axis.title = element_blank(),
        axis.text.y = element_text(size = 8),
        plot.subtitle = element_text(size = 9.5)) +
  labs(subtitle = 'City-wide average annual\nfrequency of rainfall-triggered\nlandslide 1980-2018')

ggsave(file.path('plots', 'landslide.png'),
       width = 1400, height = 1300, units = 'px')
