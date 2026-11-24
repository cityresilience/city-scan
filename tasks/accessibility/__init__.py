from core.py.log_module import setup_logger
logger = setup_logger(__name__)


def collect(scan):
    from .collection import graph_collection, POI_collection

    logger.info("Collecting accessibility data...")
    graph_collection(
        aoi=scan.aoi, city_name=scan.city_name,
        output_dir=scan.output_dir, buffer=5000,
        network_type='all', simplify=True, return_graph=True
    )
    POI_collection(
        aoi=scan.aoi, city_name=scan.city_name,
        city_inputs_path=scan.city_inputs_path, buffer=5000,
        output_dir=scan.output_dir
    )


def analyze(scan):
    from .collection import graph_collection
    from .analysis import calc_basic_stats, filter_major_roads, network_plot, road_orientation, compute_graph_centralities, compute_accessibility_analysis

    logger.info("Analyzing accessibility data...")
    network_graph = graph_collection(
        aoi=scan.aoi, city_name=scan.city_name,
        output_dir=scan.output_dir, buffer=5000,
        network_type='all', simplify=True, return_graph=True
    )
    filter_major_roads(graph = network_graph, 
                       output_dir=scan.output_dir, 
                       city_name=scan.city_name)

    calc_basic_stats(
        city_name=scan.city_name, graph=network_graph,
        output_dir=scan.output_dir, return_df=False
    )
    network_plot(
        city_name=scan.city_name, graph=network_graph,
        output_dir=scan.output_dir
    )
    road_orientation(
        city_name=scan.city_name, graph=network_graph,
        output_dir=scan.output_dir
    )
    nodes_gdf, edges_gdf = compute_graph_centralities(
        city_name=scan.city_name, output_dir=scan.output_dir,
        graph=network_graph, k=500, seed=42,
        node_betweenness_centrality=True,
        node_closeness_centrality=True,
        degree_centrality=True,
        edge_betweenness_centrality=True
    )
    compute_accessibility_analysis(
        city_name=scan.city_name, output_dir=scan.output_dir,
        graph=network_graph, city_inputs_path=scan.city_inputs_path,
        nodes_gdf=nodes_gdf, edges_gdf=edges_gdf
    )


def run(scan):
    collect(scan)
    analyze(scan)
    logger.info("Done with accessibility analysis")
