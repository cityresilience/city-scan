from core.py.log_module import setup_logger
logger = setup_logger(__name__)


def collect(scan):
    from .collection import datacollection

    composite = []
    if scan.menu.get("lst_summer"):
        composite.append('summer')
    if scan.menu.get("lst_winter"):
        composite.append('winter')
    if not composite:
        composite = ['summer', 'winter']

    logger.info(f"Collecting LST data ({composite})...")
    datacollection(
        aoi=scan.aoi, city_name=scan.city_name,
        output_dir=scan.output_dir, composite=composite,
        first_year=scan.first_year, last_year=scan.last_year
    )


def analyze(scan):
    from .analysis import compute_histogram

    logger.info("Analyzing LST data...")
    compute_histogram(
        city_name=scan.city_name, output_dir=scan.output_dir
    )


def run(scan):
    collect(scan)
    analyze(scan)
    logger.info("Done with LST data collection")
