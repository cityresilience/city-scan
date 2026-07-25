
from __future__ import annotations

from ucra.context import PipelineContext


def run(ctx: PipelineContext) -> None:
    import ee
    import geemap
    import tempfile
    import shutil
    import numpy as np
    import pandas as pd
    import geopandas as gpd
    import rasterio
    import rasterio.mask
    from pathlib import Path

    project_dir = ctx.project_dir
    country = ctx.country
    aoi_folder = ctx.aoi_folder
    output_folder = ctx.output_folder
    cities = ctx.cities

    def run_lst_for_all_cities_and_stats(cities, first_year=2013, last_year=2023):
        """
        Landsat-based LST exports and stats/avg_temp.csv for the existing heat.R script.
        """

        def mask_l8_sr(image):
            qa_mask = image.select('QA_PIXEL').bitwiseAnd(int('11111', 2)).eq(0)
            saturation_mask = image.select('QA_RADSAT').eq(0)
            thermal_band = image.select('ST_B10').multiply(0.00341802).add(149.0)
            return image.addBands(thermal_band, None, True).updateMask(qa_mask).updateMask(saturation_mask)

        def seasonal_filter(landsat, comp_name):
            if comp_name == "summer":
                seasonal_imgs = []
                for yr in range(first_year, last_year + 1):
                    img = landsat.filterDate(f"{yr}-05-01", f"{yr}-09-30").mean()
                    seasonal_imgs.append(img)
                return ee.ImageCollection(seasonal_imgs).mean()

            if comp_name == "winter":
                seasonal_imgs = []
                for yr in range(first_year, last_year):
                    img = landsat.filterDate(f"{yr}-11-01", f"{yr+1}-02-28").mean()
                    seasonal_imgs.append(img)
                return ee.ImageCollection(seasonal_imgs).mean()

            raise ValueError(f"Unknown composite: {comp_name}")

        def export_with_fallback_scale(img, aoi, tmp_tif, scales=(30, 60, 90)):
            last_error = None
            for scale in scales:
                try:
                    print(f"Trying LST export at {scale} m: {tmp_tif.name}")
                    geemap.ee_export_image(
                        img,
                        filename=str(tmp_tif),
                        scale=scale,
                        region=aoi,
                        file_per_band=False
                    )
                    if tmp_tif.exists() and tmp_tif.stat().st_size > 0:
                        return scale
                except Exception as e:
                    last_error = e
                    print(f"LST export failed at {scale} m: {e}")

            raise RuntimeError(f"All export scales failed for {tmp_tif.name}. Last error: {last_error}")

        def export_city_lst(city):
            city_lower = city.replace(" ", "_").lower()
            shp_name = city + "_AOI.shp"
            shp_path = Path(city) / aoi_folder / shp_name

            shp = gpd.read_file(shp_path).to_crs(epsg=4326)
            features = [geom.__geo_interface__ for geom in shp.geometry]
            geom_json = shp.geometry.iloc[0].__geo_interface__
            aoi = ee.Geometry(geom_json)

            landsat = (
                ee.ImageCollection("LANDSAT/LC08/C02/T1_L2")
                .filterBounds(aoi)
                .filterDate(f"{first_year}-01-01", f"{last_year}-12-31")
                .map(mask_l8_sr)
                .select("ST_B10")
            )

            results = {}

            for comp in ("summer", "winter"):
                img = seasonal_filter(landsat, comp).subtract(273.15).rename("lst")
                out_file = Path(city) / output_folder / f"{city_lower}_lst_{comp}.tif"

                tmp_dir = Path(tempfile.mkdtemp(prefix=f"lst_{city_lower}_{comp}_"))
                try:
                    tmp_tif = tmp_dir / f"{city_lower}_lst_{comp}.tif"

                    used_scale = export_with_fallback_scale(img, aoi, tmp_tif, scales=(30, 60, 90))
                    print(f"Used {used_scale} m export scale for {city} {comp}")

                    with rasterio.open(tmp_tif) as src:
                        out_image, out_transform = rasterio.mask.mask(
                            src,
                            features,
                            crop=True,
                            all_touched=True,
                            nodata=np.nan
                        )
                        out_meta = src.meta.copy()

                    out_meta.update({
                        "driver": "GTiff",
                        "height": out_image.shape[1],
                        "width": out_image.shape[2],
                        "transform": out_transform,
                        "compress": "LZW",
                        "tiled": True,
                        "BIGTIFF": "IF_SAFER",
                    })

                    with rasterio.open(out_file, "w", **out_meta) as dest:
                        dest.write(out_image)

                    arr = out_image[0].astype(float)
                    arr[arr <= -9990] = np.nan
                    mean_val = float(np.nanmean(arr)) if np.isfinite(np.nanmean(arr)) else np.nan
                    results[comp] = mean_val

                    print(f"Wrote {out_file}")

                finally:
                    shutil.rmtree(tmp_dir, ignore_errors=True)

            return {
                "city": city,
                "avg": results.get("summer", np.nan),
                "winter_avg": results.get("winter", np.nan)
            }

        rows = []
        for city in cities:
            try:
                rows.append(export_city_lst(city))
            except Exception as e:
                print(f"LST failed for {city}: {e}")

        stats_dir = Path("stats")
        stats_dir.mkdir(exist_ok=True)

        df = pd.DataFrame(rows)
        if not df.empty:
            df[["city", "avg"]].to_csv(stats_dir / "avg_temp.csv", index=False)
            df.to_csv(stats_dir / "avg_temp_extended.csv", index=False)
            print(f"Wrote {stats_dir / 'avg_temp.csv'}")
            print(f"Wrote {stats_dir / 'avg_temp_extended.csv'}")
        else:
            print("No LST stats were produced.")

    run_lst_for_all_cities_and_stats(cities, first_year=2013, last_year=2023)
