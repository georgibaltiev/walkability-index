
from pathlib import Path

from sqlalchemy import text
from sqlalchemy.engine import Engine

from db.config import POINT_OF_INTEREST_GEOJSONS


SQL_FILE = Path(__file__).resolve().parent.parent / "sql" / "topology.sql"


def run(engine: Engine) -> None:
    sql = SQL_FILE.read_text()
    print("Setting up pedestrian_network topology and spatial indexes...")
    with engine.begin() as conn:
        for statement in _split_statements(sql):
            conn.execute(text(statement))

        _setup_spatial_tables(conn)
    print("Topology and indexes ready.")


def _split_statements(sql: str) -> list[str]:
    return [stmt.strip() for stmt in sql.split(";") if stmt.strip()]


def _setup_spatial_tables(conn) -> None:
    for table_name in ("buildings", *[dataset.table_name for dataset in POINT_OF_INTEREST_GEOJSONS]):
        conn.execute(text(
            f"CREATE INDEX IF NOT EXISTS {table_name}_geom_idx "
            f"ON {table_name} USING GIST (geometry);"
        ))
        conn.execute(text(
            f"ALTER TABLE {table_name} ADD COLUMN IF NOT EXISTS nearest_node INTEGER;"
        ))
