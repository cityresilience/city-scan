from core.py.log_module import setup_logger
logger = setup_logger(__name__)


def collect_ndvi(scan):
    from .collection import datacollection

    logger.info("Collecting NDVI data...")
    datacollection(
        aoi=scan.aoi, city_name=scan.city_name,
        output_dir=scan.output_dir, index_type='ndvi',
        first_year=scan.first_year, last_year=scan.last_year
    )


def collect_ndmi(scan):
    from .collection import datacollection

    logger.info("Collecting NDMI data...")
    datacollection(
        aoi=scan.aoi, city_name=scan.city_name,
        output_dir=scan.output_dir, index_type='ndmi',
        first_year=scan.first_year, last_year=scan.last_year
    )


def analyze_ndvi(scan):
    from .analysis import compute_histogram

    logger.info("Analyzing NDVI data...")
    compute_histogram(
        city_name=scan.city_name, output_dir=scan.output_dir
    )


def run_ndvi(scan):
    collect_ndvi(scan)
    analyze_ndvi(scan)
    logger.info("Done with NDVI data collection")


def run_ndmi(scan):
    collect_ndmi(scan)
    logger.info("Done with NDMI data collection")
