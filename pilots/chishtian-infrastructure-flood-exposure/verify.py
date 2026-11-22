"""Independently check saved exposure results against the source raster cells.

Run after run.py. Creates no files and makes no changes to inputs or outputs.
"""
import sqlite3

import geopandas as gpd
import numpy as np
import pandas as pd
import pymupdf
import rasterio
from pyproj import Transformer
from shapely import line_interpolate_point

from flood_exposure import FLOOD, OUT


def check(condition, message):
    if not condition:
        raise ValueError(message)


def main():
    gpkg = OUT / 'exposure.gpkg'
    with sqlite3.connect(f'{gpkg.as_uri()}?mode=ro', uri=True) as db:
        check(db.execute('PRAGMA integrity_check').fetchone()[0] == 'ok',
              'GeoPackage integrity check failed')
    summary = pd.read_csv(OUT / 'exposure.csv')
    check(len(summary) == 36, 'Expected 36 summary rows')
    check(np.allclose(summary.supplied_total,
                      summary.mapped_exposed + summary.zero_unresolved + summary.outside_cached_extent),
          'Exposure totals do not balance')
    for _, group in summary.groupby(['layer', 'hazard']):
        check((np.diff(group.sort_values('return_period_years').mapped_exposed) >= -1e-7).all(),
              'Exposure decreases with return period')
    tx = Transformer.from_crs(32643, 4326, always_xy=True)
    max_error = 0.
    for layer in ['water_lines', 'sewer_lines', 'water_points', 'sewer_points']:
        g = gpd.read_file(gpkg, layer=layer)
        lines = layer.endswith('lines')
        if lines:
            check(abs(g.length.sum() - g.geometry.union_all().length) < .001,
                  f'Overlapping or duplicated network length in {layer}')
            coords, weights = [], []
            for line in g.explode(index_parts=False).geometry:
                count = max(1, int(np.ceil(line.length / .5)))
                step = line.length / count
                points = line_interpolate_point(line, (np.arange(count) + .5) * step)
                coords.extend((p.x, p.y) for p in points)
                weights.extend([step / 1000] * count)
            xy = np.asarray(coords)
            lon, lat = tx.transform(xy[:, 0], xy[:, 1])
            weights = np.asarray(weights)
        else:
            ll = g.to_crs(4326)
            lon, lat = ll.geometry.x.to_numpy(), ll.geometry.y.to_numpy()
        states = {}
        for hazard in ['fluvial', 'pluvial']:
            with rasterio.open(FLOOD / f'chishtian_{hazard}_2020.tif') as src:
                cc, rr = (~src.transform) * (lon, lat)
                cc, rr = np.floor(cc).astype(int), np.floor(rr).astype(int)
                inside = (cc >= 0) & (cc < src.width) & (rr >= 0) & (rr < src.height)
                if lines:
                    check(inside.all(), f'Line sample outside cached extent: {layer}')
                for rp in [10, 100, 1000]:
                    raster = src.read(src.descriptions.index(f'r{rp}') + 1)
                    positive = np.zeros(len(cc), dtype=bool)
                    positive[inside] = raster[rr[inside], cc[inside]] > 0
                    states[hazard, rp] = positive
                    field = f'{hazard}_{rp}_' + ('km' if lines else 'exposed')
                    if lines:
                        error = abs(float(weights[positive].sum()) - float(g[field].sum()))
                        max_error = max(max_error, error)
                        check(error < .020, f'Independent line sample differs by over 20 m: {field}')
                    else:
                        check(np.array_equal(positive, g[field].to_numpy() > 0),
                              f'Independent point sample differs: {field}')
                    row = summary[(summary.layer == layer) & (summary.hazard == hazard) &
                                  (summary.return_period_years == rp)].iloc[0]
                    check(np.isclose(row.mapped_exposed, g[field].sum()),
                          f'Asset attributes and summary disagree: {field}')
        for rp in [10, 100, 1000]:
            union = states['fluvial', rp] | states['pluvial', rp]
            field = f'combined_{rp}_' + ('km' if lines else 'exposed')
            if lines:
                check(abs(weights[union].sum() - g[field].sum()) < .020,
                      f'Combined independent line sample differs: {field}')
            else:
                check(np.array_equal(union, g[field].to_numpy() > 0),
                      f'Combined independent point sample differs: {field}')
            row = summary[(summary.layer == layer) & (summary.hazard == 'combined') &
                          (summary.return_period_years == rp)].iloc[0]
            check(np.isclose(row.mapped_exposed, g[field].sum()),
                  f'Combined attributes and summary disagree: {field}')
    for name, pages in [('maps.pdf', 2), ('maps_enlarged.pdf', 12)]:
        with pymupdf.open(OUT / name) as doc:
            check(len(doc) == pages, f'Wrong page count: {name}')
            for page in doc:
                check(page.rect.width == 612 and page.rect.height == 792,
                      f'Wrong page size: {name}')
                check('Chishtian:' in page.get_text(), f'Missing map heading: {name}')
                page.get_pixmap(matrix=pymupdf.Matrix(.5, .5))
    print(f'Passed: GIS integrity, totals, point samples, network samples and PDFs. '
          f'Maximum river/rainwater length difference: {max_error * 1000:.2f} m.')


if __name__ == '__main__':
    main()
