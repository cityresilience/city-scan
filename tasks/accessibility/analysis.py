import time
import warnings
import osmnx as ox
import networkx as nx
import pandas as pd
from core.py.log_module import setup_logger
from joblib import Parallel, delayed # type: ignore
logger = setup_logger(__name__)
import os
import random
import geopandas as gpd
import yaml

# compute basic stats
def calc_basic_stats(
        city_name,
        graph, 
        output_dir,
        return_df = False,
        ):
    
    """
    Perform basic network statistics the road network graph object.

    Parameters
    ----------
    city_name : str
        City name used for locating the clipped raster file.
    output_dir : str
        Base output directory.
    graph : street network graph object
        extracted street network graph from graph_collection().
    return_df : bool
        If True, return dataframe, default is False.

    Returns
    -------
    stats_df : pandas.DataFrame
        DataFrame containing min, p25, median, mean, p75, max, sum.
    """
    start = time.time()
    # Suppress DeprecationWarnings within this block
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", category=DeprecationWarning)
        # calculate basic stats
        stats = ox.stats.basic_stats(graph)

        # Descriptions for each metric
        descriptions = {
            'n': 'Total number of nodes (e.g., intersections, dead-ends)',
            'm': 'Total number of edges (street segments)',
            'k_avg': 'Average node degree (connectivity of the graph)',
            'edge_length_total': 'Total length of all edges in meters',
            'edge_length_avg': 'Average length of each edge (segment)',
            'streets_per_node_avg': 'Average number of streets per node',
            'intersection_count': 'Total number of true intersections',
            'street_length_total': 'Total length of undirected street segments',
            'street_segment_count': 'Number of street segments (simplified, undirected)',
            'street_length_avg': 'Average length of each street segment',
            'circuity_avg': 'Average circuity (detour factor compared to straight line)',
            'self_loop_proportion': 'Proportion of edges that loop back to the same node',
            'streets_per_node_counts': 'Count of nodes with specific street counts',
            'streets_per_node_proportions': 'Proportion of nodes with specific street counts',
        }

        # Convert the stats and descriptions to a dataframe
        rows = []
        for key, value in stats.items():
            if isinstance(value, dict):
                rows.append([key, str(value), descriptions.get(key, '')])
            else:
                rows.append([key, round(value, 2), descriptions.get(key, '')])

        df_stats = pd.DataFrame(rows, columns=["Metric", "Value", "Description"])
        end = time.time()
        logger.info (f"Calculating basic stats took {end - start:.2f} seconds")
        
        
        # Save output CSV
        tabular_dir = os.path.join(output_dir, "tabular")
        os.makedirs(tabular_dir, exist_ok=True)

        output_path = os.path.join(tabular_dir, f"{city_name}_network_stats.csv")

        try:
            df_stats.to_csv(output_path, index=False)
            logger.info(f"street network statistics saved to: {output_path}")
        except Exception as e:
            logger.error(f"Error saving statistics CSV: {e}")

        if return_df:
            return df_stats

        return None
        
        

# graph centralities (betweenness, centralities, closeness)
def compute_closeness_node(G, node):
    return node, nx.closeness_centrality(G, u=node, distance='length')

def compute_graph_centralities(
    city_name, 
    output_dir,
    graph,
    degree_centrality=True,
    node_closeness_centrality=True,
    node_betweenness_centrality=True,
    edge_betweenness_centrality=True,
    k=None,
    seed=None
):
    """
    Compute selected centrality measures for a given OSMnx graph.

    Parameters:
    ----------
    city_name : str
        City name used for locating the clipped raster file.
    output_dir : str
        Base output directory.
    graph : networkx.MultiDiGraph
        The road network graph.
    degree_centrality : bool, default=True
        If True, compute node degree centrality.
    node_closeness_centrality : bool, default=True
        If True, compute node closeness centrality.
    node_betweenness_centrality : bool, default=True
        If True, compute node betweenness centrality.
    edge_betweenness_centrality : bool, default=True
        If True, compute edge betweenness centrality.
    k : int or None, optional
        Number of samples for approximation in betweenness centrality.
        If None, full calculation is performed.
    seed : int or None, optional
        Random seed for reproducibility when using ``k``.

    Returns
    -------
    nodes_gdf : geopandas.GeoDataFrame
        Node GeoDataFrame with selected centrality measures.
    edges_gdf : geopandas.GeoDataFrame
        Edge GeoDataFrame with edge betweenness centrality if selected.
    """
    
    start = time.time()
    # Suppress DeprecationWarnings within this block
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", category=DeprecationWarning)
        
        # Ensure the graph is undirected
        G = ox.utils_graph.get_undirected(graph) if hasattr(ox, 'utils_graph') else ox.convert.to_undirected(graph)

        # --- Node Centrality Computation ---
        deg_cent = {}
        close_cent = {}
        btwn_cent = {}

        if degree_centrality:
            deg_cent = nx.degree_centrality(G)
            end = time.time()
            logger.info(f"✔ Node Degree Centrality computed: {end - start:.2f} seconds")

        if node_closeness_centrality:
                logger.info(f"Starting Node Closeness Centrality computation")
                if k is not None:
                    rng = random.Random(seed)
                    sample_nodes = rng.sample(list(G.nodes), k=min(k, len(G.nodes)))
                    results = Parallel(n_jobs=-1)(
                        delayed(compute_closeness_node)(G, n) for n in sample_nodes
                    )
                    close_cent = dict(results)
                    end = time.time()
                    logger.info(f"✔ Node Closeness Centrality computed (sampled: {len(close_cent)} nodes): {end - start:.2f} seconds")
                else:
                    close_cent = nx.closeness_centrality(G, distance='length')
                    end = time.time()
                    logger.info(f"✔ Node Closeness Centrality computed (full graph): {end - start:.2f} seconds")
        if node_betweenness_centrality:
            logger.info(f"Starting Node Betweenness Centrality computation")
            btwn_k = min(k, len(G.nodes)) if k else k
            btwn_cent = nx.betweenness_centrality(
                G, weight='length', normalized=True, k=btwn_k, seed=seed
            )
            end = time.time()
            logger.info(f"✔ Node Betweenness Centrality computed: {end - start:.2f} seconds")

        # Convert graph to GeoDataFrame (nodes only)
        nodes_gdf = ox.graph_to_gdfs(G, nodes=True, edges=False)

        # Add centralities to nodes GeoDataFrame
        if deg_cent:
            nodes_gdf['degree_centrality'] = nodes_gdf.index.map(deg_cent)
        if close_cent:
            nodes_gdf['closeness_centrality'] = nodes_gdf.index.map(close_cent)
        if btwn_cent:
            nodes_gdf['betweenness_centrality'] = nodes_gdf.index.map(btwn_cent)

        # --- Edge Centrality Computation ---
        edges_gdf = ox.graph_to_gdfs(G, nodes=False, edges=True)

        if edge_betweenness_centrality:
            logger.info(f"Starting Edge Betweenness Centrality computation")
            edge_k = min(k, len(G.nodes)) if k else k
            edge_btwn_cent = nx.edge_betweenness_centrality(
                G, weight='length', normalized=True, k=edge_k, seed=seed
            )
            # Convert to Series and align by edge keys (u, v, key)
            edge_btwn_series = pd.Series(edge_btwn_cent)
            edges_gdf['edge_centrality'] = edge_btwn_series
            end = time.time()
            logger.info(f"✔ Edge Betweenness Centrality computed: {end - start:.2f} seconds")

        # Save output
        spatial_dir = os.path.join(output_dir, "spatial")
        os.makedirs(spatial_dir, exist_ok=True)
        gkpg_path = os.path.join(spatial_dir, f"{city_name}_nodes_and_edges_centralities.gpkg")
        try:
            nodes_gdf.to_file(gkpg_path, layer="nodes", driver="GPKG")
            edges_gdf.to_file(gkpg_path, layer="edges", driver="GPKG")
            logger.info(f"street network with centralities saved to: {gkpg_path}")
        except Exception as e:
            logger.error(f"Error saving street network with centralities: {e}")

        end = time.time()
        logger.info(f"✅ Total computation time: {end - start:.2f} seconds")

    return nodes_gdf, edges_gdf




# compute accessibility analysis

def make_isochrone(graph, nodes_gdf, edges_gdf, origin_gdf, distance_list, key, buffer_size=0.0006):
    """
    Generate network-based isochrones and accessibility distances from one or more origin points.

    This function computes the shortest-path distance along a road network from the nearest
    network node of each origin feature to all other nodes using Dijkstra's algorithm. It then
    assigns the minimum distance to each node and edge, and generates buffered isochrone
    polygons for specified distance thresholds.

    Parameters
    ----------
    graph : networkx.MultiDiGraph
        Road network graph (typically from OSMnx).
    nodes_gdf : geopandas.GeoDataFrame
        GeoDataFrame of graph nodes with geometries indexed by node IDs.
    edges_gdf : geopandas.GeoDataFrame
        GeoDataFrame of graph edges with columns ``u`` and ``v`` representing node IDs.
    origin_gdf : geopandas.GeoDataFrame
        GeoDataFrame of origin points (e.g., schools, hospitals, facilities).
    distance_list : list of float
        Distance thresholds (in network units, typically meters) used to generate isochrones.
    key : str
        Label used to name output distance fields (e.g., ``'school'`` → ``distance_to_nearest_school``).
    buffer_size : float, default=0.0006
        Buffer radius (in CRS units) applied to reachable edges when constructing isochrone polygons.

    Returns
    -------
    nodes_access : geopandas.GeoDataFrame
        Copy of ``nodes_gdf`` with an added column
        ``distance_to_nearest_<key>`` representing the minimum network distance to the nearest origin.
    edges_access : geopandas.GeoDataFrame
        Copy of ``edges_gdf`` with an added column
        ``distance_to_nearest_<key>`` computed as the mean of its endpoint node distances.
    isochrone_buffer : geopandas.GeoDataFrame
        GeoDataFrame containing isochrone polygons for each distance threshold with columns:

        - ``geometry`` : buffered union of reachable edges
        - ``distance`` : corresponding distance threshold
    """
    import warnings
    import networkx as nx
    import geopandas as gpd
    import osmnx as ox
    import numpy as np
    
    # # Ensure everything is in the same CRS
    # nodes_gdf = nodes_gdf.to_crs(graph.graph["crs"])
    # edges_gdf = edges_gdf.to_crs(graph.graph["crs"])
    # origin_gdf = origin_gdf.to_crs(graph.graph["crs"])
    
    # Ensure stable join keys
    if "node_id" not in nodes_gdf.columns:
        nodes_gdf = nodes_gdf.reset_index().rename(columns={"index": "node_id"})

    if "u" not in edges_gdf.columns or "v" not in edges_gdf.columns:
        edges_gdf = edges_gdf.reset_index()



    with warnings.catch_warnings():
        warnings.simplefilter("ignore", category=DeprecationWarning)

        # Convert to undirected graph
        G = ox.utils_graph.get_undirected(graph) if hasattr(ox, 'utils_graph') else ox.convert.to_undirected(graph)

        # Snap origins to nearest nodes
        origin_gdf = origin_gdf.copy()
        origin_gdf['nearest_node'] = origin_gdf.geometry.apply(
            lambda x: ox.distance.nearest_nodes(G, x.x, x.y)
        )
        target_nodes = origin_gdf['nearest_node'].unique()

        # Dijkstra: compute shortest path lengths from each origin node
        lengths = {}
        for target in target_nodes:
            sp = nx.single_source_dijkstra_path_length(G, target, weight='length')
            for node, dist in sp.items():
                if node not in lengths or dist < lengths[node]:
                    lengths[node] = dist

        # Map distances to nodes_gdf
        nodes_access = nodes_gdf.copy()
        
        # Ensure stable join keys
        if "node_id" not in nodes_access.columns:
            nodes_access = nodes_access.reset_index().rename(columns={"index": "node_id"})

        nodes_access[f'distance_to_nearest_{key}'] = nodes_access["node_id"].map(lengths)
        logger.info(f'nodes_access is done')

        # Map distances to edges using the mean of the two node distances
        edges_access = edges_gdf.copy()
        if "u" not in edges_access.columns or "v" not in edges_access.columns:
            edges_access = edges_access.reset_index()
        
        edges_access[f'distance_to_nearest_{key}'] = edges_access.apply(
            lambda row: np.mean([
                lengths.get(row['u'], np.nan),
                lengths.get(row['v'], np.nan)
            ]),
            axis=1
        )
        logger.info(f'edges_access is done')

        # Create isochrone buffers
        buffer_list = []
        for d in distance_list:
            filtered = edges_access[edges_access[f'distance_to_nearest_{key}'] <= d]
            if not filtered.empty:
                buffer_geom = filtered.buffer(buffer_size).unary_union
                buffer_list.append({'geometry': buffer_geom, 'distance': d})

        if buffer_list:
            isochrone_buffer = gpd.GeoDataFrame(buffer_list, crs=edges_access.crs)
        else:
            # No edges reachable within any distance threshold — common on
            # disconnected-graph AOIs. Emit empty layer so the rest of the pipeline continues.
            logger.warning(f"No edges within isochrone thresholds for {key}; emitting empty layer")
            isochrone_buffer = gpd.GeoDataFrame(
                {"geometry": [], "distance": []}, geometry="geometry", crs=edges_access.crs
            )
        logger.info(f'isochrone buffer is done')

        return nodes_access, edges_access, isochrone_buffer


def compute_accessibility_analysis(
    city_name,
    output_dir,
    graph,
    city_inputs_path,
    nodes_gdf,
    edges_gdf,
    buffer_size=0.0006
):
    """
    Compute multi-facility network accessibility and generate isochrone outputs.

    This function reads accessibility distance thresholds from a YAML configuration file,
    computes network-based accessibility for each facility category using
    ``make_isochrone()``, and merges the resulting accessibility fields into the
    base network node and edge layers.

    For each category, the function also exports isochrone polygon layers and produces
    a consolidated GeoPackage containing network nodes and edges with all computed
    accessibility attributes.

    Parameters
    ----------
    city_name : str
        Name of the city used for output file naming.
    output_dir : str
        Base output directory for the city.
    graph : networkx.MultiDiGraph
        Road network graph (typically from OSMnx).
    city_inputs_path : str
        Path to the YAML configuration file defining isochrone distances.
    nodes_gdf : geopandas.GeoDataFrame
        Base node layer of the network.
    edges_gdf : geopandas.GeoDataFrame
        Base edge layer of the network.
    buffer_size : float, default=0.0006
        Buffer radius applied when constructing isochrone polygons.

    Returns
    -------
    merged_nodes : geopandas.GeoDataFrame
        Node layer with accessibility attributes for all facility categories.
    merged_edges : geopandas.GeoDataFrame
        Edge layer with accessibility attributes for all facility categories.
    """

    import os
    import yaml
    import geopandas as gpd
    import osmnx as ox

    # # -----------------------------------------------------
    # # Ensure projected coordinates
    # # -----------------------------------------------------
    # working_crs = nodes_gdf.estimate_utm_crs()
    # logger.info(f'working CRS = {working_crs}')
    # if not ox.projection.is_projected(graph):
    #     graph = ox.project_graph(graph, to_crs = working_crs)

    # nodes_gdf = nodes_gdf.to_crs(working_crs)
    # edges_gdf = edges_gdf.to_crs(working_crs)

    # Lock node id as explicit column
    if "node_id" not in nodes_gdf.columns:
        nodes_gdf = nodes_gdf.reset_index().rename(columns={"index": "node_id"})
        edges_gdf = edges_gdf.reset_index()

    # -----------------------------------------------------
    # Setup output directories
    # -----------------------------------------------------
    spatial_dir = os.path.join(output_dir, "spatial")
    os.makedirs(spatial_dir, exist_ok=True)

    # -----------------------------------------------------
    # Load YAML configuration
    # -----------------------------------------------------
    with open(city_inputs_path, "r") as f:
        config = yaml.safe_load(f)

    isochrone_config = config.get("isochrone", {})

    # -----------------------------------------------------
    # Initialize merged network layers
    # -----------------------------------------------------
    merged_nodes = nodes_gdf.copy()
    merged_edges = edges_gdf.copy()

    # -----------------------------------------------------
    # Process each accessibility category
    # -----------------------------------------------------
    for key, distance_list in isochrone_config.items():
        
        origin_path = os.path.join(spatial_dir, f"{city_name}_osm_{key}.gpkg")
        if not os.path.exists(origin_path):
            logger.warning(f"Origin file not found for {key}: {origin_path}")
            continue

        origin_gdf = gpd.read_file(origin_path)
        origin_gdf["geometry"] = origin_gdf.geometry.centroid

        logger.info(f"Computing accessibility for: {key}")
        
        try:
            nodes_access, edges_access, isochrone_buffer = make_isochrone(
                graph=graph,
                nodes_gdf=nodes_gdf,
                edges_gdf=edges_gdf,
                origin_gdf=origin_gdf,
                distance_list=distance_list,
                key=key,
                buffer_size=buffer_size
            )
        except Exception as e:
            logger.error(f"Error: {e}")
            continue


        # -------------------------------------------------
        # Export isochrone polygons
        # -------------------------------------------------
        iso_path = os.path.join(spatial_dir, f"{city_name}_{key}_isochrone.gpkg")
        isochrone_buffer.to_file(iso_path, driver="GPKG")

        # -------------------------------------------------
        # Merge accessibility fields into network layers
        # -------------------------------------------------
        logger.info(f'merging values to distance_to_nearest_{key}')
        # Ensure node_id is a column (not index) before merging
        if "node_id" not in nodes_access.columns:
            nodes_access = nodes_access.reset_index().rename(columns={"index": "node_id"})
        if "node_id" not in merged_nodes.columns:
            merged_nodes = merged_nodes.reset_index().rename(columns={"index": "node_id"})
        
        merged_nodes = merged_nodes.merge(
            nodes_access[["node_id", f"distance_to_nearest_{key}"]],
            on="node_id",
            how="left"
        )

        merged_edges = merged_edges.merge(
            edges_access[["u", "v", f"distance_to_nearest_{key}"]],
            on=["u", "v"],
            how="left"
        )


    # -----------------------------------------------------
    # Export merged network accessibility layers
    # -----------------------------------------------------
    gkpg_path = os.path.join(spatial_dir, f"{city_name}_nodes_and_edges_accessibilities.gpkg")

    try:
        merged_nodes.to_file(gkpg_path, layer="nodes", driver="GPKG")
        merged_edges.to_file(gkpg_path, layer="edges", driver="GPKG")
        logger.info(f"Street network with accessibilities saved to: {gkpg_path}")
    except Exception as e:
        logger.error(f"Error saving street network with accessibilities: {e}")

    return merged_nodes, merged_edges

def network_plot(graph, city_name, output_dir):
    """Plot the full road network graph."""
    if graph is None:
        return
    images_dir = os.path.join(output_dir, "images")
    os.makedirs(images_dir, exist_ok=True)
    fig, ax = ox.plot_graph(graph, bgcolor='#ffffff', node_color='#336699', node_zorder=2, node_size=5, show=False)
    fig.savefig(f'{images_dir}/{city_name}_network_plot.png', dpi=300)
    logger.info(f"Network plot saved to: {images_dir}/{city_name}_network_plot.png")


def road_orientation(graph, city_name, output_dir):
    """
    Conduct road orientation analysis and generate a radar plot

    Parameters
    ----------
    city_name : str
        Name of the city used for output file naming.
    output_dir : str
        Base output directory for the city.
    graph : networkx.MultiDiGraph
        Road network graph (typically from OSMnx)."""
    
    import matplotlib.pyplot as plt
    undirected = ox.utils_graph.get_undirected(graph) if hasattr(ox, 'utils_graph') else ox.convert.to_undirected(graph)
    road_bearing = ox.add_edge_bearings(undirected)
    fig, ax = ox.plot.plot_orientation(road_bearing, title=city_name, area=True, figsize=(8,8))
    plt.close()
    images_dir = os.path.join(output_dir, "images")
    os.makedirs(images_dir, exist_ok=True)
    fig.savefig(f'{images_dir}/{city_name}_road_orientation.png', dpi=300, bbox_inches='tight')

def filter_major_roads(graph, output_dir, city_name):
    from os.path import exists
    spatial_dir = os.path.join(output_dir, "spatial")
    os.makedirs(spatial_dir, exist_ok=True)
    if graph is not None:
        # Ensure G is a MultiDiGraph
        if not isinstance(graph, nx.MultiDiGraph):
            graph = nx.MultiDiGraph(graph)
        
        graph_gpkg = f'{spatial_dir}/{city_name}_nodes_and_edges.gpkg'
        if not exists(graph_gpkg):
            ox.save_graph_geopackage(graph, filepath = graph_gpkg)

        roads_gdf = gpd.read_file(f'{spatial_dir}/{city_name}_nodes_and_edges.gpkg', layer='edges')

        # Filter for major roads based on keywords in the 'highway' attribute
        major_road_keywords = ['primary', 'trunk', 'motorway', 'primary_link', 'trunk_link', 'motorway_link']

        # Filter for major roads using a lambda function
        major_roads_gdf = roads_gdf[roads_gdf['highway'].apply(lambda highway_value: any(keyword in highway_value for keyword in major_road_keywords))]
        major_roads_gdf.to_file(f'{spatial_dir}/{city_name}_major_roads.gpkg', driver='GPKG', layer = 'major_roads')
        logger.info(f"major roads saved to: {spatial_dir}/{city_name}_major_roads.gpkg")