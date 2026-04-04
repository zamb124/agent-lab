"""
Матчинг правил списания и quantity_from (без БД).
"""

from __future__ import annotations

import pytest

from core.billing.settlement_rules import (
    SettlementApplicationMode,
    SettlementRule,
    SettlementRuleMatch,
    SettlementRulesDocument,
    quantity_from_span,
    resolve_matched_rules,
    rule_matches_span,
)


def _span(**kwargs: object) -> dict:
    base = {
        "span_id": "s1",
        "operation_name": "flows.node.run",
        "service_name": "flows",
        "event_type": None,
        "attributes": {},
    }
    base.update(kwargs)
    return base


def test_rule_matches_operation_name_prefix() -> None:
    rule = SettlementRule(
        rule_id="r1",
        resource_name="tool:*",
        usage_type="tool_call",
        match=SettlementRuleMatch(operation_name_prefix="flows."),
    )
    assert rule_matches_span(rule, _span(operation_name="flows.x")) is True
    assert rule_matches_span(rule, _span(operation_name="crm.x")) is False


def test_rule_matches_attribute_equals() -> None:
    rule = SettlementRule(
        rule_id="r1",
        resource_name="llm:*",
        usage_type="llm_request",
        match=SettlementRuleMatch(
            attribute_equals={"platform.billing.resource_name": "llm:gpt-4"},
        ),
    )
    attrs = {"platform.billing.resource_name": "llm:gpt-4"}
    assert rule_matches_span(rule, _span(attributes=attrs)) is True
    assert rule_matches_span(rule, _span(attributes={})) is False


def test_resolve_first_win() -> None:
    doc = SettlementRulesDocument(
        application_mode=SettlementApplicationMode.FIRST_WIN,
        rules=[
            SettlementRule(
                rule_id="b",
                priority=20,
                resource_name="llm:*",
                usage_type="llm_request",
                match=SettlementRuleMatch(operation_name_prefix="x."),
            ),
            SettlementRule(
                rule_id="a",
                priority=10,
                resource_name="tool:*",
                usage_type="tool_call",
                match=SettlementRuleMatch(operation_name_prefix="x."),
            ),
        ],
    )
    span = _span(operation_name="x.y")
    out = resolve_matched_rules(doc, span)
    assert len(out) == 1
    assert out[0].rule_id == "a"


def test_resolve_exclusive_group_one_winner() -> None:
    doc = SettlementRulesDocument(
        application_mode=SettlementApplicationMode.ALL_MATCHING,
        rules=[
            SettlementRule(
                rule_id="low",
                priority=50,
                exclusive_group="g",
                resource_name="llm:*",
                usage_type="llm_request",
                match=SettlementRuleMatch(operation_name_prefix="z."),
            ),
            SettlementRule(
                rule_id="high",
                priority=5,
                exclusive_group="g",
                resource_name="tool:*",
                usage_type="tool_call",
                match=SettlementRuleMatch(operation_name_prefix="z."),
            ),
            SettlementRule(
                rule_id="solo",
                priority=1,
                resource_name="embedding:*",
                usage_type="embedding_request",
                match=SettlementRuleMatch(operation_name_prefix="z."),
            ),
        ],
    )
    span = _span(operation_name="z.q")
    out = resolve_matched_rules(doc, span)
    ids = {r.rule_id for r in out}
    assert ids == {"high", "solo"}


def test_quantity_const_and_attr() -> None:
    span = _span(attributes={"platform.llm.input_tokens": 7})
    assert quantity_from_span("const:3", span) == 3
    assert quantity_from_span("attr:platform.llm.input_tokens", span) == 7


def test_quantity_from_invalid() -> None:
    with pytest.raises(ValueError, match="неизвестный формат"):
        quantity_from_span("bad", _span())

    with pytest.raises(ValueError, match="атрибут"):
        quantity_from_span("attr:platform.missing", _span(attributes={}))
