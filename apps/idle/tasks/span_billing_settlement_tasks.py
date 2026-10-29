"""
Фоновое списание по spans с platform.billing.pending_settlement (очередь idle).
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from apps.idle.di import Di
from apps.idle.tasks.task_names import TASK_SPAN_BILLING_SETTLEMENT_TICK
from core.billing.settlement_rules import SettlementRulesDocument
from core.billing.span_billing_settlement import SpanBillingSettlement
from core.config import get_settings
from core.context import set_context
from core.logging import get_logger
from core.logging.attributes import (
    EVENT_BILLING_SETTLEMENT_LAG,
    LOG_BILLING_SETTLEMENT_LAG_MS,
    LOG_OPERATION_NAME,
)
from core.models.context_models import Context
from core.models.identity_models import Company, User
from core.tasks import platform_task
from core.tracing.models import Span

logger = get_logger(__name__)


@platform_task(TASK_SPAN_BILLING_SETTLEMENT_TICK)
async def span_billing_settlement_tick(
    schedule_task_id: str | None = None,
    company_id: str | None = None,
    *,
    di: Di,
) -> dict[str, int]:
    settings = get_settings()
    cfg = settings.billing.span_settlement
    if not cfg.enabled:
        return {"spans_fetched": 0, "settled": 0, "errors": 0}

    if not settings.tracing.postgres_enabled or not settings.database.tracing_url:
        raise ValueError(
            "billing.span_settlement.enabled requires tracing.postgres_enabled and database.tracing_url"
        )

    now = datetime.now(timezone.utc)
    from_time = now - timedelta(minutes=cfg.lookback_minutes)

    billing = di.billing_service
    settlement = SpanBillingSettlement(di.shared_storage)

    scoped_company_id = company_id
    spans = await Span.list_pending_billing_settlement_by_start_time_and_span_id_asc(
        from_time=from_time,
        to_time=now,
        limit=cfg.batch_limit,
        company_id=scoped_company_id,
    )

    rules_by_company: dict[str, SettlementRulesDocument] = {}

    settled = 0
    errors = 0
    prev_company_id: str | None = None
    for span in spans:
        span_company_id = span.company_id
        if not span_company_id:
            errors += 1
            logger.error("idle.span_billing_settlement_tick", span_id=span.span_id)
            continue

        if span_company_id != prev_company_id:
            _ = set_context(Context(
                user=User(user_id="billing-worker", name="Billing Worker"),
                active_company=Company(company_id=span_company_id, name=span_company_id),
                session_id=f"billing-settlement:{span_company_id}",
                channel="taskiq",
            ))
            prev_company_id = span_company_id

        rules_doc = rules_by_company.get(span_company_id)
        if rules_doc is None:
            rules_doc = await billing.load_settlement_rules_document_for_company(span_company_id)
            rules_by_company[span_company_id] = rules_doc
        if span.end_time is not None:
            end_time = span.end_time
            if end_time.tzinfo is None:
                end_time = end_time.replace(tzinfo=timezone.utc)
            settlement_lag_ms = int((now - end_time).total_seconds() * 1000)
            logger.info(
                EVENT_BILLING_SETTLEMENT_LAG,
                **{
                    LOG_BILLING_SETTLEMENT_LAG_MS: settlement_lag_ms,
                    LOG_OPERATION_NAME: span.operation_name,
                    "span_id": span.span_id,
                    "company_id": span_company_id,
                },
            )
        try:
            n = await billing.settle_pending_span_in_job(
                span=span,
                settlement=settlement,
                rules_doc=rules_doc,
            )
            settled += n
        except Exception as exc:
            errors += 1
            logger.error(
                "idle.span_billing_settlement_tick",
                span_id=span.span_id,
                error=exc,
                exc_info=(type(exc), exc, exc.__traceback__),
            )

    logger.info(
        "idle.span_billing_settlement_tick",
        spans_fetched=len(spans),
        settled=settled,
        errors=errors,
        schedule_task_id=schedule_task_id,
        company_id=scoped_company_id,
    )
    return {"spans_fetched": len(spans), "settled": settled, "errors": errors}
