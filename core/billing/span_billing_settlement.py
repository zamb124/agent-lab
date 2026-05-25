"""
Идемпотентность списания: составной ключ span_id + rule_id; совместимость со старым ключом только по span.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

from core.types import parse_json_value

if TYPE_CHECKING:
    from core.db.storage import Storage

# Старый путь: одно списание на span (атрибуты platform.billing.*).
LEGACY_SPAN_ONLY_RULE_ID = "__legacy_span_only__"

_SETTLED_PREFIX = "billing:settled:"
_LEGACY_PREFIX = "billing:settled_span:"


def _usage_id_from_storage_raw(raw: str, *, span_id: str, rule_id: str) -> str:
    """
    Storage хранит JSONB: json.dumps(usage_id) при записи превращается в скаляр string;
    при чтении AsyncPG может отдать уже Python-str без JSON-кавычек — тогда json.loads падает.
    """
    stripped = raw.strip()
    if not stripped:
        raise ValueError(f"settlement composite key {span_id!r}/{rule_id!r}: usage_id пуст")
    try:
        parsed = parse_json_value(stripped, "settlement.usage_id")
    except ValueError as exc:
        if stripped.startswith(("{", "[", '"')):
            raise ValueError(
                f"settlement composite key {span_id!r}/{rule_id!r}: ожидалась строка usage_id"
            ) from exc
        return raw
    if not isinstance(parsed, str):
        raise ValueError(
            f"settlement composite key {span_id!r}/{rule_id!r}: ожидалась строка usage_id, получено {type(parsed).__name__}"
        )
    return parsed


class SpanBillingSettlement:
    def __init__(self, storage: "Storage") -> None:
        self._storage: Storage = storage

    def _composite_key(self, span_id: str, rule_id: str) -> str:
        return f"{_SETTLED_PREFIX}{span_id}:{rule_id}"

    def _legacy_key(self, span_id: str) -> str:
        return f"{_LEGACY_PREFIX}{span_id}"

    async def get_usage_id(self, span_id: str, rule_id: str) -> str | None:
        raw = await self._storage.get(self._composite_key(span_id, rule_id), force_global=True)
        if raw:
            return _usage_id_from_storage_raw(raw, span_id=span_id, rule_id=rule_id)
        if rule_id == LEGACY_SPAN_ONLY_RULE_ID:
            raw_old = await self._storage.get(self._legacy_key(span_id), force_global=True)
            if not raw_old:
                return None
            return _usage_id_from_storage_raw(raw_old, span_id=span_id, rule_id=LEGACY_SPAN_ONLY_RULE_ID)
        return None

    async def mark(self, span_id: str, rule_id: str, usage_id: str) -> None:
        _ = await self._storage.set(
            self._composite_key(span_id, rule_id),
            json.dumps(usage_id),
            force_global=True,
        )
        if rule_id == LEGACY_SPAN_ONLY_RULE_ID:
            _ = await self._storage.set(self._legacy_key(span_id), json.dumps(usage_id), force_global=True)
