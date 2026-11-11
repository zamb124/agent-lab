"""Адверсариальные и «невозможные» сценарии склада.

Система считает деньги — поэтому тестируем не только штатные отказы,
но и защитные гарды против рассинхрона состояния:

* повреждённый инвариант «quant.reserved = сумма открытых строк»
  (строка ссылается на удалённый остаток, резерв меньше строки);
* строка ``kind=container`` без контейнера / контейнер чужого склада
  в полосе другого склада;
* смешанное содержимое тары при вывозе «за границу запаса»;
* цикл в дереве локаций и вложение ячейки в тару;
* «битые» конфигурации: тип операции без локаций, удалённые
  справочники под живым документом, режимы putaway без flow,
  ЕИ с нулевым фактором, пустой штрихкод;
* политика ``backorder=never`` и жизненный цикл довоза бэкордера.
"""

from __future__ import annotations

import uuid
from decimal import Decimal

import pytest

from apps.stock.models.common import STOCK_DB, StockMoveSpec, new_id
from apps.stock.models.decision import StockDecision
from apps.stock.models.enums import (
    BackorderPolicy,
    ReflexMode,
    ReservationPolicy,
    StockBarcodeEntityType,
    StockContainerKind,
    StockDecisionStatus,
    StockLayoutPreset,
    StockLocationUsage,
    StockMoveLineKind,
    StockOperationCode,
    StockRemovalStrategy,
    StockTracking,
    StockTransferState,
    ValuationMethod,
)
from apps.stock.models.location import StockLocation
from apps.stock.models.move import StockMove
from apps.stock.models.move_line import StockMoveLine
from apps.stock.models.operation_type import StockOperationType
from apps.stock.models.putaway_rule import StockPutawayRule
from apps.stock.models.quant import StockQuant
from apps.stock.models.resource_type import StockResourceType
from apps.stock.models.warehouse import StockWarehouse
from apps.stock.services.task_service import line_fits_resource
from core.catalog.models import CatalogUom
from core.errors.boundary import (
    PlatformConflictError,
    PlatformNotFoundError,
)
from core.utils.time import utcnow

from .test_stock_domain import StockEnv, _make_env, _receipt, _stock_quant


async def _env(stock_di, unique_id: str) -> StockEnv:
    return await _make_env(
        stock_di,
        company_id=f"co-{unique_id}",
        unique=unique_id,
        valuation=ValuationMethod.FIFO,
    )


async def _bin(env: StockEnv, suffix: str) -> StockLocation:
    return await env.di.topology_service.create_location(
        company_id=env.company_id,
        warehouse_id=env.warehouse.warehouse_id,
        parent_id=env.warehouse.view_location_id,
        name=f"BIN-{suffix}",
        usage=StockLocationUsage.BIN,
        barcode=None,
    )


async def _pallet(
    env: StockEnv,
    suffix: str,
    parent_id: str | None = None,
    warehouse_id: str | None = None,
) -> StockLocation:
    wh_id = warehouse_id or env.warehouse.warehouse_id
    ctype = await env.di.topology_service.create_container_type(
        company_id=env.company_id,
        warehouse_id=wh_id,
        name=f"CT-{suffix}",
        kind=StockContainerKind.PALLET,
        allowed_parent_type_ids=[],
        is_reusable=True,
    )
    return await env.di.topology_service.create_container(
        company_id=env.company_id,
        warehouse_id=wh_id,
        parent_location_id=parent_id or env.warehouse.stock_location_id,
        container_type_id=ctype.container_type_id,
        name=f"PLT-{suffix}",
        barcode=None,
    )


async def _receipt_to_location(env: StockEnv, dest_id: str, qty: Decimal) -> None:
    """Положить товар в конкретную локацию/тару: приход на склад +
    внутренний перенос из фактического места прихода (putaway-рефлекс
    волён выбрать любую ячейку — источник читаем из остатка)."""
    _ = await _receipt(env, qty, Decimal("4"))
    quants = await StockQuant.list_unordered_for_locations(
        env.company_id,
        await StockLocation.list_subtree_ids_by_parent_path_asc(env.company_id, env.warehouse.view_location_id),
    )
    loaded = [
        q for q in quants if q.product_id == env.product.product_id and q.quantity > Decimal("0")
    ]
    if all(q.location_id == dest_id for q in loaded):
        return
    src_id = loaded[0].location_id if loaded else env.warehouse.stock_location_id
    internal = env.op_types[StockOperationCode.INTERNAL]
    move_in = await env.di.move_engine.create_transfer(
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
            transfer_id=move_in.transfer_id,
        )


async def _assigned_outgoing(env: StockEnv, qty: Decimal) -> tuple[str, str]:
    """Доставка в состоянии assigned: (transfer_id, move_id)."""
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
                product_qty=qty,
                uom_id=env.uom_id,
            )
        ],
    )
    for step in ("confirm", "assign"):
        _ = await getattr(env.di.move_engine, f"{step}_transfer")(
            company_id=env.company_id,
            transfer_id=transfer.transfer_id,
        )
    moves = await StockMove.list_for_transfer_by_created_at_asc(env.company_id, transfer.transfer_id)
    assert len(moves) == 1
    return transfer.transfer_id, moves[0].move_id


class TestCorruptedReservation:
    """Гарды против рассинхрона «строки резерва ↔ quant.reserved»."""

    async def test_release_with_deleted_quant(self, stock_di, unique_id: str) -> None:
        """Резервная строка есть, а остаток удалён (краш/ручная правка
        БД) → release падает ``reservation_state_invalid``, а не
        молча «отпускает» несуществующее."""
        env = await _env(stock_di, unique_id)
        _ = await _receipt(env, Decimal("5"), Decimal("4"))
        _, move_id = await _assigned_outgoing(env, Decimal("3"))
        quant = await _stock_quant(env)
        assert quant is not None and quant.reserved_quantity == Decimal("3")

        _ = await StockQuant.objects.filter(
            company_id=env.company_id, quant_id=quant.quant_id
        ).delete()
        with pytest.raises(PlatformConflictError) as exc:
            await env.di.move_engine.unreserve_move(
                company_id=env.company_id,
                move_id=move_id,
            )
        assert exc.value.error_code == "reservation_state_invalid"

    async def test_release_with_shrunk_reservation(self, stock_di, unique_id: str) -> None:
        """quant.reserved < сумма строк → release падает
        ``reservation_underflow``: списывать резерв ниже нуля нельзя,
        иначе «доступное» раздуется мимо полки."""
        env = await _env(stock_di, unique_id)
        _ = await _receipt(env, Decimal("5"), Decimal("4"))
        _, move_id = await _assigned_outgoing(env, Decimal("4"))
        quant = await _stock_quant(env)
        assert quant is not None

        quant.reserved_quantity = Decimal("1")  # < 4 по строке
        _ = await quant.save()
        with pytest.raises(PlatformConflictError) as exc:
            await env.di.move_engine.unreserve_move(
                company_id=env.company_id,
                move_id=move_id,
            )
        assert exc.value.error_code == "reservation_underflow"


class TestContainerGuards:
    """Тара: циклы, вложения, чужие склады, смешанное содержимое."""

    async def test_move_container_into_own_child_cycle(self, stock_di, unique_id: str) -> None:
        """Паллета в свой же короб — цикл дерева, запрещён."""
        env = await _env(stock_di, unique_id)
        pallet = await _pallet(env, unique_id)
        box_type = await env.di.topology_service.create_container_type(
            company_id=env.company_id,
            warehouse_id=env.warehouse.warehouse_id,
            name=f"BX-{unique_id}",
            kind=StockContainerKind.BOX,
            allowed_parent_type_ids=[],
            is_reusable=True,
        )
        box = await env.di.topology_service.create_container(
            company_id=env.company_id,
            warehouse_id=env.warehouse.warehouse_id,
            parent_location_id=pallet.location_id,
            container_type_id=box_type.container_type_id,
            name=f"BOX-{unique_id}",
            barcode=None,
        )
        with pytest.raises(PlatformConflictError) as exc:
            _ = await env.di.topology_service.move_container(
                company_id=env.company_id,
                container_id=pallet.location_id,
                dest_location_id=box.location_id,
                user_id="op",
            )
        assert exc.value.error_code == "container_cycle"

    async def test_move_bin_as_container_rejected(self, stock_di, unique_id: str) -> None:
        """Ячейка — не тара: move_container на BIN → container_not_container."""
        env = await _env(stock_di, unique_id)
        bin_a = await _bin(env, f"A{unique_id}")
        bin_b = await _bin(env, f"B{unique_id}")
        with pytest.raises(PlatformConflictError) as exc:
            _ = await env.di.topology_service.move_container(
                company_id=env.company_id,
                container_id=bin_a.location_id,
                dest_location_id=bin_b.location_id,
                user_id="op",
            )
        assert exc.value.error_code == "container_not_container"

    async def test_bin_inside_container_nesting_invalid(self, stock_di, unique_id: str) -> None:
        """rebind поддерева: внутрь тары кладут только тару —
        «ячейка в коробе» невозможна физически."""
        env = await _env(stock_di, unique_id)
        pallet = await _pallet(env, unique_id)
        bin_a = await _bin(env, f"C{unique_id}")
        with pytest.raises(PlatformConflictError) as exc:
            _ = await StockLocation.rebind_subtree(
                company_id=env.company_id,
                root=bin_a,
                new_parent=pallet,
                new_warehouse_id=env.warehouse.warehouse_id,
            )
        assert exc.value.error_code == "container_nesting_invalid"
        # Дерево не пострадало.
        fresh = await StockLocation.by_id(env.company_id, bin_a.location_id)
        assert fresh is not None
        assert fresh.parent_id == env.warehouse.view_location_id

    async def test_container_line_foreign_warehouse(self, stock_di, unique_id: str) -> None:
        """Строка-контейнер в полосе склада А со ссылкой на тару
        склада B → container_warehouse_mismatch: постинг не трогает
        чужие остатки без чужой полосы."""
        env = await _env(stock_di, unique_id)
        other = await env.di.warehouse_service.create_warehouse(
            company_id=env.company_id,
            code=f"W2{unique_id[:8]}",
            name="Second",
            owner_user_id="u",
            layout_preset=StockLayoutPreset.SIMPLE,
            removal_strategy=StockRemovalStrategy.FIFO,
        )
        pallet_b = await _pallet(
            env,
            f"F{unique_id}",
            parent_id=other.stock_location_id,
            warehouse_id=other.warehouse_id,
        )
        dest = await _bin(env, f"D{unique_id}")
        _, move_id = await _assigned_outgoing(env, Decimal("1"))

        with pytest.raises(PlatformConflictError) as exc:
            _ = await StockMove.post_lines_in_lane(
                company_id=env.company_id,
                move_id=move_id,
                warehouse_id=env.warehouse.warehouse_id,
                drafts=[],
                container_move=(pallet_b.location_id, dest.location_id),
                owner_entity_id=None,
                operation_code=StockOperationCode.INTERNAL.value,
                idempotency_key=f"t-{uuid.uuid7().hex}",
                actor_user_id="op",
                command_type="stock/scan/commit_requested",
            )
        assert exc.value.error_code == "container_warehouse_mismatch"

    async def test_container_line_without_container(self, stock_di, unique_id: str) -> None:
        """Строка kind=container без container_id (битая вставка) —
        проводка падает ``container_missing``, а не NPE."""
        env = await _env(stock_di, unique_id)
        _ = await _receipt(env, Decimal("5"), Decimal("4"))
        transfer_id, move_id = await _assigned_outgoing(env, Decimal("1"))
        bin_a = await _bin(env, f"E{unique_id}")
        _ = await StockMoveLine.objects.create(
            instance=StockMoveLine(
                move_line_id=new_id("mli"),
                company_id=env.company_id,
                move_id=move_id,
                transfer_id=transfer_id,
                warehouse_id=env.warehouse.warehouse_id,
                kind=StockMoveLineKind.CONTAINER,
                product_id=env.product.product_id,
                location_id=env.warehouse.stock_location_id,
                location_dest_id=bin_a.location_id,
                created_at=utcnow(),
            )
        )
        with pytest.raises(PlatformConflictError) as exc:
            _ = await env.di.move_engine.validate_transfer(
                company_id=env.company_id, transfer_id=transfer_id
            )
        assert exc.value.error_code == "container_missing"

    async def test_outbound_container_mixed_contents(self, stock_di, unique_id: str) -> None:
        """TOCTOU-сценарий: резерв целой паллеты снят по чистому
        содержимому (least_containers проверяет однородность), но до
        проводки на неё физически доложили чужой товар. При постинге
        проверка видит смесь → container_mixed_contents: «лишнее»
        не уедет за границу запаса мимо леджера."""
        env = await _env(stock_di, unique_id)
        env.product = await env.di.stock_catalog_service.create_product(
            company_id=env.company_id,
            name=f"LC {unique_id}",
            sku=f"LC-{unique_id}",
            uom_id=env.uom_id,
            valuation_method=ValuationMethod.FIFO,
            standard_price=Decimal("0"),
            tracking=StockTracking.NONE,
            is_storable=True,
            category="general",
            removal_strategy=StockRemovalStrategy.LEAST_CONTAINERS,
        )
        pallet = await _pallet(env, unique_id)
        _ = await _receipt_to_location(env, pallet.location_id, Decimal("2"))
        # Доставка первого товара — резерв целой паллетой.
        op_out = env.op_types[StockOperationCode.OUTGOING]
        delivery = await env.di.move_engine.create_transfer(
            company_id=env.company_id,
            warehouse_id=env.warehouse.warehouse_id,
            operation_type_id=op_out.operation_type_id,
            partner_entity_id=None,
            owner_entity_id=None,
            scheduled_at=None,
            origin_document_type=None,
            origin_document_id=None,
            barcode=None,
            moves=[
                StockMoveSpec(
                    product_id=env.product.product_id,
                    product_qty=Decimal("2"),
                    uom_id=env.uom_id,
                )
            ],
        )
        for step in ("confirm", "assign"):
            _ = await getattr(env.di.move_engine, f"{step}_transfer")(
                company_id=env.company_id,
                transfer_id=delivery.transfer_id,
            )
        moves = await StockMove.list_for_transfer_by_created_at_asc(env.company_id, delivery.transfer_id)
        lines = await StockMoveLine.list_for_move_by_created_at_asc(env.company_id, moves[0].move_id)
        assert any(ln.kind == StockMoveLineKind.CONTAINER for ln in lines)
        # Между резервом и проводкой на паллету доложили другой товар
        # (физический факт: рабочий поставил чужой короб на паллету).
        other = await env.di.stock_catalog_service.create_product(
            company_id=env.company_id,
            name=f"OT {unique_id}",
            sku=f"OT-{unique_id}",
            uom_id=env.uom_id,
            valuation_method=ValuationMethod.FIFO,
            standard_price=Decimal("0"),
            tracking=StockTracking.NONE,
            is_storable=True,
            category="general",
            removal_strategy=None,
        )
        _ = await StockQuant.objects.create(
            instance=StockQuant(
                quant_id=new_id("qt"),
                company_id=env.company_id,
                warehouse_id=env.warehouse.warehouse_id,
                product_id=other.product_id,
                location_id=pallet.location_id,
                quantity=Decimal("1"),
                in_date=utcnow(),
                created_at=utcnow(),
                updated_at=utcnow(),
            )
        )
        with pytest.raises(PlatformConflictError) as exc:
            _ = await env.di.move_engine.validate_transfer(
                company_id=env.company_id, transfer_id=delivery.transfer_id
            )
        assert exc.value.error_code == "container_mixed_contents"


class TestBrokenConfiguration:
    """Документы поверх удалённых/битых справочников."""

    async def test_create_transfer_without_any_locations(self, stock_di, unique_id: str) -> None:
        """Тип операции без дефолтных локаций + строка без явных —
        движок не может вывести направление → move_locations_missing."""
        env = await _env(stock_di, unique_id)
        bare = env.op_types[StockOperationCode.INTERNAL]
        _ = await StockOperationType.objects.filter(
            company_id=env.company_id, operation_type_id=bare.operation_type_id
        ).update(
            using=STOCK_DB,
            default_source_location_id=None,
            default_dest_location_id=None,
        )
        with pytest.raises(PlatformConflictError) as exc:
            _ = await env.di.move_engine.create_transfer(
                company_id=env.company_id,
                warehouse_id=env.warehouse.warehouse_id,
                operation_type_id=bare.operation_type_id,
                partner_entity_id=None,
                owner_entity_id=None,
                scheduled_at=None,
                origin_document_type=None,
                origin_document_id=None,
                barcode=None,
                moves=[
                    StockMoveSpec(
                        product_id=env.product.product_id,
                        product_qty=Decimal("1"),
                        uom_id=env.uom_id,
                    )
                ],
            )
        assert exc.value.error_code == "move_locations_missing"

    async def test_create_transfer_ghost_product(self, stock_di, unique_id: str) -> None:
        env = await _env(stock_di, unique_id)
        op = env.op_types[StockOperationCode.INCOMING]
        with pytest.raises(PlatformNotFoundError) as exc:
            _ = await env.di.move_engine.create_transfer(
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
                        product_id=f"prod_ghost_{unique_id}",
                        product_qty=Decimal("1"),
                        uom_id=env.uom_id,
                    )
                ],
            )
        assert exc.value.error_code == "product_not_found"

    async def test_confirm_after_operation_type_deleted(self, stock_di, unique_id: str) -> None:
        """Черновик накладной пережил удаление типа операции —
        confirm отвечает operation_type_not_found, а не молча едет."""
        env = await _env(stock_di, unique_id)
        op = env.op_types[StockOperationCode.INCOMING]
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
                    product_qty=Decimal("1"),
                    uom_id=env.uom_id,
                    unit_price=Decimal("4"),
                )
            ],
        )
        _ = await StockOperationType.objects.filter(
            company_id=env.company_id, operation_type_id=op.operation_type_id
        ).delete()
        with pytest.raises(PlatformNotFoundError) as exc:
            _ = await env.di.move_engine.confirm_transfer(
                company_id=env.company_id, transfer_id=transfer.transfer_id
            )
        assert exc.value.error_code == "operation_type_not_found"

    async def test_apply_decision_after_warehouse_deleted(self, stock_di, unique_id: str) -> None:
        """Move живёт, а склад-владелец удалён → transfer_config_invalid."""
        env = await _env(stock_di, unique_id)
        op = env.op_types[StockOperationCode.INCOMING]
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
                    product_qty=Decimal("1"),
                    uom_id=env.uom_id,
                )
            ],
        )
        move = (await StockMove.list_for_transfer_by_created_at_asc(env.company_id, transfer.transfer_id))[0]
        _ = await StockWarehouse.objects.filter(
            company_id=env.company_id, warehouse_id=env.warehouse.warehouse_id
        ).delete()
        with pytest.raises(PlatformConflictError) as exc:
            _ = await env.di.placement_service.apply_decision(
                company_id=env.company_id,
                move_id=move.move_id,
                location_id=env.warehouse.stock_location_id,
                idempotency_key=uuid.uuid7().hex,
            )
        assert exc.value.error_code == "transfer_config_invalid"

    async def test_claim_with_deleted_resource_type(self, stock_di, unique_id: str) -> None:
        """Ресурс жив, а его класс удалён из справочника —
        захват задания на нём → resource_type_not_found."""
        env = await _env(stock_di, unique_id)
        rtype = await env.di.topology_service.create_resource_type(
            company_id=env.company_id,
            warehouse_id=env.warehouse.warehouse_id,
            name=f"RT-{unique_id}",
            allowed_container_type_ids=[],
            storage_type_ids=[],
            handles_loose=True,
            max_level=None,
        )
        resource = await env.di.topology_service.create_resource(
            company_id=env.company_id,
            warehouse_id=env.warehouse.warehouse_id,
            resource_type_id=rtype.resource_type_id,
            code=f"RES-{unique_id}",
            barcode=None,
        )
        _ = await _receipt(env, Decimal("5"), Decimal("4"))
        _, move_id = await _assigned_outgoing(env, Decimal("2"))
        lines = await StockMoveLine.list_open_for_move_by_created_at_asc(env.company_id, move_id)
        _ = await StockResourceType.objects.filter(
            company_id=env.company_id, resource_type_id=rtype.resource_type_id
        ).delete()
        with pytest.raises(PlatformNotFoundError) as exc:
            _ = await env.di.task_service.claim(
                company_id=env.company_id,
                warehouse_id=env.warehouse.warehouse_id,
                move_line_ids=[lines[0].move_line_id],
                user_id=f"op-{unique_id}",
                resource_id=resource.resource_id,
            )
        assert exc.value.error_code == "resource_type_not_found"

    async def test_uom_zero_factor(self, stock_di, unique_id: str) -> None:
        """ЕИ с factor=0 в спецификации строки → uom_factor_zero:
        конвертация «в ноль» запрещена, иначе количество обнулится."""
        env = await _env(stock_di, unique_id)
        base = await CatalogUom.by_id(env.company_id, env.uom_id)
        assert base is not None
        _ = await CatalogUom.create(
            CatalogUom(
                uom_id=new_id("uom"),
                company_id=env.company_id,
                name=f"ZERO-{unique_id}",
                category=base.category,
                factor=Decimal("0"),
            )
        )
        rows = await CatalogUom.objects.filter(
            company_id=env.company_id, name=f"ZERO-{unique_id}"
        ).all()
        assert len(rows) == 1
        op = env.op_types[StockOperationCode.INCOMING]
        with pytest.raises(PlatformConflictError) as exc:
            _ = await env.di.move_engine.create_transfer(
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
                        product_qty=Decimal("5"),
                        uom_id=rows[0].uom_id,
                        unit_price=Decimal("4"),
                    )
                ],
            )
        assert exc.value.error_code == "uom_factor_zero"

    async def test_register_empty_barcode(self, stock_di, unique_id: str) -> None:
        env = await _env(stock_di, unique_id)
        with pytest.raises(PlatformConflictError) as exc:
            _ = await env.di.barcode_service.register(
                company_id=env.company_id,
                barcode="",
                entity_type=StockBarcodeEntityType.PRODUCT,
                entity_id=env.product.product_id,
            )
        assert exc.value.error_code == "barcode_empty"


class TestPutawayModes:
    """Режимы putaway-рефлекса: битый enum, INLINE без flow, сбой flow."""

    async def _draft_move(self, env: StockEnv) -> StockMove:
        op = env.op_types[StockOperationCode.INCOMING]
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
                    product_qty=Decimal("2"),
                    uom_id=env.uom_id,
                )
            ],
        )
        move = (await StockMove.list_for_transfer_by_created_at_asc(env.company_id, transfer.transfer_id))[0]
        return move

    async def test_putaway_mode_invalid(self, stock_di, unique_id: str) -> None:
        """Неизвестный режим (данные приехали мимо валидации —
        битая строка в БД) → putaway_mode_invalid."""
        env = await _env(stock_di, unique_id)
        op = env.op_types[StockOperationCode.INCOMING]
        move = await self._draft_move(env)
        bad = op.model_copy(update={"putaway_mode": "bogus"})
        with pytest.raises(PlatformConflictError) as exc:
            _ = await env.di.placement_service.resolve_putaway(
                company_id=env.company_id,
                warehouse=env.warehouse,
                operation_type=bad,
                move=move,
            )
        assert exc.value.error_code == "putaway_mode_invalid"

    async def test_inline_without_flow(self, stock_di, unique_id: str) -> None:
        """INLINE требует flow_id — иначе putaway_flow_missing."""
        env = await _env(stock_di, unique_id)
        op = env.op_types[StockOperationCode.INCOMING]
        move = await self._draft_move(env)
        broken = op.model_copy(update={"putaway_mode": ReflexMode.INLINE, "putaway_flow_id": None})
        with pytest.raises(PlatformConflictError) as exc:
            _ = await env.di.placement_service.resolve_putaway(
                company_id=env.company_id,
                warehouse=env.warehouse,
                operation_type=broken,
                move=move,
            )
        assert exc.value.error_code == "putaway_flow_missing"

    async def test_inline_flow_unreachable(self, stock_di, unique_id: str) -> None:
        """INLINE с flow_id, но сервис flows недоступен →
        putaway_flow_failed (ошибка вызова мапится в конфликт,
        а не проглатывается)."""
        env = await _env(stock_di, unique_id)
        op = env.op_types[StockOperationCode.INCOMING]
        move = await self._draft_move(env)
        inline = op.model_copy(
            update={
                "putaway_mode": ReflexMode.INLINE,
                "putaway_flow_id": f"flow_missing_{unique_id}",
            }
        )
        with pytest.raises(PlatformConflictError) as exc:
            _ = await env.di.placement_service.resolve_putaway(
                company_id=env.company_id,
                warehouse=env.warehouse,
                operation_type=inline,
                move=move,
            )
        assert exc.value.error_code == "putaway_flow_failed"


class TestBackorderLifecycle:
    """Бэкордер: политика never и довоз остатка отдельным документом."""

    async def _partial_delivery(self, env: StockEnv, ordered: Decimal, done: Decimal):
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
                    product_qty=ordered,
                    uom_id=env.uom_id,
                )
            ],
        )
        for step in ("confirm", "assign"):
            _ = await getattr(env.di.move_engine, f"{step}_transfer")(
                company_id=env.company_id,
                transfer_id=transfer.transfer_id,
            )
        _, _, lines = await env.di.warehouse_service.get_transfer(
            company_id=env.company_id, transfer_id=transfer.transfer_id
        )
        _ = await env.di.task_service.update_move_line(
            company_id=env.company_id,
            move_line_id=lines[0].move_line_id,
            done_quantity=done,
            picked=None,
            lot_id=None,
            location_dest_id=None,
        )
        return transfer

    async def test_backorder_fulfilled_later(self, stock_di, unique_id: str) -> None:
        """Отгрузили 4 из 10 → бэкордер на 6. Довозим его же
        документом — итог по складу ровно 10 уехало, денежная
        проводка делится на две записи журнала."""
        env = await _env(stock_di, unique_id)
        _ = await _receipt(env, Decimal("10"), Decimal("4"))
        delivery = await self._partial_delivery(env, Decimal("10"), Decimal("4"))
        done = await env.di.move_engine.validate_transfer(
            company_id=env.company_id, transfer_id=delivery.transfer_id
        )
        assert done.state == StockTransferState.DONE
        transfers = await env.di.warehouse_service.list_transfers(
            company_id=env.company_id,
            warehouse_id=env.warehouse.warehouse_id,
            state=None,
            limit=20,
            offset=0,
        )
        backorders = [t for t in transfers.items if t.backorder_of_id == delivery.transfer_id]
        assert len(backorders) == 1
        backorder = backorders[0]
        # Бэкордер живёт обычным жизненным циклом.
        for step in ("confirm", "assign"):
            _ = await getattr(env.di.move_engine, f"{step}_transfer")(
                company_id=env.company_id,
                transfer_id=backorder.transfer_id,
            )
        _ = await env.di.move_engine.validate_transfer(
            company_id=env.company_id, transfer_id=backorder.transfer_id
        )
        quant = await _stock_quant(env)
        assert quant is not None
        # 10 − 4 − 6 = 0 на полке.
        assert quant.quantity == Decimal("0")

    async def test_backorder_never_drops_residual(self, stock_di, unique_id: str) -> None:
        """Политика never: частичная отгрузка НЕ создаёт доказку —
        move закрывается done с done_qty < product_qty, остаток
        списан с требования без нового документа."""
        env = await _env(stock_di, unique_id)
        op = env.op_types[StockOperationCode.OUTGOING]
        _ = await env.di.warehouse_service.update_operation_type(
            company_id=env.company_id,
            operation_type_id=op.operation_type_id,
            name=None,
            reservation_policy=None,
            backorder_policy=BackorderPolicy.NEVER,
            putaway_mode=None,
            putaway_flow_id=None,
            auto_validate=None,
        )
        _ = await _receipt(env, Decimal("10"), Decimal("4"))
        delivery = await self._partial_delivery(env, Decimal("10"), Decimal("4"))
        done = await env.di.move_engine.validate_transfer(
            company_id=env.company_id, transfer_id=delivery.transfer_id
        )
        assert done.state == StockTransferState.DONE
        transfers = await env.di.warehouse_service.list_transfers(
            company_id=env.company_id,
            warehouse_id=env.warehouse.warehouse_id,
            state=None,
            limit=20,
            offset=0,
        )
        assert all(t.backorder_of_id is None for t in transfers.items)
        quant = await _stock_quant(env)
        assert quant is not None
        assert quant.quantity == Decimal("6")  # уехало только 4


class TestReadSurfaces:
    """Читающие поверхности, которые до аудита не имели прямых тестов."""

    async def test_update_warehouse_renames(self, stock_di, unique_id: str) -> None:
        env = await _env(stock_di, unique_id)
        updated = await env.di.warehouse_service.update_warehouse(
            company_id=env.company_id,
            warehouse_id=env.warehouse.warehouse_id,
            name=f"Renamed {unique_id}",
            code=None,
        )
        assert updated.name == f"Renamed {unique_id}"

    async def test_container_contents(self, stock_di, unique_id: str) -> None:
        env = await _env(stock_di, unique_id)
        pallet = await _pallet(env, unique_id)
        contents = await env.di.topology_service.container_contents(
            company_id=env.company_id, container_id=pallet.location_id
        )
        assert contents.container.location_id == pallet.location_id
        assert contents.quants == [] and contents.children == []
        bin_a = await _bin(env, f"G{unique_id}")
        with pytest.raises(PlatformNotFoundError):
            _ = await env.di.topology_service.container_contents(
                company_id=env.company_id, container_id=bin_a.location_id
            )

    async def test_collect_candidates_subtree(self, stock_di, unique_id: str) -> None:
        """Вселенная кандидатов — всё поддерево склада (bin'ы и тара)."""
        env = await _env(stock_di, unique_id)
        bin_a = await _bin(env, f"H{unique_id}")
        op = env.op_types[StockOperationCode.INCOMING]
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
                    product_qty=Decimal("1"),
                    uom_id=env.uom_id,
                )
            ],
        )
        move = (await StockMove.list_for_transfer_by_created_at_asc(env.company_id, transfer.transfer_id))[0]
        candidates = await env.di.placement_service.collect_candidates(
            company_id=env.company_id, warehouse=env.warehouse, move=move
        )
        assert bin_a.location_id in candidates

    async def test_line_fits_resource_rules(self, stock_di, unique_id: str) -> None:
        """Чистая проверка допуска техники: ярус, тип хранения,
        допуск к таре и россыпи — по контракту StockResourceType."""
        env = await _env(stock_di, unique_id)
        line = StockMoveLine(
            move_line_id="mli-x",
            company_id=env.company_id,
            move_id="mv-x",
            product_id=env.product.product_id,
            location_id="loc-a",
            location_dest_id="loc-b",
            created_at=utcnow(),
        )
        src = await _bin(env, f"I{unique_id}")
        src = src.model_copy(update={"level": 3})
        rtype = StockResourceType(
            resource_type_id="rt-x",
            company_id=env.company_id,
            warehouse_id=env.warehouse.warehouse_id,
            name="Forklift",
            handles_loose=True,
            max_level=2,
            storage_type_ids=[],
            allowed_container_type_ids=[],
            created_at=utcnow(),
            updated_at=utcnow(),
        )
        # Ярус выше потолка техники.
        assert (
            line_fits_resource(line, source_location=src, container=None, resource_type=rtype)
            is False
        )
        # Потолок снят — россыпь разрешена.
        rtype2 = rtype.model_copy(update={"max_level": None})
        assert (
            line_fits_resource(line, source_location=src, container=None, resource_type=rtype2)
            is True
        )
        # Россыпь запрещена — строка не по таре.
        rtype3 = rtype2.model_copy(update={"handles_loose": False})
        assert (
            line_fits_resource(line, source_location=src, container=None, resource_type=rtype3)
            is False
        )
        # Строка по таре + тип тары не в списке допуска.
        container_line = line.model_copy(
            update={"kind": StockMoveLineKind.CONTAINER, "container_id": "cx"}
        )
        pallet = await _pallet(env, f"J{unique_id}")
        rtype4 = rtype2.model_copy(update={"allowed_container_type_ids": ["ct-other"]})
        assert (
            line_fits_resource(
                container_line,
                source_location=src,
                container=pallet,
                resource_type=rtype4,
            )
            is False
        )


class TestAtConfirmReserve:
    """`reservation_policy=at_confirm`: confirm сам резервирует и
    пишет аудируемый StockDecision — «горячая» приёмка одной кнопкой."""

    async def test_confirm_writes_applied_decision(self, stock_di, unique_id: str) -> None:
        env = await _env(stock_di, unique_id)
        op = env.op_types[StockOperationCode.INCOMING]
        _ = await env.di.warehouse_service.update_operation_type(
            company_id=env.company_id,
            operation_type_id=op.operation_type_id,
            name=None,
            reservation_policy=ReservationPolicy.AT_CONFIRM,
            backorder_policy=None,
            putaway_mode=None,
            putaway_flow_id=None,
            auto_validate=None,
        )
        bin_a = await _bin(env, f"AC{unique_id}")
        _ = await StockPutawayRule.create(
            company_id=env.company_id,
            warehouse_id=env.warehouse.warehouse_id,
            location_in_id=env.warehouse.view_location_id,
            location_out_id=bin_a.location_id,
            product_id=env.product.product_id,
        )
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
                    product_qty=Decimal("3"),
                    uom_id=env.uom_id,
                    unit_price=Decimal("4"),
                )
            ],
        )
        _ = await env.di.move_engine.confirm_transfer(
            company_id=env.company_id, transfer_id=transfer.transfer_id
        )
        # Правило сработало на confirm: dest перезаписан на BIN-A,
        # решение легло в stock_decisions (status=applied).
        move = (await StockMove.list_for_transfer_by_created_at_asc(env.company_id, transfer.transfer_id))[0]
        assert move.location_dest_id == bin_a.location_id
        decision = await StockDecision.latest_for_transfer_by_created_at_desc(env.company_id, transfer.transfer_id)
        assert decision is not None
        assert decision.status == StockDecisionStatus.APPLIED
        assert decision.chosen_location_id == bin_a.location_id
        assert bin_a.location_id in decision.candidate_location_ids


class TestShadowPutaway:
    """SHADOW-режим: рефлекс советует, но решение остаётся suggest."""

    async def test_shadow_decision_is_suggested(self, stock_di, unique_id: str) -> None:
        env = await _env(stock_di, unique_id)
        op = env.op_types[StockOperationCode.INCOMING]
        shadow = op.model_copy(update={"putaway_mode": ReflexMode.SHADOW})
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
                    product_qty=Decimal("2"),
                    uom_id=env.uom_id,
                )
            ],
        )
        move = (await StockMove.list_for_transfer_by_created_at_asc(env.company_id, transfer.transfer_id))[0]
        decision = await env.di.placement_service.resolve_putaway(
            company_id=env.company_id,
            warehouse=env.warehouse,
            operation_type=shadow,
            move=move,
        )
        assert decision is not None
        assert decision.status == StockDecisionStatus.SUGGESTED
        assert decision.applied_at is None
