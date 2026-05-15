"""
Структура внешних ссылок на записи в интеграциях: attributes.external_refs.

Ключ верхнего уровня — provider_id зарегистрированного коннектора (строка).
"""

from __future__ import annotations

from datetime import datetime, UTC
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class ExternalRef(BaseModel):
    """Один источник: стабильный record_id у провайдера и публичные метаданные."""

    model_config = ConfigDict(extra="forbid")

    record_id: str = Field(min_length=1)
    account_key: str | None = None
    last_seen_at: datetime | None = None
    raw_version: str | None = None

    def to_json_dict(self) -> dict[str, Any]:
        return self.model_dump(mode="json", exclude_none=True)


def merge_external_refs(
    attributes: dict[str, Any],
    *,
    source_id: str,
    ref: ExternalRef,
) -> dict[str, Any]:
    """
    Возвращает копию attributes с обновлённым external_refs[source_id] без затирания других источников.
    """
    if not source_id.strip():
        raise ValueError("source_id обязателен")
    raw_refs = attributes.get("external_refs")
    if raw_refs is None:
        refs: dict[str, Any] = {}
    elif not isinstance(raw_refs, dict):
        raise ValueError("attributes.external_refs должен быть объектом")
    else:
        refs = dict(raw_refs)
    refs[source_id] = ref.to_json_dict()
    out = dict(attributes)
    out["external_refs"] = refs
    return out


def external_ref_now(
    *,
    record_id: str,
    account_key: str | None = None,
    raw_version: str | None = None,
) -> ExternalRef:
    return ExternalRef(
        record_id=record_id,
        account_key=account_key,
        last_seen_at=datetime.now(UTC),
        raw_version=raw_version,
    )
