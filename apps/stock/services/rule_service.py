"""Правила склада: размещение, пополнение min/max, маршруты.

Агрегат «как склад решает сам»: ``stock_putaway_rules» — куда нести
приход, ``stock_reorder_rules`` — когда доказать полку,
``stock_routes`` — по какой цепочке плеч пойдёт товар. Это
конфигурация поведения: записи не двигают запас, их читают рефлексы
(``PlacementService.suggest``, тик ``stock_reorder``) и движок
цепочек при создании накладной.
"""

from __future__ import annotations

from decimal import Decimal

from apps.stock.models import (
    STOCK_QUANT_USAGES,
    StockLocation,
    StockLocationUsage,
    StockOperationType,
    StockProduct,
    StockPutawayRule,
    StockReorderRule,
    StockRoute,
    StockRouteStepSpec,
    StockWarehouse,
)
from core.errors.boundary import PlatformConflictError, PlatformNotFoundError


def _not_found(message: str, error_code: str) -> PlatformNotFoundError:
    return PlatformNotFoundError(message, error_code=error_code)


def _conflict(message: str, error_code: str) -> PlatformConflictError:
    return PlatformConflictError(message, error_code=error_code)


class RuleService:
    """CRUD правил поведения склада: putaway, reorder, маршруты."""

    # --- Правила пополнения (min/max) ---

    async def list_reorder_rules(
        self,
        *,
        company_id: str,
        warehouse_id: str | None,
    ) -> list[StockReorderRule]:
        """Каталог min/max-правил — «полка не должна пустеть»."""
        return await StockReorderRule.list_by_rule_id(
            company_id, warehouse_id=warehouse_id
        )

    async def create_reorder_rule(
        self,
        *,
        company_id: str,
        warehouse_id: str,
        product_id: str,
        location_id: str,
        min_qty: Decimal,
        max_qty: Decimal,
        operation_type_id: str,
        route_id: str | None = None,
    ) -> StockReorderRule:
        """Завести правило «держи на полке от min до max».

        Проверки: локация принадлежит складу и хранит товар (не вид/
        партнёр), тип операции — этого склада, min ≤ max. Дальше тик
        ``stock_reorder`` сам следит за остатком и создаёт черновики
        пополнения.
        """
        if min_qty > max_qty:
            raise _conflict(
                "Reorder min_qty must be <= max_qty",
                "reorder_rule_invalid_range",
            )
        location = await StockLocation.by_id(company_id, location_id)
        if (
            location is None
            or location.warehouse_id != warehouse_id
            or location.usage not in STOCK_QUANT_USAGES | {StockLocationUsage.VIEW}
        ):
            raise _not_found(
                "Reorder location not found in warehouse",
                "location_not_found",
            )
        ot = await StockOperationType.by_id(company_id, operation_type_id)
        if ot is None or ot.warehouse_id != warehouse_id:
            raise _not_found(
                "Operation type not found", "operation_type_not_found"
            )
        product = await StockProduct.by_id(company_id, product_id)
        if product is None:
            raise _not_found(
                "Product not found", "product_not_found"
            )
        if route_id is not None:
            route = await StockRoute.by_id(company_id, route_id)
            if route is None or route.warehouse_id != warehouse_id:
                raise _not_found(
                    "Route not found", "route_not_found"
                )
        return await StockReorderRule.create(
            company_id=company_id,
            warehouse_id=warehouse_id,
            product_id=product_id,
            location_id=location_id,
            min_qty=min_qty,
            max_qty=max_qty,
            operation_type_id=operation_type_id,
            route_id=route_id,
        )

    async def set_reorder_rule_active(
        self, *, company_id: str, rule_id: str, is_active: bool
    ) -> StockReorderRule:
        """Пауза/возобновление правила — «пока не пополняем эту полку»."""
        rule = await StockReorderRule.by_id(company_id, rule_id)
        if rule is None:
            raise _not_found(
                "Reorder rule not found", "reorder_rule_not_found"
            )
        await StockReorderRule.update_is_active_and_updated_at(company_id, rule_id, is_active)
        rule.is_active = is_active
        return rule

    # --- Правила размещения ---

    async def list_putaway_rules(
        self, *, company_id: str, warehouse_id: str
    ) -> list[StockPutawayRule]:
        """Все правила размещения склада, по sequence."""
        warehouse = await StockWarehouse.by_id(company_id, warehouse_id)
        if warehouse is None:
            raise _not_found("Warehouse not found", "warehouse_not_found")
        return await StockPutawayRule.list_by_sequence_and_rule_id_for_warehouse(
            company_id, warehouse_id
        )

    async def _check_putaway_location(
        self,
        company_id: str,
        warehouse_id: str,
        location_id: str,
        *,
        is_destination: bool,
    ) -> None:
        location = await StockLocation.by_id(company_id, location_id)
        if location is None:
            raise _not_found(
                "Location not found in warehouse",
                "location_not_found",
            )
        if is_destination and location.usage in {
            StockLocationUsage.PARTNER,
            StockLocationUsage.ADJUSTMENT,
        }:
            raise _conflict(
                "Putaway destination must be a storage location",
                "putaway_rule_bad_location",
            )
        if location.warehouse_id != warehouse_id:
            raise _not_found(
                "Location not found in warehouse",
                "location_not_found",
            )

    async def create_putaway_rule(
        self,
        *,
        company_id: str,
        warehouse_id: str,
        location_in_id: str,
        location_out_id: str,
        product_id: str | None = None,
        category: str | None = None,
        owner_entity_id: str | None = None,
        sequence: int = 0,
    ) -> StockPutawayRule:
        """Завести правило «этот товар — в ту зону».

        ``location_in`` — зона приёмки (правило срабатывает, когда приёмник
        строки лежит внутри неё), ``location_out`` — целевая зона хранения.
        Фильтры product/category/owner сужают правило; чем конкретнее
        правило — тем раньше оно предлагается кладовщику.
        """
        warehouse = await StockWarehouse.by_id(company_id, warehouse_id)
        if warehouse is None:
            raise _not_found("Warehouse not found", "warehouse_not_found")
        await self._check_putaway_location(
            company_id, warehouse_id, location_in_id, is_destination=False
        )
        await self._check_putaway_location(
            company_id, warehouse_id, location_out_id, is_destination=True
        )
        if product_id is not None:
            product = await StockProduct.by_id(company_id, product_id)
            if product is None:
                raise _not_found(
                    "Product not found", "product_not_found"
                )
        return await StockPutawayRule.create(
            company_id=company_id,
            warehouse_id=warehouse_id,
            location_in_id=location_in_id,
            location_out_id=location_out_id,
            product_id=product_id,
            category=category,
            owner_entity_id=owner_entity_id,
            sequence=sequence,
        )

    async def update_putaway_rule(
        self,
        *,
        company_id: str,
        rule_id: str,
        location_in_id: str | None = None,
        location_out_id: str | None = None,
        product_id: str | None = None,
        category: str | None = None,
        owner_entity_id: str | None = None,
        sequence: int | None = None,
    ) -> StockPutawayRule:
        """Правка правила: те же проверки принадлежности, что при создании."""
        rule = await StockPutawayRule.by_id(company_id, rule_id)
        if rule is None:
            raise _not_found(
                "Putaway rule not found", "putaway_rule_not_found"
            )
        if location_in_id is not None:
            await self._check_putaway_location(
                company_id,
                rule.warehouse_id,
                location_in_id,
                is_destination=False,
            )
        if location_out_id is not None:
            await self._check_putaway_location(
                company_id,
                rule.warehouse_id,
                location_out_id,
                is_destination=True,
            )
        if product_id is not None:
            product = await StockProduct.by_id(company_id, product_id)
            if product is None:
                raise _not_found(
                    "Product not found", "product_not_found"
                )
        fresh = await StockPutawayRule.update_locations_filters_and_sequence(
            company_id,
            rule_id,
            location_in_id=location_in_id,
            location_out_id=location_out_id,
            product_id=product_id,
            category=category,
            owner_entity_id=owner_entity_id,
            sequence=sequence,
        )
        assert fresh is not None
        return fresh

    async def set_putaway_rule_active(
        self, *, company_id: str, rule_id: str, is_active: bool
    ) -> StockPutawayRule:
        """Пауза/возобновление правила размещения."""
        rule = await StockPutawayRule.by_id(company_id, rule_id)
        if rule is None:
            raise _not_found(
                "Putaway rule not found", "putaway_rule_not_found"
            )
        await StockPutawayRule.update_is_active(company_id, rule_id, is_active)
        rule.is_active = is_active
        return rule

    async def delete_putaway_rule(
        self, *, company_id: str, rule_id: str
    ) -> StockPutawayRule:
        """Удаление правила — справочник, без бухгалтерских последствий."""
        rule = await StockPutawayRule.by_id(company_id, rule_id)
        if rule is None:
            raise _not_found(
                "Putaway rule not found", "putaway_rule_not_found"
            )
        await StockPutawayRule.delete_rule(company_id, rule_id)
        return rule

    # --- Маршруты ---

    async def list_routes(
        self,
        *,
        company_id: str,
        warehouse_id: str | None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[StockRoute]:
        """Каталог маршрутов компании, опционально — по складу."""
        items = await StockRoute.list_active_by_name(
            company_id, warehouse_id=warehouse_id, limit=limit + offset
        )
        return items[offset:]

    async def get_route(
        self, *, company_id: str, route_id: str
    ) -> StockRoute:
        """Маршрут с плечами — «как пойдёт товар по этой цепочке»."""
        route = await StockRoute.by_id(company_id, route_id)
        if route is None:
            raise _not_found(
                "Route not found", "route_not_found"
            )
        return route

    async def create_route(
        self,
        *,
        company_id: str,
        warehouse_id: str | None,
        name: str,
        code: str,
        steps: list[StockRouteStepSpec],
    ) -> StockRoute:
        """Завести маршрут с плечами одним вызовом.

        Валидация: каждый шаг ссылается на существующий тип операции;
        для локального маршрута (``warehouse_id`` задан) все типы
        операций должны принадлежать этому складу — иначе цепочка
        «разъедется» между складами без транзитной локации.
        Межскладской маршрут объявляется с ``warehouse_id=None`` и
        прошивает склады через transit-локации шагов.
        """
        seen_sequences: set[int] = set()
        for spec in steps:
            if spec.sequence in seen_sequences:
                raise _conflict(
                    "Duplicate route step sequence",
                    "route_step_sequence_duplicate",
                )
            seen_sequences.add(spec.sequence)
            ot = await StockOperationType.by_id(
                company_id, spec.operation_type_id
            )
            if ot is None:
                raise _not_found(
                    "Operation type not found",
                    "operation_type_not_found",
                )
            if warehouse_id is not None and ot.warehouse_id != warehouse_id:
                raise _conflict(
                    "Route step operation type belongs to another warehouse",
                    "route_step_warehouse_mismatch",
                )
        return await StockRoute.create(
            company_id=company_id,
            warehouse_id=warehouse_id,
            name=name,
            code=code,
            steps=steps,
        )
