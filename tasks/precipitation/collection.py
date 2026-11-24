from core.py.log_module import setup_logger
logger = setup_logger(__name__)

import os

import ee

from core.py import gee_fns as fns


def datacollection(
    aoi,
    city_name,
    output_dir,
    return_raster=False
):
    """Precipitation trend + anomaly + dryness from TerraClimate.

    Source: IDAHO_EPSCOR/TERRACLIMATE (monthly, ~4 km, global).
      - precip_trend      : linear-fit slope of annual precip total, 2000 -> latest (mm/yr)
      - precip_anomaly    : recent 5-yr mean annual precip minus 2000->latest mean (mm)
      - rainfall_deficit  : recent 5-yr mean PDSI (negative = drought), ready-made index
    """

    logger.info("Starting precipitation data collection...")

    tc = ee.ImageCollection('IDAHO_EPSCOR/TERRACLIMATE')
    max_date = ee.Date(tc.reduceColumns(ee.Reducer.max(), ['system:time_start']).get('max'))
    end_year = ee.Number(max_date.get('year'))
    years = ee.List.sequence(2000, end_year)

    def annual_precip(y):
        y = ee.Number(y)
        pr = tc.select('pr').filter(ee.Filter.calendarRange(y, y, 'year')).sum()
        return pr.addBands(ee.Image.constant(y).float().rename('year')).set('year', y)

    annual = ee.ImageCollection(years.map(annual_precip))

    # 25 trend: linear fit of annual precip vs year -> 'scale' band = slope (mm/yr)
    trend = annual.select(['year', 'pr']).reduce(ee.Reducer.linearFit()).select('scale')

    # 25 anomaly: recent 5-yr mean annual precip minus full-period mean
    period_mean = annual.select('pr').mean()
    recent_mean = (annual.filter(ee.Filter.gte('year', end_year.subtract(5)))
                   .select('pr').mean())
    anomaly = recent_mean.subtract(period_mean)

    # 26 deficit: recent 5-yr mean PDSI (ready-made drought index)
    pdsi_recent = (tc.select('pdsi')
                   .filterDate(max_date.advance(-5, 'year'), max_date).mean())

    spatial_dir = os.path.join(output_dir, "spatial")
    os.makedirs(spatial_dir, exist_ok=True)

    results = {}
    SCALE = 4638.3  # TerraClimate native

    for name, img in [("precip_trend", trend),
                      ("precip_anomaly", anomaly),
                      ("rainfall_deficit", pdsi_recent)]:
        out_path = os.path.join(spatial_dir, f"{city_name}_{name}.tif")
        fns.tiled_collection(img, aoi, out_path, scale=SCALE,
                             dtype='float32', nodata=float('nan'), output_dir=output_dir)
        logger.info(f"Saved {name}: {out_path}")
        results[name] = out_path

    return results
