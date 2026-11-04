"""Типизированный клиент сервиса shop.

Тонкая обвязка поверх `ServiceClient`: те же payload, что WS-команды
`shop/<entity>/<verb>_requested`, через их REST-зеркала. Возвращает JsonObject —
контракт REST.
"""

from __future__ import annotations

from urllib.parse import quote

from core.clients.service_client import ServiceClient
from core.clients.shop_models import (
    ShopCatalogListArgs,
    ShopMenuImportApplyArgs,
    ShopProductsEnrichApplyArgs,
)
from core.types import JsonObject, require_json_object

_API = "/shop/api/v1/shops"


class ShopClient:
    """Доступ к каталогу заведения и write-back агента меню."""

    def __init__(self, service_client: ServiceClient | None = None) -> None:
        self._http: ServiceClient = (
            service_client if service_client is not None else ServiceClient()
        )

    async def catalog_list(self, args: ShopCatalogListArgs) -> JsonObject:
        raw = await self._http.get("shop", f"{_API}/{quote(args.shop_id)}/products")
        return require_json_object(raw, "shop.catalog_list")

    async def menu_import_apply(self, args: ShopMenuImportApplyArgs) -> JsonObject:
        raw = await self._http.post(
            "shop",
            f"{_API}/{quote(args.shop_id)}/menu-imports/{quote(args.work_item_id)}/apply",
            json=args.model_dump(mode="json"),
            timeout=120.0,
        )
        return require_json_object(raw, "shop.menu_import_apply")

    async def products_enrich_apply(self, args: ShopProductsEnrichApplyArgs) -> JsonObject:
        raw = await self._http.post(
            "shop",
            f"{_API}/{quote(args.shop_id)}/products/enrich/{quote(args.work_item_id)}/apply",
            json=args.model_dump(mode="json"),
        )
        return require_json_object(raw, "shop.products_enrich_apply")


__all__ = ["ShopClient"]
