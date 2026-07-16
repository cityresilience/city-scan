
# Path to Application Default Credentials - the file that gcloud creates when you run gcloud auth application-default login. If you haven't authenticate your GCS, the you probably (must) need to do that first.


if (!exists("USE_GCS")) {GCS <- TRUE}

GCS_PROJECT <- "city-scan-gee-test"
GCS_BUCKET <- "crp-city-scan"
GLOBAL_DATA_BUCKET <- "city-scan-global-data"

message("HOME: ", Sys.getenv("HOME"))
message("path.expand ~: ", path.expand("~"))

# Try multiple candidate paths for ADC — sandboxed IDEs may block some
adc_candidates <- if (.Platform$OS.type == "windows") {
  c(Sys.getenv("GOOGLE_APPLICATION_CREDENTIALS"),
    file.path(Sys.getenv("APPDATA"), "gcloud", "application_default_credentials.json"))
} else {
  c(Sys.getenv("GOOGLE_APPLICATION_CREDENTIALS"),
    file.path(Sys.getenv("HOME"), ".config", "gcloud", "application_default_credentials.json"),
    file.path(path.expand("~"), ".config", "gcloud", "application_default_credentials.json"))
}
adc_candidates <- adc_candidates[nchar(adc_candidates) > 0]
adc_path <- Find(file.exists, adc_candidates)
if (is.null(adc_path)) adc_path <- adc_candidates[1] # fallback for error message


# Debug output
message("\n=== GCS AUTH DEBUG ===")
message("USE_GCS: ", USE_GCS)
message("scan_id exists: ", exists("scan_id"))
if (exists("scan_id")) message("scan_id value: ", scan_id)
message("adc candidates: ", paste(adc_candidates, collapse = " | "))
message("adc_path: ", adc_path)
message("adc_path exists: ", file.exists(adc_path))

# If USE_GCS is true -> Authenticate & override file reading functions
if (file.exists(adc_path)) {
  message("\nAuthenticating to GCS...")
  Sys.setenv(GOOGLE_APPLICATION_CREDENTIALS = adc_path, GCS_AUTH_FILE = adc_path)
  tryCatch({
    gcs_auth(token = gargle::credentials_app_default(scopes = "https://www.googleapis.com/auth/cloud-platform"))
    message("GCS authentication successful")
  }, error = function(e) {
    if (USE_GCS) {
      USE_GCS <- FALSE
      message("GCS authentication failed: ", e$message)
      message("Falling back to using local files.")
    } else {
      message("GCS authentication failed; ", e$message)
      message("Scan is already set to use local files (USE_GCS=FALSE)")
    }})
  if (USE_GCS) {
    message("About to source gcs-overrides.R...")
    source(here("core/R/gcs-overrides.R"))
  }
} else {
  message("\nUsing local files for data input.")
  if (!USE_GCS) message("Reason: USE_GCS is FALSE")
  if (USE_GCS) message("Reason: adc_path does not exist")
}
