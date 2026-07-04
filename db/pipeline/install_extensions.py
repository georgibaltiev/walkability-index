
from sqlalchemy import text
from sqlalchemy.engine import Engine


def run(engine: Engine) -> None:
    with engine.begin() as conn:
        conn.execute(text("CREATE EXTENSION IF NOT EXISTS postgis;"))
        conn.execute(text("CREATE EXTENSION IF NOT EXISTS pgrouting;"))
    print("Extensions ready (postgis, pgrouting).")
