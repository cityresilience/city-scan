#!/usr/bin/env Rscript
# Pre-render script: reads sections.yml for section order, generates index.qmd
# with include directives. Section gating is via sections.yml + per-task
# charts/index.qmd existence (plus a basic_info.yml conditional for oxford).

library(yaml)
library(here)

# Detect if here() resolves to scan-calculations/ or city root
in_sc <- file.exists(here("sections.yml"))
city_root <- if (in_sc) normalizePath(here("..")) else here()
sc_dir <- if (in_sc) here() else here("scan-calculations")

order <- read_yaml(file.path(sc_dir, "sections.yml"))
city_inputs <- read_yaml(file.path(city_root, "01-user-input", "city_inputs.yml"))
city_name <- city_inputs$city_name

lines <- c(
  "---",
  paste0("title: \"", city_name, " City Scan\""),
  "engine: knitr",
  "execute:",
  "  echo: false",
  "  warning: false",
  "  message: false",
  "---",
  "",
  "```{r}",
  "#| label: setup",
  "#| include: false",
  "USE_GCS <<- FALSE",
  "here::i_am(\"scan-calculations/index.qmd\")",
  "source(here::here(\"core/R/setup.R\"))",
  "source(here::here(\"core/R/fns.R\"))",
  "dir.create(here(\"03-render-output\", \"plots\"), recursive = TRUE, showWarnings = FALSE)",
  "knitr::opts_chunk$set(error = TRUE)",
  "source(here::here(\"core/R/benchmark-assembly.R\"))",
  "```",
  ""
)

# Tasks with a full custom qmd in scan-calculations/ (replaces the task include)
custom_includes <- c(
  demographics = "demographics_charts.qmd",
  fathom       = "fathom_charts.qmd",
  earthquake   = "earthquake_charts.qmd"
)

# Tasks that get an extra note file appended after the standard task include
note_includes <- c(
  worldpop  = "worldpop_density_note.qmd",
  elevation = "elevation_note.qmd",
  slope     = "slope_note.qmd"
)

# Read basic_info.yml for conditional sections
basic_info_path <- list.files(file.path(city_root, "02-process-output", "tabular"), pattern = "basic_info\\.yml$", full.names = TRUE)
basic_info <- if (length(basic_info_path) > 0) read_yaml(basic_info_path[1]) else list()

n_tasks <- 0
for (task in order$sections) {
  # Skip oxford if city is not in Oxford Economics
  if (task == "oxford" && !isTRUE(basic_info$in_oxford)) next

  # Check charts/index.qmd exists for this task (proxy for "was the task run?")
  task_qmd <- file.path(city_root, "tasks", task, "charts", "index.qmd")
  if (!file.exists(task_qmd)) next

  if (task %in% names(custom_includes)) {
    # Use the improved custom qmd instead of the raw task include
    lines <- c(lines, paste0("{{< include ", custom_includes[task], " >}}"), "")
  } else {
    # Standard task include
    lines <- c(lines, paste0("{{< include ../tasks/", task, "/charts/index.qmd >}}"), "")
  }

  # Append note file if one exists for this task
  if (task %in% names(note_includes)) {
    lines <- c(lines, paste0("{{< include ", note_includes[task], " >}}"), "")
  }

  n_tasks <- n_tasks + 1
}

output_file <- file.path(sc_dir, "index.qmd")
writeLines(lines, output_file)
message("Generated ", output_file, " with ", n_tasks, " task sections")
