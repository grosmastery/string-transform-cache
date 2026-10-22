"""Integration tests: HTTP API through to the database."""

import uuid

import pytest
from fastapi.testclient import TestClient

from cache_service.config import Settings
from cache_service.main import create_app
from tests.helpers import SAMPLE_OUTPUT, SAMPLE_REQUEST, CountingTransformer


def test_create_then_read_returns_sample_output(client: TestClient) -> None:
    created = client.post("/payload", json=SAMPLE_REQUEST)

    assert created.status_code == 201
    assert created.json()["message"] == "Payload created"

    read = client.get(f"/payload/{created.json()['id']}")

    assert read.status_code == 200
    assert read.json() == {"output": SAMPLE_OUTPUT}


def test_repeated_request_reuses_id_without_transforming_again(
    client: TestClient, transformer: CountingTransformer
) -> None:
    first = client.post("/payload", json=SAMPLE_REQUEST).json()
    calls_after_first = len(transformer.calls)

    second = client.post("/payload", json=SAMPLE_REQUEST)

    assert second.status_code == 200
    assert second.json()["id"] == first["id"]
    assert len(transformer.calls) == calls_after_first == 6


def test_read_does_not_call_transformer(
    client: TestClient, transformer: CountingTransformer
) -> None:
    payload_id = client.post("/payload", json=SAMPLE_REQUEST).json()["id"]
    transformer.calls.clear()

    client.get(f"/payload/{payload_id}")

    assert transformer.calls == []


def test_cache_survives_application_restart(
    database_url: str, transformer: CountingTransformer
) -> None:
    settings = Settings(database_url=database_url)
    with TestClient(create_app(settings, transformer)) as first_run:
        payload_id = first_run.post("/payload", json=SAMPLE_REQUEST).json()["id"]
    transformer.calls.clear()

    with TestClient(create_app(settings, transformer)) as second_run:
        response = second_run.post("/payload", json=SAMPLE_REQUEST)
        partial = second_run.post(
            "/payload", json={"list_1": ["first string"], "list_2": ["new string"]}
        )

    assert response.json()["id"] == payload_id
    assert partial.status_code == 201
    assert transformer.calls == ["new string"]


@pytest.mark.parametrize(
    "body",
    [
        {"list_1": ["a"], "list_2": ["b", "c"]},
        {"list_1": [], "list_2": []},
        {"list_1": ["a"]},
        {"list_1": ["a"], "list_2": [1]},
    ],
    ids=["length-mismatch", "empty", "missing-list", "non-string"],
)
def test_invalid_body_is_rejected(
    client: TestClient, transformer: CountingTransformer, body: dict
) -> None:
    response = client.post("/payload", json=body)

    assert response.status_code == 422
    assert transformer.calls == []


def test_unknown_payload_returns_404(client: TestClient) -> None:
    assert client.get(f"/payload/{uuid.uuid4()}").status_code == 404


def test_malformed_payload_id_returns_422(client: TestClient) -> None:
    assert client.get("/payload/not-a-uuid").status_code == 422
