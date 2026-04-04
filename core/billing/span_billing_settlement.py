"""
Идемпотентность списания: составной ключ span_id + rule_id; совместимость со старым ключом только по span.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from core.db.storage import Storage

# Старый путь: одно списание на span (атрибуты platform.billing.*).
LEGACY_SPAN_ONLY_RULE_ID = "__legacy_span_only__"

_SETTLED_PREFIX = "billing:settled:"
_LEGACY_PREFIX = "billing:settled_span:"


class SpanBillingSettlement:
    def __init__(self, storage: "Storage"):
        self._storage = storage

    def _composite_key(self, span_id: str, rule_id: str) -> str:
        return f"{_SETTLED_PREFIX}{span_id}:{rule_id}"

    def _legacy_key(self, span_id: str) -> str:
        return f"{_LEGACY_PREFIX}{span_id}"

    async def get_usage_id(self, span_id: str, rule_id: str) -> Optional[str]:
        raw = await self._storage.get(self._composite_key(span_id, rule_id), force_global=True)
        if raw:
            parsed = json.loads(raw)
            if not isinstance(parsed, str):
                raise ValueError(f"settlement composite key {span_id!r}/{rule_id!r}: ожидалась строка usage_id")
            return parsed
        if rule_id == LEGACY_SPAN_ONLY_RULE_ID:
            raw_old = await self._storage.get(self._legacy_key(span_id), force_global=True)
            if not raw_old:
                return None
            parsed_old = json.loads(raw_old)
            if not isinstance(parsed_old, str):
                raise ValueError(f"legacy settlement key {span_id!r}: ожидалась строка usage_id")
            return parsed_old
        return None

    async def mark(self, span_id: str, rule_id: str, usage_id: str) -> None:
        await self._storage.set(
            self._composite_key(span_id, rule_id),
            json.dumps(usage_id),
            force_global=True,
        )
        if rule_id == LEGACY_SPAN_ONLY_RULE_ID:
            await self._storage.set(self._legacy_key(span_id), json.dumps(usage_id), force_global=True)
