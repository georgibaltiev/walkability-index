from __future__ import annotations

from typing import Sequence

import geopandas as gpd
import pandas as pd
from sqlalchemy import inspect, text
from sqlalchemy.engine import Engine

from db.config import TARGET_CRS


def fetch_buildings(engine: Engine) -> pd.DataFrame:
    query = text("""
        SELECT
            b.building_id,
            b.nearest_node,
            ST_Distance(
                ST_ClosestPoint(b.geometry, v.the_geom),
                v.the_geom
            ) AS edge_offset_m
        FROM buildings b
        JOIN pedestrian_network_vertices_pgr v ON v.id = b.nearest_node
        WHERE b.nearest_node IS NOT NULL;
    """)
    with engine.connect() as conn:
        return pd.read_sql(query, conn)


def fetch_poi_targets(engine: Engine, table_name: str) -> pd.DataFrame:
    query = text(f"""
        SELECT
            p.poi_id,
            p.nearest_node,
            ST_Distance(p.geometry, v.the_geom) AS edge_offset_m
        FROM {table_name} p
        JOIN pedestrian_network_vertices_pgr v ON v.id = p.nearest_node
        WHERE p.nearest_node IS NOT NULL;
    """)
    with engine.connect() as conn:
        return pd.read_sql(query, conn)


def route_shortest_paths(
    engine: Engine,
    source_nodes: Sequence[int],
    target_nodes: Sequence[int],
) -> pd.DataFrame:
    source_nodes = list(dict.fromkeys(int(node) for node in source_nodes))
    target_nodes = list(dict.fromkeys(int(node) for node in target_nodes))
    if not source_nodes or not target_nodes:
        return pd.DataFrame(columns=["start_vid", "end_vid", "min_distance"])

    query = f"""
        SELECT
            start_vid,
            end_vid,
            MIN(agg_cost) AS min_distance
        FROM pgr_dijkstra(
            'SELECT edge_id AS id, source, target, cost FROM pedestrian_network',
            ARRAY[{','.join(map(str, source_nodes))}],
            ARRAY[{','.join(map(str, target_nodes))}],
            directed := false
        )
        WHERE agg_cost > 0
        GROUP BY start_vid, end_vid;
    """
    with engine.connect() as conn:
        return pd.read_sql(text(query), conn)


def load_feature_frame(engine: Engine) -> pd.DataFrame:
    with engine.connect() as conn:
        return pd.read_sql(text("SELECT * FROM building_walkability_features"), conn)


def persist_feature_frame(engine: Engine, feature_frame: pd.DataFrame) -> None:
    feature_frame.to_sql("building_walkability_features", engine, if_exists="replace", index=False)


def load_poi_layer(engine: Engine, table_name: str) -> pd.DataFrame:
    inspector = inspect(engine)
    column_names = {column["name"] for column in inspector.get_columns(table_name)}
    if "name" in column_names:
        query = f"SELECT poi_id, name, geometry FROM {table_name}"
    else:
        query = f"SELECT poi_id, geometry FROM {table_name}"

    poi_layer = gpd.read_postgis(query, engine, geom_col="geometry", crs=TARGET_CRS).to_crs("EPSG:4326")
    if "name" in poi_layer.columns:
        poi_layer["display_name"] = poi_layer["name"].fillna(table_name)
    else:
        poi_layer["display_name"] = table_name
    return poi_layer