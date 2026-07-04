from __future__ import annotations

from typing import Mapping, Optional
import pandas as pd
from sqlalchemy.engine import Engine

from db.config import (
    POINT_OF_INTEREST_GEOJSONS,
    WALKABILITY_DISTANCE_FLOOR_METERS,
    WALKABILITY_CATEGORY_COEFFICIENTS,
)
from db.analysis.data_access import fetch_buildings, fetch_poi_targets, route_shortest_paths

CHUNK_SIZE = 50
TARGET_CHUNK_SIZE = 50

def build_distance_frame(engine: Engine) -> pd.DataFrame:
    if not POINT_OF_INTEREST_GEOJSONS:
        raise RuntimeError("No POI GeoJSON layers found — load the inputs first.")

    buildings = fetch_buildings(engine)
    if buildings.empty:
        return pd.DataFrame(columns=["building_id"])

    feature_frame = pd.DataFrame({"building_id": buildings["building_id"].astype(int)})

    for dataset in POINT_OF_INTEREST_GEOJSONS:
        column_name = f"distance_to_{dataset.table_name}_m"
        print(f"Calculating distances to {dataset.table_name}...")
        target_nodes = fetch_poi_targets(engine, dataset.table_name)

        if target_nodes.empty:
            feature_frame[column_name] = None
            continue

        distances = _calculate_distances_for_category(engine, buildings, target_nodes)
        feature_frame[column_name] = feature_frame["building_id"].map(distances)

    return feature_frame


def calculate_walkability_index(
    distance_frame: pd.DataFrame,
    coefficients: Mapping[str, float] | None = None,
    distance_floor_meters: float = WALKABILITY_DISTANCE_FLOOR_METERS,
) -> pd.DataFrame:
    """Computes a walkability index scaled from 0 to 100.

    Formula per category i with coefficient c_i and distance d_i:
    contribution_i = c_i * (1 / max(d_i, floor))
    walkability_index = 100 * sum(contribution_i) / sum(c_i * (1 / floor))
    """
    applied_coefficients = dict(WALKABILITY_CATEGORY_COEFFICIENTS)
    if coefficients is not None:
        applied_coefficients.update(coefficients)

    scored = distance_frame.copy()

    total_weighted_inverse = pd.Series(0.0, index=scored.index)
    total_possible_inverse = 0.0

    safe_floor = max(float(distance_floor_meters), 1e-9)

    for dataset in POINT_OF_INTEREST_GEOJSONS:
        coefficient = applied_coefficients.get(dataset.table_name)
        if coefficient is None:
            continue

        distance_column = f"distance_to_{dataset.table_name}_m"
        if distance_column not in scored.columns:
            continue

        raw_distances = pd.to_numeric(scored[distance_column], errors="coerce")

        clamped_distances = raw_distances.clip(lower=safe_floor)
        inverse_distance = 1.0 / clamped_distances
        inverse_distance = inverse_distance.where(raw_distances.notna(), 0.0)

        contribution_column = f"{dataset.table_name}_weight"
        scored[contribution_column] = inverse_distance

        total_weighted_inverse += coefficient * inverse_distance
        total_possible_inverse += coefficient * (1.0 / safe_floor)

    if total_possible_inverse > 0:
        scored["walkability_index"] = (total_weighted_inverse / total_possible_inverse) * 100.0
    else:
        scored["walkability_index"] = 0.0

    scored["walkability_index"] = scored["walkability_index"].clip(lower=0.0, upper=100.0)

    return scored


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
            route_frame = route_shortest_paths(engine, source_nodes, target_chunk_nodes)
            if route_frame.empty:
                continue

            merged = route_frame.merge(
                target_chunk_offsets[["nearest_node", "edge_offset_m"]],
                left_on="end_vid",
                right_on="nearest_node",
                how="left",
            )
            merged["total_distance"] = merged["min_distance"] + merged["edge_offset_m"]
            grouped = merged.groupby("start_vid", as_index=False)["total_distance"].min()

            for _, row in grouped.iterrows():
                node_id = int(row["start_vid"])
                distance = float(row["total_distance"])
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