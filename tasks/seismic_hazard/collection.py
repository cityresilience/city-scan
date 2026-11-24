# import
import os
import io
import requests
import zipfile
import geopandas as gpd
import rasterio
import rasterio.windows
from core.py.log_module import setup_logger

logger = setup_logger(__name__)


def datacollection(
        aoi: gpd.GeoDataFrame,
        city_name: str,
        output_dir: str,
        return_raster: bool = True
    ):
    """
    Download seismic hazard raster (PGA, 475-year return period) from OpenQuake,
    clip to AOI, and save as GeoTIFF.

    Source: Global Earthquake Model (GEM) — OpenQuake
    File: v2023_1_pga_475_rock_3min.tif (PGA on rock, 3 arc-min resolution)

    Parameters
    ----------
    aoi : GeoDataFrame
        AOI polygon(s).
    city_name : str
        City name for naming output files.
    output_dir : str
        Directory where clipped raster will be saved.
    return_raster : bool
        If True, return clipped raster array & metadata.

    Returns
    -------
    (array, metadata) or None
    """

    logger.info("Starting seismic hazard data collection…")

    # Validate AOI
    if aoi is None or aoi.empty:
        logger.error("AOI is empty. Cannot continue.")
        return None

    if aoi.crs is None:
        logger.error("AOI has no CRS defined.")
        return None

    logger.info(f"AOI CRS: {aoi.crs}")

    # Download ZIP from OpenQuake
    url = "https://cloud.openquake.org/s/6SnFk2f92JEr76H/download"
    desired_file = "v2023_1_pga_475_rock_3min.tif"

    logger.info(f"Downloading seismic hazard ZIP from OpenQuake…")

    try:
        response = requests.get(url)
        response.raise_for_status()

        with zipfile.ZipFile(io.BytesIO(response.content)) as z:
            if desired_file not in z.namelist():
                logger.error(f"{desired_file} not found in ZIP. Available: {z.namelist()}")
                return None
            geotiff_bytes = z.read(desired_file)

        logger.info("Seismic hazard raster extracted from ZIP.")

    except Exception as e:
        logger.error(f"Error downloading seismic hazard data: {e}")
        return None

    # Clip raster to AOI
    try:
        aoi_native = aoi.copy()

        with rasterio.MemoryFile(geotiff_bytes) as memfile:
            with memfile.open() as src:
                if aoi_native.crs != src.crs:
                    aoi_native = aoi_native.to_crs(src.crs)

                # Buffer AOI by 1 degree for broader context (low-res data)
                aoi_buffered = aoi_native.buffer(1.0)
                bounds = aoi_buffered.total_bounds
                window = rasterio.windows.from_bounds(
                    *bounds, transform=src.transform
                )

                clipped_image = src.read(window=window)
                clipped_transform = src.window_transform(window)

                clipped_meta = src.meta.copy()
                clipped_meta.update({
                    "driver": "GTiff",
                    "height": clipped_image.shape[1],
                    "width": clipped_image.shape[2],
                    "transform": clipped_transform,
                })

    except Exception as e:
        logger.error(f"Error clipping seismic hazard raster: {e}")
        return None

    # Save clipped raster
    spatial_dir = os.path.join(output_dir, "spatial")
    os.makedirs(spatial_dir, exist_ok=True)

    output_path = os.path.join(spatial_dir, f"{city_name}_seismic_hazard.tif")

    try:
        with rasterio.open(output_path, "w", **clipped_meta) as dst:
            dst.write(clipped_image)
        logger.info(f"Clipped seismic hazard saved to: {output_path}")
    except Exception as e:
        logger.error(f"Error saving clipped raster: {e}")
        return None

    logger.info("Seismic hazard complete.")

    if return_raster:
        return clipped_image, clipped_meta

    return None
