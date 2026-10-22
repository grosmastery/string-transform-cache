"""Command line parsing and validation, built on Pydantic Settings."""

import argparse
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Self, TextIO

from pydantic import BaseModel, Field, HttpUrl, PositiveInt, field_validator, model_validator
from pydantic_settings import (
    BaseSettings,
    CliSettingsSource,
    PydanticBaseSettingsSource,
    SettingsConfigDict,
)

STDIO = "-"


class PayloadRequest(BaseModel):
    """Client-side copy of the service's request contract.

    Validating locally gives the user an immediate, precise error instead of a
    round trip to the server. The client deliberately does not import the
    service package, so it stays installable without the server dependencies.
    """

    list_1: list[str] = Field(min_length=1)
    list_2: list[str] = Field(min_length=1)

    @model_validator(mode="after")
    def lists_have_same_length(self) -> Self:
        if len(self.list_1) != len(self.list_2):
            raise ValueError("list_1 and list_2 must have the same length")
        return self


class CliSettings(BaseSettings):
    """Send a payload to the cache service and print the generated output."""

    model_config = SettingsConfigDict(
        cli_prog_name="cache-cli",
        cli_kebab_case=True,
        cli_hide_none_type=True,
        cli_shortcuts={
            "host": "h",
            "repeat": "r",
            "input": "i",
            "json-input": ["json", "j"],
            "output": "o",
        },
        # Only the command line counts; env vars and .env files would make runs
        # depend on invisible state.
        extra="forbid",
    )

    host: HttpUrl = Field(
        default=HttpUrl("http://localhost:8000"),
        description="base URL of the cache service",
    )
    repeat: PositiveInt = Field(
        default=1,
        description="number of create/read iterations",
    )
    input: str | None = Field(
        default=None,
        description="JSON input file, '-' for stdin",
    )
    # Kept as a string: a model-typed field would be exploded by the CLI source
    # into per-field flags (--json.list-1 ...), which is not the requested interface.
    json_input: str | None = Field(
        default=None,
        description="input payload as a JSON string",
    )
    output: str = Field(
        default=STDIO,
        description="output file, '-' for stdout",
    )

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls: type[BaseSettings],
        init_settings: PydanticBaseSettingsSource,
        env_settings: PydanticBaseSettingsSource,
        dotenv_settings: PydanticBaseSettingsSource,
        file_secret_settings: PydanticBaseSettingsSource,
    ) -> tuple[PydanticBaseSettingsSource, ...]:
        # The CLI source is passed in explicitly by ``parse_args``.
        return (init_settings,)

    @field_validator("input")
    @classmethod
    def input_file_exists(cls, value: str | None) -> str | None:
        if value is not None and value != STDIO and not Path(value).is_file():
            raise ValueError(f"input file not found: {value}")
        return value

    @field_validator("json_input")
    @classmethod
    def json_input_is_valid(cls, value: str | None) -> str | None:
        if value is not None:
            PayloadRequest.model_validate_json(value)
        return value

    @model_validator(mode="after")
    def exactly_one_input(self) -> Self:
        if (self.input is None) == (self.json_input is None):
            raise ValueError("provide exactly one of --input or --json")
        return self

    def read_request(self, stdin: TextIO = sys.stdin) -> PayloadRequest:
        if self.json_input is not None:
            raw = self.json_input
        elif self.input == STDIO:
            raw = stdin.read()
        else:
            assert self.input is not None  # guaranteed by exactly_one_input
            raw = Path(self.input).read_text(encoding="utf-8")
        return PayloadRequest.model_validate_json(raw)


def _build_parser() -> argparse.ArgumentParser:
    # The brief assigns -h to --host, which clashes with argparse's default -h
    # for help. Host wins because it is the more frequently typed option; help
    # stays available as --help.
    parser = argparse.ArgumentParser(
        prog="cache-cli",
        description=CliSettings.__doc__,
        add_help=False,
        allow_abbrev=False,
    )
    parser.add_argument("--help", action="help", help="show this help message and exit")
    return parser


def parse_args(argv: Sequence[str] | None = None) -> CliSettings:
    """Parse and validate the command line (``sys.argv[1:]`` by default)."""
    source = CliSettingsSource(CliSettings, root_parser=_build_parser())
    args = list(sys.argv[1:] if argv is None else argv)
    return CliSettings(_cli_settings_source=source(args=args))
