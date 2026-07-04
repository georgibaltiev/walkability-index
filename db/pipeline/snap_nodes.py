
from pathlib import Path

from sqlalchemy import text
from sqlalchemy.engine import Engine

from db.config import POINT_OF_INTEREST_GEOJSONS


SQL_DIR = Path(__file__).resolve().parent.parent / "sql"
POINT_SQL_FILE = SQL_DIR / "snap_point_of_interest.sql"
BUILDINGS_SQL_FILE = SQL_DIR / "snap_buildings.sql"


def run(engine: Engine) -> None:
    with engine.begin() as conn:
        print("Resetting prior snap metrics...")
        conn.execute(text(
            "UPDATE buildings SET nearest_node = NULL "
            "WHERE nearest_node IS NOT NULL;"
        ))
        for dataset in POINT_OF_INTEREST_GEOJSONS:
            conn.execute(text(
                f"UPDATE {dataset.table_name} SET nearest_node = NULL "
                f"WHERE nearest_node IS NOT NULL;"
            ))

        print("Identifying main connected component of the network...")
        conn.execute(text("DROP TABLE IF EXISTS network_components;"))
        conn.execute(text("""
            CREATE TABLE network_components AS
            SELECT * FROM pgr_connectedComponents(
                'SELECT edge_id AS id, source, target, cost FROM pedestrian_network'
            );
        """))
        row = conn.execute(text("""
            SELECT component
            FROM network_components
            GROUP BY component
            ORDER BY COUNT(*) DESC
            LIMIT 1;
        """)).fetchone()
        if row is None:
            raise RuntimeError("network_components table is empty — load the network first.")
        main_component_id = row[0]
        print(f"Main component id = {main_component_id}.")

        for dataset in POINT_OF_INTEREST_GEOJSONS:
            print(f"Snapping {dataset.table_name} to the main grid (edge-accurate)...")
            sql = _load_sql(POINT_SQL_FILE).replace("__TABLE_NAME__", dataset.table_name)
            sql = sql.replace("__ID_COLUMN__", dataset.index_label)
            conn.execute(text(sql), {"main_component_id": main_component_id})

        print("Snapping buildings to the main grid (edge-accurate)...")
        sql = _load_sql(BUILDINGS_SQL_FILE)
        conn.execute(text(sql), {"main_component_id": main_component_id})
        conn.execute(text("DROP TABLE network_components;"))
    print("Snapping complete.")


def _load_sql(path: Path) -> str:
    return path.read_text()
