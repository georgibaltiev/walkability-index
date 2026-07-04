import os

import pandas as pd
from sqlalchemy.engine import Engine

from db.analysis.data_access import load_feature_frame, persist_feature_frame
from db.analysis.walkability_calculator import build_distance_frame, calculate_walkability_index


def run(engine: Engine) -> None:
    print("Preparing walkability inputs...")
    distance_frame = _load_or_build_distance_frame(engine)
    print("Computing walkability index...")
    feature_frame = calculate_walkability_index(distance_frame)
    persist_feature_frame(engine, feature_frame)
    print("Walkability features persisted.")


def _load_or_build_distance_frame(engine: Engine) -> pd.DataFrame:
    force_rebuild = os.environ.get("DB_FORCE_DISTANCE_REBUILD", "").lower() in {"1", "true", "yes"}
    if force_rebuild:
        print("DB_FORCE_DISTANCE_REBUILD is enabled. Recomputing distances...")
        return build_distance_frame(engine)

    try:
        cached = load_feature_frame(engine)
    except Exception:
        print("No cached feature table found. Recomputing distances...")
        return build_distance_frame(engine)

    has_building_id = "building_id" in cached.columns
    distance_columns = [column for column in cached.columns if column.startswith("distance_to_")]

    if not has_building_id or not distance_columns:
        print("Cached feature table has no distance columns. Recomputing distances...")
        return build_distance_frame(engine)

    print("Using cached distance columns from building_walkability_features.")
    return cached[["building_id", *distance_columns]]
