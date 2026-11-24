from core.py.log_module import setup_logger
logger = setup_logger(__name__)


def collect(scan):
    from .collection import datacollection

    logger.info("Collecting relative wealth index data...")
    datacollection(
        aoi=scan.aoi, city_name=scan.city_name,
        country_iso3=scan.country_iso3, output_dir=scan.output_dir,
        return_gdf=True,
        country_iso3_list=scan.country_iso3_list
    )


def analyze(scan):
    import geopandas as gpd
    import os
    from .analysis import compute_stats_gdf, compute_histogram

    logger.info("Analyzing relative wealth index data...")
    rwi_path = os.path.join(scan.output_dir, "spatial", f"{scan.city_name}_rwi.gpkg")
    gdf = gpd.read_file(rwi_path)
    compute_stats_gdf(
        city_name=scan.city_name, output_dir=scan.output_dir,
        gdf=gdf, value_col='rwi'
    )
    compute_histogram(
        city_name=scan.city_name, output_dir=scan.output_dir
    )


def visualize(scan):
    from .visualization import run_viz_gdf

    logger.info("Visualizing relative wealth index data...")
    run_viz_gdf(
        city_name=scan.city_name, output_dir=scan.output_dir,
        value_col='rwi'
    )


def run(scan):
    collect(scan)
    analyze(scan)
    logger.info("Done with relative wealth index analysis")
