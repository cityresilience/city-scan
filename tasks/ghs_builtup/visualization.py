import os
import numpy as np
import matplotlib.pyplot as plt
import geopandas as gpd
import rasterio
import contextily as ctx

from core.py.log_module import setup_logger
logger = setup_logger(__name__)

# ----------------------------------------------------------
# HELPER: load clipped raster from output_dir if needed
# ----------------------------------------------------------
def _load_clipped_raster(city_name, output_dir, year):
    raster_path = os.path.join(output_dir, "spatial", f"{city_name}_ghs_built_E{year}.tif")

    if not os.path.exists(raster_path):
        logger.error(f"Raster not found for visualization: {raster_path}")
        return None, None

    with rasterio.open(raster_path) as src:
        arr = src.read()          # read ALL bands -> could return shape (1, H, W)
        meta = src.meta
    
    return arr, meta


# ----------------------------------------------------------
# 1. CHOROPLETH MAP (FIXED VERSION)
# ----------------------------------------------------------
def plot_rastermap(
    city_name: str,
    output_dir: str,
    year: int,
    figsize=(16, 16),
    cmap="magma",
):
    """
    Plot ghs_built map using raster clipped to the AOI.
    Includes basemap (CartoDB Positron No Labels).
    """

    logger.info("Generating map…")

    # ----------------------------------
    # Load raster if not provided
    # ----------------------------------
    
    clipped_image, clipped_meta = _load_clipped_raster(city_name, output_dir, year)
    if clipped_image is None:
        return

    # ----------------------------------
    # FIX: Squeeze raster → always 2D
    # ----------------------------------
    data = clipped_image.squeeze().astype(float)

    # Clean nodata
    data[data <= 0] = np.nan
    data[data > 10000] = np.nan

    # ----------------------------------
    # FIX: Compute raster bounds for correct placement on basemap
    # ----------------------------------
    transform = clipped_meta["transform"]
    height, width = data.shape

    x_min = transform[2]
    x_max = x_min + transform[0] * width
    y_max = transform[5]
    y_min = y_max + transform[4] * height  # Note: transform[4] is usually negative

    extent = [x_min, x_max, y_min, y_max]

    # ----------------------------------
    # Plot
    # ----------------------------------
    fig, ax = plt.subplots(figsize=figsize)

    raster_show = ax.imshow(
        data,
        cmap=cmap,
        extent=extent,
        origin="upper",
        interpolation="nearest", 
        zorder=10
    )

    # Add basemap if possible
    try:
        ctx.add_basemap(
            ax,
            crs=clipped_meta["crs"],
            source=ctx.providers.CartoDB.PositronNoLabels, 
            zorder=1
        )
    except Exception:
        logger.warning("Basemap failed to load; continuing without background.")

    # Colorbar
    cbar = fig.colorbar(raster_show, ax=ax, fraction=0.036, pad=0.04)
    cbar.set_label(f"Built Up Surface Distribution in {year}", rotation=90)

    ax.set_title(f"{city_name} – Built Up Surface - {year}")
    ax.axis("off")

    # Save
    img_dir = os.path.join(output_dir, "images")
    os.makedirs(img_dir, exist_ok=True)

    out_path = os.path.join(img_dir, f"{city_name}_ghs_built_E{year}_map.png")
    plt.savefig(out_path, dpi=200, bbox_inches="tight")
    plt.close()

    logger.info(f"Raster Plot saved to: {out_path}")

# ----------------------------------------------------------
# 2. HISTOGRAM
# ----------------------------------------------------------
def plot_histogram(
    city_name: str,
    output_dir: str,
    year: int,
    figsize=(16, 8),
    color="tab:red"
):
    """
    Plot histogram of raster values.
    """

    logger.info("Generating histogram…")

    # Load raster if not provided
    clipped_image, clipped_meta = _load_clipped_raster(city_name, output_dir, year)
    if clipped_image is None:
        return

    # Flatten raster values
    arr = clipped_image.astype(float).flatten()
    valid = arr[(arr > 0) & (arr <= 10000)]  # remove nodata and unrealistic values

    if len(valid) == 0:
        logger.error("No valid raster values for histogram.")
        return

    # Plot
    fig, ax = plt.subplots(figsize=figsize)

    ax.hist(valid, bins=50, color=color, alpha=0.9)
    ax.grid(True, linestyle="--", alpha=0.5)

    # Clean labels
    ax.set_xlabel("")
    ax.set_ylabel("")
    ax.set_title(f"{city_name} – {year} Built Up Surface Distribution Histogram")

    # Save
    img_dir = os.path.join(output_dir, "images")
    os.makedirs(img_dir, exist_ok=True)

    out_path = os.path.join(img_dir, f"{city_name}_ghs_built_E{year}_histogram.png")
    plt.savefig(out_path, dpi=200, bbox_inches="tight")
    plt.close()

    logger.info(f"Histogram saved to: {out_path}")


# ----------------------------------------------------------
# 3. RUN ALL VISUALIZATIONS
# ----------------------------------------------------------
def run_viz(
    city_name: str,
    output_dir: str,
    start_year: int = 1975,
    end_year: int = 2030,
    choropleth_kwargs=None,
    histogram_kwargs=None
):
    """
    Run all visualization functions for a given city.
    """

    logger.info("Running visualization suite…")

    choropleth_kwargs = choropleth_kwargs or {}
    histogram_kwargs = histogram_kwargs or {}

    years = range(start_year, end_year+5, 5)
    for year in years: 
        plot_rastermap(
            city_name=city_name,
            output_dir=output_dir,
            year=year,
            **choropleth_kwargs
        )

        plot_histogram(
            city_name=city_name,
            output_dir=output_dir,
            year=year,
            **histogram_kwargs
        )

    logger.info("All visualizations completed.")


if __name__ == "__main__":
    print("Run using run_viz() for a project workflow.")
