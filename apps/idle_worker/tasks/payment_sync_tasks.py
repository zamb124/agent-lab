"""
Периодическая сверка pending транзакций через API платежных провайдеров.
"""

from __future__ import annotations

from apps.idle_worker.di import Di
from apps.idle_worker.tasks.task_names import TASK_PAYMENT_SYNC_TICK
from core.clients.payment.factory import PaymentProviderFactory
from core.config import get_settings
from core.logging import get_logger
from core.payments.service import PaymentService
from core.payments.sync_service import PaymentSyncService
from core.tasks import platform_task

logger = get_logger(__name__)


@platform_task(TASK_PAYMENT_SYNC_TICK)
async def payment_sync_tick(
    schedule_task_id: str | None = None,
    company_id: str | None = None,
    *,
    di: Di,
) -> dict[str, int]:
    _ = schedule_task_id, company_id
    settings = get_settings()

    if not settings.payment_providers.sync_enabled:
        logger.debug("idle.payment_sync_tick")
        return {"companies_checked": 0, "total_updated": 0}

    payment_service = PaymentService(
        storage=di.shared_storage,
    )
    sync_service = PaymentSyncService(
        payment_service=payment_service,
        storage=di.shared_storage,
    )

    if not PaymentProviderFactory.get_available_providers():
        PaymentProviderFactory.initialize()

    stats = await sync_service.sync_all_companies()

    logger.info(
        "idle.payment_sync_tick",
        companies=stats.companies_checked,
        pending=stats.total_pending,
        updated=stats.total_updated,
    )

    return {
        "companies_checked": stats.companies_checked,
        "total_pending": stats.total_pending,
        "total_updated": stats.total_updated,
    }
