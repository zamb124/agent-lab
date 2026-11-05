"""Telegram getUpdates-поллер customer-auth (очередь ``idle``).

Хост без входящего доступа от api.telegram.org не получает webhook —
CustomerAuthService тянет updates long-poll'ом. Задача цепляет следующий
полл по выходе из бюджета (непрерывный цикл), минутный cron — только
страховка на случай убитого воркера.
"""

from __future__ import annotations

from apps.idle.di import Di
from core.customers.task_names import CUSTOMER_AUTH_TG_POLL
from core.logging import get_logger
from core.tasks import enqueue, platform_task

logger = get_logger(__name__)


@platform_task(CUSTOMER_AUTH_TG_POLL)
async def customer_auth_tg_poll(
    schedule_task_id: str | None = None,
    company_id: str | None = None,
    *,
    di: Di,
) -> dict[str, int]:
    processed = await di.customer_auth_service.poll_telegram_updates()
    if processed is None:
        return {"processed": 0}
    # Лок уже снят в finally сервиса — преемник захватит его без окна простоя.
    _ = await enqueue(CUSTOMER_AUTH_TG_POLL)
    if processed:
        logger.info(
            "idle.customer_auth_tg_poll",
            processed=processed,
            schedule_task_id=schedule_task_id,
            company_id=company_id,
        )
    return {"processed": processed}
