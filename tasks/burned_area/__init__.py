from core.py.log_module import setup_logger
logger = setup_logger(__name__)


def collect(scan):
    from .collection import datacollection

    logger.info("Collecting burned area data...")
    datacollection(
        aoi=scan.aoi, city_name=scan.city_name,
        output_dir=scan.output_dir, return_gdf=True
    )


def analyze(scan):
    logger.info("Burned area has no separate analysis step")


def run(scan):
    collect(scan)
    analyze(scan)
    logger.info("Done with burned area data collection")
