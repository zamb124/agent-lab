"""
Фоновое списание по spans с platform.billing.pending_settlement (очередь idle).
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from apps.flows.config import get_settings
from apps.flows.src.container import get_container
from apps.idle_worker.broker import broker as idle_broker
from core.billing.settlement_rules import SettlementRulesDocument
from core.billing.span_billing_settlement import SpanBillingSettlement
from core.logging import get_logger

logger = get_logger(__name__)


@idle_broker.task(task_name="span_billing_settlement_tick", queue_name="idle")
async def span_billing_settlement_tick(
    scheduler_task_id: str | None = None,
    company_id: str | None = None,
) -> dict[str, int]:
    settings = get_settings()
    cfg = settings.billing.span_settlement
    if not cfg.enabled:
        return {"spans_fetched": 0, "settled": 0, "errors": 0}

    if not settings.tracing.postgres_enabled or not settings.database.tracing_url:
        raise ValueError(
            "billing.span_settlement.enabled требует tracing.postgres_enabled и database.tracing_url"
        )

    now = datetime.now(timezone.utc)
    from_time = now - timedelta(minutes=cfg.lookback_minutes)

    container = get_container()
    span_repo = container.span_repository
    billing = container.billing_service
    settlement = SpanBillingSettlement(container.shared_storage)

    spans = await span_repo.list_spans_pending_billing_settlement(
        from_time=from_time,
        to_time=now,
        limit=cfg.batch_limit,
    )

    rules_by_company: dict[str, SettlementRulesDocument] = {}

    settled = 0
    errors = 0
    for span_dict in spans:
        company_id = span_dict.get("company_id")
        if not company_id or not isinstance(company_id, str):
            errors += 1
            logger.error(
                "span_billing_settlement_tick: span без company_id span_id=%s",
                span_dict.get("span_id"),
            )
            continue
        rules_doc = rules_by_company.get(company_id)
        if rules_doc is None:
            rules_doc = await billing.load_settlement_rules_document_for_company(company_id)
            rules_by_company[company_id] = rules_doc
        try:
            n = await billing.settle_pending_span_in_job(
                span_dict=span_dict,
                settlement=settlement,
                fallback_user_id=cfg.fallback_user_id,
                rules_doc=rules_doc,
            )
            settled += n
        except Exception as exc:
            errors += 1
            logger.error(
                "span_billing_settlement_tick: span_id=%s error=%s",
                span_dict.get("span_id"),
                exc,
                exc_info=(type(exc), exc, exc.__traceback__),
            )

    logger.info(
        "span_billing_settlement_tick done: spans_fetched=%s settled=%s errors=%s scheduler_task_id=%s company_id=%s",
        len(spans),
        settled,
        errors,
        scheduler_task_id,
        company_id,
    )
    return {"spans_fetched": len(spans), "settled": settled, "errors": errors}
