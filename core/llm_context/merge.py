"""Хелперы слияния наложений профиля контекста LLM."""

from __future__ import annotations

from core.types import JsonObject, require_json_object


def deep_merge_dict(base: JsonObject, override: JsonObject) -> JsonObject:
    """Рекурсивно сливает JSON-подобные словари; override побеждает."""
    out: JsonObject = dict(base)
    for key, value in override.items():
        existing = out.get(key)
        if isinstance(existing, dict) and isinstance(value, dict):
            out[key] = deep_merge_dict(
                require_json_object(existing, f"{key}.base"),
                require_json_object(value, f"{key}.override"),
            )
        else:
            out[key] = value
    return out


def merge_dict_layers(*layers: JsonObject | None) -> JsonObject:
    """Сливает опциональные слои словарей по порядку."""
    merged: JsonObject = {}
    for layer in layers:
        if layer is None:
            continue
        merged = deep_merge_dict(merged, layer)
    return merged


__all__ = ["deep_merge_dict", "merge_dict_layers"]
