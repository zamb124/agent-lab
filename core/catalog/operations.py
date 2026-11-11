"""Общие `op_*` каталога: мастер-карта и базовые чтения во всех сервисах.

Регистрируются в роутерах сервисов под префиксом владельца —
``<svc>/catalog_products/*`` (как ``<svc>/namespaces/list`` →
``op_namespaces_list``). Здесь живут только операции над базовой
карточкой и справочником ЕИ; фасетные правки и overlay'ы — в
операциях самих сервисов (владение ``instance_id`` проверяется там).

Права: чтение — ``company#viewer``, запись — ``company#editor``.
"""

from __future__ import annotations

from decimal import Decimal

from pydantic import Field

from core.authz.errors import AuthzDenied
from core.authz.models import AuthzObject
from core.catalog.contracts import CatalogProductDetail
from core.catalog.models import CatalogProduct, CatalogUom
from core.di.platform import PlatformDi
from core.models.base import StrictBaseModel
from core.models.identity_models import User
from core.pagination import CursorPage, ListResponse
from core.request_scope import CompanyScope, require_company, require_company_viewer
from core.websocket import EmptyPayload, raise_forbidden


async def _company_editor(di: PlatformDi) -> CompanyScope:
    """Активная компания + `company#editor` (запись мастер-карты)."""
    scope = require_company()
    try:
        await di.authz_service.require_can_edit(
            AuthzObject.company(scope.company_id), user_id=scope.user_id
        )
    except AuthzDenied as exc:
        raise_forbidden(exc)
    return scope


class CatalogProductsListPayload(StrictBaseModel):
    query: str | None = Field(
        default=None, description="Подстрока по имени/SKU (pg_trgm)."
    )
    include_archived: bool = Field(default=False)
    limit: int = Field(default=50, ge=1, le=200)
    cursor: str | None = Field(default=None)


class CatalogProductIdPayload(StrictBaseModel):
    product_id: str = Field(min_length=1)


class CatalogProductCreatePayload(StrictBaseModel):
    """Создание товара из мастер-карты: только базовые поля."""

    name: str = Field(min_length=1, max_length=300)
    uom_id: str = Field(min_length=1)
    description: str = ""
    image_file_ids: list[str] = Field(default_factory=list)
    sku: str | None = Field(default=None, max_length=128)
    weight: Decimal | None = Field(default=None, ge=0)
    volume: Decimal | None = Field(default=None, ge=0)
    barcodes: list[str] = Field(default_factory=list, max_length=20)


class CatalogProductUpdatePayload(StrictBaseModel):
    """Правка базовых полей; отсутствующее поле не трогается.

    ``is_archived=True`` — архив «выключает везде»: витрины прячут
    позицию, склад отказывает новым документам, история читается.
    """

    product_id: str = Field(min_length=1)
    name: str | None = Field(default=None, min_length=1, max_length=300)
    description: str | None = None
    image_file_ids: list[str] | None = None
    sku: str | None = Field(default=None, max_length=128)
    weight: Decimal | None = Field(default=None, ge=0)
    volume: Decimal | None = Field(default=None, ge=0)
    barcodes: list[str] | None = Field(default=None, max_length=20)
    """PUT-форма набора кодов товара: ``None`` — не трогать, список —
    полная замена (коды упаковок отдельно)."""
    is_archived: bool | None = None


class CatalogProductsSuggestPayload(StrictBaseModel):
    """Вход дедупа «подключить или создать»: любые из name/sku/barcode."""

    name: str | None = Field(default=None, max_length=300)
    sku: str | None = Field(default=None, max_length=128)
    barcode: str | None = Field(default=None, max_length=128)
    limit: int = Field(default=8, ge=1, le=20)


async def op_products_list(
    payload: CatalogProductsListPayload, *, user: User, di: PlatformDi
) -> CursorPage[CatalogProduct]:
    _ = user
    scope = await require_company_viewer(di.authz_service)
    return await di.catalog_service.list_products_page(
        company_id=scope.company_id,
        query=payload.query,
        include_archived=payload.include_archived,
        limit=payload.limit,
        cursor=payload.cursor,
    )


async def op_products_item(
    payload: CatalogProductIdPayload, *, user: User, di: PlatformDi
) -> CatalogProductDetail:
    _ = user
    scope = await require_company_viewer(di.authz_service)
    return await di.catalog_service.get_product_detail(
        company_id=scope.company_id, product_id=payload.product_id
    )


async def op_products_suggest(
    payload: CatalogProductsSuggestPayload, *, user: User, di: PlatformDi
) -> ListResponse[CatalogProduct]:
    _ = user
    scope = await require_company_viewer(di.authz_service)
    return ListResponse(
        items=await di.catalog_service.suggest_duplicates(
            company_id=scope.company_id,
            name=payload.name,
            sku=payload.sku,
            barcode=payload.barcode,
            limit=payload.limit,
        )
    )


async def op_products_create(
    payload: CatalogProductCreatePayload, *, user: User, di: PlatformDi
) -> CatalogProduct:
    _ = user
    scope = await _company_editor(di)
    return await di.catalog_service.create_product(
        company_id=scope.company_id,
        name=payload.name,
        uom_id=payload.uom_id,
        description=payload.description,
        image_file_ids=payload.image_file_ids,
        sku=payload.sku,
        weight=payload.weight,
        volume=payload.volume,
        barcodes=payload.barcodes,
    )


async def op_products_update(
    payload: CatalogProductUpdatePayload, *, user: User, di: PlatformDi
) -> CatalogProduct:
    _ = user
    scope = await _company_editor(di)
    return await di.catalog_service.update_product(
        company_id=scope.company_id,
        product_id=payload.product_id,
        name=payload.name,
        description=payload.description,
        image_file_ids=payload.image_file_ids,
        sku=payload.sku,
        weight=payload.weight,
        volume=payload.volume,
        barcodes=payload.barcodes,
        is_archived=payload.is_archived,
    )


async def op_uoms_list(
    payload: EmptyPayload, *, user: User, di: PlatformDi
) -> ListResponse[CatalogUom]:
    _ = user
    _ = payload
    scope = await require_company_viewer(di.authz_service)
    return ListResponse(
        items=await di.catalog_service.list_uoms(company_id=scope.company_id)
    )
