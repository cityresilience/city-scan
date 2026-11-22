"""Intersect supplied infrastructure with existing City Scan flood footprints."""
from pathlib import Path
import hashlib
import geopandas as gpd
import numpy as np
import pandas as pd
import rasterio
from rasterio.features import shapes
from shapely.geometry import shape, box
from shapely.ops import unary_union

ROOT = Path(__file__).resolve().parent
RAW = ROOT / 'inputs/infrastructure'
FLOOD = ROOT / 'inputs/flood'
OUT = ROOT / 'outputs'
CRS = 'EPSG:32643'
RPS = [10, 100, 1000]

def projected(geom, crs):
    return gpd.GeoSeries([geom], crs=crs).to_crs(CRS).iloc[0]


def polygons(array, transform):
    return unary_union([shape(s) for s, v in shapes(array.astype('uint8'),
                        mask=array.astype(bool), transform=transform) if v == 1])


def save_layer(g, name):
    if len(g):
        g.to_file(OUT / 'exposure.gpkg', layer=name, driver='GPKG')


def load_inputs():
    boundary_all = gpd.read_file(RAW / 'MC Boundary/Proposed_MC_Boundaries_PICP_Cities.shp').to_crs(CRS)
    boundary = boundary_all[boundary_all.LG_Name == 'Chistian'].copy()
    scan = gpd.read_file(FLOOD / 'study_area.fgb').to_crs(CRS)
    if len(boundary) != 1 or scan.empty:
        raise ValueError('Expected one Chishtian municipal boundary and a nonempty study area')
    specs = {
        'water_lines': ('Water Supply/Chishtian/Water_Supply_Lines.shp', 'WL'),
        'water_points': ('Water Supply/Chishtian/Water_Resources.shp', 'WP'),
        'sewer_lines': ('Sewerage/Chishtian/Existing_Sewer_Lines.shp', 'SL'),
        'sewer_points': ('Sewerage/Chishtian/Disposal_Station.shp', 'SP'),
    }
    layers = {}
    for key, (rel, prefix) in specs.items():
        g = gpd.read_file(RAW / rel).to_crs(CRS)
        if g.empty or g.crs is None or g.geometry.isna().any() or g.geometry.is_empty.any() or not g.geometry.is_valid.all():
            raise ValueError(f'Empty, missing or invalid geometry in {rel}')
        expected = {'LineString', 'MultiLineString'} if key.endswith('lines') else {'Point'}
        if not set(g.geom_type).issubset(expected):
            raise ValueError(f'Unexpected geometry type in {rel}')
        g['asset_id'] = [f'{prefix}{i+1:03}' for i in range(len(g))]
        g['source_row'] = np.arange(len(g))
        g['source_layer'] = rel
        g['intersects_mc'] = g.intersects(boundary.geometry.union_all())
        g['within_mc'] = g.within(boundary.geometry.union_all())
        g['intersects_scan_aoi'] = g.intersects(scan.geometry.union_all())
        g['status_group'] = np.where(g.Type.str.lower().str.contains('non'),
                                     'source-labelled non-functional', 'not labelled non-functional')
        layers[key] = g
    return boundary_all, boundary, scan, layers


def load_hazards():
    hazards, footprints, metadata = {}, {}, []
    for ft in ['fluvial', 'pluvial']:
        path = FLOOD / f'chishtian_{ft}_2020.tif'
        with rasterio.open(path) as s:
            footprints[ft] = projected(box(*s.bounds), s.crs)
            metadata.append(dict(path=str(path), sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
                                 bands=s.descriptions, crs=str(s.crs), transform=list(s.transform),
                                 nodata=s.nodata, shape=s.shape, resolution=s.res,
                                 caveat='Zero conflates source missing and subthreshold values.'))
            for rp in RPS:
                a = s.read(s.descriptions.index(f'r{rp}')+1)
                if not (set(np.unique(a)).issubset({0., 1.})):
                    raise ValueError('Validation failed: set(np.unique(a)).issubset({0., 1.})')
                hazards[ft, rp] = projected(polygons(a > 0, s.transform), s.crs)
    if not (footprints['fluvial'].equals(footprints['pluvial'])):
        raise ValueError("Validation failed: footprints['fluvial'].equals(footprints['pluvial'])")
    footprints['combined'] = footprints['fluvial'].intersection(footprints['pluvial'])
    for rp in RPS:
        hazards['combined', rp] = hazards['fluvial', rp].union(hazards['pluvial', rp])
    return hazards, footprints, metadata


def analyse(layers, hazards, footprints):
    summary = []
    # Export all RP positive zones, using native pixel edges transformed to UTM.
    zones = [dict(hazard=ft, return_period=rp, baseline=2020, threshold_cm=15,
                  geometry=geom) for (ft, rp), geom in hazards.items() if not geom.is_empty]
    save_layer(gpd.GeoDataFrame(zones, crs=CRS), 'mapped_flood_zones')
    save_layer(gpd.GeoDataFrame({'name': list(footprints), 'geometry': list(footprints.values())}, crs=CRS),
               'cached_raster_footprints')
    for key, g in layers.items():
        is_line = key.endswith('lines')
        sector = 'water' if key.startswith('water') else 'sewerage'
        total = g.length / 1000 if is_line else pd.Series(1., index=g.index)
        g['total_km' if is_line else 'inventory_count'] = total
        for ft in ['fluvial', 'pluvial', 'combined']:
            cover = g.geometry.intersection(footprints[ft])
            covered = cover.length / 1000 if is_line else g.geometry.intersects(footprints[ft]).astype(float)
            for rp in RPS:
                inter = g.geometry.intersection(hazards[ft, rp])
                exposed = inter.length / 1000 if is_line else g.geometry.intersects(hazards[ft, rp]).astype(float)
                outside = total - covered
                unresolved = covered - exposed
                if not (float(unresolved.min()) >= -1e-7):
                    raise ValueError('Validation failed: float(unresolved.min()) >= -1e-7')
                if not (np.allclose(total, exposed + unresolved + outside, atol=1e-7)):
                    raise ValueError('Validation failed: np.allclose(total, exposed + unresolved + outside, atol=1e-7)')
                g[f'{ft}_{rp}_' + ('km' if is_line else 'exposed')] = exposed
                unit = 'km' if is_line else 'facilities'
                def record(idx, category):
                    t, e, u, o = (float(s.loc[idx].sum()) for s in [total, exposed, unresolved, outside])
                    return dict(sector=sector, layer=key, asset_type=category, hazard=ft,
                                return_period_years=rp, baseline=2020, threshold_cm=15, unit=unit,
                                supplied_total=t, mapped_exposed=e, zero_unresolved=u,
                                outside_cached_extent=o, mapped_exposed_pct=100*e/t if t else None,
                                note='Remainder unresolved; all supplied assets included. Combined is spatial OR of separate same-RP events, not a joint event probability.')
                summary.append(record(g.index, 'ALL'))
                g[f'{ft}_r{rp}_zero_unresolved'] = unresolved
                g[f'{ft}_r{rp}_outside_extent'] = outside
                if is_line:
                    seg = g[['asset_id', 'Type', 'source_row', 'geometry']].copy()
                    seg.geometry = inter
                    seg = seg[seg.length > 1e-7].copy()
                    seg['length_km'] = seg.length / 1000
                    save_layer(seg, f'{key}_{ft}_r{rp}_segments')
                else:
                    g[f'{ft}_r{rp}_state'] = np.select([exposed > 0, outside > 0],
                        ['mapped exposure', 'outside cached extent'], default='zero unresolved')
        if not ((g.combined_100_km >= g.fluvial_100_km-1e-7).all() if is_line else (g.combined_100_exposed >= g.fluvial_100_exposed).all()):
            raise ValueError('Validation failed: (g.combined_100_km >= g.fluvial_100_km-1e-7).all() if is_line else (g.combined_100_exposed >= g.fluvial_100_exposed).all()')
        save_layer(g, key)
    pd.DataFrame(summary).to_csv(OUT / 'exposure.csv', index=False)
    return pd.DataFrame(summary)

