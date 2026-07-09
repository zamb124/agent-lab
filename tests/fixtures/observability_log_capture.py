"""Shared helpers for structured log capture in observability metric tests."""

from __future__ import annotations

import ast
import asyncio
import json
import logging
import time
from collections.abc import Callable
from typing import cast

import pytest

from core.types import JsonObject, parse_json_object, require_json_object


def caplog_message_to_dict(raw: str) -> JsonObject:
    """structlog в caplog может дать JSON или repr(dict) в зависимости от рендера."""
    stripped = raw.strip()
    if stripped.startswith("{"):
        try:
            return parse_json_object(stripped, "caplog.message")
        except (json.JSONDecodeError, ValueError):
            pass
    try:
        return require_json_object(
            cast(object, ast.literal_eval(stripped)),
            "caplog.literal",
        )
    except (ValueError, SyntaxError) as exc:
        raise AssertionError(
            f"observability caplog: не удалось разобрать message: {raw[:200]!r}"
        ) from exc


def caplog_record_dict(rec: logging.LogRecord) -> JsonObject:
    return caplog_message_to_dict(rec.getMessage())


def find_caplog_record(
    caplog: pytest.LogCaptureFixture,
    *,
    message: str,
    logger_name: str | None = None,
) -> logging.LogRecord:
    for rec in caplog.records:
        if logger_name is not None and rec.name != logger_name:
            continue
        msg = rec.getMessage()
        if message in msg:
            return rec
        if msg.strip().startswith("{"):
            try:
                parsed = caplog_message_to_dict(msg)
                if parsed.get("message") == message:
                    return rec
            except AssertionError:
                continue
    scope = f" logger={logger_name!r}" if logger_name else ""
    raise AssertionError(f"Нет log record с событием {message!r}{scope}")


def find_caplog_records(
    caplog: pytest.LogCaptureFixture,
    *,
    message: str,
    logger_name: str | None = None,
) -> list[logging.LogRecord]:
    matched: list[logging.LogRecord] = []
    for rec in caplog.records:
        if logger_name is not None and rec.name != logger_name:
            continue
        msg = rec.getMessage()
        if message in msg:
            matched.append(rec)
            continue
        if msg.strip().startswith("{"):
            try:
                parsed = caplog_message_to_dict(msg)
                if parsed.get("message") == message:
                    matched.append(rec)
            except AssertionError:
                continue
    return matched


def require_log_fields(
    rec: logging.LogRecord,
    *,
    required: dict[str, type | tuple[type, ...]],
) -> JsonObject:
    fields = caplog_record_dict(rec)
    for key, expected_type in required.items():
        if key not in fields:
            raise AssertionError(f"Поле {key!r} отсутствует в log record: {fields!r}")
        value = fields[key]
        if not isinstance(value, expected_type):
            raise AssertionError(
                f"Поле {key!r}: ожидался {expected_type}, получено {type(value).__name__}={value!r}"
            )
    return fields


def require_numeric_field(
    fields: JsonObject,
    key: str,
    *,
    min_value: float = 0.0,
) -> float:
    raw = fields.get(key)
    if not isinstance(raw, (int, float)):
        raise AssertionError(f"Поле {key!r} должно быть числом, получено {raw!r}")
    numeric = float(raw)
    if numeric < min_value:
        raise AssertionError(f"Поле {key!r}={numeric} < {min_value}")
    return numeric


async def wait_for_caplog_event(
    caplog: pytest.LogCaptureFixture,
    *,
    message: str,
    logger_name: str | None = None,
    timeout: float = 8.0,
    poll_interval: float = 0.05,
    predicate: Callable[[JsonObject], bool] | None = None,
) -> logging.LogRecord:
    deadline = time.monotonic() + timeout
    last_count = len(caplog.records)
    while time.monotonic() < deadline:
        records = find_caplog_records(
            caplog,
            message=message,
            logger_name=logger_name,
        )
        if predicate is None:
            if records:
                return records[-1]
        else:
            for rec in reversed(records):
                fields = caplog_record_dict(rec)
                if predicate(fields):
                    return rec
        if len(caplog.records) != last_count:
            last_count = len(caplog.records)
        await asyncio.sleep(poll_interval)
    scope = f" logger={logger_name!r}" if logger_name else ""
    raise AssertionError(
        f"Событие {message!r} не появилось в caplog за {timeout}s{scope}"
    )
