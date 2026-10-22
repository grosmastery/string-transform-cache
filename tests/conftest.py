"""Shared fixtures.

Tests run against a real SQLite file per test rather than mocks of the
session: the caching logic is mostly SQL (lookups, conflict handling), so
mocking it away would test very little.
"""

from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine
from sqlmodel import Session

from cache_service.config import Settings
from cache_service.db import build_engine, init_db
from cache_service.main import create_app

SAMPLE_REQUEST = {
    "list_1": ["first string", "second string", "third string"],
    "list_2": ["other string", "another string", "last string"],
}
SAMPLE_OUTPUT = (
    "FIRST STRING, OTHER STRING, SECOND STRING, ANOTHER STRING, THIRD STRING, LAST STRING"
)


class CountingTransformer:
    """Behaves like the real transformer and records every call."""

    def __init__(self) -> None:
        self.calls: list[str] = []

    def __call__(self, value: str) -> str:
        self.calls.append(value)
        return value.upper()


@pytest.fixture
def transformer() -> CountingTransformer:
    return CountingTransformer()


@pytest.fixture
def database_url(tmp_path: Path) -> str:
    return f"sqlite:///{tmp_path / 'test.db'}"


@pytest.fixture
def engine(database_url: str) -> Iterator[Engine]:
    engine = build_engine(database_url)
    init_db(engine)
    yield engine
    engine.dispose()


@pytest.fixture
def session(engine: Engine) -> Iterator[Session]:
    with Session(engine) as session:
        yield session


@pytest.fixture
def client(database_url: str, transformer: CountingTransformer) -> Iterator[TestClient]:
    app = create_app(Settings(database_url=database_url), transformer=transformer)
    with TestClient(app) as test_client:
        yield test_client
