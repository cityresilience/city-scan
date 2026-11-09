from core.py.log_module import setup_logger
logger = setup_logger(__name__)


def collect(scan):
    from . import collection

    logger.info("Collecting elevation data...")
    # Use FABDEM from GEE (full global coverage) rather than the GCS zip tiles,
    # whose archives are incomplete for some AOIs (e.g. Uzbekistan's 56-60/70-73E
    # edges) — the zip path silently drops missing tiles. gee_fabdem falls back to
    # SRTM if GEE is unavailable. Same signature as datacollection().
    collection.gee_fabdem(
        aoi=scan.aoi, city_name=scan.city_name,
        output_dir=scan.output_dir, return_raster=True,
        create_raster_buffer=True
    )
    if collection.data_source:
        scan.sources["elevation"] = collection.data_source


def analyze(scan):
    from .analysis import generate_contours, elevation_stats, elevation_interpretation

    logger.info("Analyzing elevation data...")
    generate_contours(
        city_name=scan.city_name, output_dir=scan.output_dir,
        return_gdf=False
    )
    elevation_stats(
        city_name=scan.city_name, output_dir=scan.output_dir
    )
    elevation_interpretation(
        city_name=scan.city_name, output_dir=scan.output_dir
    )


def visualize(scan):
    from .visualization import plot_elevation_rastermap, plot_elevation_stats

    logger.info("Visualizing elevation data...")
    plot_elevation_rastermap(
        city_name=scan.city_name, output_dir=scan.output_dir
    )
    plot_elevation_stats(
        city_name=scan.city_name, output_dir=scan.output_dir,
        render_dir=scan.render_dir
    )


def run(scan):
    collect(scan)
    analyze(scan)
    logger.info("Done with elevation analysis")
