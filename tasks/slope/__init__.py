from core.py.log_module import setup_logger
logger = setup_logger(__name__)


def collect(scan):
    from .collection import datacollection

    logger.info("Collecting slope data...")
    datacollection(
        aoi=scan.aoi, city_name=scan.city_name,
        output_dir=scan.output_dir, return_raster=False
    )


def analyze(scan):
    from .analysis import compute_slope_histogram, generate_slope_yaml

    logger.info("Analyzing slope data...")
    bins = [0, 2, 5, 10, 20, 90]
    compute_slope_histogram(
        city_name=scan.city_name, bins=bins,
        output_dir=scan.output_dir, enrich=True, return_df=False
    )
    generate_slope_yaml(
        city_name=scan.city_name, output_dir=scan.output_dir
    )


def visualize(scan):
    from .visualization import plot_slope_rastermap, render_slope_treemap_png, render_slope_treemap_html

    logger.info("Visualizing slope data...")
    bins = [0, 2, 5, 10, 20, 90]
    plot_slope_rastermap(
        city_name=scan.city_name, bins=bins,
        output_dir=scan.output_dir
    )
    render_slope_treemap_png(
        city_name=scan.city_name, output_dir=scan.output_dir,
        render_dir=scan.render_dir
    )
    render_slope_treemap_html(
        city_name=scan.city_name, output_dir=scan.output_dir,
        render_dir=scan.render_dir, font_dict=scan.font_dict
    )


def run(scan):
    collect(scan)
    analyze(scan)
    logger.info("Done with slope analysis")
