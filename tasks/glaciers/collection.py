# DRAFT for review — glacier extent (23) + glacier change (24), fully GEE.
#
# RGI comes from the GEE community asset (NSIDC needs Earthdata login, so we use GEE).
#   projects/sat-io/open-datasets/RGI/RGI_VECTOR_MERGED_V7  (~2000 baseline outlines)
#
# 23 extent : rasterized RGI glacier mask.  NOTE: request asked for VECTOR outlines, but
#             RGI is now pulled from GEE, so this outputs a RASTER mask. A true vector would
#             need ee.batch.Export.table.toCloudStorage — flag for review.
# 24 change : per-epoch NDSI + band-ratio (Red/SWIR1) from Landsat, NO threshold — two 6-band
#             stacks (one band per epoch: 2000/2005/…/2025). Each epoch = median of ablation-
#             season Landsat over a +/-2yr window (denoise). Masked to a BUFFERED RGI-2000 outline
#             (buffer catches Pamir surges), clipped to the glacier bbox -> EECU bounded.
#
# Tunables to review: BUFFER_M, EPOCHS, EPOCH_WINDOW.
from core.py.log_module import setup_logger
logger = setup_logger(__name__)

import os

import ee

from core.py import gee_fns as fns

RGI_ASSET = 'projects/sat-io/open-datasets/RGI/RGI_VECTOR_MERGED_V7'
BUFFER_M = 1500            # buffer around RGI-2000 outlines (m) — catch advances/surges
EPOCHS = [2000, 2005, 2010, 2015, 2020, 2025]   # 5-yr epochs -> one band each
EPOCH_WINDOW = 2           # +/- years around each epoch (5-yr median -> denoise, fill L7 gaps)
ABLATION = (7, 9)          # ablation-season months (Jul-Sep) for snow-free ice


def _region_gdf(rgi_aoi):
    """GeoDataFrame of the glacier-region bbox, aggregated from per-feature bounds.
    Never unions the ~15k outlines (that's what blows the 2M-edge limit) — each glacier's
    own bounding box is 4 corners, and we take the min/max across the collection."""
    import geopandas as gpd
    from shapely.geometry import box

    def _fb(f):
        ring = ee.List(f.geometry().bounds().coordinates().get(0))
        ll = ee.List(ring.get(0))   # [minx, miny]
        ur = ee.List(ring.get(2))   # [maxx, maxy]
        return f.set({'minx': ll.get(0), 'miny': ll.get(1),
                      'maxx': ur.get(0), 'maxy': ur.get(1)})

    fc = rgi_aoi.map(_fb)
    minx, miny, maxx, maxy = ee.List([
        fc.aggregate_min('minx'), fc.aggregate_min('miny'),
        fc.aggregate_max('maxx'), fc.aggregate_max('maxy'),
    ]).getInfo()
    return gpd.GeoDataFrame(geometry=[box(minx, miny, maxx, maxy)], crs=4326)


def _epoch_metrics(year, region):
    """Median ablation-season Landsat over [year-W, year+W] -> (NDSI, Red/SWIR1 ratio), no threshold.
    Green/Red/SWIR1 from C2 L2 SR (L5/7: B2/B3/B5; L8/9: B3/B4/B6)."""
    def prep(col, green, red, swir1):
        def _f(img):
            qa = img.select('QA_PIXEL')
            cloud = qa.bitwiseAnd(1 << 3).eq(0).And(qa.bitwiseAnd(1 << 4).eq(0))
            sr = img.select([green, red, swir1], ['green', 'red', 'swir1']).multiply(0.0000275).add(-0.2)
            return sr.updateMask(cloud)
        return (col.filter(ee.Filter.calendarRange(year - EPOCH_WINDOW, year + EPOCH_WINDOW, 'year'))
                   .filter(ee.Filter.calendarRange(ABLATION[0], ABLATION[1], 'month'))
                   .filterBounds(region).map(_f))

    l5 = prep(ee.ImageCollection('LANDSAT/LT05/C02/T1_L2'), 'SR_B2', 'SR_B3', 'SR_B5')
    l7 = prep(ee.ImageCollection('LANDSAT/LE07/C02/T1_L2'), 'SR_B2', 'SR_B3', 'SR_B5')
    l8 = prep(ee.ImageCollection('LANDSAT/LC08/C02/T1_L2'), 'SR_B3', 'SR_B4', 'SR_B6')
    l9 = prep(ee.ImageCollection('LANDSAT/LC09/C02/T1_L2'), 'SR_B3', 'SR_B4', 'SR_B6')
    comp = l5.merge(l7).merge(l8).merge(l9).median()

    ndsi = comp.normalizedDifference(['green', 'swir1']).rename(f'ndsi_{year}')
    ratio = comp.select('red').divide(comp.select('swir1')).rename(f'ratio_{year}')
    return ndsi, ratio


def datacollection_extent(aoi, city_name, output_dir):
    """23 — rasterized RGI glacier mask over the glacier-region bbox."""
    logger.info("Starting glacier extent (RGI) collection...")
    AOI, _ = fns.aoi_to_ee_geometry(aoi)
    rgi = ee.FeatureCollection(RGI_ASSET).filterBounds(AOI)
    if rgi.size().getInfo() == 0:
        logger.warning("No RGI glaciers intersect the AOI — skipping glacier extent.")
        return None

    spatial_dir = os.path.join(output_dir, "spatial")
    os.makedirs(spatial_dir, exist_ok=True)
    out_path = os.path.join(spatial_dir, f"{city_name}_glacier_extent.tif")
    if os.path.exists(out_path):   # already collected — don't redo (24h Cloud Run timeout is tight)
        logger.info(f"glacier_extent already exists — skipping: {out_path}")
        return None

    region_gdf = _region_gdf(rgi)
    glacier_mask = ee.Image(1).clipToCollection(rgi).rename('glacier')   # 1 over glaciers, masked elsewhere
    fns.tiled_collection(glacier_mask, region_gdf, out_path, scale=30,
                         dtype='int8', nodata=0, fillna=0, output_dir=output_dir)
    logger.info(f"Saved glacier extent (mask): {out_path}")
    return None


def datacollection_change(aoi, city_name, output_dir):
    """24 — per-epoch NDSI + Red/SWIR1 ratio (6-band each). Checks existence FIRST and only
    builds/exports what's MISSING — a re-run NEVER redoes the huge, slow ndsi export."""
    logger.info("Starting glacier change collection...")
    spatial_dir = os.path.join(output_dir, "spatial")
    os.makedirs(spatial_dir, exist_ok=True)

    ndsi_path = os.path.join(spatial_dir, f"{city_name}_glacier_ndsi.tif")
    if os.path.exists(ndsi_path):
        logger.info(f"  glacier_ndsi EXISTS -> SKIP (never re-run): {ndsi_path}")
        return None

    AOI, _ = fns.aoi_to_ee_geometry(aoi)
    rgi = ee.FeatureCollection(RGI_ASSET).filterBounds(AOI)
    if rgi.size().getInfo() == 0:
        logger.warning("No RGI glaciers in AOI — skipping glacier change.")
        return None
    region_gdf = _region_gdf(rgi)
    buffered = rgi.map(lambda f: f.buffer(BUFFER_M))   # buffer catches Pamir surges past the 2000 outline

    ndsi = ee.Image.cat([_epoch_metrics(y, AOI)[0] for y in EPOCHS]).clipToCollection(buffered)
    logger.info(f"  Exporting glacier_ndsi ({len(EPOCHS)} bands)...")
    fns.tiled_collection(ndsi, region_gdf, ndsi_path, scale=30,
                         dtype='float32', nodata=float('nan'), output_dir=output_dir)
    logger.info(f"  Saved glacier_ndsi: {ndsi_path}")

    # --- RATIO DISABLED (commented out): too slow for the current delivery. Re-enable to
    #     produce glacier_ratio.
    # ratio_path = os.path.join(spatial_dir, f"{city_name}_glacier_ratio.tif")
    # if not os.path.exists(ratio_path):
    #     ratio = ee.Image.cat([_epoch_metrics(y, AOI)[1] for y in EPOCHS]).clipToCollection(buffered)
    #     fns.tiled_collection(ratio, region_gdf, ratio_path, scale=30,
    #                          dtype='float32', nodata=float('nan'), output_dir=output_dir)
    #     logger.info(f"  Saved glacier_ratio: {ratio_path}")
    return None
