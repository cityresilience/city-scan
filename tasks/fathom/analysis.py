import os
from os.path import exists
from core.py.log_module import setup_logger
logger = setup_logger(__name__)


def conditional_assign(dictionary, key, value):
    """
    Assign a key-value pair to a dictionary only if value is not None.

    Parameters
    ----------
    dictionary : dict
        Target dictionary.
    key : Any
        Dictionary key.
    value : Any
        Value to assign.

    Returns
    -------
    None
    """
    if value is not None:
        dictionary[key] = value


# ==========================================================
# WSF STATISTICS
# Equivalent of Caroline's clean.py — clean_flood()
# ==========================================================

def calculate_flood_wsf_stats(output_dir, city_name, flood_raster):
    """
    Calculate cumulative built-up exposure (sqkm) by WSF year.

    Parameters
    ----------
    output_dir : str
        Root output directory.
    city_name : str
        Lowercase city name.
    flood_raster : str
        Flood raster filename (must include _utm suffix).

    Returns
    -------
    dict or None
        Dictionary {year: cumulative_exposed_sqkm}.
        Returns None if required WSF asset is missing.
    """
    import numpy as np
    import rasterio
    from rasterio.vrt import WarpedVRT
    from rasterio.warp import Resampling

    spatial_dir = os.path.join(output_dir, "spatial")

    # Ensure flood_raster uses _utm suffix
    if not flood_raster.endswith("_utm.tif"):
        logger.warning(f"Flood raster should use _utm suffix: {flood_raster}")

    wsf_path = os.path.join(spatial_dir, f"{city_name}_wsf_evolution_utm.tif")
    flood_path = os.path.join(spatial_dir, flood_raster)

    # Ensure required inputs exist
    if not exists(wsf_path) or not exists(flood_path):
        return None

    # Accumulate exposed built-up pixel counts per WSF construction year, windowed.
    # The flood raster is warped onto the WSF grid on the fly (WarpedVRT, nearest —
    # window-decomposable, so identical to the old reprojected _wsf.tif) instead of
    # materialising a national intermediate raster (was ~38 GiB → OOM and a
    # read-before-flush race on the GCS-mounted filesystem).
    year_counts = {year: 0 for year in range(1985, 2016)}

    with rasterio.open(wsf_path) as wsf, rasterio.open(flood_path) as flood_src:
        pixel_x, pixel_y = wsf.res
        with WarpedVRT(flood_src, crs=wsf.crs, transform=wsf.transform,
                       width=wsf.width, height=wsf.height,
                       resampling=Resampling.nearest) as fld:
            for _, window in wsf.block_windows(1):
                wsf_block = wsf.read(1, window=window)
                flood_block = fld.read(1, window=window)
                for year in range(1985, 2016):
                    year_counts[year] += np.count_nonzero(
                        flood_block[wsf_block == year]
                    )

    flood_stats = {}
    cumulative = 0
    for year in range(1985, 2016):
        cumulative += year_counts[year] * pixel_x * pixel_y / 1e6
        flood_stats[year] = cumulative

    return flood_stats


# ==========================================================
# WSF EXPOSURE WRAPPER
# ==========================================================

def exposure_flood_wsf(
    aoi,
    menu,
    flood_years,
    flood_ssps,
    output_dir,
    city_name,
):
    """
    Compute WSF exposure statistics for all enabled flood types.

    Parameters
    ----------
    menu : dict
        Configuration flags for flood types.
    flood_years : list[int]
        List of analysis years.
    flood_ssps : list[int]
        SSP scenario identifiers for future years.
    output_dir : str
        Root output directory.
    city_name : str
        Lowercase city name.

    Returns
    -------
    dict
        Nested dictionary:
        {
            flood_type: {
                year: {1985-2015 exposure series}  (<=2020)
                year: {ssp: exposure series}       (>2020)
            }
        }
    """
    from core.py import raster_module as raster_pro
    
    # Convert single integer to list
    if isinstance(flood_years, int):
        flood_years = [flood_years]
    
    if isinstance(flood_ssps, int):
        flood_ssps = [flood_ssps]
    
    logger.info("Starting WSF flood exposure computation")

    utm_crs = aoi.estimate_utm_crs()
    spatial_dir = os.path.join(output_dir, "spatial")
    wsf_path = os.path.join(
        spatial_dir, f"{city_name}_wsf_evolution_utm.tif"
    )

    # -----------------------------------------------------
    # Validate WSF baseline asset
    # -----------------------------------------------------
    if not exists(wsf_path):
        wsf_source_path = os.path.join(
            spatial_dir, f"{city_name}_wsf_evolution.tif"
        )
        
        if exists(wsf_source_path):
            logger.info(
                f"WSF UTM raster not found. Reprojecting from: {wsf_source_path}"
            )
            try:
                raster_pro.reproject_raster(
                    wsf_source_path,
                    wsf_path,
                    dst_crs=utm_crs,
                    compress='deflate'
                )
                logger.info(f"Successfully reprojected to: {wsf_path}")
            except Exception as e:
                logger.error(
                    f"Failed to reproject WSF raster: {e}. "
                    "Exposure calculation aborted."
                )
                return {}
        else:
            logger.error(
                f"WSF baseline rasters not found: {wsf_path} or {wsf_source_path}. "
                "Exposure calculation aborted."
            )
            return {}

    logger.info(f"WSF baseline raster found: {wsf_path}")

    results = {}
    flood_types = ["coastal", "fluvial", "pluvial", "comb"]

    for ft in flood_types:

        if not menu.get(f"flood_{ft}", False):
            logger.info(f"Skipping flood type '{ft}' (disabled in menu)")
            continue

        logger.info(f"Processing flood type: {ft}")
        results[ft] = {}

        try:
            for year in flood_years:

                # =====================================================
                # Historical
                # =====================================================
                if year <= 2020:
                    raster_name = f"{city_name}_{ft}_{year}_utm.tif"
                    raster_path = os.path.join(spatial_dir, raster_name)

                    if not exists(raster_path):
                        logger.warning(
                            f"Missing raster: {raster_path}"
                        )
                        continue

                    logger.info(
                        f"Computing exposure | type={ft}, year={year}"
                    )

                    try:
                        stats = calculate_flood_wsf_stats(
                            output_dir,
                            city_name,
                            raster_name,
                        )
                        conditional_assign(results[ft], year, stats)

                    except Exception as e:
                        logger.error(
                            f"Failed exposure calc | "
                            f"type={ft}, year={year}: {e}",
                            exc_info=True,
                        )

                # =====================================================
                # Future (SSP)
                # =====================================================
                else:
                    results[ft][year] = {}

                    for ssp in flood_ssps:
                        raster_name = (
                            f"{city_name}_{ft}_{year}_ssp{ssp}.tif"
                        )
                        raster_path = os.path.join(
                            spatial_dir, raster_name
                        )

                        if not exists(raster_path):
                            logger.warning(
                                f"Missing raster: {raster_path}"
                            )
                            continue

                        logger.info(
                            f"Computing exposure | "
                            f"type={ft}, year={year}, ssp={ssp}"
                        )

                        try:
                            stats = calculate_flood_wsf_stats(
                                output_dir,
                                city_name,
                                raster_name,
                            )
                            conditional_assign(
                                results[ft][year],
                                ssp,
                                stats,
                            )

                        except Exception as e:
                            logger.error(
                                f"Failed exposure calc | "
                                f"type={ft}, year={year}, ssp={ssp}: {e}",
                                exc_info=True,
                            )

        except Exception as e:
            logger.error(
                f"Unexpected failure in flood type '{ft}': {e}",
                exc_info=True,
            )

    logger.info("Completed WSF flood exposure computation")
    
    # Save results to CSV
    tabular_dir = os.path.join(output_dir, "tabular")
    os.makedirs(tabular_dir, exist_ok=True)
    
    rows = []
    
    for ft in results:
        for year in results[ft]:
            if results[ft][year]:  # Check if not empty
                year_data = results[ft][year]
                # Check if this is a dict of SSPs (future years) or direct year data (historical)
                if isinstance(year_data, dict) and isinstance(list(year_data.values())[0] if year_data else None, dict):
                    # Future years with SSPs
                    for ssp in year_data:
                        if year_data[ssp]:
                            for yr in range(1985, 2016):
                                if yr in year_data[ssp]:
                                    rows.append([yr, f'{ft}_{year}_ssp{ssp}', year_data[ssp][yr]])
                else:
                    # Historical years
                    for yr in range(1985, 2016):
                        if yr in year_data:
                            rows.append([yr, f'{ft}_{year}', year_data[yr]])
    
    if rows:
        import pandas as pd
        df = pd.DataFrame(rows, columns=['year', 'type', 'exposed_built_up_sqkm'])
        df_pivot = df.pivot(index='year', columns='type', values='exposed_built_up_sqkm')
        csv_path = os.path.join(tabular_dir, f"{city_name}_flood_wsf.csv")
        df_pivot.to_csv(csv_path)
        logger.info(f"Saved WSF flood exposure stats to: {csv_path}")
    
    return results


# ==========================================================
# POPULATION EXPOSURE
# ==========================================================

def calculate_flood_pop_stats(output_dir, city_name, flood_raster):
    """
    Calculate dense population exposure (percentage) to flooding.
    
    Parameters
    ----------
    output_dir : str
        Root output directory.
    city_name : str
        Lowercase city name.
    flood_raster : str
        Flood raster filename (must include _utm suffix).
    
    Returns
    -------
    float or None
        Percentage of dense population exposed, or None if assets missing.
    """
    import numpy as np
    import rasterio
    from rasterio.vrt import WarpedVRT
    from rasterio.warp import Resampling

    spatial_dir = os.path.join(output_dir, "spatial")

    # Ensure flood_raster uses _utm suffix
    if not flood_raster.endswith("_utm.tif"):
        logger.warning(f"Flood raster should use _utm suffix: {flood_raster}")

    pop_path = os.path.join(spatial_dir, f"{city_name}_population.tif")
    dense_pop_path = os.path.join(spatial_dir, f"{city_name}_dense_population.tif")
    flood_path = os.path.join(spatial_dir, flood_raster)

    # Check required inputs
    if not exists(pop_path) or not exists(flood_path):
        return None

    # Create dense population raster if needed (population grid, ~100m — small)
    if not exists(dense_pop_path):
        try:
            with rasterio.open(pop_path) as pop:
                pop_array = pop.read(1)
                out_meta = pop.meta.copy()
                out_meta.update({'nodata': np.nan})

                # Replace nodata value
                pop_nodata = -99999
                pop_array = np.where(pop_array == pop_nodata, np.nan, pop_array)

                # Create binary mask for values >= 60th percentile
                pop60 = np.nanpercentile(pop_array, 60)
                pop_array_60 = np.where(pop_array >= pop60, 1, 0)

                with rasterio.open(dense_pop_path, 'w', **out_meta) as dst:
                    dst.write(pop_array_60, 1)
        except Exception as e:
            logger.debug(f"Failed to create dense population raster: {e}")
            return None

    # Compute dense population exposure windowed: warp the dense-pop mask onto the
    # flood grid on the fly (WarpedVRT, nearest) and accumulate two scalars per
    # block, instead of materialising a national _pop.tif intermediate (was
    # ~38 GiB → OOM and a read-before-flush race).
    try:
        numerator = 0
        denom = 0.0
        with rasterio.open(flood_path) as fld, rasterio.open(dense_pop_path) as dense_src:
            with WarpedVRT(dense_src, crs=fld.crs, transform=fld.transform,
                           width=fld.width, height=fld.height,
                           resampling=Resampling.nearest) as pop:
                for _, window in fld.block_windows(1):
                    flood_block = fld.read(1, window=window)
                    pop_block = pop.read(1, window=window)
                    numerator += np.count_nonzero(flood_block[pop_block == 1])
                    denom += np.nansum(pop_block)

        if denom == 0:
            return None
        return numerator / denom * 100
    except Exception as e:
        logger.debug(f"Failed to compute population exposure: {e}")
        return None


# ==========================================================
# OSM EXPOSURE
# ==========================================================

def calculate_flood_osm_stats(output_dir, city_name, poi, flood_raster):
    """
    Calculate OSM POI exposure to flooding.
    
    Parameters
    ----------
    output_dir : str
        Root output directory.
    city_name : str
        Lowercase city name.
    poi : str
        POI category (e.g., 'hospitals', 'schools').
    flood_raster : str
        Flood raster filename (must include _utm suffix).
    
    Returns
    -------
    tuple or None
        (total_pois, pois_in_flood_zone, percentage) or None if assets missing.
    """
    import geopandas as gpd
    import rasterio
    from rasterio.transform import rowcol
    import numpy as np
    
    spatial_dir = os.path.join(output_dir, "spatial")
    
    osm_path = os.path.join(spatial_dir, f"{city_name}_OSM_{poi}.gpkg")
    flood_path = os.path.join(spatial_dir, flood_raster)
    
    # Ensure flood_raster uses _utm suffix
    if not flood_raster.endswith("_utm.tif"):
        logger.warning(f"Flood raster should use _utm suffix: {flood_raster}")
    
    # Check required inputs
    if not exists(osm_path) or not exists(flood_path):
        logger.debug(f"OSM or flood raster missing: osm={exists(osm_path)}, flood={exists(flood_path)}")
        return None
    
    try:
        # Open the flood raster and sample it only at POI locations (no full
        # national read — src.sample reads just the needed pixels).
        with rasterio.open(flood_path) as src:
            flood_crs = src.crs
            flood_nodata = src.nodata
            logger.debug(f"Flood raster CRS: {flood_crs}")

            # Load OSM GeoDataFrame - try without layer name first, then with poi as layer
            try:
                osm_gdf = gpd.read_file(osm_path)
                logger.debug(f"Loaded OSM GeoPackage without layer specification")
            except Exception as e:
                logger.debug(f"Failed to load without layer: {e}. Trying with layer='{poi}'")
                try:
                    osm_gdf = gpd.read_file(osm_path, layer=poi)
                    logger.debug(f"Loaded OSM GeoPackage with layer='{poi}'")
                except Exception as e2:
                    logger.error(f"Could not load OSM GeoPackage {osm_path}: {e2}")
                    return None

            if osm_gdf.empty:
                logger.debug(f"OSM GeoPackage empty for POI type: {poi}")
                return None

            logger.debug(f"OSM GeoDataFrame CRS: {osm_gdf.crs}")
            logger.debug(f"OSM geometry types: {osm_gdf.geometry.type.unique()}")
            logger.debug(f"OSM feature count: {len(osm_gdf)}")

            # Validate and align CRS to UTM
            if osm_gdf.crs != flood_crs:
                logger.info(
                    f"CRS mismatch for {poi}: OSM={osm_gdf.crs}, Flood={flood_crs}. "
                    f"Reprojecting OSM to match flood raster (UTM)..."
                )
                osm_gdf = osm_gdf.to_crs(flood_crs)
                logger.debug(f"OSM reprojected to: {osm_gdf.crs}")

            # Convert all geometries to centroids (handles both points and polygons)
            logger.debug("Converting geometries to centroids...")
            osm_gdf['geometry'] = osm_gdf.geometry.centroid
            logger.debug(f"All geometries converted to centroids. CRS: {osm_gdf.crs}")

            # Sample the flood raster at each centroid; nodata / out-of-bounds
            # sample back as not-flooded.
            coords = [(geom.x, geom.y) for geom in osm_gdf.geometry]
            osm_gdf['in_flood_zone'] = [
                bool(val[0] > 0 and val[0] != flood_nodata)
                for val in src.sample(coords, indexes=1)
            ]

        # Calculate metrics
        total_pois = len(osm_gdf)
        pois_in_flood_zone = int(osm_gdf['in_flood_zone'].sum())
        percentage = (pois_in_flood_zone / total_pois) * 100 if total_pois > 0 else 0

        logger.info(
            f"OSM exposure ({poi}): {total_pois} total, {pois_in_flood_zone} in flood "
            f"({percentage:.2f}%)"
        )

        return (total_pois, pois_in_flood_zone, percentage)
    
    except Exception as e:
        logger.error(f"Failed to compute OSM exposure for {poi}: {e}", exc_info=True)
        return None


# ==========================================================
# ROAD EXPOSURE
# ==========================================================

def calculate_flood_road_stats(output_dir, city_name, utm_crs, flood_raster):
    """
    Calculate road network exposure to flooding.
    
    Parameters
    ----------
    output_dir : str
        Root output directory.
    city_name : str
        Lowercase city name.
    utm_crs : CRS
        UTM CRS for coordinate system.
    flood_raster : str
        Flood raster filename (must include _utm suffix).
    
    Returns
    -------
    tuple or None
        (total_length_m, flooded_length_m, percentage) or None if assets missing.
    """
    import rasterio
    import geopandas as gpd
    import numpy as np

    spatial_dir = os.path.join(output_dir, "spatial")

    # Ensure flood_raster uses _utm suffix
    if not flood_raster.endswith("_utm.tif"):
        logger.warning(f"Flood raster should use _utm suffix: {flood_raster}")
    
    road_path = os.path.join(spatial_dir, f"{city_name}_major_roads.gpkg")
    flood_path = os.path.join(spatial_dir, flood_raster)
    
    # Check required inputs
    if not exists(road_path) or not exists(flood_path):
        logger.debug(f"Road or flood raster missing: road={exists(road_path)}, flood={exists(flood_path)}")
        return None
    
    try:
        from rasterio.features import rasterize

        # Load road GeoDataFrame
        road_gdf = gpd.read_file(road_path)

        if road_gdf.empty:
            logger.debug(f"Road GeoPackage empty")
            return None

        logger.debug(f"Road feature count: {len(road_gdf)}")

        # Open the flood raster once and rasterize roads + count overlap PER BLOCK,
        # so neither the national flood array nor a second national road-raster is
        # ever held in memory (was ~2x the national grid -> OOM at native res).
        total_road_pixels = 0
        flooded_road_pixels = 0
        with rasterio.open(flood_path) as src:
            flood_crs = src.crs
            flood_transform = src.transform
            pixel_size_m = abs(flood_transform[0])  # Assume square pixels
            logger.debug(f"Flood raster CRS: {flood_crs}")
            logger.debug(f"Road GeoDataFrame CRS: {road_gdf.crs}")

            # Validate and align CRS to UTM
            if road_gdf.crs != flood_crs:
                logger.info(
                    f"CRS mismatch for roads: Roads={road_gdf.crs}, Flood={flood_crs}. "
                    f"Reprojecting roads to match flood raster (UTM)..."
                )
                road_gdf = road_gdf.to_crs(flood_crs)
                logger.debug(f"Roads reprojected to: {road_gdf.crs}")

            road_shapes = [(geom, 1) for geom in road_gdf.geometry]

            for _, window in src.block_windows(1):
                flood_block = src.read(1, window=window)
                road_block = rasterize(
                    road_shapes,
                    out_shape=flood_block.shape,
                    transform=src.window_transform(window),
                    default_value=0
                )
                road_mask = road_block > 0
                total_road_pixels += int(np.count_nonzero(road_mask))
                flooded_road_pixels += int(
                    np.count_nonzero(road_mask & (flood_block > 0))
                )

        total_length_m = total_road_pixels * pixel_size_m
        flooded_length_m = flooded_road_pixels * pixel_size_m

        # Calculate percentage
        if total_road_pixels > 0:
            percentage = (flooded_length_m / total_length_m) * 100
        else:
            percentage = 0
        
        logger.info(
            f"Road exposure: {total_length_m:.0f}m total, {flooded_length_m:.0f}m in flood "
            f"({percentage:.2f}%)"
        )
        
        return (total_length_m, flooded_length_m, percentage)
    
    except Exception as e:
        logger.error(f"Failed to compute road exposure: {e}", exc_info=True)
        return None


# ==========================================================
# POPULATION EXPOSURE WRAPPER
# ==========================================================

def exposure_flood_pop(
    aoi,
    menu,
    flood_years,
    flood_ssps,
    output_dir,
    city_name,
):
    """
    Compute dense population exposure statistics for all enabled flood types.
    
    Parameters
    ----------
    aoi : GeoDataFrame
        Area of interest.
    menu : dict
        Configuration flags for flood types.
    flood_years : int or list[int]
        Analysis years.
    flood_ssps : int or list[int]
        SSP scenario identifiers.
    output_dir : str
        Root output directory.
    city_name : str
        Lowercase city name.
    
    Returns
    -------
    dict
        {flood_type: {year: percentage} or {year: {ssp: percentage}}}
    """
    # Normalize inputs
    if isinstance(flood_years, int):
        flood_years = [flood_years]
    if isinstance(flood_ssps, int):
        flood_ssps = [flood_ssps]
    
    logger.info("Starting population flood exposure computation")
    
    spatial_dir = os.path.join(output_dir, "spatial")
    pop_path = os.path.join(spatial_dir, f"{city_name}_population.tif")
    
    # Check for required baseline asset
    if not exists(pop_path):
        logger.warning(f"Population raster not found: {pop_path}. Skipping population exposure.")
        return {}
    
    results = {}
    flood_types = ["coastal", "fluvial", "pluvial", "comb"]
    
    for ft in flood_types:
        if not menu.get(f"flood_{ft}", False):
            logger.info(f"Skipping flood type '{ft}' (disabled in menu)")
            continue
        
        logger.info(f"Processing flood type: {ft}")
        results[ft] = {}
        
        try:
            for year in flood_years:
                if year <= 2020:
                    raster_name = f"{city_name}_{ft}_{year}_utm.tif"
                    raster_path = os.path.join(spatial_dir, raster_name)
                    
                    if not exists(raster_path):
                        logger.warning(f"Missing raster: {raster_path}")
                        continue
                    
                    logger.info(f"Computing exposure | type={ft}, year={year}")
                    
                    try:
                        stats = calculate_flood_pop_stats(
                            output_dir, city_name, raster_name
                        )
                        conditional_assign(results[ft], year, stats)
                    except Exception as e:
                        logger.error(
                            f"Failed exposure calc | type={ft}, year={year}: {e}",
                            exc_info=True,
                        )
                
                else:
                    results[ft][year] = {}
                    
                    for ssp in flood_ssps:
                        raster_name = f"{city_name}_{ft}_{year}_ssp{ssp}.tif"
                        raster_path = os.path.join(spatial_dir, raster_name)
                        
                        if not exists(raster_path):
                            logger.warning(f"Missing raster: {raster_path}")
                            continue
                        
                        logger.info(
                            f"Computing exposure | type={ft}, year={year}, ssp={ssp}"
                        )
                        
                        try:
                            stats = calculate_flood_pop_stats(
                                output_dir, city_name, raster_name
                            )
                            conditional_assign(results[ft][year], ssp, stats)
                        except Exception as e:
                            logger.error(
                                f"Failed exposure calc | type={ft}, year={year}, ssp={ssp}: {e}",
                                exc_info=True,
                            )
        
        except Exception as e:
            logger.error(
                f"Unexpected failure in flood type '{ft}': {e}",
                exc_info=True,
            )
    
    logger.info("Completed population flood exposure computation")
    
    # Save results to CSV
    tabular_dir = os.path.join(output_dir, "tabular")
    os.makedirs(tabular_dir, exist_ok=True)
    
    rows = []
    
    for ft in results:
        for year in results[ft]:
            year_data = results[ft][year]
            if year_data is None:
                continue
            
            # Check if dict (future years with SSPs) or numeric (historical)
            if isinstance(year_data, dict):
                # Future years with SSPs
                for ssp in year_data:
                    if year_data[ssp] is not None:
                        rows.append([f'{ft}_{year}_ssp{ssp}', year_data[ssp]])
            else:
                # Historical years
                rows.append([f'{ft}_{year}', year_data])
    
    if rows:
        import pandas as pd
        df = pd.DataFrame(rows, columns=['type', 'exposed_dense_pop_pct'])
        csv_path = os.path.join(tabular_dir, f"{city_name}_flood_pop.csv")
        df.to_csv(csv_path, index=False)
        logger.info(f"Saved population exposure stats to: {csv_path}")
    
    return results


# ==========================================================
# OSM EXPOSURE WRAPPER
# ==========================================================

def exposure_flood_osm(
    aoi,
    menu,
    flood_years,
    flood_ssps,
    output_dir,
    city_name,
    city_inputs,
):
    """
    Compute OSM POI exposure statistics for all enabled flood types.
    
    Parameters
    ----------
    aoi : GeoDataFrame
        Area of interest.
    menu : dict
        Configuration flags for flood types.
    flood_years : int or list[int]
        Analysis years.
    flood_ssps : int or list[int]
        SSP scenario identifiers.
    output_dir : str
        Root output directory.
    city_name : str
        Lowercase city name.
    city_inputs : dict
        City configuration with osm_query.
    
    Returns
    -------
    dict
        {flood_type: {year: {poi: tuple} or {year: {ssp: {poi: tuple}}}}}
    """
    # Normalize inputs
    if isinstance(flood_years, int):
        flood_years = [flood_years]
    if isinstance(flood_ssps, int):
        flood_ssps = [flood_ssps]
    
    logger.info("Starting OSM flood exposure computation")
    
    spatial_dir = os.path.join(output_dir, "spatial")
    
    # Extract POI types from city_inputs
    pois = city_inputs.get('osm_query', [])
    # logger.info(f"OSM POI types requested: {pois}")
    
    if not pois:
        logger.warning("No OSM POI types found in city_inputs['osm_query']. Skipping OSM exposure.")
        return {}
    
    # Check for at least one OSM asset
    osm_exists = False
    for poi in pois:
        osm_path = os.path.join(spatial_dir, f"{city_name}_OSM_{poi}.gpkg")
        if exists(osm_path):
            osm_exists = True
            logger.info(f"Found OSM asset: {osm_path}")
            break
        else:
            logger.debug(f"OSM asset not found: {osm_path}")
    
    if not osm_exists:
        logger.warning(f"No OSM GeoPackages found for POI types: {pois}. Skipping OSM exposure.")
        return {}
    
    results = {}
    flood_types = ["coastal", "fluvial", "pluvial", "comb"]
    
    for ft in flood_types:
        if not menu.get(f"flood_{ft}", False):
            logger.debug(f"Skipping flood type '{ft}' (disabled in menu)")
            continue
        
        logger.info(f"Processing flood type: {ft}")
        results[ft] = {}
        
        try:
            for year in flood_years:
                logger.debug(f"Processing year: {year}")
                
                if year <= 2020:
                    results[ft][year] = {}
                    
                    for poi in pois:
                        raster_name = f"{city_name}_{ft}_{year}_utm.tif"
                        raster_path = os.path.join(spatial_dir, raster_name)
                        
                        if not exists(raster_path):
                            logger.debug(f"Missing raster: {raster_path}")
                            continue
                        
                        logger.info(
                            f"Computing exposure | type={ft}, year={year}, poi={poi}"
                        )
                        
                        try:
                            stats = calculate_flood_osm_stats(
                                output_dir, city_name, poi, raster_name
                            )
                            conditional_assign(results[ft][year], poi, stats)
                            if stats:
                                logger.debug(f"OSM stats for {poi}: {stats}")
                        except Exception as e:
                            logger.error(
                                f"Failed exposure calc | type={ft}, year={year}, poi={poi}: {e}",
                                exc_info=False,
                            )
                
                else:
                    results[ft][year] = {}
                    
                    for ssp in flood_ssps:
                        results[ft][year][ssp] = {}
                        
                        for poi in pois:
                            raster_name = f"{city_name}_{ft}_{year}_ssp{ssp}.tif"
                            raster_path = os.path.join(spatial_dir, raster_name)
                            
                            if not exists(raster_path):
                                logger.debug(f"Missing raster: {raster_path}")
                                continue
                            
                            logger.info(
                                f"Computing exposure | type={ft}, year={year}, ssp={ssp}, poi={poi}"
                            )
                            
                            try:
                                stats = calculate_flood_osm_stats(
                                    output_dir, city_name, poi, raster_name
                                )
                                conditional_assign(results[ft][year][ssp], poi, stats)
                                if stats:
                                    logger.debug(f"OSM stats for {poi} SSP{ssp}: {stats}")
                            except Exception as e:
                                logger.error(
                                    f"Failed exposure calc | type={ft}, year={year}, ssp={ssp}, poi={poi}: {e}",
                                    exc_info=False,
                                )
        
        except Exception as e:
            logger.error(
                f"Unexpected failure in flood type '{ft}': {e}",
                exc_info=True,
            )
    
    logger.info("Completed OSM flood exposure computation")
    logger.info(f"OSM results keys: {list(results.keys())}")
    
    # Save results to CSV
    try:
        tabular_dir = os.path.join(output_dir, "tabular")
        os.makedirs(tabular_dir, exist_ok=True)
        
        rows = []
        
        for ft in results:
            logger.debug(f"Processing results for flood type: {ft}")
            for year in results[ft]:
                year_data = results[ft][year]
                logger.debug(f"Year {year} data: {year_data}")
                
                if isinstance(year_data, dict) and year_data:
                    # Check if this is a dict of SSPs or dict of POIs
                    first_val = next(iter(year_data.values()), None)
                    logger.debug(f"First value type: {type(first_val)}")
                    
                    if isinstance(first_val, dict):
                        # SSPs dict (future years)
                        logger.debug(f"Processing future years with SSPs")
                        for ssp in year_data:
                            for poi in year_data[ssp]:
                                if year_data[ssp][poi]:
                                    total_pois, pois_flood, pct = year_data[ssp][poi]
                                    rows.append([
                                        poi, f'{ft}_{year}_ssp{ssp}', 
                                        total_pois, pois_flood, pct
                                    ])
                    else:
                        # POIs dict (historical years)
                        logger.debug(f"Processing historical years")
                        for poi in year_data:
                            if year_data[poi]:
                                total_pois, pois_flood, pct = year_data[poi]
                                rows.append([
                                    poi, f'{ft}_{year}',
                                    total_pois, pois_flood, pct
                                ])
        
        logger.info(f"Total OSM rows to save: {len(rows)}")
        
        if rows:
            import pandas as pd
            df = pd.DataFrame(rows, columns=[
                'poi', 'type', 'total_pois', 
                'pois_in_flood_zone', 'percentage_in_flood_zone'
            ])
            csv_path = os.path.join(tabular_dir, f"{city_name}_flood_osm.csv")
            df.to_csv(csv_path, index=False)
            logger.info(f"Saved OSM exposure stats to: {csv_path}")
        else:
            logger.warning("No OSM exposure data to save (rows list is empty)")
    
    except Exception as e:
        logger.error(f"Failed to save OSM CSV: {e}", exc_info=True)
    
    return results


# ==========================================================
# ROAD EXPOSURE WRAPPER
# ==========================================================

def exposure_flood_road(
    aoi,
    menu,
    flood_years,
    flood_ssps,
    output_dir,
    city_name,
):
    """
    Compute road network exposure statistics for all enabled flood types.
    """
    # Normalize inputs
    if isinstance(flood_years, int):
        flood_years = [flood_years]
    if isinstance(flood_ssps, int):
        flood_ssps = [flood_ssps]
    
    logger.info("Starting road flood exposure computation")
    
    spatial_dir = os.path.join(output_dir, "spatial")
    road_path = os.path.join(spatial_dir, f"{city_name}_major_roads.gpkg")
    
    # Check for required baseline asset
    if not exists(road_path):
        logger.warning(f"Road GeoPackage not found: {road_path}. Skipping road exposure.")
        return {}
    
    logger.info(f"Found road asset: {road_path}")
    
    utm_crs = aoi.estimate_utm_crs()
    results = {}
    flood_types = ["coastal", "fluvial", "pluvial", "comb"]
    
    for ft in flood_types:
        if not menu.get(f"flood_{ft}", False):
            logger.debug(f"Skipping flood type '{ft}' (disabled in menu)")
            continue
        
        logger.info(f"Processing flood type: {ft}")
        results[ft] = {}
        
        try:
            for year in flood_years:
                logger.debug(f"Processing year: {year}")
                
                if year <= 2020:
                    raster_name = f"{city_name}_{ft}_{year}_utm.tif"
                    raster_path = os.path.join(spatial_dir, raster_name)
                    
                    if not exists(raster_path):
                        logger.debug(f"Missing raster: {raster_path}")
                        continue
                    
                    logger.info(f"Computing exposure | type={ft}, year={year}")
                    
                    try:
                        stats = calculate_flood_road_stats(
                            output_dir, city_name, utm_crs, raster_name
                        )
                        conditional_assign(results[ft], year, stats)
                        if stats:
                            logger.debug(f"Road stats: {stats}")
                    except Exception as e:
                        logger.error(
                            f"Failed exposure calc | type={ft}, year={year}: {e}",
                            exc_info=False,
                        )
                
                else:
                    results[ft][year] = {}
                    
                    for ssp in flood_ssps:
                        raster_name = f"{city_name}_{ft}_{year}_ssp{ssp}.tif"
                        raster_path = os.path.join(spatial_dir, raster_name)
                        
                        if not exists(raster_path):
                            logger.debug(f"Missing raster: {raster_path}")
                            continue
                        
                        logger.info(
                            f"Computing exposure | type={ft}, year={year}, ssp={ssp}"
                        )
                        
                        try:
                            stats = calculate_flood_road_stats(
                                output_dir, city_name, utm_crs, raster_name
                            )
                            conditional_assign(results[ft][year], ssp, stats)
                            if stats:
                                logger.debug(f"Road stats SSP{ssp}: {stats}")
                        except Exception as e:
                            logger.error(
                                f"Failed exposure calc | type={ft}, year={year}, ssp={ssp}: {e}",
                                exc_info=False,
                            )
        
        except Exception as e:
            logger.error(
                f"Unexpected failure in flood type '{ft}': {e}",
                exc_info=True,
            )
    
    logger.info("Completed road flood exposure computation")
    logger.info(f"Road results keys: {list(results.keys())}")
    
    # Save results to CSV
    try:
        tabular_dir = os.path.join(output_dir, "tabular")
        os.makedirs(tabular_dir, exist_ok=True)
        
        rows = []
        
        for ft in results:
            logger.debug(f"Processing results for flood type: {ft}")
            for year in results[ft]:
                year_data = results[ft][year]
                logger.debug(f"Year {year} data type: {type(year_data)}, value: {year_data}")
                
                if year_data is None:
                    logger.debug(f"Skipping None data for {ft} {year}")
                    continue
                
                # Check if dict (future years with SSPs) or tuple (historical)
                if isinstance(year_data, dict):
                    # Future years with SSPs
                    logger.debug(f"Processing future years with SSPs")
                    for ssp in year_data:
                        if year_data[ssp]:
                            total_length, flooded_length, pct = year_data[ssp]
                            rows.append([
                                f'{ft}_{year}_ssp{ssp}',
                                total_length, flooded_length, pct
                            ])
                else:
                    # Historical years (tuple)
                    logger.debug(f"Processing historical year as tuple")
                    if year_data:
                        total_length, flooded_length, pct = year_data
                        rows.append([
                            f'{ft}_{year}',
                            total_length, flooded_length, pct
                        ])
        
        logger.info(f"Total road rows to save: {len(rows)}")
        
        if rows:
            import pandas as pd
            df = pd.DataFrame(rows, columns=[
                'type', 'total_major_road_meter',
                'meter_in_flood_zones', 'percentage_in_flood_zones'
            ])
            csv_path = os.path.join(tabular_dir, f"{city_name}_flood_road.csv")
            df.to_csv(csv_path, index=False)
            logger.info(f"Saved road exposure stats to: {csv_path}")
        else:
            logger.warning("No road exposure data to save (rows list is empty)")
    
    except Exception as e:
        logger.error(f"Failed to save road CSV: {e}", exc_info=True)
    
    return results