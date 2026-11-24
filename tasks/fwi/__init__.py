from core.py.log_module import setup_logger
logger = setup_logger(__name__)


def collect(scan):
    from .collection import datacollection

    logger.info("Collecting FWI data...")
    datacollection(
        aoi=scan.aoi, city_name=scan.city_name,
        output_dir=scan.output_dir,
        fwi_first_year=scan.fwi_first_year,
        fwi_last_year=scan.fwi_last_year,
        return_raster=True
    )


def analyze(scan):
    from .collection import datacollection
    from .analysis import generate_nth_raster, calculate_weekly_nth

    logger.info("Analyzing FWI data...")
    fwi_raster_dict, fwi_meta = datacollection(
        aoi=scan.aoi, city_name=scan.city_name,
        output_dir=scan.output_dir,
        fwi_first_year=scan.fwi_first_year,
        fwi_last_year=scan.fwi_last_year,
        return_raster=True
    )
    generate_nth_raster(
        fwi_raster_dict=fwi_raster_dict, nth_percentile=98.6,
        output_dir=scan.output_dir, city_name=scan.city_name,
        out_meta=fwi_meta
    )
    calculate_weekly_nth(
        fwi_raster_dict=fwi_raster_dict, nth_percentile=95,
        output_dir=scan.output_dir, city_name=scan.city_name
    )


def run(scan):
    collect(scan)
    analyze(scan)
    logger.info("Done with FWI analysis")
