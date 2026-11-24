"""AOI buffer matching R's static_map_bounds.

Replicates aspect_buffer(aoi, 8.77/7.55, buffer_percent=0.05)
from core/R/fns.R:907 + core/R/maps-static.R:16-18
"""
import geopandas as gpd
from shapely.geometry import box, Polygon
from pyproj import Transformer

# map_width / map_height from core/R/maps-static.R:16-18
MAP_ASPECT_RATIO = 8.77 / 7.55


def static_map_buffer(aoi, aspect_ratio=MAP_ASPECT_RATIO, buffer_percent=0.05):
    """Create a buffered bounding box matching R's static_map_bounds.

    Projects AOI to EPSG:3857, adjusts to aspect ratio, applies buffer,
    and returns a WGS84 GeoDataFrame with the rectangular extent.
    """
    # Project AOI to EPSG:3857 (Web Mercator) — same as R's to_crs
    aoi_3857 = aoi.to_crs(epsg=3857)
    total_bounds = aoi_3857.total_bounds  # [minx, miny, maxx, maxy]
    cx = (total_bounds[0] + total_bounds[2]) / 2
    cy = (total_bounds[1] + total_bounds[3]) / 2
    x_distance = total_bounds[2] - total_bounds[0]
    y_distance = total_bounds[3] - total_bounds[1]

    # Adjust to aspect ratio (same logic as R)
    if x_distance / y_distance < aspect_ratio:
        x_distance = y_distance * aspect_ratio
    elif x_distance / y_distance > aspect_ratio:
        y_distance = x_distance / aspect_ratio

    # Apply buffer and build bounds in 3857
    half_x = x_distance / 2 * (1 + buffer_percent)
    half_y = y_distance / 2 * (1 + buffer_percent)
    bounds_3857 = box(cx - half_x, cy - half_y, cx + half_x, cy + half_y)

    # Project back to WGS84
    to_wgs = Transformer.from_crs("EPSG:3857", "EPSG:4326", always_xy=True)
    coords_3857 = list(bounds_3857.exterior.coords)
    coords_wgs = [to_wgs.transform(x, y) for x, y in coords_3857]
    buffer_poly = Polygon(coords_wgs)

    return gpd.GeoDataFrame(geometry=[buffer_poly], crs="EPSG:4326")
