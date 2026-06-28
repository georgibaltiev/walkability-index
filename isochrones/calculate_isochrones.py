import geopandas as gpd
import osmnx as ox
import momepy
import networkx as nx
from shapely.geometry import Point
from shapely.ops import unary_union
from shapely import concave_hull

pedestrian_network_geojson_path = 'data/pedestrian_network.geojson'

from shapely.ops import nearest_points, split, snap
from shapely.geometry import LineString

def snap_point_to_network(point, pedestrian_network_gdf):
    """Find the nearest point on the network edges, not just nodes."""
    # Find nearest edge
    nearest_idx = pedestrian_network_gdf.distance(point).idxmin()
    nearest_edge = pedestrian_network_gdf.loc[nearest_idx, "geometry"]

    snapped = nearest_points(point, nearest_edge)[1]
    return snapped, nearest_idx

def calculate_network_buffer(points_of_interest, pedestrian_network):
    # Reproject FIRST before anything else
    pedestrian_network = pedestrian_network.to_crs(epsg=32635)
    points_of_interest = points_of_interest.to_crs(epsg=32635)

    pedestrian_network = pedestrian_network.explode(index_parts=False).reset_index(drop=True)
    pedestrian_network = pedestrian_network[
        pedestrian_network.geometry.geom_type == "LineString"
    ]

    graph = momepy.gdf_to_nx(pedestrian_network, approach="primal")

    # Extract node keys and geometries directly from the graph
    # This guarantees keys match exactly what networkx expects
    node_keys = list(graph.nodes)
    node_points = [Point(graph.nodes[n]["x"], graph.nodes[n]["y"]) for n in node_keys]
    nodes_gdf = gpd.GeoDataFrame(
        {"node_key": node_keys},
        geometry=node_points,
        crs="EPSG:32635"
    )

    buffers = []
    for geom in points_of_interest.geometry:
        buffers.append(network_buffer(geom, graph, nodes_gdf, distance_m=1000))

    return buffers


def network_buffer(point, graph, nodes_gdf, distance_m=1000):
    # Get the actual graph node key (not the GeoDataFrame index)
    _, nearest_idx = snap_point_to_network(point, nodes_gdf)
    nearest_node_key = nodes_gdf.loc[nearest_idx, "node_key"]

    reachable = nx.single_source_dijkstra_path_length(
        graph, nearest_node_key, cutoff=distance_m, weight="mm_len"
    )

    reachable_points = [
        Point(graph.nodes[n]["x"], graph.nodes[n]["y"])
        for n in reachable
    ]

    if len(reachable_points) < 3:
        return point.buffer(distance_m)

    return concave_hull(unary_union(reachable_points), ratio=0.0)


def main():

    poi_geojson_path='./data/supermarkets.geojson'

    points_of_interest = gpd.read_file(poi_geojson_path)
    pedestrian_network = gpd.read_file(pedestrian_network_geojson_path)

    buffers = calculate_network_buffer(points_of_interest, pedestrian_network)


    points_of_interest_projected = points_of_interest.to_crs(epsg=32635)

    individual = gpd.GeoDataFrame(points_of_interest_projected.drop(columns="geometry"), geometry=buffers, crs="EPSG:32635").to_crs(epsg=4326)
    individual.to_file("data/geojson/network_buffers.geojson", driver="GeoJSON")

    union_geom = unary_union(buffers)
    union = gpd.GeoDataFrame(geometry=[union_geom], crs="EPSG:32635").to_crs(epsg=4326)
    union.to_file("data/geojson/network_buffers_union.geojson", driver="GeoJSON")


if __name__ == '__main__':
    main()
