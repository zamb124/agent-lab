"""
Слияние частичного ``index_profile_config`` с базовым ``IndexProfileConfig``.
"""

from __future__ import annotations

from core.llm_context.merge import deep_merge_dict
from core.rag_indexing_schema import IndexProfileConfig
from core.types import JsonObject, require_json_object


def merge_index_profile_config(base: IndexProfileConfig, override: JsonObject) -> IndexProfileConfig:
    """
    Частичное переопределение профиля индексации (например только ``split.strategy``).

    ``override`` — JSON-объект с теми же ключами верхнего уровня, что у ``IndexProfileConfig``;
    вложенные объекты (``split``, ``parsing``) сливаются с базой.
    """
    base_payload = require_json_object(base.model_dump(mode="json"), "index_profile.base")
    merged = deep_merge_dict(base_payload, override)
    return IndexProfileConfig.model_validate(merged)


def merge_index_profile_dict_overlays(
    *layers: JsonObject | None,
) -> JsonObject | None:
    """Последовательное наложение словарей; ``None`` пропускаются."""
    acc: JsonObject | None = None
    for layer in layers:
        if layer is None:
            continue
        if acc is None:
            acc = dict(layer)
        else:
            acc = deep_merge_dict(acc, layer)
    return acc
