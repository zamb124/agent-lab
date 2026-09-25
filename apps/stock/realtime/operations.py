"""Операции склада: один `op_*` на verb, boundary-адаптер к сервисам.

Проверки: чтение — `stock_warehouse#can_view` (либо `company#viewer` для
справочников), запись — `can_edit` склада либо `company#editor`. Internal
`stock/company/init` сверяет `company_id` payload с активной компанией
internal-контекста (idle_worker → `build_internal_context_headers`).
"""

from __future__ import annotations

from apps.stock.di import Di
from apps.stock.events import (
    StockValuationChangedPayload,
    publish_stock_valuation_changed,
)
from apps.stock.models import (
    StockDecision,
    StockLocation,
    StockLot,
    StockMove,
    StockMoveLine,
    StockOperationType,
    StockPackage,
    StockProductTemplate,
    StockQuant,
    StockTransfer,
    StockValueLayer,
    StockWarehouse,
    UnitOfMeasure,
)
from apps.stock.models.api import (
    StockBarcodeResolvePayload,
    StockBarcodeResolveResponse,
    StockCompanyInitResponse,
    StockItemsResponse,
    StockLocationCreatePayload,
    StockLocationIdPayload,
    StockLocationsListPayload,
    StockLocationUpdatePayload,
    StockLotCreatePayload,
    StockLotsListPayload,
    StockMoveApplyDecisionPayload,
    StockMoveLineUpdatePayload,
    StockOperationTypesListPayload,
    StockOperationTypeUpdatePayload,
    StockPackageCreatePayload,
    StockPagePayload,
    StockProductCreatePayload,
    StockProductDetail,
    StockProductIdPayload,
    StockProductUpdatePayload,
    StockProductValueResponse,
    StockQuantInventoryApplyPayload,
    StockQuantInventorySetPayload,
    StockQuantsListPayload,
    StockTransferCreatePayload,
    StockTransferDetail,
    StockTransferIdPayload,
    StockTransferReturnPayload,
    StockTransfersListPayload,
    StockValuationCorrectionPayload,
    StockValuationLayersPayload,
    StockValuationProductValuePayload,
    StockValuationRevaluePayload,
    StockWarehouseCreatePayload,
    StockWarehouseIdPayload,
    StockWarehousePulsePayload,
    StockWarehousePulseResponse,
    StockWarehouseUpdatePayload,
)
from core.authz.errors import AuthzDenied
from core.authz.models import AuthzObject
from core.errors.boundary import PlatformNotFoundError
from core.models import StrictBaseModel
from core.models.identity_models import User
from core.pagination import OffsetPage
from core.request_scope import CompanyScope, require_company, require_company_viewer
from core.websocket import EmptyPayload, raise_forbidden


async def _company_editor(di: Di) -> CompanyScope:
    """Активная компания + `company#editor` (каталожная запись склада)."""
    scope = require_company()
    try:
        await di.authz_service.require_can_edit(
            AuthzObject.company(scope.company_id), user_id=scope.user_id
        )
    except AuthzDenied as exc:
        raise_forbidden(exc)
    return scope


async def _warehouse_viewer(di: Di, scope: CompanyScope, warehouse_id: str) -> None:
    await di.stock_access_service.require_view(
        company_id=scope.company_id,
        warehouse_id=warehouse_id,
        user_id=scope.user_id,
    )


async def _warehouse_editor(di: Di, scope: CompanyScope, warehouse_id: str) -> None:
    await di.stock_access_service.require_edit(
        company_id=scope.company_id,
        warehouse_id=warehouse_id,
        user_id=scope.user_id,
    )


async def _warehouse_of_transfer(
    scope: CompanyScope, transfer_id: str
) -> str:
    transfer = await StockTransfer.by_id(scope.company_id, transfer_id)
    if transfer is None:
        raise PlatformNotFoundError(
            "Transfer not found", error_code="transfer_not_found"
        )
    return transfer.warehouse_id


# --- Продукты ---


async def op_products_list(
    payload: StockPagePayload, *, user: User, di: Di
) -> OffsetPage[StockProductDetail]:
    _ = user
    scope = await require_company_viewer(di.authz_service)
    page = await di.warehouse_service.list_products(
        company_id=scope.company_id, limit=payload.limit, offset=payload.offset
    )
    items: list[StockProductDetail] = []
    for product in page.items:
        template = await StockProductTemplate.by_id(
            scope.company_id, product.template_id
        )
        if template is not None:
            items.append(StockProductDetail(product=product, template=template))
    return OffsetPage(
        items=items, total=page.total, limit=page.limit, offset=page.offset
    )


async def op_products_item(
    payload: StockProductIdPayload, *, user: User, di: Di
) -> StockProductDetail:
    _ = user
    scope = await require_company_viewer(di.authz_service)
    product, template = await di.warehouse_service.get_product(
        company_id=scope.company_id, product_id=payload.product_id
    )
    return StockProductDetail(product=product, template=template)


async def op_products_create(
    payload: StockProductCreatePayload, *, user: User, di: Di
) -> StockProductDetail:
    _ = user
    scope = await _company_editor(di)
    product = await di.warehouse_service.create_product(
        company_id=scope.company_id,
        name=payload.name,
        sku=payload.sku,
        uom_id=payload.uom_id,
        valuation_method=payload.valuation_method,
        standard_price=payload.standard_price,
        tracking=payload.tracking,
        is_storable=payload.is_storable,
        category=payload.category,
        barcode=payload.barcode,
    )
    _, template = await di.warehouse_service.get_product(
        company_id=scope.company_id, product_id=product.product_id
    )
    return StockProductDetail(product=product, template=template)


async def op_products_update(
    payload: StockProductUpdatePayload, *, user: User, di: Di
) -> StockProductDetail:
    _ = user
    scope = await _company_editor(di)
    product = await di.warehouse_service.update_product(
        company_id=scope.company_id,
        product_id=payload.product_id,
        name=payload.name,
        sku=payload.sku,
        barcode=payload.barcode,
        is_active=payload.is_active,
        valuation_method=payload.valuation_method,
        standard_price=payload.standard_price,
        tracking=payload.tracking,
    )
    _, template = await di.warehouse_service.get_product(
        company_id=scope.company_id, product_id=product.product_id
    )
    return StockProductDetail(product=product, template=template)


# --- Локации ---


async def op_locations_list(
    payload: StockLocationsListPayload, *, user: User, di: Di
) -> StockItemsResponse[StockLocation]:
    _ = user
    scope = await require_company_viewer(di.authz_service)
    return StockItemsResponse(
        items=await di.warehouse_service.list_locations(
            company_id=scope.company_id, warehouse_id=payload.warehouse_id
        )
    )


async def op_locations_item(
    payload: StockLocationIdPayload, *, user: User, di: Di
) -> StockLocation:
    _ = user
    scope = await require_company_viewer(di.authz_service)
    return await di.warehouse_service.get_location(
        company_id=scope.company_id, location_id=payload.location_id
    )


async def op_locations_create(
    payload: StockLocationCreatePayload, *, user: User, di: Di
) -> StockLocation:
    _ = user
    scope = require_company()
    await _warehouse_editor(di, scope, payload.warehouse_id)
    return await di.warehouse_service.create_location(
        company_id=scope.company_id,
        warehouse_id=payload.warehouse_id,
        parent_id=payload.parent_id,
        name=payload.name,
        usage=payload.usage,
        removal_method=payload.removal_method,
        barcode=payload.barcode,
    )


async def op_locations_update(
    payload: StockLocationUpdatePayload, *, user: User, di: Di
) -> StockLocation:
    _ = user
    scope = require_company()
    location = await di.warehouse_service.get_location(
        company_id=scope.company_id, location_id=payload.location_id
    )
    if location.warehouse_id is not None:
        await _warehouse_editor(di, scope, location.warehouse_id)
    else:
        _ = await _company_editor(di)
    return await di.warehouse_service.update_location(
        company_id=scope.company_id,
        location_id=payload.location_id,
        name=payload.name,
        removal_method=payload.removal_method,
        barcode=payload.barcode,
        is_active=payload.is_active,
    )


# --- Склады ---


async def op_warehouses_list(
    payload: StockPagePayload, *, user: User, di: Di
) -> OffsetPage[StockWarehouse]:
    _ = user
    scope = await require_company_viewer(di.authz_service)
    return await di.warehouse_service.list_warehouses(
        company_id=scope.company_id, limit=payload.limit, offset=payload.offset
    )


async def op_warehouses_item(
    payload: StockWarehouseIdPayload, *, user: User, di: Di
) -> StockWarehouse:
    _ = user
    scope = require_company()
    await _warehouse_viewer(di, scope, payload.warehouse_id)
    return await di.warehouse_service.get_warehouse(
        company_id=scope.company_id, warehouse_id=payload.warehouse_id
    )


async def op_warehouses_create(
    payload: StockWarehouseCreatePayload, *, user: User, di: Di
) -> StockWarehouse:
    _ = user
    scope = await _company_editor(di)
    return await di.warehouse_service.create_warehouse(
        company_id=scope.company_id,
        code=payload.code,
        name=payload.name,
        owner_user_id=scope.user_id,
    )


async def op_warehouses_update(
    payload: StockWarehouseUpdatePayload, *, user: User, di: Di
) -> StockWarehouse:
    _ = user
    scope = require_company()
    await _warehouse_editor(di, scope, payload.warehouse_id)
    return await di.warehouse_service.update_warehouse(
        company_id=scope.company_id,
        warehouse_id=payload.warehouse_id,
        name=payload.name,
        code=payload.code,
    )


# --- Типы операций ---


async def op_operation_types_list(
    payload: StockOperationTypesListPayload, *, user: User, di: Di
) -> StockItemsResponse[StockOperationType]:
    _ = user
    scope = require_company()
    await _warehouse_viewer(di, scope, payload.warehouse_id)
    return StockItemsResponse(
        items=await di.warehouse_service.list_operation_types(
            company_id=scope.company_id, warehouse_id=payload.warehouse_id
        )
    )


async def op_operation_types_update(
    payload: StockOperationTypeUpdatePayload, *, user: User, di: Di
) -> StockOperationType:
    _ = user
    scope = require_company()
    op_type = await StockOperationType.by_id(
        scope.company_id, payload.operation_type_id
    )
    if op_type is None:
        raise PlatformNotFoundError(
            "Operation type not found", error_code="operation_type_not_found"
        )
    await _warehouse_editor(di, scope, op_type.warehouse_id)
    return await di.warehouse_service.update_operation_type(
        company_id=scope.company_id,
        operation_type_id=payload.operation_type_id,
        name=payload.name,
        reservation_policy=payload.reservation_policy,
        backorder_policy=payload.backorder_policy,
        putaway_mode=payload.putaway_mode,
        putaway_flow_id=payload.putaway_flow_id,
        auto_validate=payload.auto_validate,
    )


# --- Transfers ---


async def op_transfers_list(
    payload: StockTransfersListPayload, *, user: User, di: Di
) -> OffsetPage[StockTransfer]:
    _ = user
    scope = require_company()
    if payload.warehouse_id is not None:
        await _warehouse_viewer(di, scope, payload.warehouse_id)
    else:
        _ = await require_company_viewer(di.authz_service)
    return await di.warehouse_service.list_transfers(
        company_id=scope.company_id,
        warehouse_id=payload.warehouse_id,
        state=payload.state,
        limit=payload.limit,
        offset=payload.offset,
    )


async def op_transfers_item(
    payload: StockTransferIdPayload, *, user: User, di: Di
) -> StockTransferDetail:
    _ = user
    scope = require_company()
    warehouse_id = await _warehouse_of_transfer(scope, payload.transfer_id)
    await _warehouse_viewer(di, scope, warehouse_id)
    transfer, moves, lines = await di.warehouse_service.get_transfer(
        company_id=scope.company_id, transfer_id=payload.transfer_id
    )
    return StockTransferDetail(transfer=transfer, moves=moves, lines=lines)


async def op_transfers_create(
    payload: StockTransferCreatePayload, *, user: User, di: Di
) -> StockTransfer:
    _ = user
    scope = require_company()
    await _warehouse_editor(di, scope, payload.warehouse_id)
    return await di.move_engine.create_transfer(
        company_id=scope.company_id,
        warehouse_id=payload.warehouse_id,
        operation_type_id=payload.operation_type_id,
        partner_entity_id=payload.partner_entity_id,
        owner_entity_id=payload.owner_entity_id,
        scheduled_at=payload.scheduled_at,
        origin_document_type=payload.origin_document_type,
        origin_document_id=payload.origin_document_id,
        barcode=payload.barcode,
        moves=payload.moves,
    )


async def op_transfers_confirm(
    payload: StockTransferIdPayload, *, user: User, di: Di
) -> StockTransfer:
    _ = user
    scope = require_company()
    warehouse_id = await _warehouse_of_transfer(scope, payload.transfer_id)
    await _warehouse_editor(di, scope, warehouse_id)
    return await di.move_engine.confirm_transfer(
        company_id=scope.company_id, transfer_id=payload.transfer_id
    )


async def op_transfers_assign(
    payload: StockTransferIdPayload, *, user: User, di: Di
) -> StockTransfer:
    _ = user
    scope = require_company()
    warehouse_id = await _warehouse_of_transfer(scope, payload.transfer_id)
    await _warehouse_editor(di, scope, warehouse_id)
    return await di.move_engine.assign_transfer(
        company_id=scope.company_id, transfer_id=payload.transfer_id
    )


async def op_transfers_validate(
    payload: StockTransferIdPayload, *, user: User, di: Di
) -> StockTransfer:
    _ = user
    scope = require_company()
    warehouse_id = await _warehouse_of_transfer(scope, payload.transfer_id)
    await _warehouse_editor(di, scope, warehouse_id)
    return await di.move_engine.validate_transfer(
        company_id=scope.company_id, transfer_id=payload.transfer_id
    )


async def op_transfers_cancel(
    payload: StockTransferIdPayload, *, user: User, di: Di
) -> StockTransfer:
    _ = user
    scope = require_company()
    warehouse_id = await _warehouse_of_transfer(scope, payload.transfer_id)
    await _warehouse_editor(di, scope, warehouse_id)
    return await di.move_engine.cancel_transfer(
        company_id=scope.company_id, transfer_id=payload.transfer_id
    )


async def op_transfers_return(
    payload: StockTransferReturnPayload, *, user: User, di: Di
) -> StockTransfer:
    _ = user
    scope = require_company()
    warehouse_id = await _warehouse_of_transfer(scope, payload.transfer_id)
    await _warehouse_editor(di, scope, warehouse_id)
    return await di.move_engine.return_transfer(
        company_id=scope.company_id,
        transfer_id=payload.transfer_id,
        move_quantities=payload.move_quantities,
    )


# --- Move lines / решения ---


async def op_move_lines_update(
    payload: StockMoveLineUpdatePayload, *, user: User, di: Di
) -> StockMoveLine:
    _ = user
    scope = require_company()
    line = await StockMoveLine.by_id(scope.company_id, payload.move_line_id)
    if line is None:
        raise PlatformNotFoundError(
            "Move line not found", error_code="move_line_not_found"
        )
    move = await StockMove.by_id(scope.company_id, line.move_id)
    if move is not None and move.transfer_id is not None:
        warehouse_id = await _warehouse_of_transfer(scope, move.transfer_id)
        await _warehouse_editor(di, scope, warehouse_id)
    else:
        _ = await _company_editor(di)
    return await di.warehouse_service.update_move_line(
        company_id=scope.company_id,
        move_line_id=payload.move_line_id,
        done_quantity=payload.done_quantity,
        picked=payload.picked,
        lot_id=payload.lot_id,
        location_dest_id=payload.location_dest_id,
    )


async def op_move_apply_decision(
    payload: StockMoveApplyDecisionPayload, *, user: User, di: Di
) -> StockDecision:
    _ = user
    scope = require_company()
    move = await StockMove.by_id(scope.company_id, payload.move_id)
    if move is not None and move.transfer_id is not None:
        warehouse_id = await _warehouse_of_transfer(scope, move.transfer_id)
        await _warehouse_editor(di, scope, warehouse_id)
    else:
        _ = await _company_editor(di)
    return await di.putaway_service.apply_decision(
        company_id=scope.company_id,
        move_id=payload.move_id,
        location_id=payload.location_id,
    )


# --- Остатки / инвентаризация ---


async def op_quants_list(
    payload: StockQuantsListPayload, *, user: User, di: Di
) -> OffsetPage[StockQuant]:
    _ = user
    scope = await require_company_viewer(di.authz_service)
    return await di.warehouse_service.list_quants(
        company_id=scope.company_id,
        location_id=payload.location_id,
        product_id=payload.product_id,
        limit=payload.limit,
        offset=payload.offset,
    )


async def op_quants_inventory_set(
    payload: StockQuantInventorySetPayload, *, user: User, di: Di
) -> StockQuant:
    _ = user
    scope = await _company_editor(di)
    return await di.move_engine.inventory_set(
        company_id=scope.company_id,
        quant_id=payload.quant_id,
        inventory_quantity=payload.inventory_quantity,
    )


async def op_quants_inventory_apply(
    payload: StockQuantInventoryApplyPayload, *, user: User, di: Di
) -> StockMove:
    _ = user
    scope = await _company_editor(di)
    return await di.move_engine.inventory_apply(
        company_id=scope.company_id, quant_id=payload.quant_id
    )


# --- Оценка ---


async def op_valuation_layers_list(
    payload: StockValuationLayersPayload, *, user: User, di: Di
) -> OffsetPage[StockValueLayer]:
    _ = user
    scope = require_company()
    if payload.warehouse_id is not None:
        await _warehouse_viewer(di, scope, payload.warehouse_id)
    else:
        _ = await require_company_viewer(di.authz_service)
    return await di.valuation_service.list_layers(
        company_id=scope.company_id,
        product_id=payload.product_id,
        warehouse_id=payload.warehouse_id,
        limit=payload.limit,
        offset=payload.offset,
    )


async def op_valuation_product_value(
    payload: StockValuationProductValuePayload, *, user: User, di: Di
) -> StockProductValueResponse:
    _ = user
    scope = require_company()
    if payload.warehouse_id is not None:
        await _warehouse_viewer(di, scope, payload.warehouse_id)
    else:
        _ = await require_company_viewer(di.authz_service)
    value = await di.valuation_service.product_value(
        company_id=scope.company_id,
        product_id=payload.product_id,
        warehouse_id=payload.warehouse_id,
    )
    return StockProductValueResponse(
        product_id=value.product_id,
        quantity=value.quantity,
        value=value.value,
        avg_cost=value.avg_cost,
        warehouse_id=value.warehouse_id,
    )


async def op_valuation_revalue(
    payload: StockValuationRevaluePayload, *, user: User, di: Di
) -> StockValueLayer:
    _ = user
    scope = await _company_editor(di)
    layer = await di.valuation_service.revalue(
        company_id=scope.company_id,
        product_id=payload.product_id,
        value_delta=payload.value_delta,
        new_price=payload.new_price,
        description=payload.description,
    )
    await publish_stock_valuation_changed(
        scope.company_id,
        StockValuationChangedPayload(
            company_id=scope.company_id,
            product_id=layer.product_id,
            layer_id=layer.layer_id,
            entry_no=layer.entry_no,
            entry_kind=layer.entry_kind,
            quantity=layer.quantity,
            value=layer.value,
            qty_after=layer.qty_after,
            value_after=layer.value_after,
            origin_layer_id=layer.origin_layer_id,
        ),
    )
    return layer


async def op_valuation_correction(
    payload: StockValuationCorrectionPayload, *, user: User, di: Di
) -> StockValueLayer:
    _ = user
    scope = await _company_editor(di)
    layer = await di.valuation_service.correction(
        company_id=scope.company_id,
        origin_layer_id=payload.origin_layer_id,
        quantity_delta=payload.quantity_delta,
        value_delta=payload.value_delta,
        description=payload.description,
    )
    await publish_stock_valuation_changed(
        scope.company_id,
        StockValuationChangedPayload(
            company_id=scope.company_id,
            product_id=layer.product_id,
            layer_id=layer.layer_id,
            entry_no=layer.entry_no,
            entry_kind=layer.entry_kind,
            quantity=layer.quantity,
            value=layer.value,
            qty_after=layer.qty_after,
            value_after=layer.value_after,
            origin_layer_id=layer.origin_layer_id,
        ),
    )
    return layer


# --- Lots / packages ---


async def op_lots_list(
    payload: StockLotsListPayload, *, user: User, di: Di
) -> StockItemsResponse[StockLot]:
    _ = user
    scope = await require_company_viewer(di.authz_service)
    return StockItemsResponse(
        items=await di.warehouse_service.list_lots(
            company_id=scope.company_id, product_id=payload.product_id
        )
    )


async def op_lots_create(
    payload: StockLotCreatePayload, *, user: User, di: Di
) -> StockLot:
    _ = user
    scope = await _company_editor(di)
    return await di.warehouse_service.create_lot(
        company_id=scope.company_id,
        product_id=payload.product_id,
        name=payload.name,
        barcode=payload.barcode,
        expiration_at=payload.expiration_at,
    )


async def op_packages_list(
    payload: EmptyPayload, *, user: User, di: Di
) -> StockItemsResponse[StockPackage]:
    _ = user
    _ = payload
    scope = await require_company_viewer(di.authz_service)
    return StockItemsResponse(
        items=await di.warehouse_service.list_packages(company_id=scope.company_id)
    )


async def op_packages_create(
    payload: StockPackageCreatePayload, *, user: User, di: Di
) -> StockPackage:
    _ = user
    scope = await _company_editor(di)
    return await di.warehouse_service.create_package(
        company_id=scope.company_id,
        package_type_id=payload.package_type_id,
        parent_package_id=payload.parent_package_id,
        location_id=payload.location_id,
        barcode=payload.barcode,
    )


# --- ЕИ ---


async def op_uoms_list(
    payload: EmptyPayload, *, user: User, di: Di
) -> StockItemsResponse[UnitOfMeasure]:
    _ = user
    _ = payload
    scope = await require_company_viewer(di.authz_service)
    return StockItemsResponse(
        items=await di.warehouse_service.list_uoms(company_id=scope.company_id)
    )


# --- Пульс / barcode ---


async def op_warehouse_pulse(
    payload: StockWarehousePulsePayload, *, user: User, di: Di
) -> StockWarehousePulseResponse:
    _ = user
    scope = require_company()
    await _warehouse_viewer(di, scope, payload.warehouse_id)
    return await di.pulse_service.warehouse_pulse(
        company_id=scope.company_id, warehouse_id=payload.warehouse_id
    )


async def op_barcode_resolve(
    payload: StockBarcodeResolvePayload, *, user: User, di: Di
) -> StockBarcodeResolveResponse:
    _ = user
    scope = await require_company_viewer(di.authz_service)
    result = await di.barcode_service.resolve(
        company_id=scope.company_id, barcode=payload.barcode
    )
    return StockBarcodeResolveResponse(
        entity_type=result.entity_type, entity_id=result.entity_id
    )


# --- Internal company init ---


class StockCompanyInitPayload(StrictBaseModel):
    company_id: str


async def op_stock_company_init(
    payload: StockCompanyInitPayload, *, user: User, di: Di
) -> StockCompanyInitResponse:
    """Виртуальные локации + базовые ЕИ компании.

    Зовётся idle-воркером `company_init_new_company` с internal context
    компании (`build_internal_context_headers`); рассинхрон `company_id`
    и активной компании — `forbidden`.
    """
    _ = user
    scope = require_company()
    if payload.company_id != scope.company_id:
        raise_forbidden(
            ValueError(
                f"company_id {payload.company_id!r} does not match active company {scope.company_id!r}"
            )
        )
    locations = await di.company_init_service.init_company_stock(
        company_id=payload.company_id
    )
    return StockCompanyInitResponse(
        company_id=payload.company_id,
        location_ids=[row.location_id for row in locations],
    )
