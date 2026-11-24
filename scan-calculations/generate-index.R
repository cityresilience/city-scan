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
  "```",
  ""
)

n_tasks <- 0
for (task in order$sections) {
  # Check charts/index.qmd exists for this task
  task_qmd <- file.path(city_root, "tasks", task, "charts", "index.qmd")
  if (!file.exists(task_qmd)) next

  lines <- c(lines, paste0("{{< include ../tasks/", task, "/charts/index.qmd >}}"), "")
  n_tasks <- n_tasks + 1
}

output_file <- file.path(sc_dir, "index.qmd")
writeLines(lines, output_file)
message("Generated ", output_file, " with ", n_tasks, " task sections")
