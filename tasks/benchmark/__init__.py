from core.py.log_module import setup_logger
logger = setup_logger(__name__)


def collect(scan):
    import subprocess
    logger.info("Assembling benchmark city tables...")
    subprocess.run(
        ["Rscript", "-e", f"source(here::here('tasks/benchmark/collection.R'))"],
        check=True
    )


def run(scan):
    collect(scan)
    logger.info("Done with benchmark")
