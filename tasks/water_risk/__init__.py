from core.py.log_module import setup_logger
logger = setup_logger(__name__)


def collect(scan):
    from .collection import datacollection

    logger.info("Collecting WRI Aqueduct water risk data...")
    datacollection(
        aoi=scan.aoi,
        city_name=scan.city_name,
        output_dir=scan.output_dir
    )


def run(scan):
    collect(scan)
    logger.info("Done with water risk collection")
