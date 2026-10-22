"""Database tables."""

import uuid
from datetime import UTC, datetime

from sqlmodel import Field, SQLModel


def _utcnow() -> datetime:
    return datetime.now(UTC)


class TransformedString(SQLModel, table=True):
    """Cached result of one transformer call, keyed by its input.

    The transformer is the expensive external dependency, so this table is
    what actually saves calls: every distinct string is transformed once, ever.
    """

    __tablename__ = "transformed_string"

    source: str = Field(primary_key=True)
    result: str
    created_at: datetime = Field(default_factory=_utcnow)


class Payload(SQLModel, table=True):
    """A generated payload.

    ``input_hash`` is unique so that identical requests resolve to the same
    identifier instead of creating duplicates. The output is stored rather than
    rebuilt on read, so GET never touches the transformer or the string cache.
    """

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    input_hash: str = Field(unique=True, index=True, max_length=64)
    output: str
    created_at: datetime = Field(default_factory=_utcnow)
