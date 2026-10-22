"""Unit tests for payload generation and the transformer cache."""

import uuid

import pytest
from sqlmodel import Session, select

from cache_service import service
from cache_service.models import Payload, TransformedString
from tests.helpers import SAMPLE_OUTPUT, SAMPLE_REQUEST, CountingTransformer


class TestInterleave:
    def test_alternates_items_starting_with_first_list(self) -> None:
        assert service.interleave(["a", "b"], ["1", "2"]) == ["a", "1", "b", "2"]

    def test_rejects_lists_of_different_length(self) -> None:
        with pytest.raises(ValueError):
            service.interleave(["a"], ["1", "2"])


class TestPayloadHash:
    def test_is_deterministic(self) -> None:
        assert service.payload_hash(["a"], ["b"]) == service.payload_hash(["a"], ["b"])

    @pytest.mark.parametrize(
        ("other_1", "other_2"),
        [
            (["b"], ["a"]),  # lists swapped
            (["a", "c"], ["b", "d"]),  # different content
            (["a,b"], [""]),  # same characters, different split
        ],
    )
    def test_distinguishes_inputs_with_different_output(
        self, other_1: list[str], other_2: list[str]
    ) -> None:
        assert service.payload_hash(["a"], ["b"]) != service.payload_hash(other_1, other_2)


class TestTransformWithCache:
    def test_calls_transformer_once_per_distinct_value(
        self, session: Session, transformer: CountingTransformer
    ) -> None:
        result = service.transform_with_cache(session, ["x", "y", "x"], transformer)

        assert result == {"x": "X", "y": "Y"}
        assert sorted(transformer.calls) == ["x", "y"]

    def test_reuses_results_stored_by_earlier_calls(
        self, session: Session, transformer: CountingTransformer
    ) -> None:
        service.transform_with_cache(session, ["x", "y"], transformer)
        transformer.calls.clear()

        result = service.transform_with_cache(session, ["y", "z"], transformer)

        assert result == {"y": "Y", "z": "Z"}
        assert transformer.calls == ["z"]

    def test_persists_results(self, session: Session, transformer: CountingTransformer) -> None:
        service.transform_with_cache(session, ["x"], transformer)

        stored = session.exec(select(TransformedString)).all()
        assert [(row.source, row.result) for row in stored] == [("x", "X")]

    def test_tolerates_rows_inserted_concurrently(self, session: Session) -> None:
        # Simulates another request storing the same string between our lookup and insert.
        service._insert_ignoring_duplicates(session, {"x": "X"})
        service._insert_ignoring_duplicates(session, {"x": "X", "y": "Y"})
        session.commit()

        assert len(session.exec(select(TransformedString)).all()) == 2

    def test_handles_more_values_than_one_lookup_chunk(
        self, session: Session, transformer: CountingTransformer
    ) -> None:
        values = [f"value {i}" for i in range(service._LOOKUP_CHUNK_SIZE * 2 + 1)]
        service.transform_with_cache(session, values, transformer)
        transformer.calls.clear()

        result = service.transform_with_cache(session, values, transformer)

        assert len(result) == len(values)
        assert transformer.calls == []


class TestCreatePayload:
    def test_builds_interleaved_transformed_output(
        self, session: Session, transformer: CountingTransformer
    ) -> None:
        payload, created = service.create_payload(
            session, SAMPLE_REQUEST["list_1"], SAMPLE_REQUEST["list_2"], transformer
        )

        assert created is True
        assert payload.output == SAMPLE_OUTPUT

    def test_reuses_identifier_for_identical_input(
        self, session: Session, transformer: CountingTransformer
    ) -> None:
        first, _ = service.create_payload(session, ["a"], ["b"], transformer)
        transformer.calls.clear()

        second, created = service.create_payload(session, ["a"], ["b"], transformer)

        assert created is False
        assert second.id == first.id
        assert transformer.calls == []
        assert len(session.exec(select(Payload)).all()) == 1

    def test_new_payload_only_transforms_unseen_strings(
        self, session: Session, transformer: CountingTransformer
    ) -> None:
        service.create_payload(session, ["a", "b"], ["c", "d"], transformer)
        transformer.calls.clear()

        payload, created = service.create_payload(session, ["b", "a"], ["e", "c"], transformer)

        assert created is True
        assert payload.output == "B, E, A, C"
        assert transformer.calls == ["e"]

    def test_get_payload_returns_none_for_unknown_id(self, session: Session) -> None:
        assert service.get_payload(session, uuid.uuid4()) is None
