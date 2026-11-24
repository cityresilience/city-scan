from core.py.log_module import setup_logger
logger = setup_logger(__name__)


def collect(scan):
    from .collection import datacollection

    logger.info("Collecting forest data...")
    datacollection(
        aoi=scan.aoi, city_name=scan.city_name,
        output_dir=scan.output_dir
    )


def analyze(scan):
    from .analysis import compute_histogram

    logger.info("Analyzing forest data...")
    compute_histogram(
        city_name=scan.city_name, output_dir=scan.output_dir
    )


def run(scan):
    collect(scan)
    analyze(scan)
    logger.info("Done with forest data collection")
