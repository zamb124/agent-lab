#!/usr/bin/env python3
"""Bootstrap OpenFGA для pytest (make test-up) — тонкая обёртка над openfga_env_bootstrap."""

from __future__ import annotations

import sys

from scripts.dev.openfga_env_bootstrap import (
    DEFAULT_TEST_API_URL,
    TEST_ENV_PATH,
    apply_env_file_to_environ,
    load_env_file,
    wait_healthy,
    write_env_file,
)
from scripts.dev.openfga_env_bootstrap import (
    main as env_main,
)

# Compat aliases for tests/fixtures/openfga.py
_ENV_PATH = TEST_ENV_PATH
_DEFAULT_API_URL = DEFAULT_TEST_API_URL
_wait_healthy = wait_healthy

__all__ = [
    "_DEFAULT_API_URL",
    "_ENV_PATH",
    "_wait_healthy",
    "apply_env_file_to_environ",
    "load_env_file",
    "write_env_file",
]


def main(argv: list[str] | None = None) -> int:
    args = list(argv) if argv is not None else list(sys.argv[1:])
    if "--api-url" not in args:
        args = ["--api-url", DEFAULT_TEST_API_URL, *args]
    if "--env-path" not in args:
        args = ["--env-path", str(TEST_ENV_PATH), *args]
    return env_main(args)


if __name__ == "__main__":
    raise SystemExit(main())
