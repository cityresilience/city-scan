from core.py.log_module import setup_logger
logger = setup_logger(__name__)


def collect(scan):
    from .collection import datacollection

    logger.info("Collecting land cover data...")
    datacollection(
        aoi=scan.aoi, city_name=scan.city_name,
        output_dir=scan.output_dir
    )


def analyze(scan):
    from .analysis import dataanalysis

    logger.info("Analyzing land cover data...")
    dataanalysis(
        city_name=scan.city_name, output_dir=scan.output_dir
    )


def run(scan):
    collect(scan)
    analyze(scan)
    logger.info("Done with land cover analysis")
