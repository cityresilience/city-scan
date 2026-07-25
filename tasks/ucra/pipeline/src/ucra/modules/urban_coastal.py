from __future__ import annotations

from pathlib import Path

from ucra.context import PipelineContext


def run(ctx: PipelineContext) -> None:
    import math
    import os
    from os.path import exists
    from shutil import copyfile

    import fiona
    import geopandas as gpd
    import numpy as np
    import pandas as pd
    import rasterio
    import rasterio.mask
    import xarray as xr
    import rioxarray  # noqa: F401
    from rasterio.merge import merge
    from rasterio.warp import Resampling, calculate_default_transform, reproject

    country = ctx.country
    crp_dir = ctx.crp_dir
    aoi_folder = ctx.aoi_folder
    output_folder = ctx.output_folder
    cities = list(pd.read_csv("centroids.csv").city)
    centroids = pd.read_csv("centroids.csv")
    epsg_dict = dict(zip(centroids.city, centroids.utm))

    # Urban land and GDP
    int_output_folder = Path("output/urbanland")
    data_folder = crp_dir.joinpath("FCS/data/urbanland")
    year_list = [2050, 2080]
    ssp_list = [1, 2, 3]
    int_output_folder.mkdir(parents=True, exist_ok=True)

    def reproj(input_folder, input_raster):
        filename = input_raster + ".tif"
        outfile = input_raster + "_4326.tif"
        with rasterio.open(input_folder / filename) as src:
            dst_crs = "EPSG:4326"
            transform, width, height = calculate_default_transform(
                src.crs, dst_crs, src.width, src.height, *src.bounds
            )
            kwargs = src.meta.copy()
            kwargs.update({"crs": dst_crs, "transform": transform, "width": width, "height": height})

            with rasterio.open(input_folder / outfile, "w", **kwargs) as dst:
                for i in range(1, src.count + 1):
                    reproject(
                        source=rasterio.band(src, i),
                        destination=rasterio.band(dst, i),
                        src_transform=src.transform,
                        src_crs=src.crs,
                        dst_transform=transform,
                        dst_crs=dst_crs,
                        resampling=Resampling.nearest,
                    )

    def clipdata(city, input_folder, input_raster, section_keyword):
        city_lower = city.lower()
        file = Path(city) / aoi_folder / f"{city_lower}_AOI.shp"

        with fiona.open(file, "r") as shapefile:
            features = [feature["geometry"] for feature in shapefile]
            outfile = input_raster + "_4326.tif"
            with rasterio.open(input_folder / outfile) as src:
                out_image, out_transform = rasterio.mask.mask(src, features, crop=True, all_touched=True)
                out_meta = src.meta.copy()

            out_meta.update(
                {
                    "driver": "GTiff",
                    "height": out_image.shape[1],
                    "width": out_image.shape[2],
                    "transform": out_transform,
                    "nodata": 0,
                }
            )

            if np.nansum(out_image) != 0:
                output_file = city_lower + f"_{section_keyword}.tif"
                with rasterio.open(Path(city) / output_folder / output_file, "w", **out_meta) as dest:
                    dest.write(out_image)
                    print(f"Wrote {output_file}")

    input_folder = Path("data/GDP")
    input_raster = "GDP_PPP_2015"
    reproj(input_folder, input_raster)
    for city in cities:
        clipdata(city, input_folder, input_raster, "gdp")

    def clip_builtup_rasters(shp, data_folder, int_output_folder):
        features = [geom.__geo_interface__ for geom in shp.geometry]
        for ssp in ssp_list:
            for year in year_list:
                out_file = f"ssp{ssp}_{year}_{country.replace(' ', '_').lower()}.tif"
                if not exists(int_output_folder / out_file):
                    with rasterio.open(
                        data_folder / f"ssp{ssp}-geotiff" / f"ssp{ssp}_{year}.tif"
                    ) as src:
                        out_image, out_transform = rasterio.mask.mask(src, features, crop=True, all_touched=True)
                        out_meta = src.meta.copy()

                    out_meta.update(
                        {
                            "driver": "GTiff",
                            "height": out_image.shape[1],
                            "width": out_image.shape[2],
                            "transform": out_transform,
                            "compress": "LZW",
                            "tiled": True,
                            "BIGTIFF": "IF_SAFER",
                        }
                    )

                    with rasterio.open(int_output_folder / out_file, "w", **out_meta) as dest:
                        dest.write(out_image)

    def clipdata_bu_proj(ssp, year, city):
        city_lower = city.lower()
        crs = epsg_dict[city]
        shp_name = city + "_AOI.shp"
        shp = gpd.read_file(Path(city) / aoi_folder / shp_name).to_crs(epsg=crs)
        features = shp.geometry

        projected_raster = f"ssp{ssp}_{year}_{country.replace(' ', '_').lower()}_{crs}.tif"
        unprojected_raster = f"ssp{ssp}_{year}_{country.replace(' ', '_').lower()}.tif"
        if not exists(int_output_folder / projected_raster):
            with rasterio.open(int_output_folder / unprojected_raster) as src:
                dst_crs = f"EPSG:{crs}"
                transform, width, height = calculate_default_transform(
                    src.crs, dst_crs, src.width, src.height, *src.bounds
                )
                kwargs = src.meta.copy()
                kwargs.update({
                    "crs": dst_crs,
                    "transform": transform,
                    "width": width,
                    "height": height,
                    "compress": "LZW",
                    "tiled": True,
                    "BIGTIFF": "IF_SAFER",
                })

                with rasterio.open(int_output_folder / projected_raster, "w", **kwargs) as dst:
                    for i in range(1, src.count + 1):
                        reproject(
                            source=rasterio.band(src, i),
                            destination=rasterio.band(dst, i),
                            src_transform=src.transform,
                            src_crs=src.crs,
                            dst_transform=transform,
                            dst_crs=dst_crs,
                            resampling=Resampling.nearest,
                        )

        with rasterio.open(int_output_folder / projected_raster) as src:
            out_image, out_transform = rasterio.mask.mask(src, features, crop=True, all_touched=True)
            out_meta = src.meta.copy()

        out_meta.update(
            {
                "driver": "GTiff",
                "height": out_image.shape[1],
                "width": out_image.shape[2],
                "transform": out_transform,
                "compress": "LZW",
                "tiled": True,
                "BIGTIFF": "IF_SAFER",
            }
        )

        out_file = f"{city_lower}_bu_ssp{ssp}_{year}.tif"
        with rasterio.open(Path(city) / output_folder / out_file, "w", **out_meta) as dest:
            dest.write(out_image)

    country_shp_path = Path("shapefile") / f"{country.replace(' ', '_').lower()}.shp"
    country_gdf = gpd.read_file(country_shp_path)
    if country_gdf.empty:
        raise ValueError(f"Country shapefile is empty: {country_shp_path}")
    country_gdf = country_gdf.to_crs(3857)
    country_gdf["geometry"] = country_gdf.buffer(2000)
    country_gdf = country_gdf.to_crs(4326)
    clip_builtup_rasters(country_gdf, data_folder, int_output_folder)
    for city in cities:
        for ssp in ssp_list:
            for year in year_list:
                clipdata_bu_proj(ssp, year, city)

    # SLR raster creation only
    data_folder = crp_dir.joinpath("FCS/data/climatecentral")
    int_output_folder = Path("output/SLR")
    int_output_folder.mkdir(parents=True, exist_ok=True)

    year_list = [2020, 2050, 2100]
    slr_list = ["", "_RL10"]
    ssp_plus_rcp = [245, 585]

    def smart_append(element, ls):
        if element not in ls:
            ls.append(element)

    def create_lat_lon_list(shp_bounds):
        lat_list = []
        for i in range(len(shp_bounds)):
            if math.floor(shp_bounds.miny[i]) >= 0:
                hemi = "N"
                for y in range(math.floor(shp_bounds.miny[i]), math.ceil(shp_bounds.maxy[i])):
                    smart_append(hemi + str(y).zfill(2), lat_list)
            elif math.ceil(shp_bounds.maxy[i]) >= 0:
                for y in range(0, math.ceil(shp_bounds.maxy[i])):
                    smart_append("N" + str(y).zfill(2), lat_list)
                for y in range(math.floor(shp_bounds.miny[i]), 0):
                    smart_append("S" + str(-y).zfill(2), lat_list)
            else:
                hemi = "S"
                for y in range(math.floor(shp_bounds.miny[i]), math.ceil(shp_bounds.maxy[i])):
                    smart_append(hemi + str(-y).zfill(2), lat_list)

        lon_list = []
        for i in range(len(shp_bounds)):
            if math.floor(shp_bounds.minx[i]) >= 0:
                hemi = "E"
                for x in range(math.floor(shp_bounds.minx[i]), math.ceil(shp_bounds.maxx[i])):
                    smart_append(hemi + str(x).zfill(3), lon_list)
            elif math.ceil(shp_bounds.maxx[i]) >= 0:
                for x in range(0, math.ceil(shp_bounds.maxx[i])):
                    smart_append("E" + str(x).zfill(3), lon_list)
                for x in range(math.floor(shp_bounds.minx[i]), 0):
                    smart_append("W" + str(-x).zfill(3), lon_list)
            else:
                hemi = "W"
                for x in range(math.floor(shp_bounds.minx[i]), math.ceil(shp_bounds.maxx[i])):
                    smart_append(hemi + str(-x).zfill(3), lon_list)

        return lat_list, lon_list

    def get_relevant_slr_tile_paths(data_folder, lat_list, lon_list, ssp_rcp, year, slr):
        tile_paths = []
        data_subfolder = f"AR6_ssp{ssp_rcp}_mediumconfidence_50.0_{year}{slr}"
        for lat in lat_list:
            for lon in lon_list:
                tile_path = data_folder / data_subfolder / f"{lat}{lon}.tif"
                if tile_path.exists():
                    tile_paths.append(tile_path)
        return tile_paths

    def build_slr_mosaic(data_folder, int_output_folder, lat_list, lon_list, ssp_rcp, year, slr):
        mosaic_file = int_output_folder / f"rcp{ssp_rcp}_50_{year}{slr}.tif"
        if mosaic_file.exists():
            return mosaic_file

        tile_paths = get_relevant_slr_tile_paths(data_folder, lat_list, lon_list, ssp_rcp, year, slr)
        if not tile_paths:
            print(f"No SLR tiles found for ssp{ssp_rcp}, year {year}, suffix '{slr}'")
            return None

        raster_handles = []
        try:
            for p in tile_paths:
                raster_handles.append(rasterio.open(p))

            mosaic, out_transform = merge(raster_handles)
            out_meta = raster_handles[0].meta.copy()
            out_meta.update(
                {
                    "driver": "GTiff",
                    "height": mosaic.shape[1],
                    "width": mosaic.shape[2],
                    "transform": out_transform,
                    "compress": "LZW",
                    "tiled": True,
                    "BIGTIFF": "IF_SAFER",
                    "nodata": 0,
                }
            )

            with rasterio.open(mosaic_file, "w", **out_meta) as dst:
                dst.write(mosaic)

            print(f"Wrote SLR mosaic: {mosaic_file}")
            return mosaic_file
        finally:
            for src in raster_handles:
                src.close()

    def clipdata_slr(slr, year, city, ssp_rcp, reproject_to_utm=True):
        city_lower = city.replace(" ", "_").lower()
        crs = epsg_dict[city]

        shp_name = city + "_AOI.shp"
        shp_4326 = gpd.read_file(Path(city) / aoi_folder / shp_name).to_crs(epsg=4326)
        features_4326 = [geom.__geo_interface__ for geom in shp_4326.geometry]

        mosaic_path = int_output_folder / f"rcp{ssp_rcp}_50_{year}{slr}.tif"
        if not mosaic_path.exists():
            print(f"Missing mosaic: {mosaic_path}")
            return

        try:
            with rasterio.open(mosaic_path) as src:
                clipped_image, clipped_transform = rasterio.mask.mask(
                    src, features_4326, crop=True, all_touched=True, nodata=0
                )
                clipped_meta = src.meta.copy()

            clipped_meta.update(
                {
                    "driver": "GTiff",
                    "height": clipped_image.shape[1],
                    "width": clipped_image.shape[2],
                    "transform": clipped_transform,
                    "compress": "LZW",
                    "tiled": True,
                    "BIGTIFF": "IF_SAFER",
                    "nodata": 0,
                }
            )

            if np.nansum(clipped_image) == 0:
                return

            out_file = f"{city_lower}_slr{slr}_{year}_ssp{ssp_rcp}.tif"
            out_path = Path(city) / output_folder / out_file

            if reproject_to_utm:
                dst_crs = f"EPSG:{crs}"
                bounds = rasterio.transform.array_bounds(
                    clipped_meta["height"], clipped_meta["width"], clipped_transform
                )
                dst_transform, dst_width, dst_height = calculate_default_transform(
                    clipped_meta["crs"],
                    dst_crs,
                    clipped_meta["width"],
                    clipped_meta["height"],
                    *bounds,
                )

                dst_meta = clipped_meta.copy()
                dst_meta.update(
                    {
                        "crs": dst_crs,
                        "transform": dst_transform,
                        "width": dst_width,
                        "height": dst_height,
                    }
                )

                with rasterio.open(out_path, "w", **dst_meta) as dst:
                    for band_idx in range(clipped_image.shape[0]):
                        reproject(
                            source=clipped_image[band_idx],
                            destination=rasterio.band(dst, band_idx + 1),
                            src_transform=clipped_transform,
                            src_crs=clipped_meta["crs"],
                            dst_transform=dst_transform,
                            dst_crs=dst_crs,
                            resampling=Resampling.nearest,
                            src_nodata=0,
                            dst_nodata=0,
                        )
            else:
                with rasterio.open(out_path, "w", **clipped_meta) as dst:
                    dst.write(clipped_image)

            print(f"Wrote city SLR raster: {out_path}")
        except ValueError:
            pass

    shp_bounds = gpd.read_file(Path("shapefile") / f"{country.replace(' ', '_').lower()}.shp").bounds
    lat_list, lon_list = create_lat_lon_list(shp_bounds)

    for ssp_rcp in ssp_plus_rcp:
        for year in year_list:
            for slr in slr_list:
                try:
                    build_slr_mosaic(
                        data_folder=data_folder,
                        int_output_folder=int_output_folder,
                        lat_list=lat_list,
                        lon_list=lon_list,
                        ssp_rcp=ssp_rcp,
                        year=year,
                        slr=slr,
                    )
                except Exception as e:
                    print(e)

    for city in cities:
        for slr in slr_list:
            for year in year_list:
                for ssp_rcp in ssp_plus_rcp:
                    try:
                        clipdata_slr(slr=slr, year=year, city=city, ssp_rcp=ssp_rcp, reproject_to_utm=True)
                    except Exception as e:
                        print(e)
