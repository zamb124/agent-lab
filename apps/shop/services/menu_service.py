"""MenuService — меню заведения: статусы, дерево разделов, позиции и слияние похожих блюд.

Каталог блюд принадлежит заведению, меню ссылается на блюда через ``ShopMenuItem``:
одно блюдо живёт в нескольких меню, цена и доступность переопределяются в позиции.
Удаление меню не трогает каталог; архивное меню только восстанавливается в draft.
"""

from __future__ import annotations

from apps.shop.config import ShopSettings
from apps.shop.models import (
    ShopMenu,
    ShopMenuItem,
    ShopMenuSection,
    ShopMenuStatus,
    ShopProduct,
    ShopProductModifierGroup,
)
from apps.shop.models.api import (
    ShopMenuCreateRequest,
    ShopMenuItemAddRequest,
    ShopMenuItemResponse,
    ShopMenuItemUpdateRequest,
    ShopMenuResponse,
    ShopMenuSectionCreateRequest,
    ShopMenuSectionReorderItem,
    ShopMenuSectionUpdateRequest,
    ShopMenuUpdateRequest,
    ShopProductMergeField,
)
from apps.shop.models.common import new_id
from apps.shop.services.shop_service import ShopService
from core.errors.boundary import PlatformConflictError, PlatformNotFoundError
from core.utils.time import utcnow

# Разрешённые переходы статуса меню: ключ — целевой статус, значение — исходные.
_MENU_TRANSITIONS: dict[ShopMenuStatus, frozenset[ShopMenuStatus]] = {
    ShopMenuStatus.DRAFT: frozenset({ShopMenuStatus.ACTIVE, ShopMenuStatus.ARCHIVED}),
    ShopMenuStatus.ACTIVE: frozenset({ShopMenuStatus.DRAFT}),
    ShopMenuStatus.ARCHIVED: frozenset({ShopMenuStatus.DRAFT, ShopMenuStatus.ACTIVE}),
}


def _require_editable(menu: ShopMenu) -> None:
    """Draft и active редактируются, архив — только восстановление в draft."""
    if menu.status == ShopMenuStatus.ARCHIVED:
        raise PlatformConflictError(
            "Archived menu is read-only", error_code="menu_status_invalid"
        )


def _item_response(item: ShopMenuItem, catalog_price_minor: int) -> ShopMenuItemResponse:
    return ShopMenuItemResponse(
        shop_menu_item_id=item.shop_menu_item_id,
        shop_menu_id=item.shop_menu_id,
        shop_menu_section_id=item.shop_menu_section_id,
        shop_product_id=item.shop_product_id,
        price_minor_override=item.price_minor_override,
        is_available=item.is_available,
        sort=item.sort,
        effective_price_minor=item.effective_price_minor(catalog_price_minor),
    )


class MenuService:
    """Меню, разделы и позиции заведения; слияние и проверка блюд каталога."""

    def __init__(self, shop_service: ShopService, settings: ShopSettings) -> None:
        self._shops: ShopService = shop_service
        self._settings: ShopSettings = settings

    # --- Меню ---

    async def list_menus(self, company_id: str, shop_id: str) -> list[ShopMenuResponse]:
        _ = await self._shops.get_shop(company_id, shop_id)
        prices = {
            p.shop_product_id: p.price_minor
            for p in await ShopProduct.list_by_shop_by_sort_asc(shop_id)
        }
        return [
            await self._menu_response(menu, prices)
            for menu in await ShopMenu.list_by_shop_by_sort_asc(shop_id)
        ]

    async def create_menu(
        self, company_id: str, shop_id: str, payload: ShopMenuCreateRequest
    ) -> ShopMenuResponse:
        _ = await self._shops.get_shop(company_id, shop_id)
        now = utcnow()
        menu = await ShopMenu.create(
            ShopMenu(
                shop_menu_id=new_id("shopmenu"),
                shop_id=shop_id,
                name=payload.name,
                status=ShopMenuStatus.DRAFT,
                sort=await ShopMenu.next_sort_by_sort_desc(shop_id),
                created_at=now,
                updated_at=now,
            )
        )
        return await self._menu_response(menu, {})

    async def update_menu(
        self,
        company_id: str,
        shop_id: str,
        shop_menu_id: str,
        payload: ShopMenuUpdateRequest,
    ) -> ShopMenuResponse:
        menu = await self._editable_menu(company_id, shop_id, shop_menu_id)
        if payload.name is not None:
            menu.name = payload.name
        menu.updated_at = utcnow()
        _ = await menu.save()
        return await self._menu_response(menu, await self._menu_prices(menu))

    async def reorder_menus(
        self, company_id: str, shop_id: str, shop_menu_ids: list[str]
    ) -> None:
        """Перестановка меню: ids получают отсортированные sort-значения в новом порядке."""
        _ = await self._shops.get_shop(company_id, shop_id)
        by_id = {m.shop_menu_id: m for m in await ShopMenu.list_by_shop_by_sort_asc(shop_id)}
        if any(mid not in by_id for mid in shop_menu_ids):
            raise PlatformNotFoundError("Menu not found", error_code="menu_not_found")
        ordered = [by_id[mid] for mid in shop_menu_ids]
        now = utcnow()
        for menu, sort in zip(ordered, sorted(m.sort for m in ordered), strict=True):
            if menu.sort != sort:
                menu.sort = sort
                menu.updated_at = now
                _ = await menu.save()

    async def set_menu_status(
        self,
        company_id: str,
        shop_id: str,
        shop_menu_id: str,
        status: ShopMenuStatus,
    ) -> ShopMenuResponse:
        """Переход статуса: activate — только с позициями, архив — только обратно в draft."""
        menu = await self._menu(company_id, shop_id, shop_menu_id)
        if menu.status != status:
            if menu.status not in _MENU_TRANSITIONS[status]:
                raise PlatformConflictError(
                    f"Menu transition {menu.status} -> {status} is not allowed",
                    error_code="menu_status_invalid",
                )
            if status == ShopMenuStatus.ACTIVE and await ShopMenuItem.count_for_menu(
                shop_menu_id
            ) == 0:
                raise PlatformConflictError(
                    "Menu without items cannot be activated", error_code="menu_empty"
                )
            menu.status = status
            menu.updated_at = utcnow()
            _ = await menu.save()
        return await self._menu_response(menu, await self._menu_prices(menu))

    async def remove_menu(self, company_id: str, shop_id: str, shop_menu_id: str) -> None:
        """Удаление меню с разделами и позициями; блюда каталога остаются."""
        menu = await self._menu(company_id, shop_id, shop_menu_id)
        _ = await ShopMenuItem.delete_by_menu(shop_menu_id)
        _ = await ShopMenuSection.delete_by_menu(shop_menu_id)
        _ = await menu.delete()

    # --- Разделы ---

    async def create_section(
        self,
        company_id: str,
        shop_id: str,
        shop_menu_id: str,
        payload: ShopMenuSectionCreateRequest,
    ) -> ShopMenuSection:
        _ = await self._editable_menu(company_id, shop_id, shop_menu_id)
        if payload.parent_id is not None:
            parent = await ShopMenuSection.get_by_id(payload.parent_id)
            if parent is None or parent.shop_menu_id != shop_menu_id:
                raise PlatformNotFoundError(
                    "Menu section not found", error_code="menu_section_not_found"
                )
        now = utcnow()
        return await ShopMenuSection.create(
            ShopMenuSection(
                shop_menu_section_id=new_id("shopmsec"),
                shop_menu_id=shop_menu_id,
                parent_id=payload.parent_id,
                name=payload.name,
                sort=await ShopMenuSection.next_sort_by_sort_desc(shop_menu_id, payload.parent_id),
                created_at=now,
                updated_at=now,
            )
        )

    async def update_section(
        self,
        company_id: str,
        shop_id: str,
        shop_menu_section_id: str,
        payload: ShopMenuSectionUpdateRequest,
    ) -> ShopMenuSection:
        section = await self._editable_section(company_id, shop_id, shop_menu_section_id)
        if payload.name is not None:
            section.name = payload.name
        section.updated_at = utcnow()
        _ = await section.save()
        return section

    async def remove_section(
        self, company_id: str, shop_id: str, shop_menu_section_id: str
    ) -> ShopMenuSection:
        """Удаляет раздел, поднимая подразделы и позиции на уровень родителя;
        возвращает удалённый раздел.

        У корневого раздела позициям некуда подняться — такой раздел с позициями
        не удаляется.
        """
        section = await self._editable_section(company_id, shop_id, shop_menu_section_id)
        items = await ShopMenuItem.list_by_section_by_sort_asc(shop_menu_section_id)
        if items and section.parent_id is None:
            raise PlatformConflictError(
                "Root section still has items", error_code="menu_section_not_empty"
            )
        now = utcnow()
        children = await ShopMenuSection.list_children_by_parent_by_sort_asc(
            section.shop_menu_id, shop_menu_section_id
        )
        next_sort = await ShopMenuSection.next_sort_by_sort_desc(
            section.shop_menu_id, section.parent_id
        )
        for offset, child in enumerate(children):
            child.parent_id = section.parent_id
            child.sort = next_sort + offset
            child.updated_at = now
            _ = await child.save()
        if section.parent_id is not None:
            next_item_sort = await ShopMenuItem.next_sort_by_sort_desc(section.parent_id)
            for offset, item in enumerate(items):
                item.shop_menu_section_id = section.parent_id
                item.sort = next_item_sort + offset
                _ = await item.save()
        _ = await section.delete()
        return section

    async def reorder_sections(
        self,
        company_id: str,
        shop_id: str,
        shop_menu_id: str,
        items: list[ShopMenuSectionReorderItem],
    ) -> None:
        """Заменяет дерево разделов целиком: parent_id каждого узла и
        sort — позиция среди siblings в порядке обхода ``items``.

        ``items`` обязан содержать все разделы меню ровно по разу,
        каждый ``parent_id`` — либо ``None``, либо id из ``items`` без циклов.
        """
        _ = await self._editable_menu(company_id, shop_id, shop_menu_id)
        by_id = {
            s.shop_menu_section_id: s
            for s in await ShopMenuSection.list_by_menu_by_sort_asc(shop_menu_id)
        }
        item_ids = [i.shop_menu_section_id for i in items]
        if len(set(item_ids)) != len(item_ids) or set(item_ids) != set(by_id):
            raise PlatformConflictError(
                "Reorder must include every menu section exactly once",
                error_code="menu_sections_reorder_incomplete",
            )
        parent_of = {i.shop_menu_section_id: i.parent_id for i in items}
        if any(pid is not None and pid not in by_id for pid in parent_of.values()):
            raise PlatformNotFoundError(
                "Menu section not found", error_code="menu_section_not_found"
            )
        for start in item_ids:
            seen: set[str] = set()
            node: str | None = start
            while node is not None:
                if node in seen:
                    raise PlatformConflictError(
                        "Menu section tree contains a cycle", error_code="menu_section_cycle"
                    )
                seen.add(node)
                node = parent_of[node]
        groups: dict[str | None, list[str]] = {}
        for item in items:
            groups.setdefault(item.parent_id, []).append(item.shop_menu_section_id)
        now = utcnow()
        for parent_id, sibling_ids in groups.items():
            for sort, section_id in enumerate(sibling_ids):
                section = by_id[section_id]
                if section.parent_id != parent_id or section.sort != sort:
                    section.parent_id = parent_id
                    section.sort = sort
                    section.updated_at = now
                    _ = await section.save()

    # --- Позиции ---

    async def add_item(
        self,
        company_id: str,
        shop_id: str,
        shop_menu_id: str,
        payload: ShopMenuItemAddRequest,
    ) -> ShopMenuItemResponse:
        _ = await self._editable_menu(company_id, shop_id, shop_menu_id)
        section = await ShopMenuSection.get_by_id(payload.shop_menu_section_id)
        if section is None or section.shop_menu_id != shop_menu_id:
            raise PlatformNotFoundError(
                "Menu section not found", error_code="menu_section_not_found"
            )
        product = await self._shops.get_product(company_id, shop_id, payload.shop_product_id)
        if (
            await ShopMenuItem.find_by_menu_and_product(shop_menu_id, product.shop_product_id)
            is not None
        ):
            raise PlatformConflictError(
                "Product is already in the menu", error_code="menu_item_duplicate"
            )
        item = await ShopMenuItem.create(
            ShopMenuItem(
                shop_menu_item_id=new_id("shopmitem"),
                shop_menu_id=shop_menu_id,
                shop_menu_section_id=section.shop_menu_section_id,
                shop_product_id=product.shop_product_id,
                price_minor_override=payload.price_minor_override,
                is_available=payload.is_available,
                sort=await ShopMenuItem.next_sort_by_sort_desc(section.shop_menu_section_id),
            )
        )
        return _item_response(item, product.price_minor)

    async def update_item(
        self,
        company_id: str,
        shop_id: str,
        shop_menu_item_id: str,
        payload: ShopMenuItemUpdateRequest,
    ) -> ShopMenuItemResponse:
        item = await self._editable_item(company_id, shop_id, shop_menu_item_id)
        if "price_minor_override" in payload.model_fields_set:
            item.price_minor_override = payload.price_minor_override
        if payload.is_available is not None:
            item.is_available = payload.is_available
        _ = await item.save()
        return await self._item_response_with_price(company_id, shop_id, item)

    async def move_item(
        self,
        company_id: str,
        shop_id: str,
        shop_menu_item_id: str,
        shop_menu_section_id: str,
    ) -> ShopMenuItemResponse:
        """Перенос позиции в конец другого раздела того же меню."""
        item = await self._editable_item(company_id, shop_id, shop_menu_item_id)
        section = await ShopMenuSection.get_by_id(shop_menu_section_id)
        if section is None or section.shop_menu_id != item.shop_menu_id:
            raise PlatformNotFoundError(
                "Menu section not found", error_code="menu_section_not_found"
            )
        if item.shop_menu_section_id != shop_menu_section_id:
            item.sort = await ShopMenuItem.next_sort_by_sort_desc(shop_menu_section_id)
            item.shop_menu_section_id = shop_menu_section_id
            _ = await item.save()
        return await self._item_response_with_price(company_id, shop_id, item)

    async def remove_item(
        self, company_id: str, shop_id: str, shop_menu_item_id: str
    ) -> ShopMenuItem:
        """Удаляет позицию меню и возвращает её; блюдо каталога остаётся."""
        item = await self._editable_item(company_id, shop_id, shop_menu_item_id)
        _ = await item.delete()
        return item

    async def reorder_items(
        self,
        company_id: str,
        shop_id: str,
        shop_menu_section_id: str,
        shop_menu_item_ids: list[str],
    ) -> ShopMenuSection:
        """Перестановка позиций раздела: ids получают отсортированные sort-значения."""
        section = await self._editable_section(company_id, shop_id, shop_menu_section_id)
        by_id = {
            i.shop_menu_item_id: i
            for i in await ShopMenuItem.list_by_section_by_sort_asc(
                section.shop_menu_section_id
            )
        }
        if any(iid not in by_id for iid in shop_menu_item_ids):
            raise PlatformNotFoundError("Menu item not found", error_code="menu_item_not_found")
        ordered = [by_id[iid] for iid in shop_menu_item_ids]
        for item, sort in zip(ordered, sorted(i.sort for i in ordered), strict=True):
            if item.sort != sort:
                item.sort = sort
                _ = await item.save()
        return section

    # --- Каталог: проверка и похожие блюда ---

    async def verify_product(
        self, company_id: str, shop_id: str, shop_product_id: str
    ) -> ShopProduct:
        """Владелец подтвердил AI-поля блюда: пометка ``ai_unverified`` снимается."""
        product = await self._shops.get_product(company_id, shop_id, shop_product_id)
        if product.ai_unverified:
            product.ai_unverified = False
            product.updated_at = utcnow()
            _ = await product.save()
        return product

    async def list_similar_products(
        self, company_id: str, shop_id: str, shop_product_id: str
    ) -> list[tuple[ShopProduct, float]]:
        """Кандидаты на слияние: pg_trgm similarity названия выше порога, по убыванию score."""
        product = await self._shops.get_product(company_id, shop_id, shop_product_id)
        return await ShopProduct.find_similar_by_name_by_score_desc(
            shop_id,
            product.name,
            exclude_shop_product_id=product.shop_product_id,
            threshold=self._settings.similar_name_threshold,
        )

    async def merge_products(
        self,
        company_id: str,
        shop_id: str,
        shop_product_id: str,
        into_shop_product_id: str,
        fields: list[ShopProductMergeField],
    ) -> ShopProduct:
        """Слияние блюда в целевое: поля ``fields``, позиции меню и модификаторы
        переходят к целевому блюду, исходное удаляется.

        Позиция исходного блюда в меню, где целевое уже есть, удаляется:
        ``(shop_menu_id, shop_product_id)`` уникальна.
        """
        if shop_product_id == into_shop_product_id:
            raise PlatformConflictError(
                "Product cannot be merged into itself", error_code="product_merge_invalid"
            )
        source = await self._shops.get_product(company_id, shop_id, shop_product_id)
        target = await self._shops.get_product(company_id, shop_id, into_shop_product_id)
        now = utcnow()
        taken = set(fields)
        if "name" in taken:
            target.name = source.name
        if "description" in taken:
            target.description = source.description
        if "measure" in taken:
            target.measure = source.measure
        if "measure_unit" in taken:
            target.measure_unit = source.measure_unit
        if "ingredients" in taken:
            target.ingredients = list(source.ingredients)
        if "nutrition" in taken:
            target.nutrition = source.nutrition
        if "allergens" in taken:
            target.allergens = list(source.allergens)
        if "badges" in taken:
            target.badges = list(source.badges)
        if "price_minor" in taken:
            target.price_minor = source.price_minor
        if "photo_file_id" in taken:
            target.photo_file_id = source.photo_file_id
        if taken and source.ai_unverified:
            target.ai_unverified = True
        if target.similar_shop_product_id == source.shop_product_id:
            target.similar_shop_product_id = None
        target.updated_at = now
        _ = await target.save()
        for item in await ShopMenuItem.list_by_product(source.shop_product_id):
            if (
                await ShopMenuItem.find_by_menu_and_product(
                    item.shop_menu_id, target.shop_product_id
                )
                is not None
            ):
                _ = await item.delete()
                continue
            item.shop_product_id = target.shop_product_id
            _ = await item.save()
        for link in await ShopProductModifierGroup.list_by_product_by_sort_asc(
            source.shop_product_id
        ):
            if await ShopProductModifierGroup.get_link(target.shop_product_id, link.group_id) is None:
                _ = await ShopProductModifierGroup.create(
                    ShopProductModifierGroup(
                        product_id=target.shop_product_id,
                        group_id=link.group_id,
                        sort=link.sort,
                        min_selected=link.min_selected,
                        max_selected=link.max_selected,
                    )
                )
            _ = await link.delete()
        for marked in await ShopProduct.list_by_similar_unordered(source.shop_product_id):
            if marked.shop_product_id == target.shop_product_id:
                continue
            marked.similar_shop_product_id = target.shop_product_id
            marked.updated_at = now
            _ = await marked.save()
        _ = await source.delete()
        return target

    async def dismiss_similar(
        self, company_id: str, shop_id: str, shop_product_id: str
    ) -> ShopProduct:
        """Владелец решил, что блюда разные: пометка ``similar_shop_product_id`` снимается."""
        product = await self._shops.get_product(company_id, shop_id, shop_product_id)
        if product.similar_shop_product_id is None:
            raise PlatformConflictError(
                "Product has no similar mark", error_code="product_similar_missing"
            )
        product.similar_shop_product_id = None
        product.updated_at = utcnow()
        _ = await product.save()
        return product

    # --- Внутреннее ---

    async def _menu(self, company_id: str, shop_id: str, shop_menu_id: str) -> ShopMenu:
        _ = await self._shops.get_shop(company_id, shop_id)
        menu = await ShopMenu.get_by_id(shop_menu_id)
        if menu is None or menu.shop_id != shop_id:
            raise PlatformNotFoundError("Menu not found", error_code="menu_not_found")
        return menu

    async def _editable_menu(
        self, company_id: str, shop_id: str, shop_menu_id: str
    ) -> ShopMenu:
        menu = await self._menu(company_id, shop_id, shop_menu_id)
        _require_editable(menu)
        return menu

    async def _editable_section(
        self, company_id: str, shop_id: str, shop_menu_section_id: str
    ) -> ShopMenuSection:
        _ = await self._shops.get_shop(company_id, shop_id)
        section = await ShopMenuSection.get_by_id(shop_menu_section_id)
        menu = None if section is None else await ShopMenu.get_by_id(section.shop_menu_id)
        if section is None or menu is None or menu.shop_id != shop_id:
            raise PlatformNotFoundError(
                "Menu section not found", error_code="menu_section_not_found"
            )
        _require_editable(menu)
        return section

    async def _editable_item(
        self, company_id: str, shop_id: str, shop_menu_item_id: str
    ) -> ShopMenuItem:
        _ = await self._shops.get_shop(company_id, shop_id)
        item = await ShopMenuItem.get_by_id(shop_menu_item_id)
        menu = None if item is None else await ShopMenu.get_by_id(item.shop_menu_id)
        if item is None or menu is None or menu.shop_id != shop_id:
            raise PlatformNotFoundError("Menu item not found", error_code="menu_item_not_found")
        _require_editable(menu)
        return item

    async def _item_response_with_price(
        self, company_id: str, shop_id: str, item: ShopMenuItem
    ) -> ShopMenuItemResponse:
        product = await self._shops.get_product(company_id, shop_id, item.shop_product_id)
        return _item_response(item, product.price_minor)

    async def _menu_prices(self, menu: ShopMenu) -> dict[str, int]:
        items = await ShopMenuItem.list_by_menu_by_sort_asc(menu.shop_menu_id)
        products = await ShopProduct.get_many(list({i.shop_product_id for i in items}))
        return {pid: p.price_minor for pid, p in products.items()}

    async def _menu_response(
        self, menu: ShopMenu, prices: dict[str, int]
    ) -> ShopMenuResponse:
        """Меню с разделами и позициями; ``prices`` — цены каталога позиций меню."""
        items = await ShopMenuItem.list_by_menu_by_sort_asc(menu.shop_menu_id)
        return ShopMenuResponse(
            shop_menu_id=menu.shop_menu_id,
            shop_id=menu.shop_id,
            name=menu.name,
            status=menu.status,
            sort=menu.sort,
            sections=await ShopMenuSection.list_by_menu_by_sort_asc(menu.shop_menu_id),
            items=[_item_response(i, prices[i.shop_product_id]) for i in items],
        )
