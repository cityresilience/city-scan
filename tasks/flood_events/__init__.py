from core.py.log_module import setup_logger
logger = setup_logger(__name__)


def collect(scan):
    import subprocess
    logger.info("Collecting flood events data...")
    subprocess.run(
        ["Rscript", "-e", f"source(here::here('tasks/flood_events/collection.R'))"],
        check=True
    )


def run(scan):
    collect(scan)
    logger.info("Done with flood_events")
