import os
import pandas as pd
import matplotlib.pyplot as plt
import plotly.express as px
import squarify
import yaml
import numpy as np
import geopandas as gpd
import rasterio
import contextily as ctx
from matplotlib.colors import ListedColormap, BoundaryNorm

from core.py.log_module import setup_logger
logger = setup_logger(__name__)

from core.py.log_module import setup_logger

logger = setup_logger(__name__)


def render_slope_treemap_png(
        city_name: str,
        output_dir: str,
        render_dir: str
    ):
    """
    Render static PNG treemap from enriched slope histogram.
    """

    city_name = city_name.lower()

    logger.info("Rendering static slope treemap…")

    hist_path = os.path.join(output_dir, "tabular", f"{city_name}_slope_histogram.csv")

    if not os.path.exists(hist_path):
        logger.error(f"Histogram not found: {hist_path}")
        return None

    slope = pd.read_csv(hist_path)

    required_cols = {"bin", "percent", "UpperRange"}
    if not required_cols.issubset(slope.columns):
        logger.error("Histogram CSV is not enriched. Run compute_slope_histogram(enrich=True).")
        return None

    os.makedirs(render_dir, exist_ok=True)

    max_upper_range = slope["UpperRange"].max()

    slope_colors = {
        "0-2": "#ffffd4",
        "2-5": "#fed98e",
        "5-10": "#fe9929",
        "10-20": "#d95f0e",
        f"20-{int(max_upper_range)}": "#993404"
    }
    render_png_dir = os.path.join(render_dir, "plots", "html")
    os.makedirs(render_png_dir, exist_ok=True)
    png_path = os.path.join(render_png_dir, f"{city_name}_slope_treemap.png")

    plt.figure(figsize=(12, 8))
    squarify.plot(
        sizes=slope["percent"],
        label=slope["bin"],
        color=[slope_colors.get(b, "#999999") for b in slope["bin"]],
        alpha=0.8,
        pad=True
    )

    plt.title(f"Slope Distribution in {city_name}")
    plt.axis("off")
    plt.tight_layout()
    plt.savefig(png_path, bbox_inches="tight")
    plt.close()

    logger.info(f"Static treemap saved: {png_path}")

    return png_path

def render_slope_treemap_html(
        city_name: str,
        output_dir: str,
        render_dir: str,
        font_dict: dict
    ):
    """
    Render interactive HTML treemap from enriched slope histogram.
    """

    city_name = city_name.lower()

    logger.info("Rendering interactive slope treemap…")

    hist_path = os.path.join(output_dir, "tabular", f"{city_name}_slope_histogram.csv")

    if not os.path.exists(hist_path):
        logger.error(f"Histogram not found: {hist_path}")
        return None

    slope = pd.read_csv(hist_path)

    required_cols = {"bin", "percent", "UpperRange"}
    if not required_cols.issubset(slope.columns):
        logger.error("Histogram CSV is not enriched. Run compute_slope_histogram(enrich=True).")
        return None

    render_html_dir = os.path.join(render_dir, "plots", "html")
    os.makedirs(render_html_dir, exist_ok=True)

    max_upper_range = slope["UpperRange"].max()

    slope_colors = {
        "0-2": "#ffffd4",
        "2-5": "#fed98e",
        "5-10": "#fe9929",
        "10-20": "#d95f0e",
        f"20-{int(max_upper_range)}": "#993404"
    }

    html_path = os.path.join(render_html_dir, f"{city_name}_slope_treemap.html")

    fig = px.treemap(
        slope,
        path=["bin"],
        values="percent",
        color="bin",
        color_discrete_map=slope_colors,
        labels={"percent": "Percentage", "bin": "Slope Range"}
    )

    fig.update_layout(
        showlegend=False,
        margin=dict(t=50, l=25, r=25, b=25),
        font=font_dict
    )

    fig.write_html(html_path, full_html=False, include_plotlyjs="cdn")

    logger.info(f"Interactive treemap saved: {html_path}")

    return html_path

from core.py.log_module import setup_logger
logger = setup_logger(__name__)


# ----------------------------------------------------------
# HELPER: load clipped raster from output_dir if needed
# ----------------------------------------------------------
def _load_clipped_raster(city_name, output_dir):
    raster_path = os.path.join(output_dir, "spatial", f"{city_name}_slope.tif")

    if not os.path.exists(raster_path):
        logger.error(f"Raster not found for visualization: {raster_path}")
        return None, None

    with rasterio.open(raster_path) as src:
        arr = src.read()
        meta = src.meta

    return arr, meta


# ----------------------------------------------------------
# RASTER MAP — histogram-aligned classification
# ----------------------------------------------------------
def plot_slope_rastermap(
    city_name: str,
    bins: list | np.ndarray,
    output_dir: str,
    clipped_image=None,
    clipped_meta=None,
    figsize=(16, 16),
):
    """
    Plot slope raster classified using the same histogram bins as treemap.
    """

    city_name = city_name.lower()

    logger.info("Generating slope raster map…")

    # ----------------------------------
    # Load raster if not provided
    # ----------------------------------
    if clipped_image is None or clipped_meta is None:
        clipped_image, clipped_meta = _load_clipped_raster(city_name, output_dir)
        if clipped_image is None:
            return

    # ----------------------------------
    # Prepare raster
    # ----------------------------------
    data = clipped_image.squeeze().astype(float)
    data[data <= 0] = np.nan

    # ----------------------------------
    # Classify into histogram bins
    # ----------------------------------
    classified = np.digitize(data, bins, right=False)

    # Remove invalid classifications
    classified[np.isnan(data)] = 0

    # ----------------------------------
    # Build slope color ramp (same as treemap)
    # ----------------------------------
    max_upper = bins[-1]

    slope_colors = [
        "#ffffd4",  # 0-2
        "#fed98e",  # 2-5
        "#fe9929",  # 5-10
        "#d95f0e",  # 10-20
        "#993404",  # 20+
    ]

    cmap = ListedColormap(["#00000000"] + slope_colors)  # transparent for 0
    bounds = np.arange(0, len(slope_colors) + 2)
    norm = BoundaryNorm(bounds, cmap.N)

    # ----------------------------------
    # Compute spatial extent
    # ----------------------------------
    transform = clipped_meta["transform"]
    height, width = data.shape

    x_min = transform[2]
    x_max = x_min + transform[0] * width
    y_max = transform[5]
    y_min = y_max + transform[4] * height

    extent = [x_min, x_max, y_min, y_max]

    # ----------------------------------
    # Plot
    # ----------------------------------
    fig, ax = plt.subplots(figsize=figsize)

    raster_show = ax.imshow(
        classified,
        cmap=cmap,
        norm=norm,
        extent=extent,
        origin="upper",
        interpolation="nearest",
        zorder=10
    )

    try:
        ctx.add_basemap(
            ax,
            crs=clipped_meta["crs"],
            source=ctx.providers.CartoDB.PositronNoLabels,
            zorder=1
        )
    except Exception:
        logger.warning("Basemap failed to load; continuing without background.")

    # ----------------------------------
    # Legend labels from bins
    # ----------------------------------
    labels = [f"{bins[i]}-{bins[i+1]}" for i in range(len(bins) - 1)]

    cbar = fig.colorbar(
        raster_show,
        ax=ax,
        fraction=0.036,
        pad=0.04,
        ticks=np.arange(1, len(labels) + 1)
    )

    cbar.ax.set_yticklabels(labels)
    cbar.set_label("Slope range", rotation=90)

    ax.set_title(f"{city_name} – slope classification")
    ax.axis("off")

    # ----------------------------------
    # Save
    # ----------------------------------
    img_dir = os.path.join(output_dir, "images")
    os.makedirs(img_dir, exist_ok=True)

    out_path = os.path.join(img_dir, f"{city_name}_slope_map.png")
    plt.savefig(out_path, dpi=200, bbox_inches="tight")
    plt.close()

    logger.info(f"Slope raster map saved to: {out_path}")

    return out_path