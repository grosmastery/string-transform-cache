"""Thin HTTP client for the cache service."""

import uuid
from dataclasses import dataclass

import httpx

from cache_cli.settings import PayloadRequest


class ServiceError(Exception):
    """The service answered with an error or could not be reached."""


@dataclass(frozen=True)
class CreatedPayload:
    id: uuid.UUID
    created: bool


class CacheServiceClient:
    def __init__(self, http: httpx.Client) -> None:
        # Taking a ready-made httpx.Client lets tests inject a MockTransport
        # or FastAPI's TestClient instead of a real network connection.
        self._http = http

    def create_payload(self, request: PayloadRequest) -> CreatedPayload:
        response = self._send("POST", "/payload", json=request.model_dump())
        return CreatedPayload(
            id=uuid.UUID(response.json()["id"]),
            created=response.status_code == httpx.codes.CREATED,
        )

    def read_payload(self, payload_id: uuid.UUID) -> str:
        return self._send("GET", f"/payload/{payload_id}").json()["output"]

    def _send(self, method: str, url: str, **kwargs: object) -> httpx.Response:
        try:
            response = self._http.request(method, url, **kwargs)
        except httpx.HTTPError as exc:
            raise ServiceError(f"{method} {url} failed: {exc}") from exc
        if response.is_error:
            raise ServiceError(f"{method} {url} returned {response.status_code}: {response.text}")
        return response
