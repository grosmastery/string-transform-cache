"""``cache-cli`` entry point."""

import json
import sys
import time
from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from pathlib import Path
from typing import TextIO

import httpx
from pydantic import ValidationError

from cache_cli.client import CacheServiceClient, ServiceError
from cache_cli.settings import STDIO, CliSettings, PayloadRequest, parse_args

EXIT_OK = 0
EXIT_SERVICE_ERROR = 1
EXIT_USAGE_ERROR = 2  # matches argparse's exit code for bad arguments


def run(client: CacheServiceClient, request: PayloadRequest, repeat: int, out: TextIO) -> None:
    """Create and read the payload ``repeat`` times, writing one JSON line per iteration.

    JSON lines keep the output machine-readable, and the per-iteration timing
    makes the effect of the cache visible: the first call pays for the
    transformer, later ones should not.
    """
    for iteration in range(1, repeat + 1):
        started = time.perf_counter()
        created = client.create_payload(request)
        output = client.read_payload(created.id)
        elapsed_ms = (time.perf_counter() - started) * 1000
        record = {
            "iteration": iteration,
            "id": str(created.id),
            "created": created.created,
            "elapsed_ms": round(elapsed_ms, 2),
            "output": output,
        }
        out.write(json.dumps(record, ensure_ascii=False) + "\n")
        out.flush()


@contextmanager
def _open_output(target: str) -> Iterator[TextIO]:
    if target == STDIO:
        yield sys.stdout
    else:
        with Path(target).open("w", encoding="utf-8") as handle:
            yield handle


def main(argv: Sequence[str] | None = None) -> int:
    try:
        settings: CliSettings = parse_args(argv)
        request = settings.read_request()
    except ValidationError as exc:
        print(f"cache-cli: invalid arguments\n{exc}", file=sys.stderr)
        return EXIT_USAGE_ERROR
    except OSError as exc:
        print(f"cache-cli: cannot read input: {exc}", file=sys.stderr)
        return EXIT_USAGE_ERROR

    try:
        with (
            httpx.Client(base_url=str(settings.host), timeout=30.0) as http,
            _open_output(settings.output) as out,
        ):
            run(CacheServiceClient(http), request, settings.repeat, out)
    except ServiceError as exc:
        print(f"cache-cli: {exc}", file=sys.stderr)
        return EXIT_SERVICE_ERROR
    except OSError as exc:
        print(f"cache-cli: cannot write output: {exc}", file=sys.stderr)
        return EXIT_USAGE_ERROR
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
