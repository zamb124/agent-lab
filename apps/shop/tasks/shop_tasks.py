"""Shop TaskIQ tasks — фоновая работа витрин (очередь ``shop``).

Сюда уходит всё тяжёлое и вторичное относительно HTTP-команды:
пересборка Redis-снапшотов, доставка уведомлений о заказе, провиженинг
кастомных доменов, ребилд поискового каталога агрегатора.
"""

from __future__ import annotations

from apps.shop.di import Di
from apps.shop.events import publish_shop_catalog_changed
from apps.shop.models import (
    Shop,
    ShopBackInStock,
    ShopCategory,
    ShopDomain,
    ShopDomainStatus,
    ShopOrder,
    ShopProduct,
    order_status_label,
)
from apps.shop.tasks.task_names import (
    SHOP_AI_DESCRIBE_BATCH,
    SHOP_NOTIFY_BACK_IN_STOCK,
    SHOP_NOTIFY_CUSTOMER,
    SHOP_NOTIFY_ORDER,
    SHOP_PROVISION_DOMAIN,
    SHOP_REBUILD_AGGREGATE,
    SHOP_REBUILD_STOREFRONT,
    SHOP_RECONCILE_DOMAINS_TICK,
)
from core.context import clear_context, set_context
from core.context.job_context import build_job_context, pick_company_billing_user
from core.identity.system_bootstrap import build_system_admin_job_context
from core.logging import get_logger
from core.models.identity_models import Company
from core.tasks import enqueue, platform_task
from core.types import JsonObject
from core.utils.time import utcnow

logger = get_logger(__name__)


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


@platform_task(SHOP_NOTIFY_CUSTOMER)
async def shop_notify_customer(
    shop_order_id: str,
    *,
    di: Di,
) -> JsonObject:
    """DM покупателю о статусе заказа: TG/MAX бренда + Redis-outbox (e2e).

    Идемпотентно по факту статуса: повторная доставка того же текста
    безопасна, ретрай TaskIQ не плодит новых сущностей.
    """
    await _enter_worker_context(trace_id=f"shop:notify-customer:{shop_order_id}")
    try:
        order = await ShopOrder.get_by_id(shop_order_id)
        if order is None or not order.customer_id:
            return JsonObject({"delivered": False, "reason": "no_customer"})
        shop = await Shop.get_by_id(order.shop_id)
        status_label = order_status_label(
            order.status, order.delivery_type, for_notify=True
        )
        shop_name = shop.name if shop is not None else ""
        text = (
            f"Заказ #{order.public_code} — {status_label}.\n"
            f"{shop_name}\nИтого: {order.total_minor // 100} "
            f"{order.currency}"
        )
        delivered = await di.customer_notify_service.send_text(
            order.customer_id,
            text,
            apex=di.settings.storefront_domain_suffix,
        )
        return JsonObject({"shop_order_id": shop_order_id, "delivered": delivered})
    finally:
        clear_context()


@platform_task(SHOP_NOTIFY_BACK_IN_STOCK)
async def shop_notify_back_in_stock(
    product_id: str,
    *,
    di: Di,
) -> JsonObject:
    """DM подписчикам «сообщить о появлении»: товар снова доступен.

    Отработанная подписка удаляется — повторный возврат обслуживает
    новый виток записей ``shop_back_in_stock``.
    """
    await _enter_worker_context(trace_id=f"shop:back-in-stock:{product_id}")
    try:
        product = await ShopProduct.get_by_id(product_id)
        if product is None or not product.is_available:
            return JsonObject({"notified": 0})
        shop = await Shop.get_by_id(product.shop_id)
        shop_name = shop.name if shop is not None else ""
        notified = 0
        for sub in await ShopBackInStock.list_pending_by_product(product_id):
            text = f"«{product.name}» снова в наличии.\n{shop_name}"
            delivered = await di.customer_notify_service.send_text(
                sub.customer_id,
                text,
                apex=di.settings.storefront_domain_suffix,
            )
            if delivered:
                notified += 1
            _ = await sub.delete()
        return JsonObject({"product_id": product_id, "notified": notified})
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


@platform_task(SHOP_AI_DESCRIBE_BATCH)
async def shop_ai_describe_batch(
    shop_id: str,
    company_id: str,
    *,
    di: Di,
) -> JsonObject:
    """AI-описания для всех позиций магазина без описания.

    Контекст — платёжный пользователь компании магазина: LLM-вызовы идут
    в биллинг компании, а не system. Без retry: генерации стоят денег,
    повтор батча идемпотентен по факту пустого описания.
    """
    trace_id = f"shop:ai-batch:{shop_id}"
    shop = await Shop.get_by_id(shop_id)
    if shop is None or str(shop.company_id) != company_id:
        return JsonObject({"updated": 0, "failed": 0})
    company = await Company.get(company_id)
    if company is None:
        raise ValueError(f"shop_ai_describe_batch: company {company_id} not found")
    billing_user = await pick_company_billing_user(company=company)
    _ = set_context(
        build_job_context(
            company=company,
            user=billing_user,
            host="shop-job.local",
            trace_id=trace_id,
            session_id=trace_id,
            channel="shop",
        )
    )
    try:
        categories = {
            c.shop_category_id: c.name
            for c in await ShopCategory.list_by_shop_by_sort_asc(shop_id)
        }
        products = [
            p
            for p in await ShopProduct.list_by_shop_by_sort_asc(shop_id)
            if not p.description.strip()
        ]
        updated = 0
        failed = 0
        for product in products:
            try:
                text = await di.ai_service.describe_product(
                    name=product.name,
                    category_name=categories.get(product.category_id or ""),
                    photo_file_id=product.photo_file_id,
                )
            except Exception as exc:
                failed += 1
                logger.warning(
                    "shop.ai_describe_batch.product_failed",
                    shop_id=shop_id,
                    shop_product_id=product.shop_product_id,
                    error=str(exc),
                )
                continue
            product.description = text
            product.updated_at = utcnow()
            _ = await product.save()
            updated += 1
        if updated:
            await di.storefront_service.invalidate_snapshot(shop_id)
            await publish_shop_catalog_changed(shop_id, shop.slug, company_id)
            _ = await enqueue(SHOP_REBUILD_STOREFRONT, slug=shop.slug)
        return JsonObject(
            {"updated": updated, "failed": failed, "total": len(products)}
        )
    finally:
        clear_context()
