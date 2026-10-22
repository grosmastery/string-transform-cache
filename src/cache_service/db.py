"""Engine and session management."""

from collections.abc import Iterator

from fastapi import Request
from sqlalchemy import Engine
from sqlmodel import Session, SQLModel, create_engine


def build_engine(database_url: str) -> Engine:
    connect_args = {}
    if database_url.startswith("sqlite"):
        # FastAPI runs sync endpoints in a thread pool, so the connection
        # must be usable from threads other than the one that created it.
        connect_args["check_same_thread"] = False
    return create_engine(database_url, connect_args=connect_args, pool_pre_ping=True)


def init_db(engine: Engine) -> None:
    # create_all is enough for this scope; a real deployment would use Alembic migrations.
    SQLModel.metadata.create_all(engine)


def get_session(request: Request) -> Iterator[Session]:
    # The engine lives on the app rather than in a module global, so each app
    # instance (notably each test) gets its own isolated database.
    with Session(request.app.state.engine) as session:
        yield session
