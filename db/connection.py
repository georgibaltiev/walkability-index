
from functools import lru_cache

import psycopg2
from sqlalchemy import create_engine
from sqlalchemy.engine import Engine

from db.config import settings


@lru_cache(maxsize=1)
def engine() -> Engine:
    return create_engine(settings.sqlalchemy_url)


def psycopg_conn():
    return psycopg2.connect(
        dbname=settings.name,
        user=settings.user,
        password=settings.password,
        host=settings.host,
        port=settings.port,
    )
