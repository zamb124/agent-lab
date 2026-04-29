"""
Дефолтный каталог settlement: матчинг по operation_name для основных спанов платформы.
"""

from __future__ import annotations

from core.billing.default_settlement_rules import default_settlement_rules_document
from core.billing.settlement_rules import resolve_matched_rules
from core.tracing import attributes as trace_attr


def _span(operation_name: str, attrs: dict | None = None) -> dict:
    return {
        "span_id": "s1",
        "operation_name": operation_name,
        "service_name": "flows",
        "event_type": None,
        "attributes": attrs or {},
    }


def test_default_document_first_win_single_rule_per_family() -> None:
    doc = default_settlement_rules_document()
    assert doc.application_mode.value == "first_win"
    assert len(doc.rules) == 10


def test_matches_llm_tracer_with_total_tokens() -> None:
    doc = default_settlement_rules_document()
    span = _span(
        "llm.gpt-4o",
        {trace_attr.ATTR_LLM_TOTAL_TOKENS: 100},
    )
    matched = resolve_matched_rules(doc, span)
    assert len(matched) == 1
    assert matched[0].rule_id == "llm_tracer_tokens"


def test_matches_openrouter_llm_usd_to_rub_before_tokens() -> None:
    doc = default_settlement_rules_document()
    span = _span(
        "llm.gpt-4o",
        {
            trace_attr.ATTR_LLM_PROVIDER: "openrouter",
            trace_attr.ATTR_BILLING_SETTLEMENT_QUANTITY_RUB: 43,
            trace_attr.ATTR_LLM_TOTAL_TOKENS: 9999,
        },
    )
    matched = resolve_matched_rules(doc, span)
    assert len(matched) == 1
    assert matched[0].rule_id == "llm_openrouter_usd_to_rub"
    assert matched[0].resource_name == "billing:rub"


def test_matches_flows_llm_resource() -> None:
    doc = default_settlement_rules_document()
    span = _span(
        "flows.llm_resource.chat",
        {trace_attr.ATTR_BILLING_QUANTITY: 1},
    )
    matched = resolve_matched_rules(doc, span)
    assert len(matched) == 1
    assert matched[0].rule_id == "flows_llm_resource_qty"


def test_matches_flows_llm_invoke() -> None:
    doc = default_settlement_rules_document()
    span = _span(
        "flows.llm.invoke_task",
        {trace_attr.ATTR_BILLING_QUANTITY: 50},
    )
    matched = resolve_matched_rules(doc, span)
    assert len(matched) == 1
    assert matched[0].rule_id == "flows_llm_invoke_qty"


def test_matches_rag_embed() -> None:
    doc = default_settlement_rules_document()
    span = _span(
        "rag.embed.batch",
        {trace_attr.ATTR_BILLING_QUANTITY: 120},
    )
    matched = resolve_matched_rules(doc, span)
    assert len(matched) == 1
    assert matched[0].rule_id == "rag_embed_tokens"


def test_matches_livekit_prefix() -> None:
    doc = default_settlement_rules_document()
    span = _span("livekit.room.create", {})
    matched = resolve_matched_rules(doc, span)
    assert len(matched) == 1
    assert matched[0].rule_id == "livekit_ops"


def test_matches_livekit_room_session_usage_minutes() -> None:
    doc = default_settlement_rules_document()
    span = _span(
        "livekit.room.session_usage",
        {trace_attr.ATTR_BILLING_QUANTITY: 3},
    )
    matched = resolve_matched_rules(doc, span)
    assert len(matched) == 1
    assert matched[0].rule_id == "livekit_room_session_minutes"
    assert matched[0].resource_name == "livekit:room_minute"


def test_matches_livekit_egress_composite_usage_minutes() -> None:
    doc = default_settlement_rules_document()
    span = _span(
        "livekit.egress.composite_usage",
        {trace_attr.ATTR_BILLING_QUANTITY: 2},
    )
    matched = resolve_matched_rules(doc, span)
    assert len(matched) == 1
    assert matched[0].rule_id == "livekit_egress_composite_minutes"


def test_matches_livekit_egress_segmented_usage_minutes() -> None:
    doc = default_settlement_rules_document()
    span = _span(
        "livekit.egress.segmented_usage",
        {trace_attr.ATTR_BILLING_QUANTITY: 7},
    )
    matched = resolve_matched_rules(doc, span)
    assert len(matched) == 1
    assert matched[0].rule_id == "livekit_egress_segmented_minutes"


def test_no_rule_for_sync_stt_observability_only() -> None:
    doc = default_settlement_rules_document()
    span = _span("sync.stt.transcribe_audio_message", {})
    matched = resolve_matched_rules(doc, span)
    assert len(matched) == 0


def test_no_rule_for_flows_external_api_observability_only() -> None:
    doc = default_settlement_rules_document()
    span = _span("flows.external_api.call", {})
    matched = resolve_matched_rules(doc, span)
    assert len(matched) == 0
