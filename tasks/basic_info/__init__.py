from core.py.log_module import setup_logger
logger = setup_logger(__name__)


def collect(scan):
    from .collection import datacollection

    logger.info("Collecting basic info...")
    datacollection(
        aoi=scan.aoi, city_name=scan.city_name,
        country_name=scan.country_name, output_dir=scan.output_dir
    )


def visualize(scan):
    import subprocess
    logger.info("Rendering basic_info charts...")
    subprocess.run(
        ["quarto", "render", "tasks/basic_info/charts/index.qmd"],
        check=True
    )


def run(scan):
    collect(scan)
