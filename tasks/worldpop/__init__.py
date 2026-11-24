from core.py.log_module import setup_logger
logger = setup_logger(__name__)


def collect(scan):
    from .collection import datacollection

    logger.info("Collecting WorldPop population data...")
    datacollection(
        aoi=scan.aoi, city_name=scan.city_name,
        country_iso3=scan.country_iso3, output_dir=scan.output_dir,
        return_raster=True,
        country_iso3_list=scan.country_iso3_list
    )


def analyze(scan):
    import subprocess
    from .analysis import compute_stats, stats_worldpop, clean_pg, clean_pug

    logger.info("Analyzing WorldPop population data...")
    compute_stats(
        city_name=scan.city_name, output_dir=scan.output_dir,
        return_df=False
    )
    stats_worldpop(city_name=scan.city_name, output_dir=scan.output_dir, dataset="worldpop_2000_2020")
    stats_worldpop(city_name=scan.city_name, output_dir=scan.output_dir, dataset="worldpop_2015_2030")
    clean_pg(city_name=scan.city_name, output_dir=scan.output_dir)
    clean_pug(city_name=scan.city_name, output_dir=scan.output_dir)

    # R-based population assembly (benchmarks, ridge plot data)
    logger.info("Running R population assembly (analysis.R)...")
    subprocess.run(
        ["Rscript", "-e", "source(here::here('tasks/worldpop/analysis.R'))"],
        check=True
    )


def visualize(scan):
    from .visualization import plot_rastermap, plot_histogram

    logger.info("Visualizing WorldPop population data...")
    plot_rastermap(city_name=scan.city_name, output_dir=scan.output_dir)
    plot_histogram(city_name=scan.city_name, output_dir=scan.output_dir)


def run(scan):
    collect(scan)
    analyze(scan)
    logger.info("Done with population WorldPop analysis")
