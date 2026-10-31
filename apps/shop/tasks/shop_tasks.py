"""Shop TaskIQ tasks — фоновая работа витрин (очередь ``shop``).

Сюда уходит всё тяжёлое и вторичное относительно HTTP-команды:
пересборка Redis-снапшотов, доставка уведомлений о заказе, провиженинг
кастомных доменов, ребилд поискового каталога агрегатора.
"""

from __future__ import annotations

from apps.shop.di import Di
from apps.shop.models import ShopDomain, ShopDomainStatus
from apps.shop.tasks.task_names import (
    SHOP_NOTIFY_ORDER,
    SHOP_PROVISION_DOMAIN,
    SHOP_REBUILD_AGGREGATE,
    SHOP_REBUILD_STOREFRONT,
    SHOP_RECONCILE_DOMAINS_TICK,
)
from core.context import clear_context, set_context
from core.identity.system_bootstrap import build_system_admin_job_context
from core.tasks import platform_task
from core.types import JsonObject


async def _enter_worker_context(*, trace_id: str) -> None:
    _ = set_context(
        await build_system_admin_job_context(
            trace_id=trace_id,
            session_id=f"shop:{trace_id}",
            channel="shop",
        )
    )


@platform_task(SHOP_REBUILD_STOREFRONT)
async def shop_rebuild_storefront(
    slug: str,
    *,
    di: Di,
) -> JsonObject:
    """Пересобрать Redis-снапшот витрины после мутации каталога."""
    await _enter_worker_context(trace_id=f"shop:rebuild:{slug}")
    try:
        snapshot = await di.storefront_service.rebuild_snapshot(slug)
        return JsonObject({"slug": slug, "rebuilt": snapshot is not None})
    finally:
        clear_context()


@platform_task(SHOP_NOTIFY_ORDER)
async def shop_notify_order(
    shop_order_id: str,
    *,
    di: Di,
) -> JsonObject:
    """Отправить уведомление о заказе владельцу (Telegram-чат магазина)."""
    await _enter_worker_context(trace_id=f"shop:notify:{shop_order_id}")
    try:
        delivered = await di.notification_service.notify_order(shop_order_id)
        return JsonObject({"shop_order_id": shop_order_id, "delivered": delivered})
    finally:
        clear_context()


@platform_task(SHOP_PROVISION_DOMAIN)
async def shop_provision_domain(
    shop_domain_id: str,
    *,
    di: Di,
) -> JsonObject:
    """Проверить DNS домена и поднять Ingress/TLS; результат ждёт HTTP через wait_result."""
    await _enter_worker_context(trace_id=f"shop:domain:{shop_domain_id}")
    try:
        record = await di.domain_service.provision_domain(shop_domain_id)
        return JsonObject(
            {"shop_domain_id": record.shop_domain_id, "status": record.status.value}
        )
    finally:
        clear_context()


@platform_task(SHOP_RECONCILE_DOMAINS_TICK)
async def shop_reconcile_domains_tick(
    schedule_task_id: str | None = None,
    company_id: str | None = None,
    *,
    di: Di,
) -> JsonObject:
    """Сверка незавершённых доменов: повторная DNS-проверка и доведение до active."""
    _ = (schedule_task_id, company_id)
    await _enter_worker_context(trace_id="shop:domains:reconcile")
    try:
        retried = 0
        for record in await ShopDomain.list_unfinished():
            updated = await di.domain_service.reconcile_domain(record)
            if updated.status == ShopDomainStatus.ACTIVE:
                retried += 1
        return JsonObject({"checked": retried})
    finally:
        clear_context()


@platform_task(SHOP_REBUILD_AGGREGATE)
async def shop_rebuild_aggregate(
    shop_id: str | None = None,
    *,
    di: Di,
) -> JsonObject:
    """Пересобрать поисковый слой агрегатора: один магазин или все published."""
    await _enter_worker_context(trace_id=f"shop:aggregate:{shop_id or 'all'}")
    try:
        indexed = await di.aggregate_service.rebuild(shop_id)
        return JsonObject({"indexed": indexed})
    finally:
        clear_context()
