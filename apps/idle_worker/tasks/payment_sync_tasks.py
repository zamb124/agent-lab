"""
Периодическая сверка pending транзакций через API платежных провайдеров.
"""

from __future__ import annotations

from apps.flows.config import get_settings
from apps.idle_worker.broker import broker as idle_broker
from apps.idle_worker.container import get_container
from core.clients.payment.factory import PaymentProviderFactory
from core.logging import get_logger
from core.payments.service import PaymentService
from core.payments.sync_service import PaymentSyncService

logger = get_logger(__name__)


@idle_broker.task(task_name="payment_sync_tick", queue_name="idle")
async def payment_sync_tick(
    schedule_task_id: str | None = None,
    company_id: str | None = None,
) -> dict[str, int]:
    _ = schedule_task_id, company_id
    settings = get_settings()

    if not settings.payment_providers.sync_enabled:
        logger.debug("payment_sync_tick: sync_enabled=False, пропускаем")
        return {"companies_checked": 0, "total_updated": 0}

    container = get_container()
    payment_service = PaymentService(
        company_repository=container.company_repository,
        storage=container.shared_storage,
    )
    sync_service = PaymentSyncService(
        payment_service=payment_service,
        storage=container.shared_storage,
    )

    if not PaymentProviderFactory.get_available_providers():
        PaymentProviderFactory.initialize()
    await PaymentProviderFactory.seed_access_tokens(container.shared_storage)

    stats = await sync_service.sync_all_companies()

    logger.info(
        "payment_sync_tick done: companies=%s pending=%s updated=%s",
        stats.companies_checked,
        stats.total_pending,
        stats.total_updated,
    )

    return {
        "companies_checked": stats.companies_checked,
        "total_pending": stats.total_pending,
        "total_updated": stats.total_updated,
    }
