
library("R/setup.R") # loads packages, source functions, set directiries

# Load data 
gwsa <- read_csv(file.path(tabular_dir,
  "G3P_v1.12_gwsa_aquifers_Senegalo-Mauretanian Basin.csv"),
                    col_types = "ccdd") %>%
    select(date = 2, gwsa = 3) %>%
    mutate(date = as.Date(date)) %>%
    arrange(date) %>%
    mutate(
      gap = c(0, diff(date)) > 120, # some missing months, identify gaps and separate lines 
      group = cumsum(gap)
    )

sws <- read_csv(file.path(tabular_dir, "G3P_v1.12_sws_aquifers_Senegalo-Mauretanian Basin.csv"),
                col_types = "ccdd") %>%
  select(date = 2, sws = 3) %>%
  mutate(date = as.Date(date))


# Plot GWSA time series
gwsa_plot <- ggplot(gwsa, aes(x = date, y = gwsa)) +
    geom_line(aes(group = group), alpha = 0.6) +
    geom_smooth(method = "loess", span = 0.2, se = FALSE, linewidth = 0.6, linetype = 2) +
    scale_x_date(date_breaks = "2 years", date_labels = "%Y") +
    labs(title = "Groundwater Storage Anomaly",
         subtitle = "Baseline is the average from April 2002 to September 2023",
         y = "Storage anomaly (mm)", x = "Year") +
    theme_minimal() +
  theme(axis.line = element_line(linewidth = .5, color = "black"),
          axis.title.x = element_blank())

# ggplot2:::print.ggplot(gwsa_plot)
ggsave("03-render-output/plots/groundwater-timeseries.png", device = "png",
        width = 5, height = 4.6, units = "in", dpi = "print")
        

# Plot GWSA & Surface Water time series
combined_plot <- ggplot(gwsa, aes(x = date, y = gwsa) )+
    geom_line(aes(group = group, color = "Groundwater Storage"), alpha= 0.6) +
    geom_line(data = sws, aes(y = sws, color = "Surface Water Storage"), alpha = 0.6) +
    scale_color_manual(values = c("Groundwater Storage" = "steelblue",
                                   "Surface Water Storage" = "darkred")) +
    scale_x_date(date_breaks = "2 years", date_labels = "%Y") +
    labs(title = "Water Storage Anomaly",
         subtitle = "Senegalo-Mauretanian Basin (GRACE/GRACE-FO)",
         y = "Storage anomaly (mm)", x = "Year", color = NULL) +
    theme_minimal() +
    theme(axis.line = element_line(linewidth = 0.5, color = "black"),
          plot.background = element_rect(fill = "white", color = NA),
          legend.position = "bottom")


# ggplot2:::print.ggplot(combined_plot)
ggsave("03-render-output/plots/groundwater-surfacewater-timeseries.png", device = "png",
        width = 5, height = 4.6, units = "in", dpi = "print")