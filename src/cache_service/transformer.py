"""The "transformer function" standing in for an external service."""

import time
from collections.abc import Callable

Transformer = Callable[[str], str]


def make_transformer(delay_seconds: float = 0.0) -> Transformer:
    """Return a transformer with configurable latency.

    The delay mimics a network round trip so the effect of caching can be seen
    when running the service; tests use the default of zero.
    """

    def transform(value: str) -> str:
        if delay_seconds:
            time.sleep(delay_seconds)
        return value.upper()

    return transform
