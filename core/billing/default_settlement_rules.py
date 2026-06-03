"""
Дефолтный каталог правил span settlement (кодовая база для всех компаний до override в storage).
Режим first_win: одно правило на спан, приоритет — меньше число раньше среди совпавших.

Источники spans с platform.billing.pending_settlement (operation_name при сохранении в БД):

- llm.{model} — core/tracing/tracer.py (record_llm_response на CLIENT span)
- flows.llm_resource.complete | .chat | .chat_with_tools — apps/flows/src/resources/wrappers/llm_resource.py
- flows.llm.invoke_task — apps/flows/src/tasks/llm_tasks.py
- rag.embed.batch — core/rag/services/embedding_client.py
- core.files.reader.image — core/files/reader/service.py
- livekit.room.session_usage | livekit.egress.composite_usage | livekit.egress.segmented_usage
  — core/calls/livekit_usage_spans.py (поминутное списание после завершения сессии / записи / речи в ленту)
- livekit.room.create | livekit.egress.room_composite_s3 | livekit.egress.track_composite_segmented
  — core/calls/livekit_client.py observability без pending_settlement (списание только через *usage выше)
- sync.calls.* | sync.stt.* (без pending_settlement) — apps/sync/realtime/tasks.py, только трейсинг
- flows.external_api.call | flows.mcp.call_tool | flows.channel.execute_action — без pending_settlement, только трейсинг
- search.provider.* — Search MCP provider calls; BYOK/company credentials create
  zero-cost usage via platform.billing.cost_origin=company, system/public main search is not marked pending

Категория биллинга tool не используется: вызовы инструментов не тарифицируются.

OpenRouter: при platform.llm.provider_reported_cost и billing.usd_to_rub_rate на span пишется
platform.billing.settlement_quantity_rub; правило llm_openrouter_usd_to_rub (first_win, приоритет 5)
считает quantity в рублях по resource billing:rub (1 ₽ за единицу quantity).
"""

from __future__ import annotations

import core.tracing.attributes as trace_attr
from core.billing.settlement_rules import (
    SettlementApplicationMode,
    SettlementRule,
    SettlementRuleMatch,
    SettlementRulesDocument,
)
from core.models.billing_models import UsageType


def default_settlement_rules_document() -> SettlementRulesDocument:
    return SettlementRulesDocument(
        version=1,
        application_mode=SettlementApplicationMode.FIRST_WIN,
        rules=[
            SettlementRule(
                rule_id="llm_openrouter_usd_to_rub",
                priority=5,
                resource_name="billing:rub",
                usage_type=UsageType.LLM_REQUEST,
                quantity_from=f"attr:{trace_attr.ATTR_BILLING_SETTLEMENT_QUANTITY_RUB}",
                match=SettlementRuleMatch(
                    operation_name_prefix="llm.",
                    attribute_equals={trace_attr.ATTR_LLM_PROVIDER: "openrouter"},
                    attribute_keys_present=[trace_attr.ATTR_BILLING_SETTLEMENT_QUANTITY_RUB],
                ),
            ),
            SettlementRule(
                rule_id="llm_tracer_tokens",
                priority=10,
                resource_name="llm:*",
                usage_type=UsageType.LLM_REQUEST,
                quantity_from=f"attr:{trace_attr.ATTR_LLM_TOTAL_TOKENS}",
                match=SettlementRuleMatch(operation_name_prefix="llm."),
            ),
            SettlementRule(
                rule_id="flows_llm_resource_qty",
                priority=15,
                resource_name="llm:*",
                usage_type=UsageType.LLM_REQUEST,
                quantity_from=f"attr:{trace_attr.ATTR_BILLING_QUANTITY}",
                match=SettlementRuleMatch(operation_name_prefix="flows.llm_resource."),
            ),
            SettlementRule(
                rule_id="flows_llm_invoke_qty",
                priority=16,
                resource_name="llm:*",
                usage_type=UsageType.LLM_REQUEST,
                quantity_from=f"attr:{trace_attr.ATTR_BILLING_QUANTITY}",
                match=SettlementRuleMatch(operation_name_prefix="flows.llm."),
            ),
            SettlementRule(
                rule_id="rag_embed_tokens",
                priority=20,
                resource_name="embedding:*",
                usage_type=UsageType.EMBEDDING_REQUEST,
                quantity_from=f"attr:{trace_attr.ATTR_BILLING_QUANTITY}",
                match=SettlementRuleMatch(operation_name_prefix="rag.embed"),
            ),
            SettlementRule(
                rule_id="core_files_reader_vision",
                priority=25,
                resource_name="llm:*",
                usage_type=UsageType.LLM_REQUEST,
                quantity_from="const:1",
                match=SettlementRuleMatch(operation_name_prefix="core.files.reader"),
            ),
            SettlementRule(
                rule_id="livekit_room_session_minutes",
                priority=26,
                resource_name="livekit:room_minute",
                usage_type=UsageType.TOOL_CALL,
                quantity_from=f"attr:{trace_attr.ATTR_BILLING_QUANTITY}",
                match=SettlementRuleMatch(
                    operation_name_equals="livekit.room.session_usage",
                    attribute_keys_present=[trace_attr.ATTR_BILLING_QUANTITY],
                ),
            ),
            SettlementRule(
                rule_id="livekit_egress_composite_minutes",
                priority=27,
                resource_name="livekit:egress_composite_minute",
                usage_type=UsageType.TOOL_CALL,
                quantity_from=f"attr:{trace_attr.ATTR_BILLING_QUANTITY}",
                match=SettlementRuleMatch(
                    operation_name_equals="livekit.egress.composite_usage",
                    attribute_keys_present=[trace_attr.ATTR_BILLING_QUANTITY],
                ),
            ),
            SettlementRule(
                rule_id="livekit_egress_segmented_minutes",
                priority=28,
                resource_name="livekit:egress_segmented_minute",
                usage_type=UsageType.TOOL_CALL,
                quantity_from=f"attr:{trace_attr.ATTR_BILLING_QUANTITY}",
                match=SettlementRuleMatch(
                    operation_name_equals="livekit.egress.segmented_usage",
                    attribute_keys_present=[trace_attr.ATTR_BILLING_QUANTITY],
                ),
            ),
            SettlementRule(
                rule_id="livekit_ops",
                priority=30,
                resource_name="livekit:*",
                usage_type=UsageType.TOOL_CALL,
                quantity_from="const:1",
                match=SettlementRuleMatch(operation_name_prefix="livekit."),
            ),
            SettlementRule(
                rule_id="search_tinyfish_call",
                priority=35,
                resource_name="search:tinyfish",
                usage_type=UsageType.TOOL_CALL,
                quantity_from="const:1",
                match=SettlementRuleMatch(operation_name_equals="search.provider.tinyfish"),
            ),
            SettlementRule(
                rule_id="search_linkup_call",
                priority=36,
                resource_name="search:linkup",
                usage_type=UsageType.TOOL_CALL,
                quantity_from="const:1",
                match=SettlementRuleMatch(operation_name_equals="search.provider.linkup"),
            ),
            SettlementRule(
                rule_id="search_serper_call",
                priority=37,
                resource_name="search:serper",
                usage_type=UsageType.TOOL_CALL,
                quantity_from="const:1",
                match=SettlementRuleMatch(operation_name_equals="search.provider.serper"),
            ),
            SettlementRule(
                rule_id="search_tavily_call",
                priority=38,
                resource_name="search:tavily",
                usage_type=UsageType.TOOL_CALL,
                quantity_from="const:1",
                match=SettlementRuleMatch(operation_name_equals="search.provider.tavily"),
            ),
        ],
    )
