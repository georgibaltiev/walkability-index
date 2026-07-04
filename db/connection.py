
from functools import lru_cache

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine

from db.config import settings


@lru_cache(maxsize=1)
def engine() -> Engine:
    return create_engine(settings.sqlalchemy_url)
