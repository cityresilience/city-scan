from __future__ import annotations

from pathlib import Path

from ucra.context import PipelineContext


def run(project_dir: str | Path, country: str) -> PipelineContext:
    import math
    import os
    import shutil

    import fiona
    import geopandas as gpd
    import matplotlib.pyplot as plt
    import pandas as pd
    from shapely.geometry import MultiPolygon, Polygon

    fiona.drvsupport.supported_drivers["kml"] = "rw"
    fiona.drvsupport.supported_drivers["KML"] = "rw"

    def create_folder(path: str | Path) -> None:
        Path(path).mkdir(parents=True, exist_ok=True)

    def convert_3d_to_2d(geometry):
        new_geo = []
        for geom in geometry:
            if getattr(geom, "has_z", False):
                if geom.geom_type == "Polygon":
                    lines = [xy[:2] for xy in list(geom.exterior.coords)]
                    new_geo.append(Polygon(lines))
                elif geom.geom_type == "MultiPolygon":
                    new_multi = []
                    for part in geom.geoms:
                        lines = [xy[:2] for xy in list(part.exterior.coords)]
                        new_multi.append(Polygon(lines))
                    new_geo.append(MultiPolygon(new_multi))
                else:
                    new_geo.append(geom)
            else:
                new_geo.append(geom)
        return new_geo

    def remove_files_from_data(remove_files):
        for root, _, files_list in os.walk(Path("data")):
            for file_name in files_list:
                if file_name in remove_files:
                    file_name_path = os.path.join(root, file_name)
                    print(f"removed {file_name_path}")
                    os.remove(file_name_path)

    def remove_dirs_from_data(remove_dirs):
        for root, dirs_list, _ in os.walk(Path("data")):
            for dir_name in dirs_list:
                if dir_name in remove_dirs:
                    dir_path = os.path.join(root, dir_name)
                    print(f"removed {dir_path}")
                    shutil.rmtree(dir_path)

    def plot_the_features(shp):
        plt.rc("font", weight="bold")
        crs = 3857
        fig = plt.figure(figsize=(12, 8))
        ax = fig.add_subplot(111)
        shp = shp.copy()
        shp["index"] = shp.index
        colours = ["red", "green", "blue", "cyan", "black"]
        for index, colour in zip(shp.index, colours):
            ax = shp[shp["index"] == index].to_crs(crs).plot(
                ax=ax,
                alpha=0.8,
                facecolor="none",
                edgecolor=colour,
                linewidth=3,
                legend=False,
            )
        ax.axis("off")

    project_dir = Path(project_dir).resolve()
    if not country:
        raise ValueError("country must be provided via config or CLI")

    os.chdir(project_dir)
    print(project_dir)

    crp_dir = project_dir.parent.parent
    aoi_folder = Path("data/AOI")
    output_folder = Path("data")

    create_folder("shapefile")

    cities: list[str] = []
    for root, _, files_list in os.walk(Path("shapefiles_received")):
        for file_name in files_list:
            if os.path.splitext(file_name)[-1] != ".shp":
                continue

            file_name_path = os.path.join(root, file_name)
            stem = os.path.splitext(file_name)[0]

            if (
                "centroid" in stem
                or country in stem
                or country.replace(" ", "_").lower() in stem
            ):
                continue

            city_name = stem.replace("_AOI", "")
            city_name = city_name.title().replace("_", " ")
            print(city_name, "---", stem)
            cities.append(city_name)

            shp_4326 = gpd.read_file(file_name_path).to_crs(epsg=4326)
            shp_4326.to_file(Path("shapefile") / f"{city_name.lower()}.shp")

    for folder in [
        "data",
        "shapefile",
        "output",
        "output/GEE",
        "output/drought",
        "plots",
        "stats",
        "stats/drought",
        "stats/CCKP",
        "stats/spei",
        "maps",
    ]:
        create_folder(folder)

    for city in cities:
        print(city)
        create_folder(Path(city))
        create_folder(Path(city) / "maps")
        create_folder(Path(city) / "data")
        create_folder(Path(city) / "data" / "AOI")
        create_folder(Path(city) / "stats")

    for city in cities:
        shp_path = Path("shapefile") / f"{city.lower()}.shp"
        shp_4326 = gpd.read_file(shp_path).to_crs(epsg=4326)
        try:
            geodf_2d = gpd.GeoDataFrame.from_file(shp_path).to_crs(epsg=4326)
            print(f"city {city} imported for removing z")
            new_geometry = convert_3d_to_2d(geodf_2d.geometry)
            if len(new_geometry) == len(geodf_2d):
                geodf_2d.geometry = new_geometry
                print(f"city {city} had a z dim. Now flattened")
            geodf_2d.to_file(shp_path, driver="ESRI Shapefile")
        except Exception as error:
            print(f"{city}---Exception error: {error}")
            shp_4326.to_file(shp_path)

    for city in cities:
        shp_4326 = gpd.read_file(Path("shapefile") / f"{city.lower()}.shp").to_crs(epsg=4326)
        shp_4326.to_file(Path(city) / "data/AOI" / f"{city}_AOI.shp")

    remove_files = [
        "urban-ssp2_nig_sum_4326.tif",
        "urban-ssp3_day_sum_4326.tif",
        "urban-ssp3_nig_sum_4326.tif",
        "urban-ssp2_nig_sum_4326.tif",
        "urban-ssp2_day_sum_4326.tif",
        "LS_RF_Median_1980_2018_COG_4326.tif",
    ]
    # NO-DELETE PROTECTION (project rule): upstream this deleted bulky source
    # datasets (WSF2019/WSFevolution dirs + reprojected *_4326.tif files) from
    # data/. Disabled so the user's raw data is preserved. The wsf_drought
    # module re-downloads WSF tiles per city, so keeping these is harmless.
    # remove_files_from_data(remove_files)
    # remove_dirs = ["WSFevolution", "WSF2019"]
    # remove_dirs_from_data(remove_dirs)
    _ = (remove_files, remove_files_from_data, remove_dirs_from_data)

    for city in cities:
        shp = gpd.read_file(Path(city) / "data/AOI" / f"{city}_AOI.shp")
        print(city)
        plot_the_features(shp)

    with open("centroids.csv", "w", encoding="utf-8") as f:
        f.write("city,x,y,utm\n")
        for city in cities:
            gdf_city = gpd.read_file(Path(city) / "data/AOI" / f"{city}_AOI.shp").to_crs(3857)
            centroid_3857 = gdf_city.geometry.centroid
            centroid_4326 = gpd.GeoSeries(centroid_3857, crs=3857).to_crs(4326)
            x = centroid_4326.x.iloc[0]
            y = centroid_4326.y.iloc[0]
            utm = 32600 + math.ceil((x + 180) / 6)
            f.write(f"{city},{x},{y},{utm}\n")

    all_countries = gpd.read_file(Path("data") / "wb_countries_admin0_10m" / "WB_countries_Admin0_10m.shp")
    country_shp = all_countries[
        all_countries["NAME_EN"].astype(str).str.strip().str.lower() == str(country).strip().lower()
    ]
    if country_shp.empty:
        raise ValueError(f"No country match found in WB_countries_Admin0_10m.shp for country='{country}'.")
    country_shp.to_file(Path("shapefile") / f"{country.replace(' ', '_').lower()}.shp")

    centroids = pd.read_csv("centroids.csv")
    gdf = gpd.GeoDataFrame(centroids, geometry=gpd.points_from_xy(centroids.x, centroids.y))
    gdf = gdf.set_crs("EPSG:4326", allow_override=True)
    gdf.to_file(Path("shapefile") / "centroids.shp")
    epsg_dict = dict(zip(centroids.city, centroids.utm))

    return PipelineContext(
        project_dir=project_dir,
        country=country,
        crp_dir=crp_dir,
        aoi_folder=aoi_folder,
        output_folder=output_folder,
        cities=cities,
        centroids=centroids,
        epsg_dict=epsg_dict,
    )
