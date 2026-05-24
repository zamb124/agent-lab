"""
Матчинг правил списания, resolve, quantity_from, parse_settlement_rules_json.
Без БД и без моков платформы — только чистые функции и Pydantic.
"""

from __future__ import annotations

import json

import pytest
from pydantic import ValidationError

from core.billing.settlement_rules import (
    SettlementApplicationMode,
    SettlementRule,
    SettlementRuleMatch,
    SettlementRulesDocument,
    parse_settlement_rules_json,
    quantity_from_span,
    resolve_matched_rules,
    rule_matches_span,
)
from core.tracing.models import BillingSettlementSpan
from core.types import JsonObject


def _span(
    *,
    operation_name: str = "flows.node.run",
    service_name: str = "flows",
    event_type: str | None = None,
    attributes: JsonObject | None = None,
) -> BillingSettlementSpan:
    return BillingSettlementSpan(
        span_id="s1",
        trace_id="t1",
        operation_name=operation_name,
        service_name=service_name,
        event_type=event_type,
        attributes=attributes if attributes is not None else {},
    )


def test_parse_settlement_rules_json_minimal_document() -> None:
    doc = parse_settlement_rules_json("{}")
    assert doc.version == 1
    assert doc.application_mode == SettlementApplicationMode.ALL_MATCHING
    assert doc.rules == []


def test_parse_settlement_rules_json_full_roundtrip() -> None:
    payload = {
        "version": 2,
        "application_mode": "first_win",
        "rules": [
            {
                "rule_id": "r1",
                "enabled": True,
                "priority": 7,
                "exclusive_group": None,
                "resource_name": "llm:*",
                "usage_type": "llm_request",
                "quantity_from": "const:2",
                "match": {"operation_name_prefix": "x."},
            }
        ],
    }
    raw = json.dumps(payload)
    doc = parse_settlement_rules_json(raw)
    assert doc.version == 2
    assert doc.application_mode == SettlementApplicationMode.FIRST_WIN
    assert len(doc.rules) == 1
    assert doc.rules[0].rule_id == "r1"
    assert doc.rules[0].quantity_from == "const:2"


def test_parse_settlement_rules_json_root_not_object_raises() -> None:
    with pytest.raises(ValueError, match="корень должен быть объектом"):
        parse_settlement_rules_json("[1]")


def test_parse_settlement_rules_json_invalid_json_raises() -> None:
    with pytest.raises(json.JSONDecodeError):
        parse_settlement_rules_json("not json {")


def test_settlement_rule_resource_name_without_colon_raises() -> None:
    with pytest.raises(ValidationError):
        SettlementRule(
            rule_id="a",
            resource_name="bad",
            usage_type="llm_request",
            match=SettlementRuleMatch(),
        )


def test_settlement_rule_invalid_usage_type_raises() -> None:
    with pytest.raises(ValidationError, match="UsageType"):
        SettlementRule(
            rule_id="a",
            resource_name="llm:*",
            usage_type="not_a_usage_type",
            match=SettlementRuleMatch(),
        )


def test_rule_matches_operation_name_prefix() -> None:
    rule = SettlementRule(
        rule_id="r1",
        resource_name="livekit:*",
        usage_type="tool_call",
        match=SettlementRuleMatch(operation_name_prefix="flows."),
    )
    assert rule_matches_span(rule, _span(operation_name="flows.x")) is True
    assert rule_matches_span(rule, _span(operation_name="crm.x")) is False


def test_rule_matches_operation_name_equals() -> None:
    rule = SettlementRule(
        rule_id="r1",
        resource_name="livekit:*",
        usage_type="tool_call",
        match=SettlementRuleMatch(operation_name_equals="exact.op"),
    )
    assert rule_matches_span(rule, _span(operation_name="exact.op")) is True
    assert rule_matches_span(rule, _span(operation_name="exact.op.other")) is False


def test_rule_matches_operation_name_regex() -> None:
    rule = SettlementRule(
        rule_id="r1",
        resource_name="livekit:*",
        usage_type="tool_call",
        match=SettlementRuleMatch(operation_name_regex=r"^flows\.(llm|agent)\."),
    )
    assert rule_matches_span(rule, _span(operation_name="flows.llm.invoke")) is True
    assert rule_matches_span(rule, _span(operation_name="flows.tool.invoke")) is False


def test_rule_matches_service_name_equals() -> None:
    rule = SettlementRule(
        rule_id="r1",
        resource_name="llm:*",
        usage_type="llm_request",
        match=SettlementRuleMatch(service_name_equals="rag"),
    )
    assert rule_matches_span(rule, _span(service_name="rag")) is True
    assert rule_matches_span(rule, _span(service_name="flows")) is False


def test_rule_matches_event_type_equals() -> None:
    rule = SettlementRule(
        rule_id="r1",
        resource_name="llm:*",
        usage_type="llm_request",
        match=SettlementRuleMatch(event_type_equals="span.end"),
    )
    assert rule_matches_span(rule, _span(event_type="span.end")) is True
    assert rule_matches_span(rule, _span(event_type="other")) is False


def test_rule_matches_prefix_and_attribute_and_equals_and() -> None:
    rule = SettlementRule(
        rule_id="r1",
        resource_name="llm:*",
        usage_type="llm_request",
        match=SettlementRuleMatch(
            operation_name_prefix="api.",
            operation_name_equals="api.v1.call",
            service_name_equals="sync",
            event_type_equals="e1",
            attribute_equals={"k": 1},
        ),
    )
    ok = _span(
        operation_name="api.v1.call",
        service_name="sync",
        event_type="e1",
        attributes={"k": 1},
    )
    assert rule_matches_span(rule, ok) is True
    assert rule_matches_span(rule, _span(operation_name="api.other", attributes={"k": 1})) is False
    assert rule_matches_span(rule, _span(operation_name="api.v1.call", attributes={"k": 2})) is False


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


def test_rule_matches_attribute_regex() -> None:
    rule = SettlementRule(
        rule_id="r1",
        resource_name="llm:*",
        usage_type="llm_request",
        match=SettlementRuleMatch(
            attribute_regex={"platform.llm.model": r"^(gpt|claude)-"},
        ),
    )
    assert rule_matches_span(rule, _span(attributes={"platform.llm.model": "gpt-4o"})) is True
    assert rule_matches_span(rule, _span(attributes={"platform.llm.model": "deepseek-chat"})) is False
    assert rule_matches_span(rule, _span(attributes={})) is False


def test_settlement_match_invalid_regex_raises() -> None:
    with pytest.raises(ValidationError, match="невалидный regex"):
        SettlementRuleMatch(operation_name_regex="[")


def test_rule_matches_attribute_keys_present() -> None:
    rule = SettlementRule(
        rule_id="r1",
        resource_name="llm:*",
        usage_type="llm_request",
        match=SettlementRuleMatch(attribute_keys_present=["platform.billing.settlement_quantity_rub"]),
    )
    assert rule_matches_span(rule, _span(attributes={})) is False
    assert rule_matches_span(
        rule, _span(attributes={"platform.billing.settlement_quantity_rub": None})
    ) is False
    assert rule_matches_span(
        rule, _span(attributes={"platform.billing.settlement_quantity_rub": 43})
    ) is True


def test_billing_settlement_span_rejects_non_object_attributes() -> None:
    with pytest.raises(ValidationError):
        BillingSettlementSpan(
            span_id="s1",
            trace_id="t1",
            operation_name="x",
            service_name="flows",
            attributes="not-a-dict",
        )


def test_billing_settlement_span_rejects_non_string_operation_name() -> None:
    with pytest.raises(ValidationError):
        BillingSettlementSpan(
            span_id="s1",
            trace_id="t1",
            operation_name=123,
            service_name="flows",
        )


def test_resolve_matched_rules_empty_rules() -> None:
    doc = SettlementRulesDocument(rules=[])
    assert resolve_matched_rules(doc, _span()) == []


def test_resolve_matched_rules_no_match() -> None:
    doc = SettlementRulesDocument(
        rules=[
            SettlementRule(
                rule_id="r1",
                resource_name="llm:*",
                usage_type="llm_request",
                match=SettlementRuleMatch(operation_name_prefix="nope."),
            )
        ],
    )
    assert resolve_matched_rules(doc, _span(operation_name="yes.op")) == []


def test_resolve_disabled_rule_excluded() -> None:
    doc = SettlementRulesDocument(
        rules=[
            SettlementRule(
                rule_id="off",
                enabled=False,
                resource_name="llm:*",
                usage_type="llm_request",
                match=SettlementRuleMatch(operation_name_prefix="z."),
            ),
            SettlementRule(
                rule_id="on",
                resource_name="livekit:*",
                usage_type="tool_call",
                match=SettlementRuleMatch(operation_name_prefix="z."),
            ),
        ],
    )
    out = resolve_matched_rules(doc, _span(operation_name="z.q"))
    assert len(out) == 1
    assert out[0].rule_id == "on"


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
                resource_name="livekit:*",
                usage_type="tool_call",
                match=SettlementRuleMatch(operation_name_prefix="x."),
            ),
        ],
    )
    span = _span(operation_name="x.y")
    out = resolve_matched_rules(doc, span)
    assert len(out) == 1
    assert out[0].rule_id == "a"


def test_resolve_first_win_across_two_exclusive_groups_picks_best_priority() -> None:
    doc = SettlementRulesDocument(
        application_mode=SettlementApplicationMode.FIRST_WIN,
        rules=[
            SettlementRule(
                rule_id="ga",
                priority=30,
                exclusive_group="g1",
                resource_name="llm:*",
                usage_type="llm_request",
                match=SettlementRuleMatch(operation_name_prefix="m."),
            ),
            SettlementRule(
                rule_id="gb",
                priority=5,
                exclusive_group="g2",
                resource_name="livekit:*",
                usage_type="tool_call",
                match=SettlementRuleMatch(operation_name_prefix="m."),
            ),
        ],
    )
    out = resolve_matched_rules(doc, _span(operation_name="m.x"))
    assert len(out) == 1
    assert out[0].rule_id == "gb"


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
                resource_name="livekit:*",
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


def test_resolve_two_exclusive_groups_both_winners_plus_standalone() -> None:
    doc = SettlementRulesDocument(
        application_mode=SettlementApplicationMode.ALL_MATCHING,
        rules=[
            SettlementRule(
                rule_id="a1",
                priority=1,
                exclusive_group="A",
                resource_name="llm:*",
                usage_type="llm_request",
                match=SettlementRuleMatch(operation_name_prefix="q."),
            ),
            SettlementRule(
                rule_id="a2",
                priority=9,
                exclusive_group="A",
                resource_name="livekit:*",
                usage_type="tool_call",
                match=SettlementRuleMatch(operation_name_prefix="q."),
            ),
            SettlementRule(
                rule_id="b1",
                priority=2,
                exclusive_group="B",
                resource_name="embedding:*",
                usage_type="embedding_request",
                match=SettlementRuleMatch(operation_name_prefix="q."),
            ),
            SettlementRule(
                rule_id="standalone",
                priority=3,
                resource_name="llm:*",
                usage_type="llm_request",
                match=SettlementRuleMatch(operation_name_prefix="q."),
            ),
        ],
    )
    out = resolve_matched_rules(doc, _span(operation_name="q.x"))
    ids = {r.rule_id for r in out}
    assert ids == {"a1", "b1", "standalone"}


def test_quantity_const_and_attr() -> None:
    span = _span(attributes={"platform.llm.input_tokens": 7})
    assert quantity_from_span("const:3", span) == 3
    assert quantity_from_span("attr:platform.llm.input_tokens", span) == 7


def test_quantity_const_zero_allowed() -> None:
    assert quantity_from_span("const:0", _span()) == 0


def test_quantity_const_negative_raises() -> None:
    with pytest.raises(ValueError, match=">= 0"):
        quantity_from_span("const:-1", _span())


def test_quantity_attr_empty_key_raises() -> None:
    with pytest.raises(ValueError, match="пустой ключ"):
        quantity_from_span("attr:", _span())


def test_quantity_attr_whitespace_only_key_raises() -> None:
    with pytest.raises(ValueError, match="пустой ключ"):
        quantity_from_span("attr:   ", _span())


def test_quantity_from_invalid_format_raises() -> None:
    with pytest.raises(ValueError, match="неизвестный формат"):
        quantity_from_span("bad", _span())


def test_quantity_attr_missing_raises() -> None:
    with pytest.raises(ValueError, match="атрибут"):
        quantity_from_span("attr:platform.missing", _span(attributes={}))


def test_quantity_attr_not_int_raises() -> None:
    with pytest.raises(ValueError, match="invalid literal"):
        quantity_from_span("attr:platform.x", _span(attributes={"platform.x": "nope"}))


def test_quantity_attr_zero_allowed() -> None:
    assert quantity_from_span("attr:platform.x", _span(attributes={"platform.x": 0})) == 0
