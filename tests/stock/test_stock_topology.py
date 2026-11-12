"""Топология склада: типы хранения/контейнеров/ресурсов, контейнеры как
`usage=container` локации (create/nesting/move/contents), ресурсы login/logout,
упаковки. Продовый путь — реальный Postgres, lanes.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from apps.stock.models import (
    StockBarcodeEntityType,
    StockContainerKind,
    StockContainerPolicy,
    StockLocationUsage,
    StockProductMixing,
    StockPutawayStrategy,
    StockTracking,
    ValuationMethod,
)
from core.errors.boundary import PlatformConflictError, PlatformNotFoundError
from tests.stock.test_stock_domain import StockEnv, _make_env


async def _env(stock_di, unique_id: str) -> StockEnv:
    return await _make_env(
        stock_di, f"co-{unique_id}", unique_id, ValuationMethod.STANDARD
    )


class TestStorageTypes:
    async def test_crud_and_unique_name(
        self, stock_di, unique_id: str
    ) -> None:
        env = await _env(stock_di, unique_id)
        st = await env.di.topology_service.create_storage_type(
            company_id=env.company_id,
            warehouse_id=env.warehouse.warehouse_id,
            name="Pallet zone",
            putaway_strategies=[StockPutawayStrategy.EMPTY_BIN],
            allowed_container_type_ids=[],
            container_policy=StockContainerPolicy.CONTAINER_ONLY,
            max_containers=4,
            product_mixing=StockProductMixing.SAME_PRODUCT,
            allow_mixed_lots=False,
            max_weight=Decimal("1000"),
        )
        assert st.storage_type_id.startswith("sst_")
        listed = await env.di.topology_service.list_storage_types(
            company_id=env.company_id, warehouse_id=env.warehouse.warehouse_id
        )
        assert [s.storage_type_id for s in listed] == [st.storage_type_id]
        with pytest.raises(PlatformConflictError) as exc:
            await env.di.topology_service.create_storage_type(
                company_id=env.company_id,
                warehouse_id=env.warehouse.warehouse_id,
                name="Pallet zone",
                putaway_strategies=[StockPutawayStrategy.EMPTY_BIN],
                allowed_container_type_ids=[],
            )
        assert exc.value.error_code == "storage_type_conflict"


class TestContainers:
    async def test_create_and_contents(
        self, stock_di, unique_id: str
    ) -> None:
        env = await _env(stock_di, unique_id)
        ctype = await env.di.topology_service.create_container_type(
            company_id=env.company_id,
            warehouse_id=env.warehouse.warehouse_id,
            name="EUR pallet",
            kind=StockContainerKind.PALLET,
            max_weight=Decimal("800"),
            allowed_parent_type_ids=[],
        )
        assert ctype.kind == StockContainerKind.PALLET
        container = await env.di.topology_service.create_container(
            company_id=env.company_id,
            warehouse_id=env.warehouse.warehouse_id,
            parent_location_id=env.warehouse.stock_location_id,
            container_type_id=ctype.container_type_id,
            name="PLT-1",
            barcode="SSCC-1",
        )
        assert container.usage == StockLocationUsage.CONTAINER
        assert container.container_type_id == ctype.container_type_id
        # barcode зарегистрирован как CONTAINER
        resolved = await env.di.barcode_service.resolve(
            company_id=env.company_id, barcode="SSCC-1"
        )
        assert resolved.entity_type == StockBarcodeEntityType.CONTAINER
        assert resolved.entity_id == container.location_id
        contents = await env.di.topology_service.container_contents(
            company_id=env.company_id, container_id=container.location_id
        )
        assert contents.quants == []
        assert contents.children == []

    async def test_nested_container_denied_by_parent_rule(
        self, stock_di, unique_id: str
    ) -> None:
        env = await _env(stock_di, unique_id)
        pallet = await env.di.topology_service.create_container_type(
            company_id=env.company_id,
            warehouse_id=env.warehouse.warehouse_id,
            name="Pallet",
            kind=StockContainerKind.PALLET,
            allowed_parent_type_ids=[],
        )
        box = await env.di.topology_service.create_container_type(
            company_id=env.company_id,
            warehouse_id=env.warehouse.warehouse_id,
            name="Box",
            kind=StockContainerKind.BOX,
            allowed_parent_type_ids=["other-type-id"],
        )
        parent = await env.di.topology_service.create_container(
            company_id=env.company_id,
            warehouse_id=env.warehouse.warehouse_id,
            parent_location_id=env.warehouse.stock_location_id,
            container_type_id=pallet.container_type_id,
            name="PLT",
            barcode=None,
        )
        with pytest.raises(PlatformConflictError) as exc:
            await env.di.topology_service.create_container(
                company_id=env.company_id,
                warehouse_id=env.warehouse.warehouse_id,
                parent_location_id=parent.location_id,
                container_type_id=box.container_type_id,
                name="BOX-1",
                barcode=None,
            )
        assert exc.value.error_code == "container_parent_denied"

    async def test_move_container_rebinds_subtree(
        self, stock_di, unique_id: str
    ) -> None:
        env = await _env(stock_di, unique_id)
        ctype = await env.di.topology_service.create_container_type(
            company_id=env.company_id,
            warehouse_id=env.warehouse.warehouse_id,
            name="Tote",
            kind=StockContainerKind.TOTE,
            allowed_parent_type_ids=[],
        )
        zone = await env.di.topology_service.create_location(
            company_id=env.company_id,
            warehouse_id=env.warehouse.warehouse_id,
            parent_id=env.warehouse.view_location_id,
            name="Zone B",
            usage=StockLocationUsage.VIEW,
            barcode=None,
        )
        cell = await env.di.topology_service.create_location(
            company_id=env.company_id,
            warehouse_id=env.warehouse.warehouse_id,
            parent_id=zone.location_id,
            name="Cell B1",
            usage=StockLocationUsage.BIN,
            barcode=None,
        )
        container = await env.di.topology_service.create_container(
            company_id=env.company_id,
            warehouse_id=env.warehouse.warehouse_id,
            parent_location_id=env.warehouse.stock_location_id,
            container_type_id=ctype.container_type_id,
            name="TOTE-1",
            barcode=None,
        )
        moved = await env.di.topology_service.move_container(
            company_id=env.company_id,
            container_id=container.location_id,
            dest_location_id=cell.location_id,
            user_id="test_user",
        )
        assert moved.parent_id == cell.location_id
        subtree = await env.di.topology_service.list_locations(
            company_id=env.company_id, warehouse_id=env.warehouse.warehouse_id
        )
        tote = next(loc for loc in subtree if loc.location_id == container.location_id)
        assert tote.parent_path.startswith(cell.parent_path)

    async def test_move_container_to_cycle_denied(
        self, stock_di, unique_id: str
    ) -> None:
        env = await _env(stock_di, unique_id)
        ctype = await env.di.topology_service.create_container_type(
            company_id=env.company_id,
            warehouse_id=env.warehouse.warehouse_id,
            name="Nestable",
            kind=StockContainerKind.TOTE,
            allowed_parent_type_ids=[],
        )
        outer = await env.di.topology_service.create_container(
            company_id=env.company_id,
            warehouse_id=env.warehouse.warehouse_id,
            parent_location_id=env.warehouse.stock_location_id,
            container_type_id=ctype.container_type_id,
            name="OUTER",
            barcode=None,
        )
        inner = await env.di.topology_service.create_container(
            company_id=env.company_id,
            warehouse_id=env.warehouse.warehouse_id,
            parent_location_id=outer.location_id,
            container_type_id=ctype.container_type_id,
            name="INNER",
            barcode=None,
        )
        with pytest.raises(PlatformConflictError) as exc:
            await env.di.topology_service.move_container(
                company_id=env.company_id,
                container_id=outer.location_id,
                dest_location_id=inner.location_id,
                user_id="test_user",
            )
        assert exc.value.error_code in {
            "container_cycle",
            "container_destination_invalid",
        }


class TestResources:
    async def test_login_logout_cycle(
        self, stock_di, unique_id: str
    ) -> None:
        env = await _env(stock_di, unique_id)
        rtype = await env.di.topology_service.create_resource_type(
            company_id=env.company_id,
            warehouse_id=env.warehouse.warehouse_id,
            name="Reach truck",
            allowed_container_type_ids=[],
            storage_type_ids=[],
            handles_loose=False,
            max_level=3,
        )
        resource = await env.di.topology_service.create_resource(
            company_id=env.company_id,
            warehouse_id=env.warehouse.warehouse_id,
            resource_type_id=rtype.resource_type_id,
            code="RT-01",
            barcode="RES-RT-01",
        )
        logged = await env.di.topology_service.resource_login(
            company_id=env.company_id,
            warehouse_id=env.warehouse.warehouse_id,
            resource_id=None,
            barcode="RES-RT-01",
            user_id="op-1",
        )
        assert logged.resource_id == resource.resource_id
        assert logged.current_user_id == "op-1"
        # Другой оператор на занятый ресурс — конфликт.
        with pytest.raises(PlatformConflictError) as exc:
            await env.di.topology_service.resource_login(
                company_id=env.company_id,
                warehouse_id=env.warehouse.warehouse_id,
                resource_id=resource.resource_id,
                barcode=None,
                user_id="op-2",
            )
        assert exc.value.error_code == "resource_occupied"
        result = await env.di.topology_service.resource_logout(
            company_id=env.company_id,
            warehouse_id=env.warehouse.warehouse_id,
            user_id="op-1",
        )
        assert result.resource_id == resource.resource_id
        freed = await env.di.topology_service.resource_login(
            company_id=env.company_id,
            warehouse_id=env.warehouse.warehouse_id,
            resource_id=resource.resource_id,
            barcode=None,
            user_id="op-2",
        )
        assert freed.current_user_id == "op-2"

    async def test_resource_barcode_resolves(
        self, stock_di, unique_id: str
    ) -> None:
        env = await _env(stock_di, unique_id)
        rtype = await env.di.topology_service.create_resource_type(
            company_id=env.company_id,
            warehouse_id=env.warehouse.warehouse_id,
            name="Forklift",
            allowed_container_type_ids=[],
            storage_type_ids=[],
        )
        resource = await env.di.topology_service.create_resource(
            company_id=env.company_id,
            warehouse_id=env.warehouse.warehouse_id,
            resource_type_id=rtype.resource_type_id,
            code="FL-1",
            barcode="RES-FL-1",
        )
        resolved = await env.di.barcode_service.resolve(
            company_id=env.company_id, barcode="RES-FL-1"
        )
        assert resolved.entity_type == StockBarcodeEntityType.RESOURCE
        assert resolved.entity_id == resource.resource_id


class TestPackagings:
    async def test_create_list_delete(
        self, stock_di, unique_id: str
    ) -> None:
        env = await _env(stock_di, unique_id)
        pack = await env.di.catalog_service.create_packaging(
            company_id=env.company_id,
            product_id=env.product.product_id,
            name="Box of 12",
            quantity=Decimal("12"),
            barcode="PK-12",
            weight=Decimal("3.5"),
            volume=None,
        )
        assert pack.quantity == Decimal("12")
        resolved = await env.di.barcode_service.resolve(
            company_id=env.company_id, barcode="PK-12"
        )
        assert resolved.entity_type == StockBarcodeEntityType.PACKAGING
        listed = await env.di.catalog_service.list_packagings(
            company_id=env.company_id, product_id=env.product.product_id
        )
        assert [p.packaging_id for p in listed] == [pack.packaging_id]
        deleted = await env.di.catalog_service.delete_packaging(
            company_id=env.company_id, packaging_id=pack.packaging_id
        )
        assert deleted.packaging_id == pack.packaging_id
        assert (
            await env.di.catalog_service.list_packagings(
                company_id=env.company_id, product_id=env.product.product_id
            )
            == []
        )


class TestGs1Resolve:
    async def test_gtin_resolves_product(
        self, stock_di, unique_id: str
    ) -> None:
        env = await _env(stock_di, unique_id)
        # У продукта barcode=GTIN — resolve по AI 01.
        gtin = "04607025392165"
        product = await env.di.stock_catalog_service.create_product(
            company_id=env.company_id,
            name="GTIN product",
            sku=f"G-{unique_id}",
            uom_id=env.uom_id,
            valuation_method=ValuationMethod.STANDARD,
            standard_price=Decimal("0"),
            tracking=StockTracking.NONE,
            is_storable=True,
            category="general",
            barcodes=[gtin],
        )
        resolved = await env.di.barcode_service.resolve(
            company_id=env.company_id, barcode=f"01{gtin}"
        )
        assert resolved.entity_type == StockBarcodeEntityType.PRODUCT
        assert resolved.entity_id == product.product_id
        assert resolved.parsed.gtin == gtin

    async def test_gs1_lot_resolves_within_product(
        self, stock_di, unique_id: str
    ) -> None:
        env = await _env(stock_di, unique_id)
        gtin = "04607025392166"
        product = await env.di.stock_catalog_service.create_product(
            company_id=env.company_id,
            name="Lot product",
            sku=f"L-{unique_id}",
            uom_id=env.uom_id,
            valuation_method=ValuationMethod.STANDARD,
            standard_price=Decimal("0"),
            tracking=StockTracking.NONE,
            is_storable=True,
            category="general",
            barcodes=[gtin],
        )
        from apps.stock.models import StockLot
        from apps.stock.services.ids import new_id
        from core.utils.time import utcnow

        lot = await StockLot.create(
            StockLot(
                lot_id=new_id("lot"),
                company_id=env.company_id,
                product_id=product.product_id,
                name="LOT-77",
                created_at=utcnow(),
            )
        )
        resolved = await env.di.barcode_service.resolve(
            company_id=env.company_id,
            barcode=f"01{gtin}\x1d10LOT-77",
        )
        assert resolved.entity_type == StockBarcodeEntityType.LOT
        assert resolved.entity_id == lot.lot_id
        assert resolved.parsed.lot_name == "LOT-77"

    async def test_unknown_barcode_raises(
        self, stock_di, unique_id: str
    ) -> None:
        env = await _env(stock_di, unique_id)
        with pytest.raises(PlatformNotFoundError) as exc:
            await env.di.barcode_service.resolve(
                company_id=env.company_id, barcode="NO-SUCH-CODE"
            )
        assert exc.value.error_code == "barcode_not_found"


class TestSubtreeListing:
    async def test_list_in_subtree_by_path(
        self, stock_di, unique_id: str
    ) -> None:
        from apps.stock.models import StockLocation

        env = await _env(stock_di, unique_id)
        zone = await env.di.topology_service.create_location(
            company_id=env.company_id,
            warehouse_id=env.warehouse.warehouse_id,
            parent_id=env.warehouse.view_location_id,
            name="Zone Z",
            usage=StockLocationUsage.VIEW,
            barcode=None,
        )
        cell = await env.di.topology_service.create_location(
            company_id=env.company_id,
            warehouse_id=env.warehouse.warehouse_id,
            parent_id=zone.location_id,
            name="Cell Z1",
            usage=StockLocationUsage.BIN,
            barcode=None,
        )
        ids = await StockLocation.list_subtree_ids_by_parent_path_asc(
            env.company_id, zone.location_id
        )
        assert zone.location_id in ids
        assert cell.location_id in ids
        assert env.warehouse.stock_location_id not in ids

    async def test_list_locations_include_virtual(
        self, stock_di, unique_id: str
    ) -> None:
        """Виртуальные концы (partner/transit/adjustment) попадают в
        список локаций только с ``include_virtual``: они вне складов,
        но ТСД резолвит их имена в маршрутах документов («→ customer»)."""
        env = await _env(stock_di, unique_id)
        plain = await env.di.topology_service.list_locations(
            company_id=env.company_id,
            warehouse_id=env.warehouse.warehouse_id,
        )
        assert all(row.warehouse_id is not None for row in plain)
        with_virtual = await env.di.topology_service.list_locations(
            company_id=env.company_id,
            warehouse_id=env.warehouse.warehouse_id,
            include_virtual=True,
        )
        virtual = [row for row in with_virtual if row.warehouse_id is None]
        usages = {row.usage for row in virtual}
        assert StockLocationUsage.PARTNER in usages
        assert StockLocationUsage.TRANSIT in usages
        assert StockLocationUsage.ADJUSTMENT in usages
        # Физические локации склада на месте — флаг добавляет, а не заменяет.
        assert any(
            row.location_id == env.warehouse.stock_location_id
            for row in with_virtual
        )
