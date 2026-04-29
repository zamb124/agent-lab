"""
Сценарии каталога правил, близкие к продакшен-конфигуратору: несколько правил, группы, first_win, смешанные match.
Без БД.
"""

from __future__ import annotations

import json

import pytest

from core.billing.settlement_rules import (
    SettlementApplicationMode,
    SettlementRule,
    SettlementRuleMatch,
    SettlementRulesDocument,
    parse_settlement_rules_json,
    resolve_matched_rules,
    rule_matches_span,
)


def _span(**kwargs: object) -> dict:
    base = {
        "span_id": "s1",
        "operation_name": "flows.llm.completion",
        "service_name": "flows",
        "event_type": None,
        "attributes": {},
    }
    base.update(kwargs)
    return base


def test_empty_match_matches_any_span_with_dict_attributes() -> None:
    rule = SettlementRule(
        rule_id="catch_all",
        resource_name="llm:*",
        usage_type="llm_request",
        match=SettlementRuleMatch(),
    )
    assert rule_matches_span(rule, _span()) is True
    assert rule_matches_span(rule, _span(attributes={"x": 1})) is True


def test_production_like_document_all_matching_stack_fixed_plus_tokens() -> None:
    """
    Один span: фикс за вызов (const:1) + строка по токенам — разные rule_id, без exclusive_group.
    """
    doc = SettlementRulesDocument(
        application_mode=SettlementApplicationMode.ALL_MATCHING,
        rules=[
            SettlementRule(
                rule_id="llm_per_call",
                priority=10,
                resource_name="llm:*",
                usage_type="llm_request",
                quantity_from="const:1",
                match=SettlementRuleMatch(
                    operation_name_prefix="flows.llm.",
                    service_name_equals="flows",
                ),
            ),
            SettlementRule(
                rule_id="llm_per_token",
                priority=20,
                resource_name="llm:*",
                usage_type="llm_request",
                quantity_from="attr:platform.llm.total_tokens",
                match=SettlementRuleMatch(operation_name_prefix="flows.llm."),
            ),
        ],
    )
    span = _span(
        operation_name="flows.llm.completion",
        attributes={"platform.llm.total_tokens": 500},
    )
    out = resolve_matched_rules(doc, span)
    assert {r.rule_id for r in out} == {"llm_per_call", "llm_per_token"}


def test_exclusive_group_prevents_double_llm_line_same_group() -> None:
    doc = SettlementRulesDocument(
        application_mode=SettlementApplicationMode.ALL_MATCHING,
        rules=[
            SettlementRule(
                rule_id="cheap",
                priority=50,
                exclusive_group="llm_billing",
                resource_name="llm:*",
                usage_type="llm_request",
                match=SettlementRuleMatch(operation_name_prefix="agent."),
            ),
            SettlementRule(
                rule_id="expensive",
                priority=5,
                exclusive_group="llm_billing",
                resource_name="llm:*",
                usage_type="llm_request",
                match=SettlementRuleMatch(operation_name_prefix="agent."),
            ),
        ],
    )
    span = _span(operation_name="agent.react.turn")
    out = resolve_matched_rules(doc, span)
    assert len(out) == 1
    assert out[0].rule_id == "expensive"


def test_first_win_prefers_lower_priority_number_among_standalone() -> None:
    doc = SettlementRulesDocument(
        application_mode=SettlementApplicationMode.FIRST_WIN,
        rules=[
            SettlementRule(
                rule_id="wide",
                priority=100,
                resource_name="livekit:*",
                usage_type="tool_call",
                match=SettlementRuleMatch(operation_name_prefix="sync."),
            ),
            SettlementRule(
                rule_id="narrow",
                priority=5,
                resource_name="livekit:*",
                usage_type="tool_call",
                match=SettlementRuleMatch(
                    operation_name_prefix="sync.command.",
                    service_name_equals="sync",
                ),
            ),
        ],
    )
    span = _span(operation_name="sync.command.execute", service_name="sync")
    out = resolve_matched_rules(doc, span)
    assert len(out) == 1
    assert out[0].rule_id == "narrow"


def test_attribute_route_prod_billing_resource_name_condition() -> None:
    rule = SettlementRule(
        rule_id="bill_attr",
        resource_name="livekit:*",
        usage_type="tool_call",
        match=SettlementRuleMatch(
            attribute_equals={
                "platform.billing.resource_name": "livekit:room_minute",
            },
        ),
    )
    span_ok = _span(
        operation_name="anything",
        attributes={"platform.billing.resource_name": "livekit:room_minute"},
    )
    span_bad = _span(
        operation_name="anything",
        attributes={"platform.billing.resource_name": "livekit:other"},
    )
    assert rule_matches_span(rule, span_ok) is True
    assert rule_matches_span(rule, span_bad) is False


def test_parse_exported_json_roundtrip_stable_rule_ids() -> None:
    raw = json.dumps(
        {
            "version": 3,
            "application_mode": "all_matching",
            "rules": [
                {
                    "rule_id": "550e8400-e29b-41d4-a716-446655440000",
                    "enabled": True,
                    "priority": 1,
                    "exclusive_group": None,
                    "resource_name": "embedding:*",
                    "usage_type": "embedding_request",
                    "quantity_from": "const:1",
                    "match": {
                        "operation_name_prefix": "rag.embed.",
                        "event_type_equals": "batch.end",
                    },
                }
            ],
        }
    )
    doc = parse_settlement_rules_json(raw)
    assert doc.version == 3
    assert doc.rules[0].rule_id == "550e8400-e29b-41d4-a716-446655440000"
    span_hit = _span(operation_name="rag.embed.batch", event_type="batch.end")
    span_miss = _span(operation_name="rag.embed.batch", event_type="start")
    assert rule_matches_span(doc.rules[0], span_hit) is True
    assert rule_matches_span(doc.rules[0], span_miss) is False
