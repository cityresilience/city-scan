from core.py.log_module import setup_logger
logger = setup_logger(__name__)


def collect(scan):
    import subprocess
    logger.info("Collecting sea level rise data...")
    subprocess.run(
        ["Rscript", "-e", f"source(here::here('tasks/sea_level_rise/collection.R'))"],
        check=True
    )


def run(scan):
    collect(scan)
    logger.info("Done with sea_level_rise")
