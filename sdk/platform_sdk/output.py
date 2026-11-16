"""Вывод CLI: JSON в stdout для машин, прогресс в stderr."""

from __future__ import annotations

import json
import sys
from contextvars import ContextVar

from platform_sdk.errors import PlatformCliError
from platform_sdk.json_types import as_json

_JSON = ContextVar("platform_cli_json", default=False)


def configure_output(*, force_json: bool) -> None:
    _JSON.set(force_json or not sys.stdout.isatty())


def json_mode() -> bool:
    return _JSON.get()


def emit(value: object) -> None:
    encoded = as_json(value, "output")
    if json_mode():
        sys.stdout.write(json.dumps(encoded, ensure_ascii=False) + "\n")
        return
    sys.stdout.write(json.dumps(encoded, ensure_ascii=False, indent=2) + "\n")


def emit_line(text: str) -> None:
    """Прогресс и человекочитаемые заметки. В JSON-режиме stdout не трогается."""
    sys.stderr.write(text + "\n")


def emit_error(error: PlatformCliError) -> None:
    sys.stderr.write(json.dumps(error.payload(), ensure_ascii=False) + "\n")
