"""Unit tests for command line parsing and validation."""

import io
import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from cache_cli.settings import parse_args
from tests.helpers import SAMPLE_REQUEST

SAMPLE_JSON = json.dumps(SAMPLE_REQUEST)


def test_defaults() -> None:
    settings = parse_args(["--json", SAMPLE_JSON])

    assert str(settings.host) == "http://localhost:8000/"
    assert settings.repeat == 1
    assert settings.output == "-"


@pytest.mark.parametrize(
    "argv",
    [
        ["-h", "http://svc:9000", "-r", "3", "-j", SAMPLE_JSON, "-o", "out.jsonl"],
        [
            "--host",
            "http://svc:9000",
            "--repeat",
            "3",
            "--json",
            SAMPLE_JSON,
            "--output",
            "out.jsonl",
        ],
        ["--host=http://svc:9000", "--repeat=3", f"--json={SAMPLE_JSON}", "--output=out.jsonl"],
    ],
    ids=["short", "long", "equals"],
)
def test_short_and_long_options_are_equivalent(argv: list[str]) -> None:
    settings = parse_args(argv)

    assert str(settings.host) == "http://svc:9000/"
    assert settings.repeat == 3
    assert settings.output == "out.jsonl"
    assert settings.read_request().model_dump() == SAMPLE_REQUEST


def test_reads_input_file(tmp_path: Path) -> None:
    input_file = tmp_path / "payload.json"
    input_file.write_text(SAMPLE_JSON, encoding="utf-8")

    settings = parse_args(["-i", str(input_file)])

    assert settings.read_request().model_dump() == SAMPLE_REQUEST


def test_reads_stdin_when_input_is_dash() -> None:
    settings = parse_args(["-i", "-"])

    assert settings.read_request(stdin=io.StringIO(SAMPLE_JSON)).model_dump() == SAMPLE_REQUEST


def test_invalid_json_from_file_is_reported(tmp_path: Path) -> None:
    input_file = tmp_path / "payload.json"
    input_file.write_text("{not json", encoding="utf-8")

    with pytest.raises(ValidationError):
        parse_args(["-i", str(input_file)]).read_request()


@pytest.mark.parametrize(
    ("argv", "message"),
    [
        ([], "exactly one of --input or --json"),
        (["-i", "-", "-j", SAMPLE_JSON], "exactly one of --input or --json"),
        (["-i", "missing.json"], "input file not found"),
        (["-r", "0", "-j", SAMPLE_JSON], "greater than 0"),
        (["-h", "not a url", "-j", SAMPLE_JSON], "URL"),
        (["-j", "{not json"], "Invalid JSON"),
        (["-j", '{"list_1": ["a"], "list_2": []}'], "at least 1 item"),
        (["-j", '{"list_1": ["a"], "list_2": ["b", "c"]}'], "same length"),
    ],
    ids=[
        "no-input",
        "two-inputs",
        "missing-file",
        "zero-repeat",
        "bad-host",
        "bad-json",
        "empty-list",
        "length-mismatch",
    ],
)
def test_invalid_arguments_are_rejected(argv: list[str], message: str) -> None:
    with pytest.raises(ValidationError, match=message):
        parse_args(argv)


def test_help_uses_long_option_only(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as exit_info:
        parse_args(["--help"])

    assert exit_info.value.code == 0
    assert "--host, -h" in capsys.readouterr().out
