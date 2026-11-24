from core.py.log_module import setup_logger
logger = setup_logger(__name__)


def collect(scan):
    from .collection import datacollection

    logger.info("Collecting GHS builtup data...")
    datacollection(
        aoi=scan.aoi, city_name=scan.city_name,
        output_dir=scan.output_dir
    )


def analyze(scan):
    from .analysis import builtup_overtime, compute_stats

    logger.info("Analyzing GHS builtup data...")
    builtup_overtime(
        aoi=scan.aoi, output_dir=scan.output_dir,
        city_name=scan.city_name, threshold=1200
    )
    compute_stats(
        city_name=scan.city_name, output_dir=scan.output_dir,
        start_year=1975, end_year=2030
    )


def visualize(scan):
    from .visualization import run_viz

    logger.info("Visualizing GHS builtup data...")
    run_viz(
        city_name=scan.city_name, output_dir=scan.output_dir,
        start_year=1975, end_year=2030
    )


def run(scan):
    collect(scan)
    analyze(scan)
    logger.info("Done with GHS builtup analysis")
