"""
Обёртка для spans значимых операций SaaS (единый стиль + поля биллинга в attributes).
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import Any, AsyncGenerator, Dict, Optional

from opentelemetry.trace import Span

import core.tracing.attributes as attr

from .context import TraceContext
from .tracer import get_tracer


@asynccontextmanager
async def traced_operation(
    operation_name: str,
    *,
    event_type: Optional[str] = None,
    operation_category: Optional[str] = None,
    billing_usage_type: Optional[str] = None,
    billing_resource_name: Optional[str] = None,
    billing_quantity: Optional[int] = None,
    billing_pending_settlement: bool = False,
    billing_cost_origin: Optional[str] = None,
    billing_custom_provider_id: Optional[str] = None,
    resource_type: Optional[str] = None,
    resource_id: Optional[str] = None,
    trace_ctx: Optional[TraceContext] = None,
    extra_attributes: Optional[Dict[str, Any]] = None,
) -> AsyncGenerator[Span, None]:
    """
    operation_name: стабильная строка вида service.area.action.
    billing_usage_type: значение UsageType (строка), например embedding_request.
    billing_pending_settlement: если True — span попадёт в фоновое списание (idle job), иначе только observability.
    billing_cost_origin: ``"platform"`` или ``"company"``; при ``"company"`` settlement создаст
        UsageRecord с ``cost=0`` (баланс не трогается, см. core/billing/service.py).
    billing_custom_provider_id: id custom OpenAI-compatible провайдера компании (опц., для аналитики).
    """
    merged: Dict[str, Any] = dict(extra_attributes or {})
    if operation_category:
        merged[attr.ATTR_OPERATION_CATEGORY] = operation_category
    if billing_usage_type:
        merged[attr.ATTR_BILLING_USAGE_TYPE] = billing_usage_type
    if billing_resource_name:
        merged[attr.ATTR_BILLING_RESOURCE_NAME] = billing_resource_name
    if billing_quantity is not None:
        merged[attr.ATTR_BILLING_QUANTITY] = billing_quantity
    if billing_pending_settlement:
        merged[attr.ATTR_BILLING_PENDING_SETTLEMENT] = True
    if billing_cost_origin is not None:
        merged[attr.ATTR_BILLING_COST_ORIGIN] = billing_cost_origin
    if billing_custom_provider_id is not None:
        merged[attr.ATTR_BILLING_CUSTOM_PROVIDER_ID] = billing_custom_provider_id

    tracer = get_tracer()
    async with tracer.platform_operation_span(
        operation_name,
        event_type=event_type,
        resource_type=resource_type,
        resource_id=resource_id,
        trace_ctx=trace_ctx,
        extra_attributes=merged if merged else None,
    ) as span:
        yield span
