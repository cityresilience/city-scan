import os
from pathlib import Path
from core.py.log_module import setup_logger

logger = setup_logger(__name__)


def _on_cloud_run():
    # K_SERVICE = Cloud Run services; CLOUD_RUN_JOB/CLOUD_RUN_EXECUTION = jobs
    return any(os.environ.get(v) is not None
               for v in ("K_SERVICE", "CLOUD_RUN_JOB", "CLOUD_RUN_EXECUTION"))


def configure_gdal_gcs(service_account_file: str | None = None) -> None:
    """
    Configure GDAL/Rasterio authentication for Google Cloud Storage (/vsigs/).

    Supports:
    A) Local ADC via `gcloud auth application-default login`
    B) Explicit service account JSON
    C) Cloud Run (automatic ADC)

    This sets GOOGLE_APPLICATION_CREDENTIALS if necessary.
    """

    # Cloud Run → rely on injected service account
    if _on_cloud_run():
        logger.info("GDAL GCS: running on Cloud Run, using injected ADC")
        return

    # 1. If already configured, respect it
    existing = os.environ.get("GOOGLE_APPLICATION_CREDENTIALS")
    if existing:
        if not Path(existing).exists():
            raise RuntimeError(
                f"GOOGLE_APPLICATION_CREDENTIALS set but file not found:\n{existing}"
            )
        logger.info(f"GDAL GCS: using existing credentials at {existing}")
        return

    # 2. Explicit service account passed in
    if service_account_file:
        path = Path(service_account_file)
        if not path.exists():
            raise RuntimeError(
                f"Provided service account file not found:\n{service_account_file}"
            )
        os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = str(path.resolve())
        logger.info(f"GDAL GCS: using explicit service account at {path}")
        return

    # 3. Fallback to local ADC
    if os.name == "nt":
        adc_path = Path(os.environ["APPDATA"]) / "gcloud" / "application_default_credentials.json"
    else:
        adc_path = Path.home() / ".config" / "gcloud" / "application_default_credentials.json"

    if adc_path.exists():
        os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = str(adc_path.resolve())
        logger.info(f"GDAL GCS: using local ADC at {adc_path}")
        return

    # 4. Nothing found
    raise RuntimeError(
        "No GDAL GCS credentials found.\n\n"
        "Options:\n"
        "A) Run: gcloud auth application-default login\n"
        "B) Pass service_account_file='/path/to/key.json'\n"
        "C) Set GOOGLE_APPLICATION_CREDENTIALS manually\n"
    )