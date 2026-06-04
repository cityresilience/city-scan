from core.py.log_module import setup_logger
logger = setup_logger(__name__)


def collect(scan):
    from .collection import datacollection

    logger.info("Collecting WSF data...")
    datacollection(
        aoi=scan.aoi, city_name=scan.city_name,
        output_dir=scan.output_dir, return_raster=True
    )


def analyze(scan):
    from .analysis import stats_wsf, harmonize_wsf, compute_histogram

    logger.info("Analyzing WSF data...")
    stats_wsf(city_name=scan.city_name, output_dir=scan.output_dir, dataset="tracker")
    stats_wsf(city_name=scan.city_name, output_dir=scan.output_dir, dataset="evolution")
    harmonize_wsf(aoi=scan.aoi, city_name=scan.city_name, output_dir=scan.output_dir)
    compute_histogram(city_name=scan.city_name, output_dir=scan.output_dir)


def run(scan):
    collect(scan)
    analyze(scan)
    logger.info("Done with WSF analysis")
