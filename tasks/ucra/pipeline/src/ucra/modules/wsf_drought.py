from __future__ import annotations

from pathlib import Path

from ucra.context import PipelineContext


def run(ctx: PipelineContext) -> None:
    import math
    import os
    import re
    import time
    import zipfile

    import geopandas as gpd
    import numpy as np
    import pandas as pd
    import rasterio
    import rasterio.mask
    import requests
    from rasterio.features import shapes
    from rasterio.merge import merge
    from rasterio.warp import Resampling, calculate_default_transform, reproject

    aoi_folder = ctx.aoi_folder
    output_folder = ctx.output_folder
    cities = ctx.cities
    centroids = ctx.centroids
    epsg_dict = ctx.epsg_dict
    country = ctx.country

    drought_output_dir = Path("output/drought")
    drought_output_dir.mkdir(parents=True, exist_ok=True)

    def city_slug(city: str) -> str:
        return city.replace(" ", "_").lower()

    def log(message: str) -> None:
        print(message)

    def download_wsf(city: str, wsf_type: str, max_retries: int = 4, timeout: tuple[int, int] = (20, 120)) -> None:
        data_folder = Path("data") / f"WSF{wsf_type}"
        data_folder.mkdir(parents=True, exist_ok=True)

        shp_name = city + "_AOI.shp"
        shp = gpd.read_file(Path(city) / aoi_folder / shp_name)
        shp_bounds = shp.bounds

        session = requests.Session()
        adapter = requests.adapters.HTTPAdapter(max_retries=0)
        session.mount("http://", adapter)
        session.mount("https://", adapter)

        def build_url(file_name: str) -> str:
            if wsf_type == "evolution":
                return f"https://download.geoservice.dlr.de/WSF_EVO/files/{file_name}/{file_name}.tif"
            if wsf_type == "2019":
                return f"https://download.geoservice.dlr.de/WSF2019/files/{file_name}.tif"
            raise ValueError(f"Unsupported wsf_type: {wsf_type}")

        for i in range(len(shp_bounds)):
            minx = math.floor(shp_bounds.minx[i] - shp_bounds.minx[i] % 2)
            maxx = math.ceil(shp_bounds.maxx[i])
            miny = math.floor(shp_bounds.miny[i] - shp_bounds.miny[i] % 2)
            maxy = math.ceil(shp_bounds.maxy[i])

            for x in range(minx, maxx, 2):
                for y in range(miny, maxy, 2):
                    file_name = f"WSF{wsf_type}_v1_{x}_{y}"
                    out_path = data_folder / f"{file_name}.tif"
                    tmp_path = data_folder / f"{file_name}.part"
                    url = build_url(file_name)

                    if out_path.exists() and out_path.stat().st_size > 0:
                        continue

                    success = False
                    for attempt in range(1, max_retries + 1):
                        try:
                            if tmp_path.exists():
                                tmp_path.unlink()

                            log(f"Downloading {file_name} ({attempt}/{max_retries})")
                            with session.get(url, stream=True, timeout=timeout) as r:
                                r.raise_for_status()
                                with open(tmp_path, "wb") as f:
                                    for chunk in r.iter_content(chunk_size=1024 * 1024):
                                        if chunk:
                                            f.write(chunk)

                            if tmp_path.exists() and tmp_path.stat().st_size > 0:
                                tmp_path.replace(out_path)
                                success = True
                                break
                        except Exception as e:
                            log(f"WSF download failed for {file_name} on attempt {attempt}: {e}")
                            time.sleep(2 * attempt)

                    if not success:
                        log(f"Skipping {file_name} after {max_retries} failed attempts")
                        if tmp_path.exists():
                            try:
                                tmp_path.unlink()
                            except Exception:
                                pass

    wsf_types = ["evolution", "2019"]
    for wsf_type in wsf_types:
        for city in cities:
            download_wsf(city, wsf_type)

    def merge_the_tiles() -> None:
        for wsf_type in wsf_types:
            data_folder = Path("data") / f"WSF{wsf_type}"
            mosaic_file = data_folder / f"WSF_mosaic{wsf_type}.tif"

            if mosaic_file.exists():
                continue

            raster_to_mosaic = []
            try:
                for p in sorted(data_folder.iterdir()):
                    if p.suffix.lower() != ".tif":
                        continue
                    if p.name.startswith("WSF_mosaic"):
                        continue
                    raster_to_mosaic.append(rasterio.open(p))

                if not raster_to_mosaic:
                    log(f"No WSF tiles found to mosaic for {wsf_type}")
                    continue

                mosaic, output = merge(raster_to_mosaic)
                output_meta = raster_to_mosaic[0].meta.copy()
                output_meta.update(
                    {
                        "driver": "GTiff",
                        "height": mosaic.shape[1],
                        "width": mosaic.shape[2],
                        "transform": output,
                        "compress": "LZW",
                        "tiled": True,
                        "BIGTIFF": "IF_SAFER",
                    }
                )

                with rasterio.open(mosaic_file, "w", **output_meta) as dst:
                    dst.write(mosaic)

                log(f"Wrote WSF mosaic: {mosaic_file}")
            except MemoryError:
                log(f"MemoryError while mosaicking WSF {wsf_type}. Consider mosaicking externally.")
            finally:
                for src in raster_to_mosaic:
                    try:
                        src.close()
                    except Exception:
                        pass

    def clipdata_wsf(city: str, wsf_type: str) -> None:
        data_folder = Path("data") / f"WSF{wsf_type}"
        city_lower = city_slug(city)
        shp_name = city + "_AOI.shp"
        shp = gpd.read_file(Path(city) / aoi_folder / shp_name)
        features = shp.geometry

        input_raster = data_folder / f"WSF_mosaic{wsf_type}.tif"
        if not input_raster.exists():
            log(f"Missing WSF mosaic: {input_raster}")
            return

        with rasterio.open(input_raster) as src:
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

        output_4326_raster_clipped = f"{city_lower}_WSF{wsf_type}_4326.tif"
        out_path = Path(city) / output_folder / output_4326_raster_clipped
        with rasterio.open(out_path, "w", **out_meta) as dest:
            dest.write(out_image)

    def utm_wsf(city: str, wsf_type: str) -> None:
        city_lower = city_slug(city)
        crs = epsg_dict.get(city)

        in_path = Path(city) / output_folder / f"{city_lower}_WSF{wsf_type}_4326.tif"
        out_path = Path(city) / output_folder / f"{city_lower}_WSF{wsf_type}_utm.tif"
        if not in_path.exists():
            log(f"Missing clipped WSF raster: {in_path}")
            return

        with rasterio.open(in_path) as src:
            dst_crs = f"EPSG:{crs}"
            transform, width, height = calculate_default_transform(src.crs, dst_crs, src.width, src.height, *src.bounds)
            kwargs = src.meta.copy()
            kwargs.update(
                {
                    "crs": dst_crs,
                    "transform": transform,
                    "width": width,
                    "height": height,
                    "compress": "LZW",
                    "tiled": True,
                    "BIGTIFF": "IF_SAFER",
                }
            )

            with rasterio.open(out_path, "w", **kwargs) as dst:
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

        if wsf_type == "evolution":
            with rasterio.open(out_path) as src:
                out_image = src.read()
                pixel_size_x, pixel_size_y = src.res

            year_dict: dict[int, float] = {}
            for year in range(1985, 2016):
                area = np.count_nonzero(out_image == year) * pixel_size_x * pixel_size_y / 1_000_000
                if year == 1985:
                    year_dict[year] = area
                else:
                    year_dict[year] = area + year_dict[year - 1]

            stats_path = Path(city) / output_folder / f"{city_lower}_built_up_stats.csv"
            with open(stats_path, "w") as f:
                f.write("year,cumulative sq km\n")
                for key, value in year_dict.items():
                    f.write(f"{key},{value}\n")

    def reclass_wsf(city: str, wsf_type: str = "evolution") -> None:
        city_lower = city_slug(city)
        in_path = Path(city) / output_folder / f"{city_lower}_WSF{wsf_type}_4326.tif"
        if not in_path.exists():
            log(f"Missing clipped WSF raster for reclass: {in_path}")
            return

        with rasterio.open(in_path) as src:
            out_image = src.read()
            out_meta = src.meta.copy()

        out_image[0][out_image[0] < 1985] = 0
        out_image[0][(out_image[0] <= 2015) & (out_image[0] >= 2006)] = 4
        out_image[0][(out_image[0] < 2006) & (out_image[0] >= 1996)] = 3
        out_image[0][(out_image[0] < 1996) & (out_image[0] >= 1986)] = 2
        out_image[0][out_image[0] == 1985] = 1

        out_file = f"{city_lower}_WSF{wsf_type}_reclass.tif"
        with rasterio.open(Path(city) / output_folder / out_file, "w", **out_meta) as dest:
            dest.write(out_image)

    def polygonize_wsf(city: str, wsf_type: str = "2019"):
        city_lower = city_slug(city)
        in_path = Path(city) / output_folder / f"{city_lower}_WSF{wsf_type}_4326.tif"
        if not in_path.exists():
            log(f"Missing clipped WSF raster for polygonize: {in_path}")
            return None

        with rasterio.open(in_path) as src:
            image = src.read(1)
            results = (
                {"properties": {"raster_val": v}, "geometry": s}
                for _, (s, v) in enumerate(shapes(image, mask=None, transform=src.transform))
            )
            geoms = list(results)
            gdf_polygonized_raster = gpd.GeoDataFrame.from_features(geoms)
            gdf_polygonized_raster = gdf_polygonized_raster[gdf_polygonized_raster.raster_val != 0]
            return gdf_polygonized_raster

    def clip_and_reclass() -> None:
        merge_the_tiles()
        for wsf_type in wsf_types:
            for city in cities:
                clipdata_wsf(city, wsf_type)
                if wsf_type == "evolution":
                    utm_wsf(city, wsf_type)
                    reclass_wsf(city)
                if wsf_type == "2019":
                    polygonize_wsf(city)

    clip_and_reclass()

    def build_slr_tabulate_csv_from_raster(city: str, slr_raster: Path) -> None:
        city_lower = city_slug(city)
        wsf_raster = Path(city) / "data" / f"{city_lower}_WSFevolution_utm.tif"
        if not wsf_raster.exists():
            log(f"Missing WSF evolution raster: {wsf_raster}")
            return

        with rasterio.open(slr_raster) as slr_src:
            slr_arr = slr_src.read(1)
            slr_nodata = slr_src.nodata
            slr_transform = slr_src.transform
            slr_crs = slr_src.crs
            slr_shape = slr_arr.shape
            cell_area = abs(slr_src.res[0] * slr_src.res[1])

        with rasterio.open(wsf_raster) as wsf_src:
            wsf_arr = np.empty(slr_shape, dtype=np.float32)
            reproject(
                source=rasterio.band(wsf_src, 1),
                destination=wsf_arr,
                src_transform=wsf_src.transform,
                src_crs=wsf_src.crs,
                dst_transform=slr_transform,
                dst_crs=slr_crs,
                dst_nodata=np.nan,
                resampling=Resampling.nearest,
            )

        slr_mask = np.ones(slr_arr.shape, dtype=bool)
        if slr_nodata is not None:
            slr_mask &= slr_arr != slr_nodata

        valid_mask = slr_mask & ~np.isnan(wsf_arr)
        years_range = list(range(1985, 2016))
        wsf_years = np.round(wsf_arr).astype(float)
        valid_mask &= np.isin(wsf_years, years_range)

        if valid_mask.sum() == 0:
            log(f"No overlapping valid SLR/WSF cells for {city} {slr_raster.name}")
            return

        slr_values = sorted(np.unique(slr_arr[valid_mask]).tolist())
        rows = []
        for slr_value in slr_values:
            row_mask = valid_mask & (slr_arr == slr_value)
            row = {"OBJECTID": len(rows) + 1, "VALUE": int(slr_value), "COUNT": int(row_mask.sum())}
            for y in years_range:
                row[f"VALUE_{y}"] = float(((row_mask) & (wsf_years == y)).sum() * cell_area)
            rows.append(row)

        out_df = pd.DataFrame(rows)
        out_csv = slr_raster.with_suffix(".csv")
        out_df.to_csv(out_csv, index=False)
        log(f"Wrote SLR CSV: {out_csv}")

    slr_pattern = re.compile(r".*_slr(?:_RL10)?_\d{4}_ssp\d+\.tif$")
    for city in cities:
        city_data_dir = Path(city) / "data"
        for slr_raster in sorted(city_data_dir.glob("*_slr*.tif")):
            if slr_pattern.match(slr_raster.name):
                build_slr_tabulate_csv_from_raster(city, slr_raster)

    data_folder = Path("data/drought")

    def unzip_files(data_folder: Path) -> None:
        extension = ".zip"
        os.chdir(data_folder)
        for item in os.listdir(data_folder):
            if item.endswith(extension):
                file_name = os.path.abspath(item)
                zip_ref = zipfile.ZipFile(file_name)
                zip_ref.extractall(data_folder)
                zip_ref.close()
                os.remove(file_name)

    country_shp_path = Path("shapefile") / (country.replace(" ", "_").lower() + ".shp")
    shp = gpd.read_file(country_shp_path)
    shp = shp.to_crs(3857)
    shp["geometry"] = shp.buffer(5000)
    shp = shp.to_crs(4326)
    features = shp.geometry

    raster_list = {"twsan": "m"}
    month_list = ["01", "02", "03", "04", "05", "06", "07", "08", "09", "10", "11", "12"]

    def clip_drought(folder: Path, raster_prefix: str, raster_suffix: str, year: str, date: str) -> None:
        try:
            input_raster = folder / f"{raster_prefix}_m_wld_{year}{date}01_{raster_suffix}.tif"
            if not input_raster.exists():
                return

            with rasterio.open(input_raster) as src:
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
            out_raster = drought_output_dir / f"{raster_prefix}_{year}{date}.tif"
            with rasterio.open(out_raster, "w", **out_meta) as dest:
                dest.write(out_image)
        except Exception as e:
            log(f"clip_drought failed for {raster_prefix}_{year}{date}: {e}")

    for raster in raster_list.keys():
        for year in range(2011, 2021):
            for month in month_list:
                clip_drought(data_folder, raster, raster_list.get(raster), str(year), str(month))

    def sample_drought_raster_to_csv(raster_path: Path, centroids_path: Path, out_csv: Path, value_col: str) -> None:
        centroids_gdf = gpd.read_file(centroids_path).to_crs(epsg=4326).copy()

        if centroids_gdf.empty:
            raise ValueError(f"Centroids shapefile is empty: {centroids_path}")
        if "city" not in centroids_gdf.columns:
            raise ValueError("Centroids shapefile must contain a 'city' column.")
        if "centroids" not in centroids_gdf.columns:
            centroids_gdf["centroids"] = range(len(centroids_gdf))
        if "OID_" not in centroids_gdf.columns:
            centroids_gdf["OID_"] = range(len(centroids_gdf))

        coords = [(geom.x, geom.y) for geom in centroids_gdf.geometry]

        with rasterio.open(raster_path) as src:
            nodata = src.nodata
            samples = []
            for val in src.sample(coords):
                if len(val) == 0:
                    samples.append(np.nan)
                    continue
                v = val[0]
                if nodata is not None and v == nodata:
                    v = np.nan
                samples.append(v)

        out_df = centroids_gdf[["OID_", "city", "centroids"]].copy()
        out_df[value_col] = samples
        out_csv.parent.mkdir(parents=True, exist_ok=True)
        out_df.to_csv(out_csv, index=False)
        log(f"Wrote drought CSV: {out_csv}")

    centroids_path = Path("shapefile") / "centroids.shp"
    for raster in raster_list.keys():
        for year in range(2011, 2021):
            for month in month_list:
                raster_file = drought_output_dir / f"{raster}_{year}{month}.tif"
                out_csv = drought_output_dir / f"{raster}_{year}{month}.csv"
                value_col = f"{raster}_{year}{month}01"
                if raster_file.exists():
                    try:
                        sample_drought_raster_to_csv(
                            raster_path=raster_file,
                            centroids_path=centroids_path,
                            out_csv=out_csv,
                            value_col=value_col,
                        )
                    except Exception as e:
                        log(f"Sampling failed for {raster_file}: {e}")
                else:
                    log(f"Missing drought raster: {raster_file}")
