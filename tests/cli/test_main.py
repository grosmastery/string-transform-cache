"""CLI tests: the client against the real application, and error handling of ``main``."""

import io
import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from cache_cli.client import CacheServiceClient
from cache_cli.main import EXIT_SERVICE_ERROR, EXIT_USAGE_ERROR, main, run
from cache_cli.settings import PayloadRequest
from tests.helpers import SAMPLE_OUTPUT, SAMPLE_REQUEST, CountingTransformer


def test_run_against_service_writes_one_line_per_iteration(
    client: TestClient, transformer: CountingTransformer
) -> None:
    # TestClient is an httpx.Client, so the real CLI client talks to the app in-process.
    out = io.StringIO()

    run(CacheServiceClient(client), PayloadRequest(**SAMPLE_REQUEST), repeat=3, out=out)

    records = [json.loads(line) for line in out.getvalue().splitlines()]
    assert [record["iteration"] for record in records] == [1, 2, 3]
    assert [record["created"] for record in records] == [True, False, False]
    assert {record["id"] for record in records} == {records[0]["id"]}
    assert all(record["output"] == SAMPLE_OUTPUT for record in records)
    assert len(transformer.calls) == 6


def test_main_reports_invalid_arguments(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["-r", "0", "-j", json.dumps(SAMPLE_REQUEST)]) == EXIT_USAGE_ERROR
    assert "invalid arguments" in capsys.readouterr().err


def test_main_reports_unreachable_service(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    # Port 1 is reserved and normally closed, so the connection is refused immediately.
    output = tmp_path / "out.jsonl"
    argv = ["-h", "http://127.0.0.1:1", "-j", json.dumps(SAMPLE_REQUEST), "-o", str(output)]

    assert main(argv) == EXIT_SERVICE_ERROR
    assert "POST /payload failed" in capsys.readouterr().err
