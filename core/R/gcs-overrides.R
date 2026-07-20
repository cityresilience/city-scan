# GCS Override Functions
# This file is only called when GCS is true and authenticaed. It will override the original functions to return both local AND GCS file paths.
#
# Layout:
#   1. ORIGINALS      - save base/package fns before overriding
#   2. PATH HELPERS   - make_relative, resolve, local_or_temp (the core logic)
#   3. LOOKUP TABLES  - list GCS buckets once into membership vectors
#   4. OVERRIDES      - list.files, file.exists, readers (all defer to resolve)
#   5. UPLOAD         - push render outputs back to GCS

# =============================================================================
# 1. ORIGINALS
# =============================================================================
list.files_orig <- base::list.files
read_csv_orig <- readr::read_csv
read_yaml_orig <- yaml::read_yaml
file.exists_orig <- base::file.exists
rast_orig <- terra::rast
vect_orig <- terra::vect
read_sf_orig <- sf::read_sf
st_read_orig <- sf::st_read


# =============================================================================
# 2. PATH HELPERS
# =============================================================================

# Strip city_dir prefix from absolute paths to get the relative path for GCS lookup
make_relative <- function(path) {
  if (exists("city_dir") && city_dir != "." && startsWith(path, city_dir)) {
    rel <- sub(paste0("^", gsub("([.])", "\\\\\\1", city_dir), "/?"), "", path)
    if (nchar(rel) == 0) return(".")
    return(rel)
  }
  return(path)
}

# Resolve a logical path to real source(s), local-first, GCS appended.
# One place for the local -> scan-GCS -> global-GCS logic that the overrides
# below otherwise copy-paste. as_vsigs=TRUE returns GCS hits as /vsigs/... for
# GDAL streaming (rast/vect/read_sf/st_read); FALSE returns the GCS object key.
resolve <- function(path, as_vsigs = FALSE) {
  out <- character(0)
  local <- if (exists("city_dir") && city_dir != "." && !startsWith(path, city_dir)) file.path(city_dir, path) else path
  if (file.exists_orig(local)) out <- c(out, local)

  if (exists("USE_GCS") && USE_GCS) {
    rel <- make_relative(path)
    scan_key <- gsub("//", "/", paste0(scan_id, "/", rel))
    if (exists("gcs_file_lookup") && scan_key %in% gcs_file_lookup)
      out <- c(out, if (as_vsigs) paste0("/vsigs/", GCS_BUCKET, "/", scan_key) else scan_key)
    if (exists("gcs_global_file_lookup") && rel %in% gcs_global_file_lookup)
      out <- c(out, if (as_vsigs) paste0("/vsigs/", GLOBAL_DATA_BUCKET, "/", rel) else rel)
  }
  unique(out)
}

# Given a resolve()'d path: if it's a real local file return it; otherwise it's
# a GCS object key -> download to tempfile and return that. For text readers
# (read_csv / read_yaml) that can't stream via /vsigs/.
local_or_temp <- function(path, fileext) {
  if (file.exists_orig(path)) return(path)
  bucket <- if (startsWith(path, paste0(scan_id, "/"))) GCS_BUCKET else GLOBAL_DATA_BUCKET
  tmp <- tempfile(fileext = fileext)
  suppressMessages(gcs_get_object(path, bucket = bucket, saveToDisk = tmp))
  tmp
}


# =============================================================================
# 3. LOOKUP TABLES  (list each bucket once; overrides do in-memory %in% checks)
# =============================================================================
if (exists("USE_GCS") && USE_GCS) {
  message("\n=== GCS OVERRIDES DEBUG ===")
  message("Building file lookups for scan_id: ", scan_id)

  # Scan-specific files from GCS (may not exist if running locally)
  gcs_file_lookup <- tryCatch({
    gcs_all_files <- gcs_list_objects(GCS_BUCKET, prefix = paste0(scan_id, "/"))
    if (is.null(gcs_all_files) || nrow(gcs_all_files) == 0) character(0)
    else gcs_all_files$name
  }, error = function(e) { message("No scan files on GCS (local mode)"); character(0) })

  # Global private data files from GCS
  gcs_global_file_lookup <- tryCatch({
    gcs_global_files <- gcs_list_objects(GLOBAL_DATA_BUCKET)
    if (is.null(gcs_global_files) || nrow(gcs_global_files) == 0) character(0)
    else gcs_global_files$name
  }, error = function(e) { message("Could not list global data bucket"); character(0) })

  # Global public data files from GCS
  gcs_public_file_lookup <- tryCatch({
    gcs_public_files <- gcs_list_objects("city-scan-global-public")
    if (is.null(gcs_public_files) || nrow(gcs_public_files) == 0) character(0)
    else gcs_public_files$name
  }, error = function(e) { message("Could not list public bucket"); character(0) })

  # Local files
  local_file_lookup <- if (exists("city_dir") && city_dir != ".") {
    list.files_orig(city_dir, recursive = TRUE, full.names = FALSE)
  } else {
    character(0)
  }

  message("Available: ", length(gcs_file_lookup), " scan files, ",
          length(gcs_global_file_lookup), " global private files, ",
          length(gcs_public_file_lookup), " global public files, ",
          length(local_file_lookup), " local files")

  # Show first few scan files for debugging
  if (length(gcs_file_lookup) > 0) {
    message("First 3 scan files: ", paste(head(gcs_file_lookup, 3), collapse = ", "))
  }
}


# =============================================================================
# 4. OVERRIDES  (all single-file lookups defer to resolve())
# =============================================================================

# Override list.files — enumerate local + scan-GCS for a directory.
# Stays its own function (resolve() locates ONE file; this enumerates a dir).
list.files <- function(path = ".", pattern = NULL, all.files = FALSE, full.names = FALSE, recursive = FALSE, ...) {

  # Get local files — use absolute path for local
  local_path <- if (exists("city_dir") && city_dir != "." && !startsWith(path, city_dir)) {
    file.path(city_dir, path)
    } else {
    path
    }

  local_files <- list.files_orig(local_path, pattern, all.files, full.names, recursive, ...)

  # Get GCS scan-specific files
  gcs_scan_files <- character(0)
  if (exists("USE_GCS") && USE_GCS && exists("gcs_file_lookup")) {
    path_clean <- gsub("/+$", "", make_relative(path))
    search_prefix <- paste0(scan_id, "/", path_clean, "/")
    gcs_matches <- gcs_file_lookup[startsWith(gcs_file_lookup, search_prefix)]
    gcs_scan_files <- sub(paste0("^", search_prefix), "", gcs_matches)
    gcs_scan_files <- gcs_scan_files[nchar(gcs_scan_files) > 0]

    if (!recursive)        gcs_scan_files <- gcs_scan_files[!grepl("/", gcs_scan_files)]
    if (!is.null(pattern)) gcs_scan_files <- gcs_scan_files[grepl(pattern, gcs_scan_files)]
    # SAME full.names form as local: prefix with local_path, not the relative path
    if (full.names)        gcs_scan_files <- file.path(local_path, gcs_scan_files)
  }

  unique(c(local_files, gcs_scan_files))
}


# Override file.exists - TRUE if local OR any GCS source has it (via resolve)
  file.exists <- function(...) {
    files <- c(...)
    vapply(files, function(filepath) {
      if (is.na(filepath) || is.null(filepath)) return(FALSE)
      length(resolve(filepath)) > 0
    }, logical(1))
  }


# Helper function to create a CSV parser with col_types support for gcs_get_object
# Usage: gcs_get_object(path, bucket, parseFunction = make_csv_parser(col_types = "ccd"))
make_csv_parser <- function(col_types = NULL, ...) {
  function(x) {
    read_csv_orig(x, col_types = col_types, ...)
  }
}

# Override read_csv - resolve to local or download-to-temp, then read
read_csv <- function(file, ...) {
  src <- resolve(file)
  if (length(src) == 0) return(read_csv_orig(file, ...))  # let original error
  read_csv_orig(local_or_temp(src[1], ".csv"), ...)
}

# Override read_yaml - resolve to local or download-to-temp, then read
read_yaml <- function(file, ...) {
  src <- resolve(file)
  if (length(src) == 0) return(read_yaml_orig(file, ...))
  read_yaml_orig(local_or_temp(src[1], ".yml"), ...)
}



# Override rast - resolve to local path or /vsigs/ stream, then read
rast <- function(x, ...) {
  if (!is.character(x) || length(x) == 0) return(rast_orig(x, ...))
  src <- resolve(x, as_vsigs = TRUE)
  rast_orig(if (length(src) > 0) src[1] else x, ...)
}

# Override vect - resolve to local path or /vsigs/ stream, then read
vect <- function(x, ...) {
  if (!is.character(x) || length(x) == 0) return(vect_orig(x, ...))
  src <- resolve(x, as_vsigs = TRUE)
  vect_orig(if (length(src) > 0) src[1] else x, ...)
}

# Override read_sf - resolve to local path or /vsigs/ stream, then read
read_sf <- function(dsn, ...) {
  if (!is.character(dsn) || length(dsn) == 0) return(read_sf_orig(dsn, ...))
  src <- resolve(dsn, as_vsigs = TRUE)
  read_sf_orig(if (length(src) > 0) src[1] else dsn, ...)
}

# Override st_read - resolve to local path or /vsigs/ stream, then read
st_read <- function(dsn, ...) {
  if (!is.character(dsn) || length(dsn) == 0) return(st_read_orig(dsn, ...))
  src <- resolve(dsn, as_vsigs = TRUE)
  st_read_orig(if (length(src) > 0) src[1] else dsn, ...)
}


# =============================================================================
# 5. UPLOAD
# =============================================================================
upload_outputs_to_gcs <- function() {
  if (USE_GCS && exists("GCS_UPLOAD") && GCS_UPLOAD) {
    message("Uploading outputs to GCS...")
    gcs_upload("03-render-output",
               bucket = GCS_BUCKET,
               name = paste0(scan_id, "/03-render-output/"),
               predefinedAcl = "bucketLevel")
    message("✓ Outputs uploaded")
  }
}
