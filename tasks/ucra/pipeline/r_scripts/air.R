args <- commandArgs(trailingOnly = TRUE)

if (length(args) < 1) {
  stop("Project directory argument is required.")
}

countr_dir <- args[1]
setwd(countr_dir)
if (!dir.exists("plots")) dir.create("plots", recursive = TRUE)


library(tidyverse)

air <- read_csv('stats/avg_air_1998_2019.csv', show_col_types = FALSE)

city_levels <- air %>%
  filter(year == 2019) %>%
  arrange(-avg) %>%
  pull(city)

air %>%
  mutate(city = factor(city, levels = city_levels)) %>%
  ggplot() +
  geom_hline(yintercept = 5, linewidth = 0.3, linetype = 'dashed', color = 'darkgrey') +
  geom_line(aes(year, avg, group = 1), linewidth = 1, color = '#a86595') +
  annotate("point", x = 1998, y = 0, alpha = 0) +
  facet_wrap('city') +
  scale_x_continuous(breaks = seq(1998, 2019, 7)) +
  theme_minimal() +
  theme(panel.grid.minor = element_blank(),
        panel.spacing = unit(1, 'lines'),
        axis.title = element_blank(),
        axis.text.y = element_text(size = 8),
        plot.subtitle = element_text(size = 9.5)) +
  labs(subtitle = 'Average PM2.5 concentration 1998-2019 (μg/m3)')

ggsave(file.path('plots', 'avg_air_1998_2019.png'), width = 1900, height = 1900, units = 'px')

city_levels <- air %>%
  filter(year == 2019) %>%
  arrange(-pct_bad_air) %>%
  pull(city)

air %>%
  mutate(city = factor(city, levels = city_levels)) %>%
  ggplot() +
  geom_line(aes(year, pct_bad_air * 100, group = 1), linewidth = 1, color = '#a86595') +
  facet_wrap('city') +
  scale_x_continuous(breaks = seq(1998, 2019, 7)) +
  theme_minimal() +
  theme(panel.grid.minor = element_blank(),
        panel.spacing = unit(1, 'lines'),
        axis.title = element_blank(),
        axis.text.y = element_text(size = 8),
        plot.subtitle = element_text(size = 9.5)) +
  labs(subtitle = 'Percentage of city area with PM2.5 concentration >= 5 μg/m3 1998-2019 (%)')

ggsave(file.path('plots', 'bad_air_1998_2019.png'), width = 1900, height = 1900, units = 'px')
