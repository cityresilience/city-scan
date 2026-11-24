from core.py.log_module import setup_logger
logger = setup_logger(__name__)


def collect(scan):
    from . import collection

    logger.info("Collecting groundwater storage data...")
    collection.datacollection(
        aoi=scan.aoi,
        city_name=scan.city_name,
        output_dir=scan.output_dir
    )
    if collection.data_source:
        scan.sources["groundwater"] = collection.data_source


def run(scan):
    collect(scan)
    logger.info("Done with groundwater collection")
