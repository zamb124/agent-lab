"""Биллинг LLM-вызова: pre-flight баланса и запись CLIENT span.

Единственная точка ``require_balance_for_billable_operation`` /
``record_llm_response`` для LLM. Call-site не дублирует эти вызовы.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from a2a.types import TaskArtifactUpdateEvent
from opentelemetry.trace import Span

from core.a2a import coerce_usage_token_count, get_part_text, mapping_from_struct, part_has_text
from core.ai.free_pool import PLATFORM_PAID_FALLBACK_SOURCE
from core.ai.llm_config import LLMCallConfig
from core.ai.models import ResolvedAIModel
from core.ai.providers import AICapability
from core.billing import get_cbr_usd_to_rub_rate
from core.billing.service import (
    BALANCE_BLOCK_OPERATION_IMAGE,
    BALANCE_BLOCK_OPERATION_LLM,
    BALANCE_BLOCK_OPERATION_VISION,
    COST_ORIGIN_COMPANY,
    COST_ORIGIN_PLATFORM,
    BillingService,
)
from core.clients.llm.messages import StreamEvent
from core.config import get_settings
from core.config.testing import is_testing
from core.context import get_context
from core.tracing.tracer import PlatformTracer
from core.types import JsonArray, JsonObject, require_json_array, require_json_object

_DEFAULT_NOTIFICATION_SERVICE = "flows"


@dataclass
class LLMCallMeter:
    """Накопленный usage и observability одного успешного LLM-вызова."""

    input_tokens: int = 0
    output_tokens: int = 0
    provider_reported_cost: float | None = None
    provider_upstream_inference_cost: float | None = None
    resolved_model: str | None = None
    resolved_provider: str | None = None
    resolved_source: str | None = None
    ttft_ms: float | None = None
    output_tokens_per_second: float | None = None
    llm_context: JsonObject | None = None
    content_parts: list[str] = field(default_factory=list)
    tool_calls: JsonArray = field(default_factory=list)

    @property
    def content(self) -> str:
        return "".join(self.content_parts)

    @property
    def has_tool_calls(self) -> bool:
        return bool(self.tool_calls)

    def observe_stream_event(self, event: StreamEvent) -> None:
        if isinstance(event, TaskArtifactUpdateEvent):
            artifact_name = event.artifact.name or "response"
            if artifact_name == "reasoning":
                return
            for part in event.artifact.parts:
                if part_has_text(part):
                    self.content_parts.append(get_part_text(part))
            return
        if not event.status.HasField("message") or not event.status.message.HasField("metadata"):
            return
        metadata = mapping_from_struct(event.status.message.metadata)
        self._apply_status_metadata(metadata)

    def apply_invoke_usage(self, usage: JsonObject) -> None:
        self._apply_usage_object(usage)

    def _apply_status_metadata(self, metadata: JsonObject) -> None:
        metadata_tool_calls = metadata.get("tool_calls")
        if metadata_tool_calls:
            self.tool_calls = require_json_array(
                metadata_tool_calls,
                "llm.billing.status.metadata.tool_calls",
            )
        md_model = metadata.get("model")
        if isinstance(md_model, str) and md_model.strip():
            self.resolved_model = md_model.strip()
        md_provider = metadata.get("provider")
        if isinstance(md_provider, str) and md_provider.strip():
            self.resolved_provider = md_provider.strip()
        md_source = metadata.get("source")
        if isinstance(md_source, str) and md_source.strip():
            self.resolved_source = md_source.strip()
        md_ttft = metadata.get("ttft_ms")
        if isinstance(md_ttft, (int, float)) and not isinstance(md_ttft, bool):
            self.ttft_ms = float(md_ttft)
        md_output_tps = metadata.get("output_tokens_per_second")
        if isinstance(md_output_tps, (int, float)) and not isinstance(md_output_tps, bool):
            self.output_tokens_per_second = float(md_output_tps)
        context_raw = metadata.get("llm_context")
        if isinstance(context_raw, dict):
            self.llm_context = require_json_object(
                context_raw,
                "llm.billing.status.metadata.llm_context",
            )
        usage_raw = metadata.get("usage")
        if isinstance(usage_raw, dict):
            self._apply_usage_object(
                require_json_object(usage_raw, "llm.billing.status.metadata.usage")
            )

    def _apply_usage_object(self, usage: JsonObject) -> None:
        input_raw = usage.get("input_tokens", usage.get("prompt_tokens", 0))
        output_raw = usage.get("output_tokens", usage.get("completion_tokens", 0))
        self.input_tokens = coerce_usage_token_count(input_raw, "usage.input_tokens")
        self.output_tokens = coerce_usage_token_count(output_raw, "usage.output_tokens")
        prc = usage.get("provider_reported_cost")
        if isinstance(prc, (int, float)) and not isinstance(prc, bool):
            self.provider_reported_cost = float(prc)
        puc = usage.get("provider_upstream_inference_cost")
        if isinstance(puc, (int, float)) and not isinstance(puc, bool):
            self.provider_upstream_inference_cost = float(puc)


class LLMClientBilling:
    """Состояние биллинга, которое несёт ``LLMClient``."""

    def __init__(
        self,
        *,
        cost_origin: str = COST_ORIGIN_PLATFORM,
        billing_resource_name: str | None = None,
        operation_code: str = BALANCE_BLOCK_OPERATION_LLM,
        notification_service: str = _DEFAULT_NOTIFICATION_SERVICE,
    ) -> None:
        self.cost_origin: str = cost_origin
        self.billing_resource_name: str | None = billing_resource_name
        self.operation_code: str = operation_code
        self.notification_service: str = notification_service
        self.prepared: bool = False
        self.paid_fallback_allowed: bool = True

    def copy(self) -> LLMClientBilling:
        copied = LLMClientBilling(
            cost_origin=self.cost_origin,
            billing_resource_name=self.billing_resource_name,
            operation_code=self.operation_code,
            notification_service=self.notification_service,
        )
        copied.prepared = self.prepared
        copied.paid_fallback_allowed = self.paid_fallback_allowed
        return copied


def billing_from_resolved_model(resolved: ResolvedAIModel) -> LLMClientBilling:
    operation_code = BALANCE_BLOCK_OPERATION_LLM
    notification_service = _DEFAULT_NOTIFICATION_SERVICE
    if resolved.capability == AICapability.LLM_VISION:
        operation_code = BALANCE_BLOCK_OPERATION_VISION
        notification_service = "frontend"
    elif resolved.capability in {AICapability.IMAGE_GEN, AICapability.IMAGE_EDIT}:
        operation_code = BALANCE_BLOCK_OPERATION_IMAGE
        notification_service = _DEFAULT_NOTIFICATION_SERVICE
    resource_name = (
        resolved.billing_resource_name if resolved.cost_origin == COST_ORIGIN_COMPANY else None
    )
    return LLMClientBilling(
        cost_origin=resolved.cost_origin,
        billing_resource_name=resource_name,
        operation_code=operation_code,
        notification_service=notification_service,
    )


def filter_paid_fallback_candidates(
    candidates: list[LLMCallConfig],
    *,
    paid_fallback_allowed: bool,
) -> list[LLMCallConfig]:
    if paid_fallback_allowed:
        return candidates
    return [
        candidate
        for candidate in candidates
        if candidate.source != PLATFORM_PAID_FALLBACK_SOURCE
    ]


async def prepare_llm_client_billing(
    billing: LLMClientBilling,
    *,
    billing_service: BillingService,
    platform_default_free_pool: bool,
    platform_paid_fallback_enabled: bool,
) -> bool:
    """Pre-flight. Возвращает, можно ли брать платный fallback в этом вызове."""
    if billing.prepared:
        return billing.paid_fallback_allowed
    paid_fallback = platform_paid_fallback_enabled
    if is_testing():
        billing.prepared = True
        billing.paid_fallback_allowed = paid_fallback
        return paid_fallback
    if billing.cost_origin == COST_ORIGIN_COMPANY:
        billing.prepared = True
        billing.paid_fallback_allowed = paid_fallback
        return paid_fallback
    actx = get_context()
    if actx is None or actx.active_company is None:
        raise ValueError("Context with active_company is required for LLM (billing)")
    user_id = str(actx.user.user_id).strip()
    if not user_id:
        raise ValueError("Context with user is required for LLM (billing)")
    if platform_default_free_pool:
        allow_charge = await billing_service.company_may_incur_billable_operation_charge(
            actx.active_company.company_id
        )
        paid_fallback = paid_fallback and allow_charge
        billing.prepared = True
        billing.paid_fallback_allowed = paid_fallback
        return paid_fallback
    await billing_service.require_balance_for_billable_operation(
        actx.active_company.company_id,
        user_id,
        operation_code=billing.operation_code,
        notification_service=billing.notification_service,
        cost_origin=billing.cost_origin,
    )
    billing.prepared = True
    billing.paid_fallback_allowed = paid_fallback
    return paid_fallback


def settlement_quantity_rub_for_meter(meter: LLMCallMeter) -> int | None:
    if meter.resolved_provider != "openrouter":
        return None
    if meter.provider_reported_cost is None or meter.provider_reported_cost <= 0:
        return None
    rate = get_cbr_usd_to_rub_rate(fallback=get_settings().billing.usd_to_rub_rate)
    rub = int(round(meter.provider_reported_cost * rate))
    if rub < 1:
        return None
    return rub


def record_llm_client_response(
    *,
    tracer: PlatformTracer,
    span: Span,
    meter: LLMCallMeter,
    duration_ms: float,
    billing: LLMClientBilling,
    fallback_provider: str,
) -> None:
    tracer.record_llm_response(
        span,
        input_tokens=meter.input_tokens,
        output_tokens=meter.output_tokens,
        has_tool_calls=meter.has_tool_calls,
        duration_ms=duration_ms,
        response_content=meter.content or None,
        tool_calls=(
            [
                require_json_object(tool_call, "llm.billing.tool_call")
                for tool_call in meter.tool_calls
            ]
            if meter.tool_calls
            else None
        ),
        llm_provider=meter.resolved_provider or fallback_provider,
        llm_model=meter.resolved_model,
        candidate_source=meter.resolved_source,
        provider_reported_cost=meter.provider_reported_cost,
        provider_upstream_inference_cost=meter.provider_upstream_inference_cost,
        settlement_quantity_rub=settlement_quantity_rub_for_meter(meter),
        billing_resource_name=billing.billing_resource_name,
        cost_origin=billing.cost_origin,
        llm_context=meter.llm_context,
        ttft_ms=meter.ttft_ms,
        output_tokens_per_second=meter.output_tokens_per_second,
    )


__all__ = [
    "LLMCallMeter",
    "LLMClientBilling",
    "billing_from_resolved_model",
    "filter_paid_fallback_candidates",
    "prepare_llm_client_billing",
    "record_llm_client_response",
    "settlement_quantity_rub_for_meter",
]
