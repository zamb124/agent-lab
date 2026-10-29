"""Контейнеры — тара как физическая локация запаса.

Бизнес-правила под тестом:

* контейнер — это ``usage=container`` локация: у неё адрес в
  дереве, свой остаток (quant'ы под ним), свой штрихкод;
* перемещение тары = переподвешивание поддерева: содержимое
  едет вместе с тарой, quant'ы не переписываются — меняется
  только parent_path топологии;
* скан-перемещение (``move_container``) умеет межскладское:
  обе стороны сериализуются своими полосами, warehouse_id
  quant'ов перебрасывается на склад приёмника;
* непустой контейнер «за границу запаса» (партнёр/списание)
  едет только через документ — иначе товар уйдёт мимо леджера;
* одноразовая тара после отгрузки партнёру выбывает из
  оборота (``is_active=false``) — не копим мусор в справочнике;
* вложение контейнера самого в себя/потомка — цикл, запрещён;
* в «вид» (зону-агрегат) тару ставить нельзя — view не полка;
* стратегия ``least_containers`` резервирует паллету целиком:
  строка ``kind=container``, постинг увозит всё содержимое.
"""

from decimal import Decimal

import pytest

from apps.stock.models.common import StockMoveSpec
from apps.stock.models.enums import (
    StockContainerKind,
    StockLayoutPreset,
    StockLocationUsage,
    StockMoveLineKind,
    StockOperationCode,
    StockPartnerRole,
    StockRemovalStrategy,
    StockTracking,
    ValuationMethod,
)
from apps.stock.models.location import StockLocation
from apps.stock.models.move import StockMove
from apps.stock.models.move_line import StockMoveLine
from apps.stock.models.quant import StockQuant
from apps.stock.services.company_init_service import virtual_location_id
from core.errors.boundary import PlatformConflictError

from .test_stock_domain import StockEnv, _make_env, _receipt


async def _env(stock_di, unique_id: str) -> StockEnv:
    return await _make_env(
        stock_di, f"co-{unique_id}", unique_id, ValuationMethod.FIFO
    )


async def _container_type(
    env: StockEnv, suffix: str, *, reusable: bool = True, **kwargs
):
    return await env.di.topology_service.create_container_type(
        company_id=env.company_id,
        warehouse_id=env.warehouse.warehouse_id,
        name=f"CT-{suffix}",
        kind=kwargs.get("kind", StockContainerKind.PALLET),
        allowed_parent_type_ids=kwargs.get("allowed_parent_type_ids", []),
        is_reusable=reusable,
    )


async def _container(
    env: StockEnv, type_id: str, parent_id: str, name: str
) -> StockLocation:
    return await env.di.topology_service.create_container(
        company_id=env.company_id,
        warehouse_id=env.warehouse.warehouse_id,
        parent_location_id=parent_id,
        container_type_id=type_id,
        name=name,
        barcode=None,
    )


async def _receipt_to(
    env: StockEnv, qty: Decimal, unit_price: Decimal | None, dest_id: str
) -> str:
    """Положить товар в контейнер: приход на запас + внутренний
    перенос в тару (приёмка напрямую в container перехватывается
    putaway-рефлексом — он выбирает ячейку, а не тару).

    Источник переноса читаем из фактического остатка: putaway
    приёмки волён выбрать любую ячейку склада, а контейнеры —
    тоже легальные кандидаты. Если рефлекс положил товар сразу
    в тару, перенос не нужен.
    """
    _ = await _receipt(env, qty, unit_price)
    quants = await StockQuant.list_unordered_for_locations(
        env.company_id,
        await StockLocation.list_subtree_ids_by_parent_path_asc(
            env.company_id, env.warehouse.view_location_id
        ),
    )
    loaded = [
        quant
        for quant in quants
        if quant.product_id == env.product.product_id
        and quant.quantity > Decimal("0")
    ]
    if all(quant.location_id == dest_id for quant in loaded):
        return ""
    src_id = loaded[0].location_id if loaded else env.warehouse.stock_location_id
    internal = env.op_types[StockOperationCode.INTERNAL]
    transfer = await env.di.move_engine.create_transfer(
        company_id=env.company_id,
        warehouse_id=env.warehouse.warehouse_id,
        operation_type_id=internal.operation_type_id,
        partner_entity_id=None,
        owner_entity_id=None,
        scheduled_at=None,
        origin_document_type=None,
        origin_document_id=None,
        barcode=None,
        moves=[
            StockMoveSpec(
                product_id=env.product.product_id,
                product_qty=qty,
                uom_id=env.uom_id,
                location_id=src_id,
                location_dest_id=dest_id,
            )
        ],
    )
    for step in ("confirm", "assign", "validate"):
        _ = await getattr(env.di.move_engine, f"{step}_transfer")(
            company_id=env.company_id,
            transfer_id=transfer.transfer_id,
        )
    return transfer.transfer_id


class TestContainerMove:
    async def test_move_keeps_contents_quant_untouched(
        self, stock_di, unique_id: str
    ) -> None:
        """Паллета с товаром переезжает в другую ячейку:
        quant остаётся на контейнере (его локация — тара),
        меняется только parent контейнера в дереве."""
        env = await _env(stock_di, unique_id)
        ctype = await _container_type(env, unique_id)
        pallet = await _container(
            env, ctype.container_type_id, env.warehouse.stock_location_id,
            f"PLT-{unique_id}",
        )
        bin_b = await env.di.topology_service.create_location(
            company_id=env.company_id,
            warehouse_id=env.warehouse.warehouse_id,
            parent_id=env.warehouse.view_location_id,
            name=f"BIN-C-{unique_id}",
            usage=StockLocationUsage.BIN,
            barcode=None,
        )
        _ = await _receipt_to(
            env, Decimal("5"), Decimal("4"), pallet.location_id
        )
        _ = await env.di.topology_service.move_container(
            company_id=env.company_id,
            container_id=pallet.location_id,
            dest_location_id=bin_b.location_id,
            user_id="test_user",
        )
        fresh = await StockLocation.by_id(
            env.company_id, pallet.location_id
        )
        assert fresh.parent_id == bin_b.location_id
        quant = await StockQuant.by_key(
            company_id=env.company_id,
            product_id=env.product.product_id,
            location_id=pallet.location_id,
            lot_id=None,
            owner_entity_id=None,
        )
        assert quant.quantity == Decimal("5")

    async def test_cross_warehouse_move_rebinds_quant_warehouse(
        self, stock_di, unique_id: str
    ) -> None:
        """Паллета едет на другой склад: команда сериализована
        двумя полосами, quant'ы переписываются на склад приёмника."""
        env = await _env(stock_di, unique_id)
        ctype = await _container_type(env, unique_id)
        pallet = await _container(
            env, ctype.container_type_id, env.warehouse.stock_location_id,
            f"PLT2-{unique_id}",
        )
        _ = await _receipt_to(
            env, Decimal("3"), Decimal("4"), pallet.location_id
        )
        other = await env.di.warehouse_service.create_warehouse(
            company_id=env.company_id,
            code=f"WX{unique_id[:8]}",
            name="Other",
            owner_user_id="test_user",
            layout_preset=StockLayoutPreset.SIMPLE,
            removal_strategy=StockRemovalStrategy.FIFO,
        )
        _ = await env.di.topology_service.move_container(
            company_id=env.company_id,
            container_id=pallet.location_id,
            dest_location_id=other.stock_location_id,
            user_id="test_user",
        )
        fresh = await StockLocation.by_id(
            env.company_id, pallet.location_id
        )
        assert fresh.warehouse_id == other.warehouse_id
        quant = await StockQuant.by_key(
            company_id=env.company_id,
            product_id=env.product.product_id,
            location_id=pallet.location_id,
            lot_id=None,
            owner_entity_id=None,
        )
        assert quant.warehouse_id == other.warehouse_id

    async def test_move_into_view_denied(
        self, stock_di, unique_id: str
    ) -> None:
        """View — зона-агрегат, не полка: контейнер туда не ставится."""
        env = await _env(stock_di, unique_id)
        ctype = await _container_type(env, unique_id)
        pallet = await _container(
            env, ctype.container_type_id, env.warehouse.stock_location_id,
            f"PLT3-{unique_id}",
        )
        with pytest.raises(PlatformConflictError) as exc:
            _ = await env.di.topology_service.move_container(
                company_id=env.company_id,
                container_id=pallet.location_id,
                dest_location_id=env.warehouse.view_location_id,
                user_id="test_user",
            )
        assert exc.value.error_code == "container_destination_invalid"

    async def test_nonempty_container_to_partner_denied(
        self, stock_di, unique_id: str
    ) -> None:
        """Полную паллету «на улицу» без документа нельзя —
        товар уехал бы мимо леджера оценки."""
        env = await _env(stock_di, unique_id)
        ctype = await _container_type(env, unique_id)
        pallet = await _container(
            env, ctype.container_type_id, env.warehouse.stock_location_id,
            f"PLT4-{unique_id}",
        )
        _ = await _receipt_to(
            env, Decimal("2"), Decimal("4"), pallet.location_id
        )
        customer = virtual_location_id(
            env.company_id, StockLocationUsage.PARTNER, StockPartnerRole.CUSTOMER
        )
        with pytest.raises(PlatformConflictError) as exc:
            _ = await env.di.topology_service.move_container(
                company_id=env.company_id,
                container_id=pallet.location_id,
                dest_location_id=customer,
                user_id="test_user",
            )
        assert exc.value.error_code == "container_not_empty"


class TestDisposableContainer:
    async def test_empty_disposable_archived_after_partner_move(
        self, stock_di, unique_id: str
    ) -> None:
        """Пустой мешок уехал клиенту и выбыл из оборота —
        многоразовая паллета в той же поездке остаётся активной."""
        env = await _env(stock_di, unique_id)
        bag_type = await _container_type(
            env, f"bag-{unique_id}", reusable=False,
            kind=StockContainerKind.BAG,
        )
        pallet_type = await _container_type(env, f"plt-{unique_id}")
        bag = await _container(
            env, bag_type.container_type_id,
            env.warehouse.stock_location_id, f"BAG-{unique_id}",
        )
        pallet = await _container(
            env, pallet_type.container_type_id,
            env.warehouse.stock_location_id, f"PLT5-{unique_id}",
        )
        customer = virtual_location_id(
            env.company_id, StockLocationUsage.PARTNER, StockPartnerRole.CUSTOMER
        )
        _ = await env.di.topology_service.move_container(
            company_id=env.company_id,
            container_id=bag.location_id,
            dest_location_id=customer,
            user_id="test_user",
        )
        _ = await env.di.topology_service.move_container(
            company_id=env.company_id,
            container_id=pallet.location_id,
            dest_location_id=customer,
            user_id="test_user",
        )
        bag = await StockLocation.by_id(env.company_id, bag.location_id)
        pallet = await StockLocation.by_id(env.company_id, pallet.location_id)
        assert bag.is_active is False
        assert pallet.is_active is True


class TestNestedContainers:
    async def test_pallet_move_carries_box_and_quant(
        self, stock_di, unique_id: str
    ) -> None:
        """Короб на паллете: переезд паллеты уносит короб —
        поддерево переподвешивается целиком, остаток короба
        продолжает жить на коробе."""
        env = await _env(stock_di, unique_id)
        pallet_type = await _container_type(env, f"pt-{unique_id}")
        box_type = await _container_type(
            env, f"bx-{unique_id}", kind=StockContainerKind.BOX
        )
        pallet = await _container(
            env, pallet_type.container_type_id,
            env.warehouse.stock_location_id, f"PLT6-{unique_id}",
        )
        box = await _container(
            env, box_type.container_type_id, pallet.location_id,
            f"BOX-{unique_id}",
        )
        _ = await _receipt_to(
            env, Decimal("2"), Decimal("4"), box.location_id
        )
        bin_b = await env.di.topology_service.create_location(
            company_id=env.company_id,
            warehouse_id=env.warehouse.warehouse_id,
            parent_id=env.warehouse.view_location_id,
            name=f"BIN-D-{unique_id}",
            usage=StockLocationUsage.BIN,
            barcode=None,
        )
        _ = await env.di.topology_service.move_container(
            company_id=env.company_id,
            container_id=pallet.location_id,
            dest_location_id=bin_b.location_id,
            user_id="test_user",
        )
        box = await StockLocation.by_id(env.company_id, box.location_id)
        pallet = await StockLocation.by_id(
            env.company_id, pallet.location_id
        )
        assert box.parent_id == pallet.location_id
        assert pallet.parent_id == bin_b.location_id
        quant = await StockQuant.by_key(
            company_id=env.company_id,
            product_id=env.product.product_id,
            location_id=box.location_id,
            lot_id=None,
            owner_entity_id=None,
        )
        assert quant.quantity == Decimal("2")


class TestLeastContainers:
    async def test_whole_container_reserved_and_posted(
        self, stock_di, unique_id: str
    ) -> None:
        """Стратегия «минимум тары»: заказ ложится на паллету
        целиком — строка kind=container, проводка увозит всё
        содержимое к партнёру."""
        env = await _env(stock_di, unique_id)
        env.product = await env.di.catalog_service.create_product(
            company_id=env.company_id,
            name=f"LC {unique_id}",
            sku=f"LC-{unique_id}",
            uom_id=env.uom_id,
            valuation_method=ValuationMethod.FIFO,
            standard_price=Decimal("0"),
            tracking=StockTracking.NONE,
            is_storable=True,
            category="general",
            barcode=None,
            removal_strategy=StockRemovalStrategy.LEAST_CONTAINERS,
        )
        ctype = await _container_type(env, f"lc-{unique_id}")
        pallet = await _container(
            env, ctype.container_type_id,
            env.warehouse.stock_location_id, f"PLT7-{unique_id}",
        )
        _ = await _receipt_to(
            env, Decimal("4"), Decimal("4"), pallet.location_id
        )
        op = env.op_types[StockOperationCode.OUTGOING]
        transfer = await env.di.move_engine.create_transfer(
            company_id=env.company_id,
            warehouse_id=env.warehouse.warehouse_id,
            operation_type_id=op.operation_type_id,
            partner_entity_id=None,
            owner_entity_id=None,
            scheduled_at=None,
            origin_document_type=None,
            origin_document_id=None,
            barcode=None,
            moves=[
                StockMoveSpec(
                    product_id=env.product.product_id,
                    product_qty=Decimal("4"),
                    uom_id=env.uom_id,
                )
            ],
        )
        for step in ("confirm", "assign"):
            _ = await getattr(env.di.move_engine, f"{step}_transfer")(
                company_id=env.company_id,
                transfer_id=transfer.transfer_id,
            )
        moves = await StockMove.list_for_transfer_by_created_at_asc(
            env.company_id, transfer.transfer_id
        )
        lines = await StockMoveLine.list_for_move_by_created_at_asc(
            env.company_id, moves[0].move_id
        )
        container_lines = [
            ln for ln in lines if ln.kind == StockMoveLineKind.CONTAINER
        ]
        assert len(container_lines) == 1
        assert container_lines[0].container_id == pallet.location_id
        _ = await env.di.move_engine.validate_transfer(
            company_id=env.company_id, transfer_id=transfer.transfer_id
        )
        quant = await StockQuant.by_key(
            company_id=env.company_id,
            product_id=env.product.product_id,
            location_id=pallet.location_id,
            lot_id=None,
            owner_entity_id=None,
        )
        # Всё содержимое уехало к клиенту вместе с тарой.
        assert quant is None or quant.quantity == Decimal("0")


class TestContainerIdempotency:
    async def test_move_container_replay_same_result(
        self, stock_di, unique_id: str
    ) -> None:
        """Повтор той же команды по ключу — тот же результат,
        дерево не переподвешивается дважды."""
        env = await _env(stock_di, unique_id)
        ctype = await _container_type(env, f"ik-{unique_id}")
        pallet = await _container(
            env, ctype.container_type_id,
            env.warehouse.stock_location_id, f"PLT8-{unique_id}",
        )
        bin_b = await env.di.topology_service.create_location(
            company_id=env.company_id,
            warehouse_id=env.warehouse.warehouse_id,
            parent_id=env.warehouse.view_location_id,
            name=f"BIN-E-{unique_id}",
            usage=StockLocationUsage.BIN,
            barcode=None,
        )
        first = await env.di.topology_service.move_container(
            company_id=env.company_id,
            container_id=pallet.location_id,
            dest_location_id=bin_b.location_id,
            user_id="test_user",
            idempotency_key=f"mv-{unique_id}",
        )
        second = await env.di.topology_service.move_container(
            company_id=env.company_id,
            container_id=pallet.location_id,
            dest_location_id=bin_b.location_id,
            user_id="test_user",
            idempotency_key=f"mv-{unique_id}",
        )
        assert second.parent_id == first.parent_id == bin_b.location_id
