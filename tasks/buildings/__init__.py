from core.py.log_module import setup_logger
logger = setup_logger(__name__)


def collect(scan):
    from .collection import datacollection

    logger.info("Collecting building footprints...")
    datacollection(
        aoi=scan.aoi, city_name=scan.city_name,
        output_dir=scan.output_dir
    )


def visualize(scan):
    import subprocess
    logger.info("Plotting building footprints...")
    subprocess.run(
        ["Rscript", "-e", "source(here::here('core/R/plot-building-footprints.R'))"],
        check=True
    )


def run(scan):
    collect(scan)
    visualize(scan)
    logger.info("Done with buildings")
