"""Доменные события каталога на шине ``platform:events``.

``catalog/product/updated`` — точка инвалидации проекций сервисов:
consumer group ``shop`` пересобирает снапшоты витрин с этим товаром,
склад — индексы предпросмотра. Доставка идёт и в компанию (UI-списки
товаров всех сервисов обновляются онлайн), и как доменный факт для
durable-групп и триггеров flows.
"""

from __future__ import annotations

from pydantic import BaseModel

from core.catalog.contracts import CatalogOverlay
from core.catalog.models.product import CatalogProduct
from core.events import (
    publish_domain_event,
    publish_event_to_company,
    register_platform_event,
)

CATALOG_PRODUCT_CREATED = "catalog/product/created"
CATALOG_PRODUCT_UPDATED = "catalog/product/updated"
CATALOG_PRODUCT_OVERLAY_CHANGED = "catalog/product_overlay/changed"
CATALOG_PRODUCT_FACET_CHANGED = "catalog/product_facet/changed"


class CatalogProductEventPayload(BaseModel):
    """Payload ``catalog/product/created|updated`` — карточка после мутации."""

    product: CatalogProduct


class CatalogProductOverlayEventPayload(BaseModel):
    """Payload ``catalog/product_overlay/changed``.

    ``overlay=None`` — override снят (полное наследование базы).
    """

    product_id: str
    facet: str
    instance_id: str | None = None
    overlay: CatalogOverlay | None = None


class CatalogProductFacetEventPayload(BaseModel):
    """Payload ``catalog/product_facet/changed`` — мутация сервисного фасета.

    ``instance_id`` — конкретный экземпляр фасета (витрина ``shop_id``);
    ``None`` — сервисный фасет без привязки к экземпляру (``stock``).
    """

    product_id: str
    facet: str
    instance_id: str | None = None


register_platform_event(
    CATALOG_PRODUCT_CREATED,
    CatalogProductEventPayload,
    description="Создан товар каталога компании.",
)
register_platform_event(
    CATALOG_PRODUCT_UPDATED,
    CatalogProductEventPayload,
    description="Изменены базовые поля товара (name/description/images/sku/вес/архив).",
)
register_platform_event(
    CATALOG_PRODUCT_OVERLAY_CHANGED,
    CatalogProductOverlayEventPayload,
    description="Изменён или снят сервисный override контента товара.",
)
register_platform_event(
    CATALOG_PRODUCT_FACET_CHANGED,
    CatalogProductFacetEventPayload,
    description="Сервисный фасет товара создан или изменён (attach, политика, листинг).",
)


async def publish_catalog_product_created(product: CatalogProduct) -> None:
    dumped = CatalogProductEventPayload(product=product).model_dump(mode="json")
    await publish_event_to_company(
        product.company_id, CATALOG_PRODUCT_CREATED, dumped
    )
    await publish_domain_event(
        CATALOG_PRODUCT_CREATED,
        dumped,
        company_id=product.company_id,
    )


async def publish_catalog_product_updated(product: CatalogProduct) -> None:
    dumped = CatalogProductEventPayload(product=product).model_dump(mode="json")
    await publish_event_to_company(
        product.company_id, CATALOG_PRODUCT_UPDATED, dumped
    )
    await publish_domain_event(
        CATALOG_PRODUCT_UPDATED,
        dumped,
        company_id=product.company_id,
    )


async def publish_catalog_overlay_changed(
    product_id: str,
    company_id: str,
    *,
    facet: str,
    instance_id: str | None,
    overlay: CatalogOverlay | None,
) -> None:
    dumped = CatalogProductOverlayEventPayload(
        product_id=product_id,
        facet=facet,
        instance_id=instance_id,
        overlay=overlay,
    ).model_dump(mode="json")
    await publish_event_to_company(
        company_id, CATALOG_PRODUCT_OVERLAY_CHANGED, dumped
    )
    await publish_domain_event(
        CATALOG_PRODUCT_OVERLAY_CHANGED,
        dumped,
        company_id=company_id,
    )


async def publish_catalog_product_facet_changed(
    product_id: str,
    company_id: str,
    *,
    facet: str,
    instance_id: str | None = None,
) -> None:
    """Фасет сервиса создан/изменён — UI-списки фасета обновляются онлайн."""
    dumped = CatalogProductFacetEventPayload(
        product_id=product_id,
        facet=facet,
        instance_id=instance_id,
    ).model_dump(mode="json")
    await publish_event_to_company(
        company_id, CATALOG_PRODUCT_FACET_CHANGED, dumped
    )
    await publish_domain_event(
        CATALOG_PRODUCT_FACET_CHANGED,
        dumped,
        company_id=company_id,
    )
