args <- commandArgs(trailingOnly = TRUE)

if (length(args) < 1) {
  stop("Project directory argument is required.")
}

countr_dir <- args[1]
setwd(countr_dir)
if (!dir.exists("plots")) dir.create("plots", recursive = TRUE)


library(tidyverse)

heat <- read_csv('stats/avg_temp.csv', show_col_types = FALSE)

ggplot(heat) +
  geom_segment(aes(x = 30, xend = avg,
                   y = fct_reorder(city, avg), yend = fct_reorder(city, avg)),
               color = 'grey', linewidth = 0.3) +
  geom_point(aes(avg, fct_reorder(city, avg), color = avg), size = 3,
             show.legend = FALSE, color = '#f04c1f') +
  theme_minimal() +
  theme(panel.grid.minor = element_blank(),
        panel.grid.major.y = element_blank(),
        axis.title = element_blank(),
        axis.text.y = element_text(size = 8),
        plot.subtitle = element_text(size = 9.5)) +
  labs(subtitle = 'Mean temperature during the\nhottest months 2013-2023 (°C)')

ggsave(file.path('plots', 'avg_temp.png'),
       width = 1300, height = 1400, units = 'px')
