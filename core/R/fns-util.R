# =========================================================
# UTILITY FUNCTIONS & HELPERS
# =========================================================


# ---------- General Helpers ----------
exists_and_true <- \(x) !is.null(x) && is.logical(x) && x

`%ni%` <- Negate(`%in%`)

which_not <- function(v1, v2, swap = F, both = F) {
  if (both) {
    list(
      "In V1, not in V2" = v1[v1 %ni% v2],
      "In V2, not in V1" = v2[v2 %ni% v1]
    )
  } else
  if (swap) {
    v2[v2 %ni% v1]
  } else {
    v1[v1 %ni% v2]
  }
}

tryCatch_named <- \(name, expr) {
  tryCatch(expr, error = \(e) {
    message(paste("Failure:", name, "-", e$message))
    warning(glue("Error on {name}: {e}"))
  })
}

rotate_ccw <- \(x) t(x)[ncol(x):1,]


# ---------- DATA RELATED HELPERS ----------

type_data <- function(data) {
  data_class <- class(data)[1]
  if (data_class %ni% c("SpatVector", "SpatRaster")) {
    stop(glue("On {yaml_key} data is neither SpatVector or SpatRaster, but {data_class}"))
  }
  data_type <- if (data_class == "SpatRaster") "raster" else geomtype(data)
  if (data_type %ni% c("raster", "points", "lines", "polygons")) {
    stop(glue("On {yaml_key} data is not of type 'raster', 'points', 'lines', or 'polygons'"))
  }
  return(data_type)
}


normalize <- function(x, na.rm = T) {
  return((x - min(x, na.rm = na.rm)) /(max(x, na.rm = na.rm)-min(x, na.rm = na.rm)))
}

Mode <- \(x, na.rm = F) {
  if (na.rm) x <- na.omit(x)
  unique_values <- unique(x)
  unique_values[which.max(tabulate(match(x, unique_values)))]
}


# ---------- FUZZY READ FILES ----------
fuzzy_read <- function(dir, fuzzy_string, FUN = NULL, path = T, convert_to_vect = F, ...) {
    all_items <- list.files(dir, full.names = FALSE)
    files_only <- all_items[!dir.exists(file.path(dir, all_items))]
    file <- files_only %>% str_subset(fuzzy_string)

    if (length(file) > 1) warning(paste("Too many", fuzzy_string, "files in", dir))
    if (length(file) < 1) {
      file <- list.files(dir, recursive = T, full.names = FALSE) %>%
        str_subset(fuzzy_string) %>%
        .[!grepl("__MACOSX", .)]
      if (length(file) > 1 && any(grepl("\\.shp$", file, ignore.case = TRUE))) {
        file <- file[grepl("\\.shp$", file, ignore.case = TRUE)]
      }
      if (length(file) > 1) warning(paste("Too many", fuzzy_string, "files in", dir))
      if (length(file) < 1) warning(paste("No", fuzzy_string, "file in", dir))
    }
    if (length(file) == 1) {
      if (is.null(FUN)) {
        FUN <- if (tolower(str_sub(file, -4, -1)) == ".tif") rast else vect
      }
      if (!path) {
      content <- suppressMessages(FUN(dir, file, ...))
      } else {
        file_path <- file.path(dir, file)

        # Try reading normally, if fails try with /vsigs/ for GCS
        content <- tryCatch({
          suppressMessages(FUN(file_path, ...))
        }, error = function(e) {
          if (exists("USE_GCS") && USE_GCS) {
            # Try with /vsigs/ prefix
            path_clean <- gsub("/+$", "", dir)
            gcs_path <- paste0("/vsigs/", GCS_BUCKET, "/", scan_id, "/", path_clean, "/", file)
            suppressMessages(FUN(gcs_path, ...))
          } else {
            stop(e)
          }
      })
      }
    if (convert_to_vect && class(content)[1] %in% c("SpatRaster", "RasterLayer")) {
        content <- rast_as_vect(content)
      }
      return(content)
    } else {
      return(NA)
    }
  }


# ---------- LOAD MAPS STATIC FOR SPECIFIC TASKS ----------
# Resolve which layers and custom scripts to render for a set of task names.
# Reads source/tasks.yml for aliases (e.g. population → worldpop), then walks
# each task's maps.yml to collect layers + custom + recursive depends.
# A maps.yml `layers:` entry may be a plain string or a `name: {overrides}`
# dict; both forms normalize to the layer name here.
# Returns list(layers, custom, dep_layers).
resolve_render_targets <- function(render_tasks) {
  task_aliases <- yaml::read_yaml(here("source/tasks.yml"))$aliases
  resolved_tasks <- render_tasks
  for (i in seq_along(resolved_tasks)) {
    alias <- task_aliases[[resolved_tasks[i]]]
    if (!is.null(alias) && is.character(alias)) resolved_tasks[i] <- alias
  }
  layer_name_of <- function(entry) if (is.character(entry)) entry else names(entry)[[1]]
  render_layers <- c(); render_custom <- c(); dep_layers <- c()
  for (task_name in resolved_tasks) {
    maps_yml <- here("tasks", task_name, "maps.yml")
    if (!file.exists(maps_yml)) next
    task_maps <- yaml::read_yaml(maps_yml)
    if (!is.null(task_maps$layers)) render_layers <- c(render_layers, vapply(task_maps$layers, layer_name_of, character(1), USE.NAMES = FALSE))
    if (!is.null(task_maps$custom)) render_custom <- c(render_custom, task_maps$custom)
    if (!is.null(task_maps$depends)) {
      for (dep in task_maps$depends) {
        dep_resolved <- task_aliases[[dep]] %||% dep
        if (is.list(dep_resolved)) dep_resolved <- dep_resolved$folder %||% dep
        dep_yml <- here("tasks", dep_resolved, "maps.yml")
        if (file.exists(dep_yml)) {
          dep_maps <- yaml::read_yaml(dep_yml)
          if (!is.null(dep_maps$layers)) dep_layers <- c(dep_layers, vapply(dep_maps$layers, layer_name_of, character(1), USE.NAMES = FALSE))
        }
      }
    }
  }
  list(layers = c(render_layers, dep_layers), custom = render_custom, dep_layers = dep_layers)
}



# ---------- MERGE LISTS ----------

# merge_text_lists <- function(...) {
#   lists <- c(...)
#   keys <- unique(names(lists))
#   merged <- sapply(keys, function(k) {
#     index <- names(lists) == k
#     new_list <- c(unlist(lists[index], F, T))
#     names(new_list) <- str_extract(names(new_list), "([^\\.]+)$", group = T)
#     unique(names(new_list)) %>%
#       sapply(function (j) {
#         index2 <- names(new_list) == j
#         new_list2 <- c(unlist(new_list[index2], F, T))
#         names(new_list2) <- str_extract(names(new_list2), "([^\\.]+)$", group = T)
#         return(new_list2)
#       }, simplify = F)
#     return(new_list)
#   }, simplify = F)
#   return(merged)
# }

merge_lists <- \(x, y, key = NULL) {
  # At leaf level: for footnotes, prefer x (manual-text) over y (generic-text)
  # For other fields, concatenate as before
  if (is.null(names(x)) | is.null(names(y))) {
    if (identical(key, "footnote") && !is.null(x) && length(x) > 0 && !all(is.na(x))) return(x)
    return(unique(c(x, y)))
  }
  nameless <- c(x[names(x) == ""], y[names(y) == ""])
  nameless <- nameless[!(nameless %in% c(names(x), names(y)))]
  unique_nodes_x <- x[setdiff(names(x), names(y))]
  unique_nodes_y <- y[setdiff(names(y), names(x))]
  common_keys <- intersect(names(x), names(y)) %>% .[. != ""]
  common_nodes <- if (length(common_keys) == 0) NULL else {
    sapply(common_keys, \(k) merge_lists(x[[k]], y[[k]], key = k), simplify = F)
  }
  merged <- unlist(list(common_nodes, unique_nodes_x, unique_nodes_y, nameless), recursive = F)
  return(merged)
}




