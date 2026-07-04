from pathlib import Path

from sqlalchemy import text
from sqlalchemy.engine import Engine


SQL_FILE = Path(__file__).resolve().parent.parent / "sql" / "topology.sql"


def run(engine: Engine) -> None:
    sql = SQL_FILE.read_text()
    print("Setting up pedestrian_network topology and spatial indexes...")
    with engine.begin() as conn:
        for statement in _split_statements(sql):
            conn.execute(text(statement))
    print("Topology and indexes ready.")


def _split_statements(sql: str) -> list[str]:
    return [stmt.strip() for stmt in sql.split(";") if stmt.strip()]
