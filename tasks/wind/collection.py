# Wind power density from the Global Wind Atlas (GWA v3, 250 m, ~2008-2017).
# No provisioning: reads the GWA per-country CDN tifs directly via /vsicurl/ and
# windows only the AOI out of each (range requests), then mosaics + clips.
# Country ISO3 list comes from the AOI (aoi_module.find_country), same as worldpop.
import os

import rasterio
from rasterio.io import MemoryFile
from rasterio.merge import merge
from rasterio.mask import mask
from core.py.log_module import setup_logger
from core.py.aoi_module import find_country

logger = setup_logger(__name__)

# GWA country GeoTIFF CDN (power density at 100 m). {ISO} = upper-case ISO3.
GWA_URL = "/vsicurl/https://gwa.cdn.nazkamapps.com/country_tifs_v4/{ISO}_power-density_100m.tif"


def datacollection(aoi, city_name, output_dir, return_raster=True):
    """Mosaic GWA power-density over the AOI's countries and clip to the AOI."""

    logger.info("Starting wind data collection…")

    if aoi is None or aoi.empty or aoi.crs is None:
        logger.error("AOI is empty or has no CRS.")
        return None

    aoi4326 = aoi.to_crs(4326)
    bounds = tuple(aoi4326.total_bounds)
    _, _, iso3_list = find_country(aoi4326)
    logger.info(f"Wind: {len(iso3_list)} countries: {', '.join(iso3_list)}")

    clips = []
    for iso3 in iso3_list:
        url = GWA_URL.format(ISO=iso3.upper())
        try:
            with rasterio.open(url) as src:
                full = rasterio.windows.Window(0, 0, src.width, src.height)
                window = rasterio.windows.from_bounds(*bounds, src.transform).intersection(full)
                if window.width < 1 or window.height < 1:
                    continue  # AOI bbox does not overlap this country's raster
                data = src.read(window=window)
                meta = src.meta.copy()
                meta.update({"height": data.shape[1], "width": data.shape[2],
                             "transform": src.window_transform(window)})
            mf = MemoryFile()
            with mf.open(**meta) as dst:
                dst.write(data)
            clips.append(mf)
            logger.info(f"  GWA {iso3.upper()}: OK")
            del data
        except Exception as e:
            logger.warning(f"  GWA {iso3.upper()}: failed ({e})")
            continue

    if not clips:
        logger.error("No GWA data for any country in the AOI.")
        return None

    datasets = [mf.open() for mf in clips]
    if len(datasets) == 1:
        mosaic, transform = datasets[0].read(), datasets[0].transform
    else:
        mosaic, transform = merge(datasets)
    meta = datasets[0].meta.copy()
    meta.update({"driver": "GTiff", "height": mosaic.shape[1], "width": mosaic.shape[2],
                 "transform": transform, "compress": "deflate", "tiled": True})
    for ds in datasets:
        ds.close()
    for mf in clips:
        mf.close()

    # Clip the mosaic to the AOI polygon.
    with MemoryFile() as tmp:
        with tmp.open(**meta) as t:
            t.write(mosaic)
        with tmp.open() as t:
            shapes = [geom.__geo_interface__ for geom in aoi4326.geometry]
            clipped, clip_transform = mask(t, shapes=shapes, crop=True, nodata=meta.get("nodata", 0))
            meta.update({"height": clipped.shape[1], "width": clipped.shape[2],
                         "transform": clip_transform})

    spatial_dir = os.path.join(output_dir, "spatial")
    os.makedirs(spatial_dir, exist_ok=True)
    out_path = os.path.join(spatial_dir, f"{city_name}_wind.tif")
    with rasterio.open(out_path, "w", **meta) as dst:
        dst.write(clipped)
    logger.info(f"Saved wind power density: {out_path}")

    if return_raster:
        return clipped, meta
    return None
