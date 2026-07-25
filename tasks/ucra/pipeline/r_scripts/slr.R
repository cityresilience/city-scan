args <- commandArgs(trailingOnly = TRUE)

if (length(args) < 1) {
  stop("Project directory argument is required.")
}

country_dir <- args[1]
setwd(country_dir)

if (!dir.exists("plots")) dir.create("plots", recursive = TRUE)

library(tidyverse)
library(scales)

cities <- read_csv("centroids.csv", show_col_types = FALSE) %>% pull(city)

safe_read <- function(path) {
  if (!file.exists(path)) return(NULL)
  read_csv(path, show_col_types = FALSE)
}

city_slug_variants <- function(city) {
  c(
    gsub(" ", "_", tolower(city)),
    gsub("-", "_", gsub(" ", "_", tolower(city))),
    tolower(city),
    city
  ) %>% unique()
}

find_slr_csv <- function(city, year, ssp, rl10 = FALSE) {
  slugs <- city_slug_variants(city)

  suffix <- if (rl10) {
    paste0("_slr_RL10_", year, "_ssp", ssp, ".csv")
  } else {
    paste0("_slr_", year, "_ssp", ssp, ".csv")
  }

  candidates <- file.path(city, "data", paste0(slugs, suffix))
  found <- candidates[file.exists(candidates)]
  if (length(found) > 0) return(found[1])

  NULL
}

extract_exposure_series <- function(path) {
  df <- safe_read(path)
  if (is.null(df) || nrow(df) == 0) return(NULL)

  required_cols <- names(df)[grepl("^VALUE_\\d{4}$", names(df))]
  if (length(required_cols) == 0 || !"VALUE" %in% names(df)) return(NULL)

  df1 <- df %>% filter(VALUE == 1)
  if (nrow(df1) == 0) return(NULL)

  df1 %>%
    select(all_of(required_cols)) %>%
    pivot_longer(cols = everything(), names_to = "var", values_to = "sq_m") %>%
    mutate(year = as.integer(gsub("VALUE_", "", var))) %>%
    arrange(year) %>%
    group_by(year) %>%
    summarise(sq_m = sum(sq_m, na.rm = TRUE), .groups = "drop") %>%
    mutate(cumulative_sq_km = cumsum(sq_m) / 1e6) %>%
    select(year, cumulative_sq_km)
}

get_city_year_value <- function(city, year, ssp, rl10 = FALSE) {
  path <- find_slr_csv(city, year, ssp, rl10)
  if (is.null(path)) return(NA_real_)

  series <- extract_exposure_series(path)
  if (is.null(series) || nrow(series) == 0) return(NA_real_)

  val <- series %>% filter(year == 2015) %>% pull(cumulative_sq_km)
  if (length(val) == 0) return(NA_real_) else val[1]
}

build_scenario_table <- function(ssp, rl10 = FALSE) {
  tibble(
    city = cities,
    `2020` = map_dbl(cities, ~ get_city_year_value(.x, 2020, ssp, rl10)),
    `2050` = map_dbl(cities, ~ get_city_year_value(.x, 2050, ssp, rl10)),
    `2100` = map_dbl(cities, ~ get_city_year_value(.x, 2100, ssp, rl10))
  ) %>%
    filter(!(is.na(`2020`) & is.na(`2050`) & is.na(`2100`)))
}

theme_slr <- function() {
  theme_minimal(base_size = 12) +
    theme(
      panel.grid.minor = element_blank(),
      panel.grid.major.y = element_blank(),
      panel.grid.major.x = element_line(color = "#D9E2F2", linewidth = 0.5),
      legend.title = element_blank(),
      legend.position = "top",
      plot.title = element_text(face = "bold", size = 18, color = "#25364A"),
      plot.subtitle = element_text(size = 11, color = "#4A5D75"),
      axis.title.y = element_blank(),
      axis.text.y = element_text(size = 11, color = "#222222"),
      axis.text.x = element_text(size = 10, color = "#222222"),
      plot.background = element_rect(fill = "white", color = NA),
      panel.background = element_rect(fill = "white", color = NA),
      legend.background = element_rect(fill = "white", color = NA)
    )
}

save_plot <- function(p, filename, width = 1400, height = 900) {
  ggsave(
    filename = file.path("plots", filename),
    plot = p,
    width = width,
    height = height,
    units = "px",
    dpi = 144,
    bg = "white"
  )
}

col_2050 <- "#8DB3CE"
col_2100_add <- "#1F5B99"
col_ssp245 <- "#2C7FB8"
col_ssp585 <- "#08306B"
col_line <- "#7E8DA0"

slr_245 <- build_scenario_table(245, rl10 = FALSE)
slr_585 <- build_scenario_table(585, rl10 = FALSE)
slr_245_rl10 <- build_scenario_table(245, rl10 = TRUE)
slr_585_rl10 <- build_scenario_table(585, rl10 = TRUE)

if (nrow(slr_245) == 0 && nrow(slr_585) == 0) {
  stop("No readable SLR CSVs were found.")
}

make_main_bar <- function(df245, df585, rl10 = FALSE, out_name = "slr.png") {
  a <- df245 %>%
    full_join(df585, by = "city", suffix = c("_245", "_585")) %>%
    transmute(
      city = city,
      y2050 = coalesce(`2050_245`, `2050_585`),
      y2100 = coalesce(`2100_245`, `2100_585`)
    ) %>%
    filter(!(is.na(y2050) & is.na(y2100))) %>%
    mutate(
      y2050 = replace_na(y2050, 0),
      y2100 = replace_na(y2100, 0),
      additional_2100 = pmax(y2100 - y2050, 0)
    ) %>%
    arrange(y2100) %>%
    mutate(city = factor(city, levels = city))

  if (nrow(a) == 0) return(NULL)

  plot_df <- a %>%
    select(city, y2050, additional_2100) %>%
    pivot_longer(cols = c(y2050, additional_2100), names_to = "part", values_to = "value") %>%
    mutate(
      part = factor(
        part,
        levels = c("y2050", "additional_2100"),
        labels = c("Exposure by 2050", "Additional exposure by 2100")
      )
    )

  ttl <- if (rl10) {
    "Settlement area exposed to 10% annual chance flood"
  } else {
    "Settlement area exposed to median projected sea level rise"
  }

  subttl <- if (rl10) {
    "Combined city ranking using scenario results: exposure by 2050 and additional increase by 2100"
  } else {
    "Combined city ranking using scenario results: exposure by 2050 and additional increase by 2100"
  }

  p <- ggplot(plot_df, aes(x = value, y = city, fill = part)) +
    geom_col(width = 0.68) +
    scale_fill_manual(values = c("Exposure by 2050" = col_2050, "Additional exposure by 2100" = col_2100_add)) +
    scale_x_continuous(labels = label_number(accuracy = 0.1), expand = expansion(mult = c(0, 0.03))) +
    labs(
      title = ttl,
      subtitle = subttl,
      x = "Exposed built-up area (sq km)"
    ) +
    theme_slr()

  save_plot(p, out_name)
}

make_old_style_all_cities <- function(df245, df585, target_year, out_name) {
  a <- df245 %>%
    full_join(df585, by = "city", suffix = c("_245", "_585")) %>%
    transmute(
      city = city,
      SSP245 = .data[[target_year %+% "_245"]],
      SSP585 = .data[[target_year %+% "_585"]]
    ) %>%
    filter(!(is.na(SSP245) & is.na(SSP585))) %>%
    mutate(
      SSP245 = replace_na(SSP245, 0),
      SSP585 = replace_na(SSP585, 0),
      avg_val = (SSP245 + SSP585) / 2
    ) %>%
    arrange(avg_val) %>%
    mutate(city = factor(city, levels = city))

  if (nrow(a) == 0) return(NULL)

  p <- ggplot(a, aes(y = city)) +
    geom_segment(aes(x = SSP245, xend = SSP585, yend = city), color = col_line, linewidth = 1.4) +
    geom_point(aes(x = SSP245, color = "SSP245"), size = 4) +
    geom_point(aes(x = SSP585, color = "SSP585"), size = 4) +
    scale_color_manual(values = c("SSP245" = col_ssp245, "SSP585" = col_ssp585)) +
    scale_x_continuous(labels = label_number(accuracy = 0.1), expand = expansion(mult = c(0, 0.03))) +
    labs(
      title = "Exposure comparison across climate scenarios",
      subtitle = paste0(target_year, " exposed built-up area under median projected sea level rise"),
      x = "Exposed built-up area (sq km)"
    ) +
    theme_slr()

  save_plot(p, out_name)
}

make_compare_plot <- function(df245, df585, target_year, rl10 = FALSE, out_name) {
  a <- df245 %>%
    full_join(df585, by = "city", suffix = c("_245", "_585")) %>%
    transmute(
      city = city,
      SSP245 = .data[[target_year %+% "_245"]],
      SSP585 = .data[[target_year %+% "_585"]]
    ) %>%
    filter(!(is.na(SSP245) & is.na(SSP585))) %>%
    mutate(
      SSP245 = replace_na(SSP245, 0),
      SSP585 = replace_na(SSP585, 0),
      avg_val = (SSP245 + SSP585) / 2
    ) %>%
    arrange(avg_val) %>%
    mutate(city = factor(city, levels = city))

  if (nrow(a) == 0) return(NULL)

  subttl <- if (rl10) {
    paste0(target_year, " exposed built-up area with 10% annual chance flood condition")
  } else {
    paste0(target_year, " exposed built-up area under median projected sea level rise")
  }

  ttl <- if (rl10) {
    "Scenario comparison for RL10 flood exposure"
  } else {
    "Exposure comparison across climate scenarios"
  }

  p <- ggplot(a, aes(y = city)) +
    geom_segment(aes(x = SSP245, xend = SSP585, yend = city), color = col_line, linewidth = 1.4) +
    geom_point(aes(x = SSP245, color = "SSP245"), size = 4) +
    geom_point(aes(x = SSP585, color = "SSP585"), size = 4) +
    scale_color_manual(values = c("SSP245" = col_ssp245, "SSP585" = col_ssp585)) +
    scale_x_continuous(labels = label_number(accuracy = 0.1), expand = expansion(mult = c(0, 0.03))) +
    labs(
      title = ttl,
      subtitle = subttl,
      x = "Exposed built-up area (sq km)"
    ) +
    theme_slr()

  save_plot(p, out_name)
}

`%+%` <- function(a, b) paste0(a, b)

# Restored core plots
make_main_bar(slr_245, slr_585, rl10 = FALSE, out_name = "slr.png")
make_main_bar(slr_245_rl10, slr_585_rl10, rl10 = TRUE, out_name = "slr_RL10.png")

# Restored previous-style scenario comparison plots
make_old_style_all_cities(slr_245, slr_585, "2050", "all_cities_slr_2050.png")
make_old_style_all_cities(slr_245, slr_585, "2100", "all_cities_slr_2100.png")

# Keep only the two useful scenario compare plots
make_compare_plot(slr_245, slr_585, "2050", rl10 = FALSE, out_name = "slr_compare_2050.png")
make_compare_plot(slr_245, slr_585, "2100", rl10 = FALSE, out_name = "slr_compare_2100.png")