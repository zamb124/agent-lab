"""Billing spans STT/TTS: `pending_settlement` → фоновый settlement → UsageRecord.

Прайс — `billing.resource_base_prices` категорий `stt`/`tts`, resource_name
`<category>:<provider>` (нет провайдера в прайсе — ключ `*` категории); при
`cost_origin=company` (BYOK) resource `<category>:byok`, settlement пишет `cost=0`.
Правила — `stt_audio_seconds` / `tts_characters` в `core/billing/default_settlement_rules.py`.
"""

from __future__ import annotations

from collections.abc import Mapping

import core.tracing.attributes as trace_attributes
from core.billing.service import COST_ORIGIN_COMPANY
from core.models.billing_models import BillingCostOrigin, UsageType
from core.models.identity_models import Company, User
from core.tracing.operation_span import traced_operation
from core.types import OtelAttributeValue


def _speech_attributes(
    *, user: User, company: Company, provider: str, extra: Mapping[str, OtelAttributeValue]
) -> dict[str, OtelAttributeValue]:
    attributes: dict[str, OtelAttributeValue] = {
        trace_attributes.ATTR_TENANT_COMPANY_ID: company.company_id,
        trace_attributes.ATTR_USER_ID: user.user_id,
        "platform.speech.provider": provider,
    }
    attributes.update(extra)
    return attributes


async def record_stt_usage_span(
    *,
    user: User,
    company: Company,
    provider: str,
    audio_seconds: float,
    cost_origin: BillingCostOrigin,
    extra_attributes: Mapping[str, OtelAttributeValue] | None = None,
) -> None:
    """Span `stt.{provider}`: quantity — секунды аудио, округлённые вверх (минимум 1)."""
    if not provider:
        raise ValueError("record_stt_usage_span: provider обязателен")
    if audio_seconds < 0:
        raise ValueError("record_stt_usage_span: audio_seconds < 0")
    resource = "stt:byok" if cost_origin == COST_ORIGIN_COMPANY else f"stt:{provider}"
    attributes = _speech_attributes(
        user=user,
        company=company,
        provider=provider,
        extra={"platform.stt.audio_seconds": audio_seconds, **(extra_attributes or {})},
    )
    async with traced_operation(
        f"stt.{provider}",
        event_type="speech.stt",
        operation_category="speech",
        billing_usage_type=UsageType.TOOL_CALL.value,
        billing_resource_name=resource,
        billing_quantity=max(1, int(audio_seconds + 0.999)),
        billing_pending_settlement=True,
        billing_cost_origin=cost_origin,
        extra_attributes=attributes,
    ):
        pass


async def record_tts_usage_span(
    *,
    user: User,
    company: Company,
    provider: str,
    char_count: int,
    cost_origin: BillingCostOrigin,
    extra_attributes: Mapping[str, OtelAttributeValue] | None = None,
) -> None:
    """Span `tts.{provider}`: quantity — символы синтеза (минимум 1)."""
    if not provider:
        raise ValueError("record_tts_usage_span: provider обязателен")
    if char_count < 0:
        raise ValueError("record_tts_usage_span: char_count < 0")
    resource = "tts:byok" if cost_origin == COST_ORIGIN_COMPANY else f"tts:{provider}"
    attributes = _speech_attributes(
        user=user,
        company=company,
        provider=provider,
        extra={"platform.tts.char_count": char_count, **(extra_attributes or {})},
    )
    async with traced_operation(
        f"tts.{provider}",
        event_type="speech.tts",
        operation_category="speech",
        billing_usage_type=UsageType.TOOL_CALL.value,
        billing_resource_name=resource,
        billing_quantity=max(1, char_count),
        billing_pending_settlement=True,
        billing_cost_origin=cost_origin,
        extra_attributes=attributes,
    ):
        pass
