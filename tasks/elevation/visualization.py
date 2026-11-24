import numpy as np
from core.py.log_module import setup_logger
from matplotlib.colors import ListedColormap, BoundaryNorm
import matplotlib.pyplot as plt
import contextily as ctx
import os
import numpy as np
import rasterio
logger = setup_logger(__name__)

def compute_elevation_bins(data, n_bins=6):
    """
    Compute elevation bins robustly.
    Handles flat AOI (min == max).
    Returns bin_edges, bin_labels
    """
    valid = data[~np.isnan(data)]

    if valid.size == 0:
        raise ValueError("No valid elevation values")

    vmin = float(valid.min())
    vmax = float(valid.max())

    # Flat AOI → single bin
    if np.isclose(vmin, vmax):
        bin_edges = np.array([vmin, vmax + 1e-6])
        labels = [f"{vmin:.0f} m"]
        return bin_edges, labels

    # Normal case
    bin_edges = np.linspace(vmin, vmax, n_bins + 1)

    labels = [
        f"{bin_edges[i]:.0f}–{bin_edges[i+1]:.0f} m"
        for i in range(len(bin_edges) - 1)
    ]

    return bin_edges, labels

# ----------------------------------------------------------
# HELPER: load clipped raster from output_dir if needed
# ----------------------------------------------------------
def _load_clipped_raster(city_name, output_dir):
    raster_path = os.path.join(output_dir, "spatial", f"{city_name}_landslide.tif")

    if not os.path.exists(raster_path):
        logger.error(f"Raster not found for visualization: {raster_path}")
        return None, None

    with rasterio.open(raster_path) as src:
        arr = src.read()          # read ALL bands -> could return shape (1, H, W)
        meta = src.meta
    
    return arr, meta



def plot_elevation_rastermap(
    city_name: str,
    output_dir: str,
    clipped_image=None,
    clipped_meta=None,
    figsize=(16, 16),
    n_bins=6,
):
    """
    Plot elevation raster map with dynamic binning.
    """

    logger.info("Generating elevation map…")
    
    # ----------------------------------
    # Load raster if not provided
    # ----------------------------------
    if clipped_image is None or clipped_meta is None:
        clipped_image, clipped_meta = _load_clipped_raster(city_name, output_dir)
        if clipped_image is None:
            return

    # ----------------------------------
    # Ensure 2D float array
    # ----------------------------------
    data = clipped_image.squeeze().astype(float)
    data[data <= 0] = np.nan

    # ----------------------------------
    # Compute extent
    # ----------------------------------
    transform = clipped_meta["transform"]
    height, width = data.shape

    x_min = transform[2]
    x_max = x_min + transform[0] * width
    y_max = transform[5]
    y_min = y_max + transform[4] * height

    extent = [x_min, x_max, y_min, y_max]

    # ----------------------------------
    # Elevation binning (ROBUST)
    # ----------------------------------
    bin_edges, labels = compute_elevation_bins(data, n_bins=n_bins)

    cmap = ListedColormap(['#f5c4c0', '#762175'])
    cmap = cmap.resampled(len(labels))

    norm = BoundaryNorm(bin_edges, cmap.N)

    # ----------------------------------
    # Plot
    # ----------------------------------
    fig, ax = plt.subplots(figsize=figsize)

    im = ax.imshow(
        data,
        cmap=cmap,
        norm=norm,
        extent=extent,
        origin="upper",
        interpolation="nearest",
        zorder=10
    )

    # Basemap
    try:
        ctx.add_basemap(
            ax,
            crs=clipped_meta["crs"],
            source=ctx.providers.CartoDB.PositronNoLabels,
            zorder=1
        )
    except Exception:
        logger.warning("Basemap failed to load")

    # ----------------------------------
    # Colorbar (categorical)
    # ----------------------------------
    cbar = fig.colorbar(
        im,
        ax=ax,
        fraction=0.036,
        pad=0.04,
        ticks=(bin_edges[:-1] + bin_edges[1:]) / 2
    )

    cbar.ax.set_yticklabels(labels)
    cbar.set_label("Meters above sea level (MASL)", rotation=90)

    # ----------------------------------
    # Final touches
    # ----------------------------------
    ax.set_title(f"{city_name} – Elevation")
    ax.axis("off")

    img_dir = os.path.join(output_dir, "images")
    os.makedirs(img_dir, exist_ok=True)

    out_path = os.path.join(img_dir, f"{city_name}_elevation_map.png")
    plt.savefig(out_path, dpi=200, bbox_inches="tight")
    plt.close()

    logger.info(f"Elevation map saved to: {out_path}")



def plot_elevation_stats(city_name: str, output_dir: str, render_dir: str):
    """
    Generate static and interactive treemap of elevation distribution.
    """

    import os
    import pandas as pd
    import matplotlib.pyplot as plt
    import squarify
    import plotly.express as px
    from matplotlib.colors import to_hex

    # --------------------------------------------------
    # Paths
    # --------------------------------------------------
    images_dir = os.path.join(output_dir, "images")
    os.makedirs(images_dir, exist_ok=True)
    tabular_dir = os.path.join(output_dir, "tabular")
    os.makedirs(tabular_dir, exist_ok=True)
    csv_path = os.path.join(tabular_dir, f"{city_name}_elevation.csv")
    os.makedirs(render_dir, exist_ok=True)
    png_dir = os.path.join(render_dir, "plots", "png")
    html_dir = os.path.join(render_dir, "plots", "html")
    os.makedirs(png_dir, exist_ok=True)
    os.makedirs(html_dir, exist_ok=True)


    if not os.path.exists(csv_path):
        raise FileNotFoundError(f"Elevation CSV not found: {csv_path}")

    # --------------------------------------------------
    # Read + validate data
    # --------------------------------------------------
    elev = pd.read_csv(csv_path)

    required_cols = {"Bin", "Pixel_Count"}
    if not required_cols.issubset(elev.columns):
        raise ValueError(f"CSV must contain columns: {required_cols}")

    elev = elev.copy()
    elev["Bin"] = elev["Bin"].astype(str).str.strip()
    elev = elev[elev["Pixel_Count"] > 0]

    total = elev["Pixel_Count"].sum()
    if total == 0:
        raise ValueError("Total elevation pixel count is zero")

    elev["percent"] = elev["Pixel_Count"] / total * 100

    # Preserve bin order as-is (important!)
    elev["Bin"] = pd.Categorical(
        elev["Bin"],
        categories=elev["Bin"].tolist(),
        ordered=True
    )

    # --------------------------------------------------
    # Color palette (Plotly → Matplotlib safe)
    # --------------------------------------------------
    base_palette = ['#f5c4c0', '#762175']

    def plotly_rgb_to_mpl(rgb_str):
        """
        Convert 'rgb(r, g, b)' → (r, g, b) in 0–1 range for matplotlib
        """
        r, g, b = rgb_str.strip("rgb()").split(",")
        return (int(r) / 255, int(g) / 255, int(b) / 255)

    plotly_colors = px.colors.sample_colorscale(
        base_palette,
        [i / max(len(elev) - 1, 1) for i in range(len(elev))]
    )

    colors = [plotly_rgb_to_mpl(c) for c in plotly_colors]


    # --------------------------------------------------
    # Static treemap (PNG)
    # --------------------------------------------------
    plt.figure(figsize=(12, 8))

    squarify.plot(
        sizes=elev["percent"],
        label=[
            f"{row.Bin}\n{row.percent:.1f}%"
            for row in elev.itertuples()
        ],
        color=colors,
        alpha=0.85,
        pad=True
    )

    plt.title(f"Elevation Distribution – {city_name}")
    plt.axis("off")
    plt.tight_layout()

    png_path = os.path.join(png_dir, f"{city_name}_elevation_treemap.png")
    plt.savefig(png_path, dpi=200, bbox_inches="tight")
    plt.close()

    # --------------------------------------------------
    # Interactive treemap (HTML)
    # --------------------------------------------------
    fig = px.treemap(
        elev,
        path=["Bin"],
        values="percent",
        color="percent",
        color_continuous_scale=base_palette,
        labels={"percent": "Percentage"}
    )

    fig.update_layout(
        title=f"Elevation Distribution – {city_name}",
        margin=dict(t=50, l=20, r=20, b=20),
        coloraxis_showscale=False
    )

    html_path = os.path.join(html_dir, f"{city_name}_elevation_treemap.html")
    fig.write_html(html_path, full_html=False, include_plotlyjs="cdn")

    return {
        "png": png_path,
        "html": html_path
    }
