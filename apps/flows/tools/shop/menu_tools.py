"""Platform Shop tools агента меню — thin wrappers over ShopClient.

Tag: shop. Агент ``shop_menu_agent`` работает по WorkItem со связью ``shop``:
``shop_id`` и режим — в ``WorkItem.variables``. Write-back идёт REST-зеркалами
``shop/menu_imports/apply_requested`` и ``shop/products/enrich_apply_requested``
от сессии сотрудника; повтор с тем же ``work_item_id`` возвращает прежний итог.
"""

from __future__ import annotations

from apps.flows.src.state import ExecutionState
from apps.flows.src.tools.decorator import tool
from apps.flows.tools.tool_access import STANDARD_USER_TOOL_GROUPS
from core.clients.shop_client import ShopClient
from core.clients.shop_models import (
    ShopCatalogListArgs,
    ShopMenuImportApplyArgs,
    ShopMenuImportSectionArgs,
    ShopProductEnrichUpdateArgs,
    ShopProductsEnrichApplyArgs,
)
from core.types import JsonObject

_TAGS = ["shop"]
_PERM = list(STANDARD_USER_TOOL_GROUPS)


@tool(
    name="shop_catalog_list",
    description=(
        "Lists dishes of the shop catalog: shop_product_id, name, price_minor, "
        "description, measure, ingredients, nutrition, allergens, photo. Use to reuse "
        "existing dishes in a menu template and to find dishes to enrich."
    ),
    tags=_TAGS,
    permission=_PERM,
    parameters_model=ShopCatalogListArgs,
    effects=["read"],
)
async def shop_catalog_list(*, state: ExecutionState, shop_id: str) -> JsonObject:
    _ = state
    return await ShopClient().catalog_list(ShopCatalogListArgs(shop_id=shop_id))


@tool(
    name="shop_menu_import_apply",
    description=(
        "Writes the recognized or composed menu of an import/template WorkItem: "
        "sections with dishes. A dish with shop_product_id reuses the catalog dish; "
        "otherwise a new dish is created (marked AI-unverified) with an optional photo "
        "crop from a WorkItem attachment. Completes the WorkItem; safe to retry."
    ),
    tags=_TAGS,
    permission=_PERM,
    parameters_model=ShopMenuImportApplyArgs,
    effects=["write"],
)
async def shop_menu_import_apply(
    *,
    state: ExecutionState,
    shop_id: str,
    work_item_id: str,
    sections: list[ShopMenuImportSectionArgs],
) -> JsonObject:
    _ = state
    return await ShopClient().menu_import_apply(
        ShopMenuImportApplyArgs(shop_id=shop_id, work_item_id=work_item_id, sections=sections)
    )


@tool(
    name="shop_products_enrich_apply",
    description=(
        "Writes enrichment of an enrich WorkItem: per dish only empty fields are filled "
        "(description, measure, ingredients, nutrition, allergens, photo_file_id); "
        "changed dishes are marked AI-unverified. Completes the WorkItem; safe to retry."
    ),
    tags=_TAGS,
    permission=_PERM,
    parameters_model=ShopProductsEnrichApplyArgs,
    effects=["write"],
)
async def shop_products_enrich_apply(
    *,
    state: ExecutionState,
    shop_id: str,
    work_item_id: str,
    updates: list[ShopProductEnrichUpdateArgs],
) -> JsonObject:
    _ = state
    return await ShopClient().products_enrich_apply(
        ShopProductsEnrichApplyArgs(shop_id=shop_id, work_item_id=work_item_id, updates=updates)
    )
