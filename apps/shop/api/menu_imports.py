"""REST-зеркало импорта меню: тело — payload команды, path-id совпадает с полем тела."""

from __future__ import annotations

from fastapi import APIRouter

from apps.shop.di import Di
from apps.shop.models.import_api import (
    ShopMenuFileImportReport,
    ShopMenuFileImportRunPayload,
    ShopMenuImportApplyPayload,
    ShopMenuImportApplyResult,
    ShopMenuImportStartPayload,
    ShopMenuTemplateBuildPayload,
    ShopProductsEnrichApplyPayload,
    ShopProductsEnrichApplyResult,
    ShopProductsEnrichPayload,
)
from apps.shop.realtime.menu_import_operations import (
    op_menu_file_imports_run,
    op_menu_imports_apply,
    op_menu_imports_list,
    op_menu_imports_start,
    op_menu_templates_build,
    op_products_enrich,
    op_products_enrich_apply,
)
from apps.shop.realtime.operations import ShopIdPayload
from core.context import require_context
from core.pagination import ListResponse
from core.websocket import raise_invalid
from core.worktracker.models import WorkItem

router = APIRouter(prefix="/shops", tags=["shop-menu-import"])


def _require_path(field: str, path_value: str, body_value: str) -> None:
    if path_value != body_value:
        raise_invalid(ValueError(f"path {field} does not match payload {field}"))


@router.post("/{shop_id}/menu-imports", response_model=WorkItem)
async def start_menu_import(
    shop_id: str, payload: ShopMenuImportStartPayload, di: Di
) -> WorkItem:
    _require_path("shop_id", shop_id, payload.shop_id)
    return await op_menu_imports_start(payload, user=require_context().user, di=di)


@router.get("/{shop_id}/menu-imports", response_model=ListResponse[WorkItem])
async def list_menu_imports(shop_id: str, di: Di) -> ListResponse[WorkItem]:
    return await op_menu_imports_list(
        ShopIdPayload(shop_id=shop_id), user=require_context().user, di=di
    )


@router.post(
    "/{shop_id}/menu-imports/{work_item_id}/apply", response_model=ShopMenuImportApplyResult
)
async def apply_menu_import(
    shop_id: str, work_item_id: str, payload: ShopMenuImportApplyPayload, di: Di
) -> ShopMenuImportApplyResult:
    _require_path("shop_id", shop_id, payload.shop_id)
    _require_path("work_item_id", work_item_id, payload.work_item_id)
    return await op_menu_imports_apply(payload, user=require_context().user, di=di)


@router.post("/{shop_id}/menu-templates", response_model=WorkItem)
async def build_menu_template(
    shop_id: str, payload: ShopMenuTemplateBuildPayload, di: Di
) -> WorkItem:
    _require_path("shop_id", shop_id, payload.shop_id)
    return await op_menu_templates_build(payload, user=require_context().user, di=di)


@router.post("/{shop_id}/products/enrich", response_model=WorkItem)
async def enrich_products(shop_id: str, payload: ShopProductsEnrichPayload, di: Di) -> WorkItem:
    _require_path("shop_id", shop_id, payload.shop_id)
    return await op_products_enrich(payload, user=require_context().user, di=di)


@router.post(
    "/{shop_id}/products/enrich/{work_item_id}/apply",
    response_model=ShopProductsEnrichApplyResult,
)
async def apply_products_enrich(
    shop_id: str, work_item_id: str, payload: ShopProductsEnrichApplyPayload, di: Di
) -> ShopProductsEnrichApplyResult:
    _require_path("shop_id", shop_id, payload.shop_id)
    _require_path("work_item_id", work_item_id, payload.work_item_id)
    return await op_products_enrich_apply(payload, user=require_context().user, di=di)


@router.post("/{shop_id}/menu-file-imports", response_model=ShopMenuFileImportReport)
async def run_menu_file_import(
    shop_id: str, payload: ShopMenuFileImportRunPayload, di: Di
) -> ShopMenuFileImportReport:
    _require_path("shop_id", shop_id, payload.shop_id)
    return await op_menu_file_imports_run(payload, user=require_context().user, di=di)
