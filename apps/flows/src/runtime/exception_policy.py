"""
Политика поглощения исключений (exception_as_response на ноде).
"""

from __future__ import annotations

import asyncio

from apps.flows.src.runtime.exceptions import BreakpointInterrupt, FlowInterrupt
from core.types import JsonObject, JsonValue, require_json_array


def normalize_allow_types(raw: JsonValue | None) -> list[str]:
    """Нормализует whitelist имён классов из конфига ноды (dict)."""
    if raw is None:
        return []
    try:
        items = require_json_array(raw, "exception_allow_types")
    except ValueError as exc:
        raise TypeError("exception_allow_types: ожидается list[str]") from exc
    out: list[str] = []
    for item in items:
        if not isinstance(item, str):
            raise TypeError(
                f"exception_allow_types: элемент должен быть str, получено {type(item).__name__}"
            )
        s = item.strip()
        if s:
            out.append(s)
    return out


def node_exception_policy(config: JsonObject) -> tuple[bool, list[str]]:
    """Читает флаги из сырого config ноды (как у BaseNode.config)."""
    raw_enabled = config.get("exception_as_response")
    if raw_enabled is None:
        enabled = False
    elif isinstance(raw_enabled, bool):
        enabled = raw_enabled
    else:
        raise TypeError("exception_as_response: ожидается bool")
    allow_types = normalize_allow_types(config.get("exception_allow_types"))
    return enabled, allow_types


def should_absorb_exception(
    exc: BaseException,
    *,
    enabled: bool,
    allow_types: list[str],
) -> bool:
    """
    Возвращает True, если исключение следует обработать как ответ (запись в execution_exceptions),
    а не пробрасывать.

    FlowInterrupt, BreakpointInterrupt, отмена и системные выходы никогда не поглощаются.
    При enabled=False всегда False.
    При пустом allow_types и enabled=True поглощается любое остальное исключение.
    Иначе поглощается только если type(exc).__name__ входит в allow_types.
    """
    if not enabled:
        return False
    if isinstance(exc, (FlowInterrupt, BreakpointInterrupt)):
        return False
    if isinstance(exc, asyncio.CancelledError):
        return False
    if isinstance(exc, (SystemExit, KeyboardInterrupt)):
        return False
    if not allow_types:
        return True
    return type(exc).__name__ in allow_types
