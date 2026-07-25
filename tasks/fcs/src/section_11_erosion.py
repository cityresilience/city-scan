"""Coastal erosion processing functions for tables, shoreline points, and transect outputs."""
import os
import pandas as pd
import matplotlib.pyplot as plt
import shapefile
import geopandas as gpd
try:
    # contextily builds a Nominatim geocoder at import, which can hit a broken
    # Windows cert store (ssl.SSLError ASN1 NOT_ENOUGH_DATA). Guard it so this
    # coastal-only module never blocks pipeline import; erosion skips for inland AOIs.
    import contextily as ctx
except Exception as _ctx_exc:  # noqa
    ctx = None
from shapely.geometry import shape, Point
import glob
from shapely.geometry import Point, LineString
from scipy.spatial import distance_matrix
import math
import logging
LOGGER = logging.getLogger('city_pipeline')

def _quiet_print(*args, level: str='debug') -> None:
    """Route legacy print-style messages through the pipeline logger."""
    message = ' '.join((str(arg) for arg in args))
    getattr(LOGGER, level, LOGGER.debug)(message)

def _shapefile_safe_copy(gdf: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    """Return a copy with shapefile-safe field names (<=10 chars, unique)."""
    rename_map = {'percentile_1': 'pct_1', 'percentile_5': 'pct_5', 'percentile_17': 'pct_17', 'percentile_50': 'pct_50', 'percentile_83': 'pct_83', 'percentile_95': 'pct_95', 'percentile_99': 'pct_99', 'cumulative_percentile_50': 'cum_pct50', 'index_right': 'idx_right'}
    out = gdf.copy()
    rename_map = {k: v for k, v in rename_map.items() if k in out.columns}
    return out.rename(columns=rename_map)

def process_erosion(tables, data, section, shp, country, city):
    """Filter erosion points to the city boundary and export the resulting table."""
    polygon = get_city_poolygon(shp)
    column_names = ['Latitude', 'Longitude', 'percentile_1', 'percentile_5', 'percentile_17', 'percentile_50', 'percentile_83', 'percentile_95', 'percentile_99']
    for subdir in section:
        file_list = glob.glob(os.path.join(os.path.join(data, subdir), 'globalErosionProjections_Long_Term_Change*.csv'))
        files = []
        appended_data = []
        for file_path in file_list:
            file_name = os.path.basename(file_path)
            file_name = os.path.splitext(file_name)[0]
            year = file_name.split('_')[-1]
            rcp = file_name.split('_')[-2]
            df_points = pd.read_csv(file_path, names=column_names, header=None)
            for lat, lon in zip(df_points.Latitude, df_points.Longitude):
                if check(lon, lat, polygon):
                    files.append(file_path)
                    sub_df = df_points[(df_points['Latitude'] == lat) & (df_points['Longitude'] == lon)].copy()
                    sub_df.loc[:, 'year'] = year
                    sub_df.loc[:, 'rcp'] = rcp
                    appended_data.append(sub_df)
    appended_data = pd.concat(appended_data)
    appended_data.to_csv(f'{tables}/{country}_{city}_{subdir}_erosion.csv')
    erosion_df = appended_data
    return erosion_df

def get_city_poolygon(shp):
    """Load the first polygon geometry from the supplied shapefile."""
    r = shapefile.Reader(shp)
    shapes = r.shapes()
    polygon = shape(shapes[0])
    return polygon

def map_storms(appended_data, shp):
    """Plot erosion points over the city boundary for visual review."""
    lon = appended_data['Longitude']
    lat = appended_data['Latitude']
    geometry = [Point(xy) for xy in zip(lon, lat)]
    wardlink = shp
    ward = gpd.read_file(wardlink, bbox=None, mask=None, rows=None)
    geo_df = gpd.GeoDataFrame(geometry=geometry)
    ward = ward.set_crs(epsg=4326, allow_override=True)
    geo_df = geo_df.set_crs(epsg=4326, allow_override=True)
    ax = ward.plot(alpha=0.35, color='#d66058', zorder=1)
    ax = gpd.GeoSeries(ward['geometry'].unary_union).boundary.plot(ax=ax, alpha=0.5, color='#ed2518', zorder=2)
    ax = geo_df.plot(ax=ax, markersize=20, color='red', marker='*', zorder=3, legend=True, legend_kwds={'loc': 'upper right', 'bbox_to_anchor': (1, 1), 'markerscale': 1.01, 'title_fontsize': 'small', 'fontsize': 'x-small'})
    ctx.add_basemap(ax, crs=geo_df.crs.to_string(), source=ctx.providers.OpenStreetMap.Mapnik)
    plt.xticks([])
    plt.yticks([])
    leg1 = ax.get_legend()
    plt.close()

def check(lon, lat, polygon):
    """Return whether a point falls inside the supplied polygon."""
    point = Point(lon, lat)
    return polygon.contains(point)

def create_points(country, shapefiles, df):
    """Create and export a shoreline point GeoDataFrame from the erosion table."""
    _quiet_print(f'Total Obs: {len(df)}', level='debug')
    _quiet_print(f'Subset Obs: {len(df)}', level='debug')

    def create_point(row):
        """Create a point geometry from a row with latitude and longitude values."""
        if pd.notnull(row['Latitude']) and pd.notnull(row['Longitude']):
            return Point(row['Longitude'], row['Latitude'])
        return None
    df['geometry'] = df.apply(create_point, axis=1)
    df = df.dropna(subset=['geometry']).reset_index(drop=True)
    _quiet_print(f'After dropping Nan-->>> Obs: {len(df)}', level='debug')
    gdf = gpd.GeoDataFrame(df, geometry='geometry')
    gdf.set_crs(epsg=4326, inplace=True)
    _quiet_print(f'Last-->> Subset Obs: {len(gdf)}', level='debug')
    _shapefile_safe_copy(gdf).to_file(f'{shapefiles}/{country}_shoreline_points.shp')
    return gdf

def create_shorelines_transect(country, shapefiles, df, years_multiplier):
    """Create shoreline transects from ordered erosion points and export them as a shapefile."""
    _quiet_print(f'Total Obs: {len(df)}', level='debug')
    _quiet_print(f'Subset Obs: {len(df)}', level='debug')
    df['geometry'] = df.apply(lambda row: Point(row['Longitude'], row['Latitude']) if pd.notnull(row['Latitude']) and pd.notnull(row['Longitude']) else None, axis=1)
    df = df.dropna(subset=['geometry']).reset_index(drop=True)
    gdf = gpd.GeoDataFrame(df, geometry='geometry', crs='EPSG:4326')
    gdf_utm = gdf.to_crs(epsg=32632)
    coords = gdf_utm['geometry'].apply(lambda geom: (geom.x, geom.y)).tolist()
    dist_matrix = distance_matrix(coords, coords)
    visited_order = [0]
    current_index = 0
    while len(visited_order) < len(gdf_utm):
        distances = dist_matrix[current_index]
        distances[visited_order] = float('inf')
        nearest_index = distances.argmin()
        visited_order.append(nearest_index)
        current_index = nearest_index
    gdf_sorted = gdf_utm.iloc[visited_order].reset_index(drop=True)
    line = LineString(gdf_sorted.geometry.tolist())
    line_gdf = gpd.GeoDataFrame(geometry=[line], crs=gdf_utm.crs)
    shoreline_gdf = gdf_sorted.to_crs(epsg=32632)
    shoreline_line = LineString(shoreline_gdf.geometry.tolist())
    transects = []
    cumulative = []
    for i, point in enumerate(shoreline_line.coords):
        if i == len(shoreline_line.coords) - 1:
            break
        if years_multiplier == 'temporal_cumulative':
            start_point = Point(point)
            end_point = Point(shoreline_line.coords[i + 1])
            _quiet_print(shoreline_gdf.head(), level='debug')
            percentile_50 = shoreline_gdf['percentile_50'].iloc[i]
            sign = 1 if percentile_50 > 0 else -1
            Timespan = shoreline_gdf['percentile_50'].iloc[i] * shoreline_gdf['Timespan'].iloc[i] + shoreline_gdf['intercept'].iloc[i] * sign
            transect_length = abs(Timespan)
            direction = -1 if percentile_50 >= 0 else 1
            cumulative.append(transect_length * direction)
            dx = end_point.x - start_point.x
            dy = end_point.y - start_point.y
            segment_angle = math.atan2(dy, dx)
            perp_angle = segment_angle + math.pi / 2 * direction
            transect_dx = math.cos(perp_angle) * transect_length
            transect_dy = math.sin(perp_angle) * transect_length
            transect_end = Point(start_point.x + transect_dx, start_point.y + transect_dy)
            transect_line = LineString([start_point, transect_end])
            transects.append(transect_line)
        else:
            start_point = Point(point)
            end_point = Point(shoreline_line.coords[i + 1])
            percentile_50 = shoreline_gdf['percentile_50'].iloc[i]
            Timespan = 1
            transect_length = abs(percentile_50 * int(Timespan))
            direction = -1 if percentile_50 >= 0 else 1
            cumulative.append(transect_length * direction)
            dx = end_point.x - start_point.x
            dy = end_point.y - start_point.y
            segment_angle = math.atan2(dy, dx)
            perp_angle = segment_angle + math.pi / 2 * direction
            transect_dx = math.cos(perp_angle) * transect_length
            transect_dy = math.sin(perp_angle) * transect_length
            transect_end = Point(start_point.x + transect_dx, start_point.y + transect_dy)
            transect_line = LineString([start_point, transect_end])
            transects.append(transect_line)
    transect_gdf = gpd.GeoDataFrame(geometry=transects, crs=shoreline_gdf.crs)
    transect_gdf = transect_gdf.to_crs(epsg=32632)
    transect_gdf['length_m'] = transect_gdf.length
    transect_gdf['cumulative_percentile_50'] = cumulative
    _shapefile_safe_copy(transect_gdf).to_file(os.path.join(shapefiles, f'{country}shoreline_one_sided_transects_1_{years_multiplier}.shp'))
    _quiet_print('Shoreline LineString shapefile saved successfully.', level='debug')
    return (transect_gdf, gdf_sorted)

def trasfer_attributes_to_transects(country, shapefiles, transect_gdf, gdf_sorted, years_multiplier):
    """Spatially join shoreline point attributes to transects and export the result."""
    shoreline_points_gdf = gdf_sorted
    shoreline_points_gdf = shoreline_points_gdf.to_crs(transect_gdf.crs)
    transects_with_attributes = gpd.sjoin(transect_gdf, shoreline_points_gdf, how='left', predicate='intersects')
    _shapefile_safe_copy(transects_with_attributes).to_file(os.path.join(shapefiles, f'{country}shoreline_transects_with_attributes_{years_multiplier}.shp'))
    _quiet_print(f'transects_with_attributes obs {len(transects_with_attributes)}', level='debug')
    _quiet_print('Transect shapefile with point attributes saved successfully.', level='debug')
    return transects_with_attributes
