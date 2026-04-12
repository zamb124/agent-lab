"""
Слияние частичного ``index_profile_config`` с базовым ``IndexProfileConfig``.
"""

from __future__ import annotations

from typing import Any

from core.rag_indexing_schema import IndexProfileConfig


def deep_merge_dict(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    """Рекурсивное слияние словарей; значения из ``override`` перекрывают ``base``."""
    out = dict(base)
    for key, value in override.items():
        if (
            key in out
            and isinstance(out[key], dict)
            and isinstance(value, dict)
        ):
            out[key] = deep_merge_dict(out[key], value)
        else:
            out[key] = value
    return out


def merge_index_profile_config(base: IndexProfileConfig, override: dict[str, Any]) -> IndexProfileConfig:
    """
    Частичное переопределение профиля индексации (например только ``split.strategy``).

    ``override`` — JSON-объект с теми же ключами верхнего уровня, что у ``IndexProfileConfig``;
    вложенные объекты (``split``, ``parsing``) сливаются с базой.
    """
    if not isinstance(override, dict):
        raise TypeError("override должен быть dict")
    merged = deep_merge_dict(base.model_dump(mode="json"), override)
    return IndexProfileConfig.model_validate(merged)


def merge_index_profile_dict_overlays(
    *layers: dict[str, Any] | None,
) -> dict[str, Any] | None:
    """Последовательное наложение словарей; ``None`` пропускаются."""
    acc: dict[str, Any] | None = None
    for layer in layers:
        if layer is None:
            continue
        if acc is None:
            acc = dict(layer)
        else:
            acc = deep_merge_dict(acc, layer)
    return acc
