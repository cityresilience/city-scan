import os
import ee
import google.auth
from core.py.log_module import setup_logger

logger = setup_logger(__name__)

_GEE_SCOPES = [
    "https://www.googleapis.com/auth/earthengine",
    "https://www.googleapis.com/auth/cloud-platform",
]


def _on_cloud_run():
    return os.environ.get("K_SERVICE") is not None


def _gee_credentials():
    """Resolve ADC with EE scopes. Supports Cloud Run SA injection,
    GOOGLE_APPLICATION_CREDENTIALS, and local gcloud ADC."""
    creds, detected_project = google.auth.default(scopes=_GEE_SCOPES)
    project = os.environ.get("GEE_PROJECT", detected_project)
    return creds, project


def init_gee():
    """Initialize GEE with explicit credentials from google.auth.default().

    Supports three credential tiers without hardcoding any account or project:
      1. Cloud Run service account (ADC injected by runtime)
      2. GOOGLE_APPLICATION_CREDENTIALS env var (service account key file)
      3. Local gcloud ADC (created with the earthengine scope)

    Does NOT interactively authenticate — that would hang a task run.
    If resolution fails, raises with a clear instruction to run `scan --check gee`.
    """
    try:
        creds, project = _gee_credentials()
        ee.Initialize(credentials=creds, project=project)
        logger.info(f"GEE initialized (project={project})")
        return
    except Exception as e:
        raise RuntimeError(
            f"GEE authentication failed ({e}). Run `scan --check gee` for a guided fix, or:\n"
            "  gcloud auth application-default login \\\n"
            "    --scopes=openid,https://www.googleapis.com/auth/userinfo.email,"
            "https://www.googleapis.com/auth/cloud-platform,"
            "https://www.googleapis.com/auth/earthengine"
        ) from e


def init_gcs():
    """Ensure GCS access is available.

    - Cloud Run: ADC is injected by the runtime (nothing to do).
    - Local: relies on `gcloud auth application-default login`.
      google.cloud.storage.Client() picks up ADC automatically.
    """
    if _on_cloud_run():
        logger.info("GCS: running on Cloud Run, using service account ADC")
        return

    # Local: just verify ADC exists so we can give a helpful error early
    if os.name == "nt":  # Windows
        adc_path = os.path.join(os.environ["APPDATA"], "gcloud", "application_default_credentials.json")
    else:
        adc_path = os.path.expanduser("~/.config/gcloud/application_default_credentials.json")
    if not os.path.exists(adc_path):
        raise RuntimeError(
            "GCS credentials not found. Run:\n"
            "  gcloud auth application-default login"
        )
    # Configure GDAL to use the same ADC for /vsigs/ access
    os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = adc_path
    logger.info("GCS: using local ADC credentials")
