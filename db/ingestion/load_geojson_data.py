import geopandas as gpd
from sqlalchemy.engine import Engine

from db.config import (
    BUILDINGS_GEOJSON,
    POINT_OF_INTEREST_GEOJSONS,
    PEDESTRIAN_NETWORK_GEOJSON,
    TARGET_CRS,
)


def run(engine: Engine) -> None:
    print("Loading and projecting datasets...")
    buildings = gpd.read_file(BUILDINGS_GEOJSON).to_crs(TARGET_CRS)

    point_of_interest_layers = []
    for dataset in POINT_OF_INTEREST_GEOJSONS:
        point_of_interest_layers.append(
            (
                dataset.table_name,
                gpd.read_file(dataset.path).to_crs(TARGET_CRS),
            )
        )

    network = gpd.read_file(PEDESTRIAN_NETWORK_GEOJSON).to_crs(TARGET_CRS)
    network = network.explode(index_parts=False).reset_index(drop=True)

    print("Writing datasets to PostgreSQL...")
    buildings.to_postgis("buildings", engine, if_exists="replace",
                         index=True, index_label="building_id")

    for table_name, layer in point_of_interest_layers:
        layer.to_postgis(
            table_name,
            engine,
            if_exists="replace",
            index=True,
            index_label="poi_id",
        )

    network.to_postgis("pedestrian_network", engine, if_exists="replace",
                       index=True, index_label="edge_id")
    print("Data ingestion complete.")
