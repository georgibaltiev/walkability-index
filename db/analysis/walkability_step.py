from sqlalchemy.engine import Engine

from db.analysis.data_access import persist_feature_frame
from db.analysis.walkability_calculator import build_distance_frame, calculate_walkability_index


def run(engine: Engine) -> None:
    distance_frame = build_distance_frame(engine)
    feature_frame = calculate_walkability_index(distance_frame)
    persist_feature_frame(engine, feature_frame)
