"""MenuFileImportService — импорт меню из XLSX или JSON Яндекс Еды без агента.

Каждая строка файла создаёт новое блюдо (похожее имя — ``similar_shop_product_id``),
модификаторы строки — группы и опции магазина с привязкой к блюду; при цели
``new_menu``/``into_menu`` блюдо встаёт в раздел меню по пути категорий файла.
Фото по URL скачивает задача ``shop_menu_photo_download`` после ответа команды;
``enrich_after`` ставит агенту WorkItem обогащения созданных блюд.
"""

from __future__ import annotations

import asyncio
import ipaddress
from urllib.parse import urlsplit

from httpx2 import HTTPError
from PIL.Image import DecompressionBombError

from apps.shop.models import (
    ModifierGroupKind,
    ModifierPriceMode,
    ModifierSelectionMode,
    ShopMenu,
    ShopMenuFileFormat,
    ShopMenuSection,
    ShopModifierGroup,
    ShopModifierOption,
    ShopProduct,
    ShopProductModifierGroup,
)
from apps.shop.models.common import new_id
from apps.shop.models.import_api import (
    ShopMenuFileImportReport,
    ShopMenuFileImportRunPayload,
    ShopProductsEnrichPayload,
)
from apps.shop.services.menu_file_parsers import (
    DEFAULT_SECTION_NAME,
    ParsedDish,
    ParsedMenuFile,
    ParsedModifierGroup,
    parse_menu_xlsx,
    parse_yandex_json,
)
from apps.shop.services.menu_import_service import MenuImportService
from apps.shop.services.menu_photo_crop import downloaded_photo_jpeg
from apps.shop.services.shop_service import ShopService
from apps.shop.tasks.task_names import SHOP_MENU_PHOTO_DOWNLOAD
from core.errors.boundary import PlatformConflictError
from core.files.reader.service import read_stored_file_by_id
from core.http.client import ProxyStrategy, get_httpx_client
from core.logging import get_logger
from core.tasks import enqueue
from core.utils.time import utcnow

logger = get_logger(__name__)

_PHOTO_MAX_BYTES = 24 * 1024 * 1024


async def _require_public_photo_url(url: str) -> None:
    """URL фото файла — внешний ресурс: адреса кластера и приватных сетей запрещены."""
    parts = urlsplit(url)
    if parts.scheme not in ("http", "https") or parts.hostname is None:
        raise PlatformConflictError("Photo URL must be http(s)", error_code="shop_menu_photo_url_invalid")
    port = parts.port if parts.port is not None else (443 if parts.scheme == "https" else 80)
    infos = await asyncio.get_running_loop().getaddrinfo(parts.hostname, port)
    if not infos or not all(ipaddress.ip_address(info[4][0]).is_global for info in infos):
        raise PlatformConflictError(
            "Photo URL resolves to a non-public address", error_code="shop_menu_photo_url_invalid"
        )


class MenuFileImportService:
    """Разбор файла меню и запись блюд, модификаторов и разделов заведения."""

    def __init__(
        self,
        shop_service: ShopService,
        menu_import_service: MenuImportService,
    ) -> None:
        self._shops: ShopService = shop_service
        self._imports: MenuImportService = menu_import_service

    async def run(
        self,
        company_id: str,
        user_id: str,
        namespace: str,
        payload: ShopMenuFileImportRunPayload,
    ) -> ShopMenuFileImportReport:
        shop = await self._shops.get_shop(company_id, payload.shop_id)
        _ = await self._imports.require_target_menu(shop, payload)
        _ = await self._imports.company_file_ref(company_id, payload.file_id)
        data, _ = await read_stored_file_by_id(payload.file_id)
        parsed = await asyncio.to_thread(self._parse, data, ShopMenuFileFormat(payload.format))
        menu = await self._imports.ensure_target_menu(
            shop, payload, shop_menu_id=new_id("shopmenu")
        )
        sections: dict[tuple[str, ...], ShopMenuSection] = {}
        groups: dict[str, ShopModifierGroup] = {}
        created: list[str] = []
        similar = 0
        photo_urls: dict[str, str] = {}
        for dish in parsed.dishes:
            product = await self._create_dish(shop.shop_id, dish, groups)
            created.append(product.shop_product_id)
            if product.similar_shop_product_id is not None:
                similar += 1
            if dish.photo_url is not None:
                photo_urls[product.shop_product_id] = dish.photo_url
            if menu is not None:
                section = await self._section(menu, dish.section_path, sections)
                _ = await self._imports.ensure_menu_item(
                    menu, section, product, shop_menu_item_id=new_id("shopmitem")
                )
        if created:
            await self._imports.publish_catalog_changed(shop)
        if photo_urls:
            _ = await enqueue(
                SHOP_MENU_PHOTO_DOWNLOAD,
                company_id=company_id,
                user_id=user_id,
                namespace=namespace,
                shop_id=shop.shop_id,
                photo_urls=photo_urls,
            )
        enrich_work_item_id = None
        if payload.enrich_after and created:
            work_item = await self._imports.start_enrich(
                company_id,
                user_id,
                namespace,
                ShopProductsEnrichPayload(shop_id=shop.shop_id, shop_product_ids=created),
            )
            enrich_work_item_id = work_item.work_item_id
        return ShopMenuFileImportReport(
            shop_id=shop.shop_id,
            shop_menu_id=menu.shop_menu_id if menu is not None else None,
            created=len(created),
            similar=similar,
            errors=parsed.errors,
            enrich_work_item_id=enrich_work_item_id,
        )

    async def download_photos(
        self, company_id: str, shop_id: str, photo_urls: dict[str, str]
    ) -> list[str]:
        """Фото блюд по URL файла; блюдо с уже заданным фото не трогается. Ждёт контекст компании.

        Битая ссылка не останавливает остальные: успешные фото сохраняются, затем
        ``PlatformConflictError`` перечисляет блюда без фото.
        """
        shop = await self._shops.get_shop(company_id, shop_id)
        updated: list[str] = []
        failed: list[str] = []
        async with get_httpx_client(timeout=30.0, strategy=ProxyStrategy.DIRECT_ONLY) as client:
            for shop_product_id, url in photo_urls.items():
                product = await self._shops.get_product(company_id, shop.shop_id, shop_product_id)
                if product.photo_file_id is not None:
                    continue
                try:
                    await _require_public_photo_url(url)
                    response = await client.get(url, follow_redirects=False)
                    _ = response.raise_for_status()
                    if len(response.content) > _PHOTO_MAX_BYTES:
                        raise PlatformConflictError(
                            "Photo exceeds 24 MiB", error_code="shop_menu_photo_url_invalid"
                        )
                    jpeg = await asyncio.to_thread(downloaded_photo_jpeg, response.content)
                except (HTTPError, OSError, DecompressionBombError, PlatformConflictError) as exc:
                    logger.warning(
                        "shop.menu_photo.download_failed",
                        shop_id=shop.shop_id,
                        shop_product_id=shop_product_id,
                        error=str(exc),
                    )
                    failed.append(shop_product_id)
                    continue
                product.photo_file_id = await self._imports.upload_product_photo(
                    shop.shop_id, product.shop_product_id, jpeg
                )
                product.updated_at = utcnow()
                _ = await product.save()
                updated.append(product.shop_product_id)
        if updated:
            await self._imports.publish_catalog_changed(shop)
        if failed:
            raise PlatformConflictError(
                f"Photo download failed for dishes: {', '.join(failed)}",
                error_code="shop_menu_photo_download_failed",
            )
        return updated

    @staticmethod
    def _parse(data: bytes, file_format: ShopMenuFileFormat) -> ParsedMenuFile:
        if file_format == ShopMenuFileFormat.XLSX:
            return parse_menu_xlsx(data)
        return parse_yandex_json(data)

    async def _create_dish(
        self, shop_id: str, dish: ParsedDish, groups: dict[str, ShopModifierGroup]
    ) -> ShopProduct:
        now = utcnow()
        product = await self._imports.create_imported_product(
            ShopProduct(
                shop_product_id=new_id("shopprod"),
                shop_id=shop_id,
                name=dish.name,
                description=dish.description,
                measure=dish.measure,
                measure_unit=dish.measure_unit,
                ingredients=list(dish.ingredients),
                nutrition=dish.nutrition,
                price_minor=dish.price_minor,
                created_at=now,
                updated_at=now,
            )
        )
        for sort, parsed_group in enumerate(dish.modifier_groups):
            group = await self._modifier_group(shop_id, parsed_group, groups)
            _ = await ShopProductModifierGroup.create(
                ShopProductModifierGroup(
                    product_id=product.shop_product_id,
                    group_id=group.shop_modifier_group_id,
                    sort=sort,
                )
            )
        return product

    async def _modifier_group(
        self, shop_id: str, parsed: ParsedModifierGroup, groups: dict[str, ShopModifierGroup]
    ) -> ShopModifierGroup:
        """Одинаковая группа файла (имя, лимиты, опции) создаётся один раз и делится блюдами."""
        key = parsed.model_dump_json()
        if key in groups:
            return groups[key]
        now = utcnow()
        group = await ShopModifierGroup.create(
            ShopModifierGroup(
                shop_modifier_group_id=new_id("shopmodgrp"),
                shop_id=shop_id,
                name=parsed.name,
                kind=ModifierGroupKind.ADDON,
                selection_mode=(
                    ModifierSelectionMode.SINGLE
                    if parsed.max_selected == 1
                    else ModifierSelectionMode.MULTI
                ),
                min_selected=parsed.min_selected,
                max_selected=parsed.max_selected,
                price_mode=ModifierPriceMode.DELTA,
                sort=len(groups),
                created_at=now,
                updated_at=now,
            )
        )
        for sort, option in enumerate(parsed.options):
            _ = await ShopModifierOption.create(
                ShopModifierOption(
                    shop_modifier_option_id=new_id("shopmodopt"),
                    group_id=group.shop_modifier_group_id,
                    name=option.name,
                    price_minor=option.price_minor,
                    max_per_option=option.max_per_option,
                    external_id=option.external_id,
                    sort=sort,
                    created_at=now,
                    updated_at=now,
                )
            )
        groups[key] = group
        return group

    async def _section(
        self,
        menu: ShopMenu,
        path: list[str],
        sections: dict[tuple[str, ...], ShopMenuSection],
    ) -> ShopMenuSection:
        names = tuple(path) if path else (DEFAULT_SECTION_NAME,)
        parent_id: str | None = None
        section: ShopMenuSection | None = None
        for depth in range(1, len(names) + 1):
            key = names[:depth]
            if key not in sections:
                sections[key] = await self._imports.ensure_section(
                    menu,
                    names[depth - 1],
                    shop_menu_section_id=new_id("shopmsec"),
                    parent_id=parent_id,
                )
            section = sections[key]
            parent_id = section.shop_menu_section_id
        if section is None:
            raise ValueError("section path is empty")
        return section
