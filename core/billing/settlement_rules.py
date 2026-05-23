"""
Каталог правил списания по spans: матчинг и выбор правил (без I/O).
"""

from __future__ import annotations

import json
import re
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field, field_validator, model_validator

from core.models.billing_models import UsageType


class SettlementApplicationMode(str, Enum):
    """Как применять несколько совпавших правил после учёта exclusive_group."""

    ALL_MATCHING = "all_matching"
    FIRST_WIN = "first_win"


class SettlementRuleMatch(BaseModel):
    """Условия на поля span; заданные поля объединяются через AND."""

    operation_name_prefix: str | None = None
    operation_name_equals: str | None = None
    operation_name_regex: str | None = None
    service_name_equals: str | None = None
    service_name_regex: str | None = None
    event_type_equals: str | None = None
    event_type_regex: str | None = None
    attribute_equals: dict[str, Any] = Field(default_factory=dict)
    attribute_regex: dict[str, str] = Field(
        default_factory=dict,
        description="Все перечисленные attributes должны матчить regex через re.search(str(value))",
    )
    attribute_keys_present: list[str] = Field(
        default_factory=list,
        description="Все перечисленные ключи должны быть в attributes и не None",
    )

    @model_validator(mode="after")
    def regex_patterns_must_compile(self) -> "SettlementRuleMatch":
        patterns: list[tuple[str, str]] = []
        for field_name in ("operation_name_regex", "service_name_regex", "event_type_regex"):
            value = getattr(self, field_name)
            if value:
                patterns.append((field_name, value))
        for key, value in self.attribute_regex.items():
            if value:
                patterns.append((f"attribute_regex.{key}", value))
        for label, pattern in patterns:
            try:
                re.compile(pattern)
            except re.error as e:
                raise ValueError(f"невалидный regex {label}: {e}") from e
        return self


class SettlementRule(BaseModel):
    rule_id: str = Field(min_length=1)
    enabled: bool = True
    priority: int = 100
    exclusive_group: str | None = None
    resource_name: str = Field(min_length=3)
    usage_type: str = Field(min_length=1)
    quantity_from: str = Field(default="const:1")
    match: SettlementRuleMatch = Field(default_factory=SettlementRuleMatch)

    @field_validator("usage_type")
    @classmethod
    def usage_type_must_be_valid(cls, v: str) -> str:
        try:
            UsageType(v)
        except ValueError as e:
            raise ValueError(f"неизвестный UsageType: {v!r}") from e
        return v

    @field_validator("resource_name")
    @classmethod
    def resource_name_format(cls, v: str) -> str:
        if ":" not in v:
            raise ValueError(f"resource_name ожидается как category:resource, получено {v!r}")
        return v


class SettlementRulesDocument(BaseModel):
    version: int = 1
    application_mode: SettlementApplicationMode = SettlementApplicationMode.ALL_MATCHING
    rules: list[SettlementRule] = Field(default_factory=list)


def parse_settlement_rules_json(raw: str) -> SettlementRulesDocument:
    data = json.loads(raw)
    if not isinstance(data, dict):
        raise ValueError("settlement rules: корень должен быть объектом")
    return SettlementRulesDocument.model_validate(data)


def _attr_value(attrs: dict[str, Any], key: str) -> Any:
    if key in attrs:
        return attrs[key]
    return None


def _regex_matches(pattern: str | None, value: Any) -> bool:
    if not pattern:
        return True
    if value is None:
        return False
    try:
        return re.search(pattern, str(value)) is not None
    except re.error as e:
        raise ValueError(f"невалидный regex {pattern!r}: {e}") from e


def rule_matches_span(rule: SettlementRule, span_dict: dict[str, Any]) -> bool:
    m = rule.match
    if m.operation_name_prefix:
        op = span_dict.get("operation_name") or ""
        if not isinstance(op, str) or not op.startswith(m.operation_name_prefix):
            return False
    if m.operation_name_equals is not None:
        if span_dict.get("operation_name") != m.operation_name_equals:
            return False
    if not _regex_matches(m.operation_name_regex, span_dict.get("operation_name")):
        return False
    if m.service_name_equals is not None:
        if span_dict.get("service_name") != m.service_name_equals:
            return False
    if not _regex_matches(m.service_name_regex, span_dict.get("service_name")):
        return False
    if m.event_type_equals is not None:
        if span_dict.get("event_type") != m.event_type_equals:
            return False
    if not _regex_matches(m.event_type_regex, span_dict.get("event_type")):
        return False
    attrs = span_dict.get("attributes") or {}
    if not isinstance(attrs, dict):
        return False
    for attr_key, expected in m.attribute_equals.items():
        if _attr_value(attrs, attr_key) != expected:
            return False
    for attr_key, pattern in m.attribute_regex.items():
        if not _regex_matches(pattern, _attr_value(attrs, attr_key)):
            return False
    for key in m.attribute_keys_present:
        if key not in attrs or attrs.get(key) is None:
            return False
    return True


def resolve_matched_rules(doc: SettlementRulesDocument, span_dict: dict[str, Any]) -> list[SettlementRule]:
    matched = [r for r in doc.rules if r.enabled and rule_matches_span(r, span_dict)]
    if not matched:
        return []

    by_group: dict[str | None, list[SettlementRule]] = {}
    standalone: list[SettlementRule] = []
    for r in matched:
        if r.exclusive_group is None:
            standalone.append(r)
        else:
            by_group.setdefault(r.exclusive_group, []).append(r)

    after_groups: list[SettlementRule] = list(standalone)
    for _g, items in by_group.items():
        items_sorted = sorted(items, key=lambda x: x.priority)
        after_groups.append(items_sorted[0])

    after_groups.sort(key=lambda x: x.priority)
    if doc.application_mode == SettlementApplicationMode.FIRST_WIN:
        return [after_groups[0]] if after_groups else []
    return after_groups


def quantity_from_span(quantity_from: str, span_dict: dict[str, Any]) -> int:
    if quantity_from.startswith("const:"):
        rest = quantity_from[len("const:") :].strip()
        q = int(rest)
        if q < 0:
            raise ValueError(f"const quantity должна быть >= 0: {quantity_from!r}")
        return q
    if quantity_from.startswith("attr:"):
        key = quantity_from[len("attr:") :].strip()
        if not key:
            raise ValueError(f"пустой ключ атрибута в {quantity_from!r}")
        attrs = span_dict.get("attributes") or {}
        if not isinstance(attrs, dict):
            raise ValueError("span без dict attributes")
        raw = attrs.get(key)
        if raw is None:
            raise ValueError(f"атрибут {key!r} отсутствует для quantity_from")
        q = int(raw)
        if q < 0:
            raise ValueError(f"quantity из атрибута {key!r} должна быть >= 0")
        return q
    raise ValueError(f"неизвестный формат quantity_from: {quantity_from!r}")
