from core.py.log_module import setup_logger
logger = setup_logger(__name__)


def collect(scan):
    from .collection import datacollection

    logger.info("Collecting liquefaction data...")
    datacollection(
        aoi=scan.aoi, city_name=scan.city_name,
        output_dir=scan.output_dir, return_raster=True
    )


def analyze(scan):
    from .analysis import compute_stats, compute_histogram

    logger.info("Analyzing liquefaction data...")
    compute_stats(
        city_name=scan.city_name, output_dir=scan.output_dir,
        return_df=False
    )
    compute_histogram(
        city_name=scan.city_name, output_dir=scan.output_dir
    )


def visualize(scan):
    from .visualization import plot_rastermap, plot_histogram

    logger.info("Visualizing liquefaction data...")
    plot_rastermap(city_name=scan.city_name, output_dir=scan.output_dir)
    plot_histogram(city_name=scan.city_name, output_dir=scan.output_dir)


def run(scan):
    collect(scan)
    analyze(scan)
    logger.info("Done with liquefaction analysis")
