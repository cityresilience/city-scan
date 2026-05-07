# Plots for City Scan

source(here("core/R/setup.R"), local = T)

# 1. Standard City Scan Plots --------------------------------------------------

# tryCatch(source(here("core/R/population-growth.R"), local = T), error = \(e) warning(e))
tryCatch(source(here("core/R/chart-urban-extent.R"), local = T), error = \(e) warning(e))
tryCatch(source(here("core/R/chart-flooding.R"), local = T), error = \(e) warning(e))
tryCatch(source(here("core/R/chart-landcover.R"), local = T), error = \(e) warning(e))
tryCatch(source(here("core/R/chart-elevation.R"), local = T), error = \(e) warning(e))
tryCatch(source(here("core/R/chart-slope.R"), local = T), error = \(e) warning(e))
tryCatch(source(here("core/R/chart-solar-pv.R"), local = T), error = \(e) warning(e))
tryCatch(source(here("core/R/chart-fwi.R"), local = T), error = \(e) warning(e))
tryCatch(source(here("core/R/chart-age-sex-distribution.R"), local = T), error = \(e) warning(e))
tryCatch(source(here("core/R/chart-flood-archive.R"), local = T), error = \(e) warning(e))
tryCatch(source(here("core/R/chart-earthquakes.R"), local = T), error = \(e) warning(e))
