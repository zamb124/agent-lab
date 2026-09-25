"""CRUD сущностей склада + создание склада (дерево локаций + 3 типа операций)."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from oxyde.exceptions import UniqueViolationError

from apps.stock.models import (
    BackorderPolicy,
    ReflexMode,
    ReservationPolicy,
    StockBarcodeEntityType,
    StockLocation,
    StockLocationUsage,
    StockLot,
    StockMove,
    StockMoveLine,
    StockOperationCode,
    StockOperationType,
    StockPackage,
    StockPackageType,
    StockProduct,
    StockProductTemplate,
    StockQuant,
    StockTracking,
    StockTransfer,
    StockTransferState,
    StockWarehouse,
    UnitOfMeasure,
    ValuationMethod,
)
from apps.stock.services.barcode_service import BarcodeService
from apps.stock.services.ids import new_id
from apps.stock.services.stock_access_service import StockAccessService
from core.errors.boundary import PlatformConflictError, PlatformNotFoundError
from core.pagination import OffsetPage
from core.utils.time import utcnow


def _conflict(message: str, error_code: str) -> PlatformConflictError:
    return PlatformConflictError(message, error_code=error_code)


def _not_found(message: str, error_code: str) -> PlatformNotFoundError:
    return PlatformNotFoundError(message, error_code=error_code)


class WarehouseService:
    """Сценарии управления справочниками склада."""

    def __init__(
        self,
        barcode: BarcodeService,
        access: StockAccessService,
    ) -> None:
        self._barcode: BarcodeService = barcode
        self._access: StockAccessService = access

    # --- UoM ---

    async def list_uoms(self, *, company_id: str) -> list[UnitOfMeasure]:
        return await UnitOfMeasure.objects.filter(company_id=company_id).order_by(
            "category", "name"
        ).all()

    # --- Products ---

    async def create_product(
        self,
        *,
        company_id: str,
        name: str,
        sku: str,
        uom_id: str,
        valuation_method: ValuationMethod,
        standard_price: Decimal,
        tracking: StockTracking,
        is_storable: bool,
        category: str,
        barcode: str | None,
    ) -> StockProduct:
        """Шаблон + вариант + barcode-индекс одним сценарием."""
        if await UnitOfMeasure.by_id(company_id, uom_id) is None:
            raise _not_found("Unit of measure not found", "uom_not_found")
        now = utcnow()
        template = await StockProductTemplate.objects.create(
            instance=StockProductTemplate(
                product_template_id=new_id("spt"),
                company_id=company_id,
                name=name,
                tracking=tracking,
                is_storable=is_storable,
                category=category,
                valuation_method=valuation_method,
                standard_price=standard_price,
                uom_id=uom_id,
                created_at=now,
                updated_at=now,
            )
        )
        try:
            product = await StockProduct.objects.create(
                instance=StockProduct(
                    product_id=new_id("spr"),
                    company_id=company_id,
                    template_id=template.product_template_id,
                    sku=sku,
                    barcode=barcode,
                    uom_id=uom_id,
                    created_at=now,
                    updated_at=now,
                )
            )
        except UniqueViolationError as exc:
            raise _conflict("SKU already exists", "sku_conflict") from exc
        if barcode is not None:
            _ = await self._barcode.register(
                company_id=company_id,
                barcode=barcode,
                entity_type=StockBarcodeEntityType.PRODUCT,
                entity_id=product.product_id,
            )
        return product

    async def update_product(
        self,
        *,
        company_id: str,
        product_id: str,
        name: str | None,
        sku: str | None,
        barcode: str | None,
        is_active: bool | None,
        valuation_method: ValuationMethod | None,
        standard_price: Decimal | None,
        tracking: StockTracking | None,
    ) -> StockProduct:
        product = await StockProduct.by_id(company_id, product_id)
        if product is None:
            raise _not_found("Product not found", "product_not_found")
        template = await StockProductTemplate.by_id(company_id, product.template_id)
        if template is None:
            raise _not_found("Product template not found", "product_not_found")
        if valuation_method is not None or standard_price is not None:
            _ = await StockProductTemplate.update_valuation_method(
                company_id=company_id,
                product_template_id=template.product_template_id,
                valuation_method=valuation_method or template.valuation_method,
                standard_price=standard_price,
            )
        if name is not None or tracking is not None:
            template.name = name if name is not None else template.name
            template.tracking = tracking if tracking is not None else template.tracking
            template.updated_at = utcnow()
            _ = await template.save()
        if sku is not None or barcode is not None or is_active is not None:
            product.sku = sku if sku is not None else product.sku
            product.is_active = (
                is_active if is_active is not None else product.is_active
            )
            if barcode is not None and barcode != product.barcode:
                _ = await self._barcode.replace(
                    company_id=company_id,
                    barcode=barcode,
                    entity_type=StockBarcodeEntityType.PRODUCT,
                    entity_id=product.product_id,
                )
                product.barcode = barcode
            product.updated_at = utcnow()
            try:
                _ = await product.save()
            except UniqueViolationError as exc:
                raise _conflict("SKU already exists", "sku_conflict") from exc
        return product

    async def get_product(
        self, *, company_id: str, product_id: str
    ) -> tuple[StockProduct, StockProductTemplate]:
        product = await StockProduct.by_id(company_id, product_id)
        if product is None:
            raise _not_found("Product not found", "product_not_found")
        template = await StockProductTemplate.by_id(company_id, product.template_id)
        if template is None:
            raise _not_found("Product template not found", "product_not_found")
        return product, template

    async def list_products(
        self, *, company_id: str, limit: int, offset: int
    ) -> OffsetPage[StockProduct]:
        rows = await StockProduct.list_for_company(
            company_id, limit=limit, offset=offset
        )
        total = await StockProduct.count_for_company(company_id)
        return OffsetPage(items=rows, total=total, limit=limit, offset=offset)

    # --- Locations ---

    async def create_location(
        self,
        *,
        company_id: str,
        warehouse_id: str,
        parent_id: str | None,
        name: str,
        usage: StockLocationUsage,
        removal_method: str | None,
        barcode: str | None,
    ) -> StockLocation:
        warehouse = await StockWarehouse.by_id(company_id, warehouse_id)
        if warehouse is None:
            raise _not_found("Warehouse not found", "warehouse_not_found")
        if usage not in {StockLocationUsage.VIEW, StockLocationUsage.INTERNAL}:
            raise _conflict(
                "Warehouse locations must be view|internal",
                "location_usage_invalid",
            )
        if parent_id is not None:
            parent = await StockLocation.by_id(company_id, parent_id)
            if parent is None or parent.warehouse_id != warehouse_id:
                raise _not_found("Parent location not found", "location_not_found")
        location = await StockLocation.objects.create(
            instance=StockLocation(
                location_id=new_id("loc"),
                company_id=company_id,
                warehouse_id=warehouse_id,
                parent_id=parent_id or warehouse.view_location_id,
                name=name,
                usage=usage,
                removal_method=removal_method or "fifo",
                barcode=barcode,
                created_at=utcnow(),
            )
        )
        if barcode is not None:
            _ = await self._barcode.register(
                company_id=company_id,
                barcode=barcode,
                entity_type=StockBarcodeEntityType.LOCATION,
                entity_id=location.location_id,
            )
        return location

    async def update_location(
        self,
        *,
        company_id: str,
        location_id: str,
        name: str | None,
        removal_method: str | None,
        barcode: str | None,
        is_active: bool | None,
    ) -> StockLocation:
        location = await StockLocation.by_id(company_id, location_id)
        if location is None:
            raise _not_found("Location not found", "location_not_found")
        location.name = name if name is not None else location.name
        location.removal_method = (
            removal_method if removal_method is not None else location.removal_method
        )
        location.is_active = is_active if is_active is not None else location.is_active
        if barcode is not None and barcode != location.barcode:
            _ = await self._barcode.replace(
                company_id=company_id,
                barcode=barcode,
                entity_type=StockBarcodeEntityType.LOCATION,
                entity_id=location.location_id,
            )
            location.barcode = barcode
        _ = await location.save()
        return location

    async def list_locations(
        self, *, company_id: str, warehouse_id: str | None
    ) -> list[StockLocation]:
        rows = await StockLocation.list_for_company(company_id)
        if warehouse_id is not None:
            rows = [r for r in rows if r.warehouse_id == warehouse_id]
        return rows

    async def get_location(
        self, *, company_id: str, location_id: str
    ) -> StockLocation:
        location = await StockLocation.by_id(company_id, location_id)
        if location is None:
            raise _not_found("Location not found", "location_not_found")
        return location

    # --- Warehouses ---

    async def create_warehouse(
        self,
        *,
        company_id: str,
        code: str,
        name: str,
        owner_user_id: str,
    ) -> StockWarehouse:
        """Склад = view + stock локация + 3 типа операций + authz-дефолты."""
        now = utcnow()
        warehouse_id = new_id("whs")
        view = await StockLocation.objects.create(
            instance=StockLocation(
                location_id=new_id("loc"),
                company_id=company_id,
                warehouse_id=warehouse_id,
                parent_id=None,
                name=f"{name} (view)",
                usage=StockLocationUsage.VIEW,
                created_at=now,
            )
        )
        stock = await StockLocation.objects.create(
            instance=StockLocation(
                location_id=new_id("loc"),
                company_id=company_id,
                warehouse_id=warehouse_id,
                parent_id=view.location_id,
                name="Stock",
                usage=StockLocationUsage.INTERNAL,
                created_at=now,
            )
        )
        try:
            warehouse = await StockWarehouse.objects.create(
                instance=StockWarehouse(
                    warehouse_id=warehouse_id,
                    company_id=company_id,
                    code=code,
                    name=name,
                    view_location_id=view.location_id,
                    stock_location_id=stock.location_id,
                    created_at=now,
                )
            )
        except UniqueViolationError as exc:
            raise _conflict("Warehouse code already exists", "warehouse_code_conflict") from exc
        supplier = await StockLocation.virtual_by_usage(
            company_id, StockLocationUsage.SUPPLIER
        )
        customer = await StockLocation.virtual_by_usage(
            company_id, StockLocationUsage.CUSTOMER
        )
        if supplier is None or customer is None:
            raise _conflict(
                "Virtual locations missing; run stock/company/init first",
                "company_not_initialized",
            )
        for op_code, op_name, src, dst in (
            (StockOperationCode.INCOMING, "Receipts", supplier.location_id, stock.location_id),
            (StockOperationCode.OUTGOING, "Delivery Orders", stock.location_id, customer.location_id),
            (StockOperationCode.INTERNAL, "Internal Transfers", stock.location_id, stock.location_id),
        ):
            _ = await StockOperationType.objects.create(
                instance=StockOperationType(
                    operation_type_id=new_id("opt"),
                    company_id=company_id,
                    warehouse_id=warehouse_id,
                    code=op_code,
                    name=f"{code} {op_name}",
                    default_source_location_id=src,
                    default_dest_location_id=dst,
                    reservation_policy=ReservationPolicy.AT_CONFIRM,
                    backorder_policy=BackorderPolicy.ALWAYS,
                    putaway_mode=ReflexMode.RULE,
                    created_at=now,
                    updated_at=now,
                )
            )
        await self._access.ensure_warehouse_defaults(
            warehouse_id=warehouse_id,
            company_id=company_id,
            owner_user_id=owner_user_id,
        )
        return warehouse

    async def update_warehouse(
        self,
        *,
        company_id: str,
        warehouse_id: str,
        name: str | None,
        code: str | None,
    ) -> StockWarehouse:
        warehouse = await StockWarehouse.by_id(company_id, warehouse_id)
        if warehouse is None:
            raise _not_found("Warehouse not found", "warehouse_not_found")
        warehouse.name = name if name is not None else warehouse.name
        warehouse.code = code if code is not None else warehouse.code
        try:
            _ = await warehouse.save()
        except UniqueViolationError as exc:
            raise _conflict("Warehouse code already exists", "warehouse_code_conflict") from exc
        return warehouse

    async def list_warehouses(
        self, *, company_id: str, limit: int, offset: int
    ) -> OffsetPage[StockWarehouse]:
        rows = await StockWarehouse.list_for_company(
            company_id, limit=limit, offset=offset
        )
        total = await StockWarehouse.count_for_company(company_id)
        return OffsetPage(items=rows, total=total, limit=limit, offset=offset)

    async def get_warehouse(
        self, *, company_id: str, warehouse_id: str
    ) -> StockWarehouse:
        warehouse = await StockWarehouse.by_id(company_id, warehouse_id)
        if warehouse is None:
            raise _not_found("Warehouse not found", "warehouse_not_found")
        return warehouse

    # --- Operation types ---

    async def list_operation_types(
        self, *, company_id: str, warehouse_id: str
    ) -> list[StockOperationType]:
        return await StockOperationType.list_for_warehouse(company_id, warehouse_id)

    async def update_operation_type(
        self,
        *,
        company_id: str,
        operation_type_id: str,
        name: str | None,
        reservation_policy: ReservationPolicy | None,
        backorder_policy: BackorderPolicy | None,
        putaway_mode: ReflexMode | None,
        putaway_flow_id: str | None,
        auto_validate: bool | None,
    ) -> StockOperationType:
        op = await StockOperationType.by_id(company_id, operation_type_id)
        if op is None:
            raise _not_found("Operation type not found", "operation_type_not_found")
        op.name = name if name is not None else op.name
        op.reservation_policy = (
            reservation_policy if reservation_policy is not None else op.reservation_policy
        )
        op.backorder_policy = (
            backorder_policy if backorder_policy is not None else op.backorder_policy
        )
        op.putaway_mode = putaway_mode if putaway_mode is not None else op.putaway_mode
        if putaway_flow_id is not None or putaway_mode == ReflexMode.RULE:
            op.putaway_flow_id = putaway_flow_id
        op.auto_validate = auto_validate if auto_validate is not None else op.auto_validate
        if op.putaway_mode == ReflexMode.INLINE and op.putaway_flow_id is None:
            raise _conflict(
                "Inline putaway requires putaway_flow_id", "putaway_flow_missing"
            )
        op.updated_at = utcnow()
        _ = await op.save()
        return op

    # --- Transfers / move lines / quants (чтение) ---

    async def list_transfers(
        self,
        *,
        company_id: str,
        warehouse_id: str | None,
        state: StockTransferState | None,
        limit: int,
        offset: int,
    ) -> OffsetPage[StockTransfer]:
        rows = await StockTransfer.list_for_company(
            company_id, warehouse_id=warehouse_id, state=state, limit=limit, offset=offset
        )
        total = await StockTransfer.count_for_company(
            company_id, warehouse_id=warehouse_id, state=state
        )
        return OffsetPage(items=rows, total=total, limit=limit, offset=offset)

    async def get_transfer(
        self, *, company_id: str, transfer_id: str
    ) -> tuple[StockTransfer, list[StockMove], list[StockMoveLine]]:
        transfer = await StockTransfer.by_id(company_id, transfer_id)
        if transfer is None:
            raise _not_found("Transfer not found", "transfer_not_found")
        moves = await StockMove.list_for_transfer(company_id, transfer_id)
        lines = await StockMoveLine.list_for_moves(
            company_id, [m.move_id for m in moves]
        )
        return transfer, moves, lines

    async def update_move_line(
        self,
        *,
        company_id: str,
        move_line_id: str,
        done_quantity: Decimal | None,
        picked: bool | None,
        lot_id: str | None,
        location_dest_id: str | None,
    ) -> StockMoveLine:
        return await StockMoveLine.update_execution(
            company_id=company_id,
            move_line_id=move_line_id,
            done_quantity=done_quantity,
            picked=picked,
            lot_id=lot_id,
            location_dest_id=location_dest_id,
        )

    async def list_quants(
        self,
        *,
        company_id: str,
        location_id: str | None,
        product_id: str | None,
        limit: int,
        offset: int,
    ) -> OffsetPage[StockQuant]:
        rows = await StockQuant.list_for_company(
            company_id, location_id=location_id, product_id=product_id,
            limit=limit, offset=offset,
        )
        total = await StockQuant.count_for_company(
            company_id, location_id=location_id, product_id=product_id
        )
        return OffsetPage(items=rows, total=total, limit=limit, offset=offset)

    # --- Lots / packages ---

    async def create_lot(
        self,
        *,
        company_id: str,
        product_id: str,
        name: str,
        barcode: str | None,
        expiration_at: datetime | None,
    ) -> StockLot:
        product = await StockProduct.by_id(company_id, product_id)
        if product is None:
            raise _not_found("Product not found", "product_not_found")
        try:
            lot = await StockLot.objects.create(
                instance=StockLot(
                    lot_id=new_id("lot"),
                    company_id=company_id,
                    product_id=product_id,
                    name=name,
                    barcode=barcode,
                    expiration_at=expiration_at,
                    created_at=utcnow(),
                )
            )
        except UniqueViolationError as exc:
            raise _conflict("Lot name already exists", "lot_conflict") from exc
        if barcode is not None:
            _ = await self._barcode.register(
                company_id=company_id,
                barcode=barcode,
                entity_type=StockBarcodeEntityType.LOT,
                entity_id=lot.lot_id,
            )
        return lot

    async def list_lots(
        self, *, company_id: str, product_id: str | None
    ) -> list[StockLot]:
        query = StockLot.objects.filter(company_id=company_id)
        if product_id is not None:
            query = query.filter(product_id=product_id)
        return await query.order_by("name").all()

    async def create_package(
        self,
        *,
        company_id: str,
        package_type_id: str | None,
        parent_package_id: str | None,
        location_id: str | None,
        barcode: str | None,
    ) -> StockPackage:
        if package_type_id is not None:
            exists = await StockPackageType.objects.filter(
                company_id=company_id, package_type_id=package_type_id
            ).exists()
            if not exists:
                raise _not_found("Package type not found", "package_type_not_found")
        package = await StockPackage.objects.create(
            instance=StockPackage(
                package_id=new_id("pkg"),
                company_id=company_id,
                package_type_id=package_type_id,
                parent_package_id=parent_package_id,
                location_id=location_id,
                barcode=barcode,
                created_at=utcnow(),
            )
        )
        if barcode is not None:
            _ = await self._barcode.register(
                company_id=company_id,
                barcode=barcode,
                entity_type=StockBarcodeEntityType.PACKAGE,
                entity_id=package.package_id,
            )
        return package

    async def list_packages(self, *, company_id: str) -> list[StockPackage]:
        return await StockPackage.objects.filter(company_id=company_id).order_by(
            "created_at"
        ).all()
