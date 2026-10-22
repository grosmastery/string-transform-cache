"""Business logic: payload generation on top of the transformer cache."""

import hashlib
import json
import uuid
from collections.abc import Iterable, Sequence
from datetime import UTC, datetime

from sqlalchemy.dialects import postgresql, sqlite
from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, select

from cache_service.models import Payload, TransformedString
from cache_service.transformer import Transformer

OUTPUT_SEPARATOR = ", "

# Keeps IN (...) clauses well below the bound-parameter limits of SQLite and PostgreSQL.
_LOOKUP_CHUNK_SIZE = 500


def payload_hash(list_1: Sequence[str], list_2: Sequence[str]) -> str:
    """Fingerprint of a request, used to recognise payloads generated before.

    Order matters (it defines the output), so the lists are hashed as-is
    rather than as sets.
    """
    canonical = json.dumps([list_1, list_2], ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def interleave(list_1: Sequence[str], list_2: Sequence[str]) -> list[str]:
    if len(list_1) != len(list_2):
        raise ValueError("lists must have the same length")
    return [item for pair in zip(list_1, list_2, strict=True) for item in pair]


def _chunks(values: Sequence[str], size: int) -> Iterable[Sequence[str]]:
    for start in range(0, len(values), size):
        yield values[start : start + size]


def _insert_ignoring_duplicates(session: Session, results: dict[str, str]) -> None:
    """Store new transformer results, tolerating rows a concurrent request just wrote.

    A plain INSERT would fail the whole request if two requests transform the
    same string at the same time; both results are identical, so keeping
    whichever landed first is correct.
    """
    dialect = session.get_bind().dialect.name
    if dialect == "postgresql":
        insert = postgresql.insert
    elif dialect == "sqlite":
        insert = sqlite.insert
    else:
        raise NotImplementedError(f"Unsupported database dialect: {dialect}")

    now = datetime.now(UTC)
    rows = [{"source": src, "result": res, "created_at": now} for src, res in results.items()]
    statement = insert(TransformedString).on_conflict_do_nothing(index_elements=["source"])
    session.execute(statement, rows)


def transform_with_cache(
    session: Session, values: Iterable[str], transformer: Transformer
) -> dict[str, str]:
    """Map every value to its transformed form, calling the transformer only for unseen values."""
    unique = sorted(set(values))

    known: dict[str, str] = {}
    for chunk in _chunks(unique, _LOOKUP_CHUNK_SIZE):
        rows = session.exec(select(TransformedString).where(TransformedString.source.in_(chunk)))
        known.update((row.source, row.result) for row in rows)

    fresh = {value: transformer(value) for value in unique if value not in known}
    if fresh:
        _insert_ignoring_duplicates(session, fresh)
        # Commit right away: transformer results are worth keeping even if
        # storing the payload itself fails afterwards.
        session.commit()

    return known | fresh


def _find_by_hash(session: Session, input_hash: str) -> Payload | None:
    return session.exec(select(Payload).where(Payload.input_hash == input_hash)).first()


def create_payload(
    session: Session, list_1: Sequence[str], list_2: Sequence[str], transformer: Transformer
) -> tuple[Payload, bool]:
    """Return the payload for the given input and whether it was newly created."""
    input_hash = payload_hash(list_1, list_2)

    existing = _find_by_hash(session, input_hash)
    if existing is not None:
        return existing, False

    transformed = transform_with_cache(session, [*list_1, *list_2], transformer)
    output = OUTPUT_SEPARATOR.join(transformed[value] for value in interleave(list_1, list_2))

    payload = Payload(input_hash=input_hash, output=output)
    session.add(payload)
    try:
        session.commit()
    except IntegrityError:
        # Lost a race against an identical request; its payload is equivalent.
        session.rollback()
        existing = _find_by_hash(session, input_hash)
        if existing is None:
            raise
        return existing, False

    session.refresh(payload)
    return payload, True


def get_payload(session: Session, payload_id: uuid.UUID) -> Payload | None:
    return session.get(Payload, payload_id)
