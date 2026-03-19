from functools import lru_cache
from sqlalchemy import create_engine
from app.config.settings import settings


@lru_cache(maxsize=1)
def get_engine():
    return create_engine(
        settings.database_url, pool_pre_ping=True, pool_size=5, max_overflow=10
    )
