from core.py.log_module import setup_logger
logger = setup_logger(__name__)

def generate_contours(
    city_name: str,
    output_dir: str,
    elev_array=None,
    elev_meta=None,
    return_gdf: bool = False,
):
    """
    Generate contour lines from an elevation raster using rasterio.features.shapes.

    This function approximates contour lines by:
    1. Classifying elevation values into discrete contour bins
    2. Polygonizing elevation classes using rasterio.features.shapes
    3. Extracting polygon boundaries as LineString geometries
    4. Writing the result to a GeoPackage

    NOTE
    ----
    This method generates contour *class boundaries*, not mathematically exact
    isolines. 

    Parameters
    ----------
    city_name : str
        City name used for file naming.
    output_dir : str
        Directory where `{city_name}_elevation.tif` is read from and
        `{city_name}_contours.gpkg` is written to.
    elev_array : np.ndarray, optional
        Elevation raster array. If None, it will be read from disk.
    elev_meta : dict, optional
        Raster metadata (transform, crs, nodata). Required if elev_array is provided.
    return_gdf : bool, default False
        If True, return the contour GeoDataFrame in memory.

    Returns
    -------
    geopandas.GeoDataFrame or None
        Contour lines GeoDataFrame if return_gdf=True, otherwise None.
    """
    import math
    import numpy as np
    import rasterio
    from rasterio.features import shapes
    from shapely.geometry import shape
    import geopandas as gpd
    from shapely.ops import unary_union
    import os

    city_name = city_name.lower()
    spatial_dir = os.path.join(output_dir, "spatial")
    os.makedirs(spatial_dir, exist_ok=True)
    dem_path = f"{spatial_dir}/{city_name}_elevation.tif"
    out_gpkg = f"{spatial_dir}/{city_name}_contours.gpkg"

    # ------------------------------------------------------------------
    # Load elevation raster (if not provided)
    # ------------------------------------------------------------------
    if elev_array is None or elev_meta is None:
        with rasterio.open(dem_path) as src:
            logger.info('reading from output_dir')
            elev_array = src.read(1)
            elev_meta = src.meta.copy()
            nodata = src.nodata
            transform = src.transform
            crs = src.crs
    else:
        logger.info('reading from given array and meta')
        nodata = elev_meta.get("nodata")
        transform = elev_meta["transform"]
        crs = elev_meta["crs"]

    # Ensure we are working with a plain ndarray
    if np.ma.isMaskedArray(elev_array):
        elev = elev_array.filled(np.nan).astype("float32")
    else:
        elev = elev_array.astype("float32")

    if nodata is not None:
        elev[elev == nodata] = np.nan

    # ------------------------------------------------------------------
    # Determine contour interval
    # ------------------------------------------------------------------
    dem_min = np.nanmin(elev)
    dem_max = np.nanmax(elev)
    dem_range = dem_max - dem_min
    logger.info(f'interval: min = {dem_min}, max = {dem_max}')

    if dem_range > 250:
        interval = math.ceil(dem_range / 500) * 10
    elif dem_range > 100:
        interval = 5
    elif dem_range > 50:
        interval = 2
    else:
        interval = 1

    contour_levels = np.arange(
        math.floor(dem_min / interval) * interval,
        math.ceil(dem_max / interval) * interval + interval,
        interval,
    )

    # ------------------------------------------------------------------
    # Reclassify elevation into contour bins
    # ------------------------------------------------------------------
    try:
        logger.info('classifying elevation')
        classed = np.digitize(elev, contour_levels, right=False).astype("int32")
        classed[np.isnan(elev)] = 0
    except Exception as e:
        logger.error(f"Error: {e}")

    # ------------------------------------------------------------------
    # Polygonize elevation classes
    # ------------------------------------------------------------------
    polygons = []
    values = []
    try:
        for geom, value in shapes(
            classed,
            mask=classed > 0,
            transform=transform,
        ):
            polygons.append(shape(geom))
            idx = int(value) - 1
            values.append(contour_levels[idx])


        gdf_poly = gpd.GeoDataFrame(
            {"elevation": values},
            geometry=polygons,
            crs=crs,
        )
        logger.info('polygonize successful')
    except Exception as e:
        logger.error(f"Error: {e}")

    # ------------------------------------------------------------------
    # Convert polygons to contour lines (boundaries)
    # ------------------------------------------------------------------
    try:
        gdf_poly["geometry"] = gdf_poly.geometry.boundary
        gdf_poly = gdf_poly.explode(index_parts=False).reset_index(drop=True)

        # Dissolve by elevation to remove internal edges
        gdf_lines = (
            gdf_poly.dissolve(by="elevation")
            .reset_index()
            .set_crs(crs)
        )
    except Exception as e:
        logger.error(f"Error: {e}")

    # ------------------------------------------------------------------
    # Write to GeoPackage
    # ------------------------------------------------------------------
    gdf_lines.to_file(
        out_gpkg,
        layer="contours",
        driver="GPKG",
    )
    logger.info(f"Success: save elevation contours to {out_gpkg}")
    if return_gdf:
        return gdf_lines

    return None

# Equivalent of Caroline's clean.py — clean_e()
def elevation_stats(
    city_name: str,
    output_dir: str,
    elev_array=None,
    elev_meta=None,
):
    """
    Compute elevation distribution statistics from a DEM raster and export
    a 6-bin elevation histogram as a CSV file.

    The workflow is:
    1. Load elevation raster (from array+meta or from disk)
    2. Generate fine-grained contour levels based on elevation range
    3. Select 6 evenly spaced contour levels to act as histogram bin edges
    4. Count pixels falling into each bin
    5. Export results to CSV

    Parameters
    ----------
    city_name : str
        City name used for file naming.
    output_dir : str
        Directory where `{city_name}_elevation.tif` is read from (if needed)
        and where `{city_name}_elevation.csv` will be written.
    elev_array : np.ndarray, optional
        Elevation raster array. If None, raster is read from disk.
    elev_meta : dict, optional
        Raster metadata (must include nodata). Required if elev_array is provided.

    Returns
    -------
    None
    """
    import math
    import csv
    import numpy as np
    import rasterio
    import os

    city_name = city_name.lower()
    spatial_dir = os.path.join(output_dir, "spatial")
    os.makedirs(spatial_dir, exist_ok=True)
    tabular_dir = os.path.join(output_dir, "tabular")
    os.makedirs(tabular_dir, exist_ok=True)

    dem_path = f"{spatial_dir}/{city_name}_elevation.tif"
    out_csv = f"{tabular_dir}/{city_name}_elevation.csv"

    # ------------------------------------------------------------------
    # Step 1: Read elevation raster
    # ------------------------------------------------------------------
    if elev_array is not None and elev_meta is not None:
        elev = elev_array.astype("float32")
        nodata = elev_meta.get("nodata")
    else:
        try:
            with rasterio.open(dem_path) as src:
                elev = src.read(1).astype("float32")
                nodata = src.nodata
        except Exception as e:
            logger.error(f"No elevation raster found or provided: {e}")
            

    if nodata is not None:
        elev[elev == nodata] = np.nan

    # FABDEM flattens water surfaces (rivers, lakes, sea) to exactly 0.0,
    # which leaks into the lowest bin and skews the legend. Treat as NA.
    elev[elev == 0] = np.nan

    # ------------------------------------------------------------------
    # Step 2: Generate contour levels (fine resolution)
    # ------------------------------------------------------------------
    dem_min = np.nanmin(elev)
    dem_max = np.nanmax(elev)
    dem_range = dem_max - dem_min

    # Decide contour interval based on terrain range
    if dem_range > 250:
        contour_interval = math.ceil(dem_range / 500) * 10
    elif dem_range > 100:
        contour_interval = 5
    elif dem_range > 50:
        contour_interval = 2
    else:
        contour_interval = 1

    contour_min = math.floor(dem_min / contour_interval) * contour_interval
    contour_max = math.ceil(dem_max / contour_interval) * contour_interval

    contour_levels = list(
        range(contour_min, contour_max + contour_interval, contour_interval)
    )

    # ------------------------------------------------------------------
    # Step 3: Reduce contour levels to 6 histogram bins
    # ------------------------------------------------------------------
    """
    We want exactly 6 bin edges spanning the full elevation range.
    This is done by selecting evenly spaced indices from contour_levels.
    """
    if dem_range == 0:
        # Flat terrain: single bin
        bin_edges = [dem_min, dem_max + 1e-6]
    else:
        n_levels = len(contour_levels)
        step = (n_levels - 1) / 5
        bin_edges = [
            contour_levels[int(round(step * i))]
            for i in range(6)
        ]


    # ------------------------------------------------------------------
    # Step 4: Compute elevation histogram (pixel counts)
    # ------------------------------------------------------------------
    hist, _ = np.histogram(elev[~np.isnan(elev)], bins=bin_edges)

    # ------------------------------------------------------------------
    # Step 5: Write CSV output
    # ------------------------------------------------------------------
    with open(out_csv, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["Bin", "Pixel_Count"])

        for i, count in enumerate(hist):
            band_label = f"{bin_edges[i]}-{bin_edges[i+1]}"
            writer.writerow([band_label, int(count)])

def elevation_interpretation(city_name: str, output_dir: str):
    """
    Generate a human-readable interpretation of elevation statistics
    based on the elevation histogram CSV.

    Parameters
    ----------
    city_name : str
        City name used for file naming.
    output_dir : str
        Directory where the elevation CSV is stored and where the YAML
        interpretation will be written.

    Returns
    -------
    dict
        Dictionary containing the generated interpretation text.
    """
    import os
    import pandas as pd
    import yaml

    tabular_dir = os.path.join(output_dir, "tabular")
    os.makedirs(tabular_dir, exist_ok=True)

    city_name = city_name.lower()
    csv_path = f"{tabular_dir}/{city_name}_elevation.csv"
    yaml_path = f"{tabular_dir}/{city_name}_elev_stats.yml"

    if not os.path.exists(csv_path):
        raise FileNotFoundError(f"Elevation CSV not found: {csv_path}")

    # ------------------------------------------------------------------
    # Step 1: Read elevation histogram CSV
    # ------------------------------------------------------------------
    df = pd.read_csv(csv_path)

    # Expected columns:
    # - Bin (e.g. "0-25")
    # - Pixel_Count

    if df.empty:
        raise ValueError("Elevation CSV is empty.")

    # ------------------------------------------------------------------
    # Step 2: Identify the most common elevation range
    # ------------------------------------------------------------------
    total_pixels = df["Pixel_Count"].sum()
    if total_pixels == 0:
        raise ValueError("Total pixel count is zero; cannot compute percentages.")

    df["percent"] = (df["Pixel_Count"] / total_pixels) * 100

    highest_percent_row = df.loc[df["percent"].idxmax()]

    # ------------------------------------------------------------------
    # Step 3: Generate interpretation text
    # ------------------------------------------------------------------
    interpretation_text = (
        f"The most common elevation range in the city is "
        f"{highest_percent_row['Bin']} meters, "
        f"covering approximately {highest_percent_row['percent']:.2f}% "
        f"of the total area."
    )

    elev_stats = {
        "elev_stats": interpretation_text
    }

    # ------------------------------------------------------------------
    # Step 4: Write YAML output
    # ------------------------------------------------------------------
    with open(yaml_path, "w") as f:
        yaml.dump(elev_stats, f, sort_keys=False)

    return elev_stats
