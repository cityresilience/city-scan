from core.py.log_module import setup_logger
logger = setup_logger(__name__)


def collect(scan):
    from . import collection

    logger.info("Collecting demographic data...")
    demographics_year = scan.city_inputs.get('demographics_year')
    collection.datacollection(
        aoi=scan.aoi, city_name=scan.city_name,
        country_iso3=scan.country_iso3, output_dir=scan.output_dir,
        return_raster=False, year=demographics_year,
        country_iso3_list=scan.country_iso3_list
    )
    if collection.data_source:
        scan.sources["demographics"] = collection.data_source


def analyze(scan):
    from .analysis import demographic_aggregate, clean_pas, clean_adr

    logger.info("Analyzing demographic data...")
    demographic_aggregate(
        city_name=scan.city_name, output_dir=scan.output_dir,
        return_df=True
    )
    clean_pas(
        city_name=scan.city_name, output_dir=scan.output_dir
    )
    clean_adr(
        city_name=scan.city_name, output_dir=scan.output_dir
    )


def visualize(scan):
    from .visualization import age_distribution_plot

    logger.info("Visualizing demographic data...")
    age_distribution_plot(
        city_name=scan.city_name, output_dir=scan.output_dir,
        render_dir=scan.render_dir, font_dict=scan.font_dict
    )


def run(scan):
    collect(scan)
    analyze(scan)
    logger.info("Done with demographic analysis")
