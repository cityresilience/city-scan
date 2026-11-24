from core.py.log_module import setup_logger
logger = setup_logger(__name__)


def collect(scan):
    import subprocess
    logger.info("Collecting cyclone data...")
    subprocess.run(
        ["Rscript", "-e", f"source(here::here('tasks/cyclones/collection.R'))"],
        check=True
    )


def run(scan):
    collect(scan)
    logger.info("Done with cyclones")
