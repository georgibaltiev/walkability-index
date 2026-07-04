from __future__ import annotations

from typing import Callable, Optional

import pandas as pd
from sqlalchemy import text
from sqlalchemy.engine import Engine

from db.config import POINT_OF_INTEREST_GEOJSONS


CHUNK_SIZE = 50
TARGET_CHUNK_SIZE = 50
FEATURE_TABLE_NAME = "building_walkability_features"


def run(engine: Engine) -> None:
    if not POINT_OF_INTEREST_GEOJSONS:
        raise RuntimeError("No POI GeoJSON layers found — load the inputs first.")

    buildings = _fetch_buildings(engine)
    if buildings.empty:
        raise RuntimeError("No buildings found with nearest network nodes — run the snap step first.")

    feature_frame = pd.DataFrame({"building_id": buildings["building_id"].astype(int)})

    for dataset in POINT_OF_INTEREST_GEOJSONS:
        column_name = f"distance_to_{dataset.table_name}_m"
        print(f"Calculating distances to {dataset.table_name}...")
        target_nodes = _fetch_poi_targets(engine, dataset.table_name)

        if target_nodes.empty:
            feature_frame[column_name] = None
            continue

        distances = _calculate_distances_for_category(engine, buildings, target_nodes)
        feature_frame[column_name] = feature_frame["building_id"].map(distances)

    print("Persisting walkability feature table...")
    _persist(engine, feature_frame)
    print(f"Walkability features written to {FEATURE_TABLE_NAME}.")


def build_distance_frame(engine: Engine) -> pd.DataFrame:
    """Return one row per building with one distance column per POI category."""
    if not POINT_OF_INTEREST_GEOJSONS:
        raise RuntimeError("No POI GeoJSON layers found — load the inputs first.")

    buildings = _fetch_buildings(engine)
    if buildings.empty:
        return pd.DataFrame(columns=["building_id"])

    feature_frame = pd.DataFrame({"building_id": buildings["building_id"].astype(int)})

    for dataset in POINT_OF_INTEREST_GEOJSONS:
        column_name = f"distance_to_{dataset.table_name}_m"
        target_nodes = _fetch_poi_targets(engine, dataset.table_name)
        if target_nodes.empty:
            feature_frame[column_name] = None
            continue
        distances = _calculate_distances_for_category(engine, buildings, target_nodes)
        feature_frame[column_name] = feature_frame["building_id"].map(distances)

    return feature_frame


def calculate_walkability_index(
    distance_frame: pd.DataFrame,
    scorer: Callable[[pd.DataFrame], pd.Series],
) -> pd.DataFrame:
    """Apply a caller-provided scoring function to build a 1-100 style index.

    The scorer receives the full distance frame and must return one numeric
    score per row. The resulting frame keeps the original distances and adds a
    walkability_index column.
    """
    scored = distance_frame.copy()
    scored["walkability_index"] = scorer(scored)
    return scored


def _fetch_buildings(engine: Engine) -> pd.DataFrame:
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


def _fetch_poi_targets(engine: Engine, table_name: str) -> pd.DataFrame:
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


def _calculate_distances_for_category(
    engine: Engine,
    buildings: pd.DataFrame,
    target_nodes: pd.DataFrame,
) -> dict[int, Optional[float]]:
    distances: dict[int, Optional[float]] = {}
    target_offsets = (
        target_nodes[["nearest_node", "edge_offset_m"]]
        .dropna(subset=["nearest_node"])
        .assign(nearest_node=lambda frame: frame["nearest_node"].astype(int))
        .groupby("nearest_node", as_index=False)["edge_offset_m"]
        .min()
    )
    target_node_values = target_offsets["nearest_node"].astype(int).tolist()

    for start in range(0, len(buildings), CHUNK_SIZE):
        chunk = buildings.iloc[start:start + CHUNK_SIZE]
        source_nodes = pd.unique(chunk["nearest_node"].astype(int)).tolist()
        chunk_costs: dict[int, float] = {}

        for target_start in range(0, len(target_node_values), TARGET_CHUNK_SIZE):
            target_chunk_nodes = target_node_values[target_start:target_start + TARGET_CHUNK_SIZE]
            target_chunk_offsets = target_offsets[
                target_offsets["nearest_node"].isin(target_chunk_nodes)
            ]
            node_costs = _route_chunk(
                engine,
                source_nodes,
                target_chunk_nodes,
                target_chunk_offsets,
            )

            for node_id, distance in node_costs.items():
                current = chunk_costs.get(node_id)
                if current is None or distance < current:
                    chunk_costs[node_id] = distance

        for _, row in chunk.iterrows():
            base = chunk_costs.get(int(row["nearest_node"]))
            if base is None:
                distances[int(row["building_id"])] = None
            else:
                distances[int(row["building_id"])] = float(base) + float(row["edge_offset_m"])

    return distances


def _route_chunk(
    engine: Engine,
    source_nodes: list[int],
    target_nodes: list[int],
    target_offsets: pd.DataFrame,
) -> dict[int, float]:
    source_nodes = list(dict.fromkeys(int(node) for node in source_nodes))
    target_nodes = list(dict.fromkeys(int(node) for node in target_nodes))
    if not source_nodes or not target_nodes:
        return {}

    source_nodes_str = ",".join(map(str, source_nodes))
    target_nodes_str = ",".join(map(str, target_nodes))
    query = f"""
        SELECT
            start_vid,
            end_vid,
            MIN(agg_cost) AS min_distance
        FROM pgr_dijkstra(
            'SELECT edge_id AS id, source, target, cost FROM pedestrian_network',
            ARRAY[{source_nodes_str}],
            ARRAY[{target_nodes_str}],
            directed := false
        )
        WHERE agg_cost > 0
        GROUP BY start_vid, end_vid;
    """
    with engine.connect() as conn:
        df = pd.read_sql(text(query), conn)

    if df.empty:
        return {}

    merged = df.merge(
        target_offsets[["nearest_node", "edge_offset_m"]],
        left_on="end_vid",
        right_on="nearest_node",
        how="left",
    )
    merged["total_distance"] = merged["min_distance"] + merged["edge_offset_m"]
    grouped = merged.groupby("start_vid", as_index=False)["total_distance"].min()
    return {
        int(row["start_vid"]): float(row["total_distance"])
        for _, row in grouped.iterrows()
    }


def _persist(engine: Engine, feature_frame: pd.DataFrame) -> None:
    feature_frame.to_sql(FEATURE_TABLE_NAME, engine, if_exists="replace", index=False)
