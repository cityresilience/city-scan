from core.py.log_module import setup_logger
logger = setup_logger(__name__)


def collect(scan):
    from .collection import datacollection

    logger.info("Collecting fathom data...")
    datacollection(
        aoi=scan.aoi, 
        city_name=scan.city_name,
        city_inputs=scan.city_inputs,
        menu=scan.menu,
        output_dir=scan.output_dir
    )


def analyze(scan):
    from .analysis import (
        exposure_flood_wsf,
        exposure_flood_pop,
        exposure_flood_osm,
        exposure_flood_road,
    )
    logger.info("Analyzing fathom data...")
    
    exposure_flood_wsf(
        aoi=scan.aoi,
        menu=scan.menu,
        flood_years=scan.flood_year,
        flood_ssps=scan.flood_ssp,
        output_dir=scan.output_dir,
        city_name=scan.city_name, 
    )
    
    exposure_flood_pop(
        aoi=scan.aoi,
        menu=scan.menu,
        flood_years=scan.flood_year,
        flood_ssps=scan.flood_ssp,
        output_dir=scan.output_dir,
        city_name=scan.city_name,
    )
    
    exposure_flood_osm(
        aoi=scan.aoi,
        menu=scan.menu,
        flood_years=scan.flood_year,
        flood_ssps=scan.flood_ssp,
        output_dir=scan.output_dir,
        city_name=scan.city_name,
        city_inputs=scan.city_inputs,
    )
    
    exposure_flood_road(
        aoi=scan.aoi,
        menu=scan.menu,
        flood_years=scan.flood_year,
        flood_ssps=scan.flood_ssp,
        output_dir=scan.output_dir,
        city_name=scan.city_name,
    )
    
    logger.info("Completed all fathom exposure analysis")
    


def run(scan):
    collect(scan)
    analyze(scan)
    logger.info("Done with fathom analysis")
