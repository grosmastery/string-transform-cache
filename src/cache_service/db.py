"""Engine and session management."""

from collections.abc import Iterator

from sqlalchemy import Engine
from sqlmodel import Session, SQLModel, create_engine

from cache_service.config import get_settings


def build_engine(database_url: str) -> Engine:
    connect_args = {}
    if database_url.startswith("sqlite"):
        # FastAPI runs sync endpoints in a thread pool, so the connection
        # must be usable from threads other than the one that created it.
        connect_args["check_same_thread"] = False
    return create_engine(database_url, connect_args=connect_args, pool_pre_ping=True)


_engine: Engine | None = None


def get_engine() -> Engine:
    global _engine
    if _engine is None:
        _engine = build_engine(get_settings().database_url)
    return _engine


def init_db(engine: Engine) -> None:
    # create_all is enough for this scope; a real deployment would use Alembic migrations.
    SQLModel.metadata.create_all(engine)


def get_session() -> Iterator[Session]:
    with Session(get_engine()) as session:
        yield session
