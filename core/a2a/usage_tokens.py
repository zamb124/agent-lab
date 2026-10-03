"""Coercion usage token counts after protobuf Struct / JSON round-trip."""

from __future__ import annotations

from core.types import JsonValue


def coerce_usage_token_count(raw: JsonValue, field: str) -> int:
    """Целые токены после Struct JSON часто приходят как float (7.0)."""
    if isinstance(raw, bool):
        raise ValueError(f"{field} must be an integer")
    if isinstance(raw, int):
        return raw
    if isinstance(raw, float) and raw.is_integer():
        return int(raw)
    raise ValueError(f"{field} must be an integer")


__all__ = ["coerce_usage_token_count"]
