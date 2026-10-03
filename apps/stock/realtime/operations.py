"""Операции склада: один `op_*` на verb, boundary-адаптер к сервисам.

Проверки: чтение — `stock_warehouse#can_view` (либо `company#viewer` для
справочников), запись — `can_edit` склада либо `company#editor`. Internal
`stock/company/init` сверяет `company_id` payload с активной компанией
internal-контекста (idle_worker → `build_internal_context_headers`).
"""

from __future__ import annotations

from apps.stock.di import Di
from apps.stock.models import (
    StockContainerType,
    StockDecision,
    StockLocation,
    StockLot,
    StockMove,
    StockMoveLine,
    StockMoveLineClaimResult,
    StockMoveLineExceptionResult,
    StockOperationType,
    StockProduct,
    StockPutawayRule,
    StockQuant,
    StockReorderRule,
    StockResource,
    StockResourceType,
    StockRoute,
    StockStorageType,
    StockTransfer,
    StockValueLayer,
    StockWarehouse,
    StockWave,
    UnitOfMeasure,
)
from apps.stock.models.api import (
    StockBarcodeResolvePayload,
    StockBarcodeResolveResponse,
    StockCompanyInitResponse,
    StockContainerContentsResponse,
    StockContainerCreatePayload,
    StockContainerIdPayload,
    StockContainerMovePayload,
    StockContainersListPayload,
    StockContainerTypeCreatePayload,
    StockContainerTypesListPayload,
    StockItemsResponse,
    StockLocationCreatePayload,
    StockLocationIdPayload,
    StockLocationsListPayload,
    StockLocationUpdatePayload,
    StockLotCreatePayload,
    StockLotsListPayload,
    StockMoveApplyDecisionPayload,
    StockMoveLineExceptionPayload,
    StockMoveLineNextPayload,
    StockMoveLineNextResponse,
    StockMoveLinesAssignPayload,
    StockMoveLinesClaimPayload,
    StockMoveLinesQueuePayload,
    StockMoveLinesReleasePayload,
    StockMoveLineUpdatePayload,
    StockOperationTypesListPayload,
    StockOperationTypeUpdatePayload,
    StockPackagingCreatePayload,
    StockPackagingIdPayload,
    StockPackagingsListPayload,
    StockPackagingView,
    StockPagePayload,
    StockProductCreatePayload,
    StockProductIdPayload,
    StockProductUpdatePayload,
    StockProductValueResponse,
    StockPutawayRuleCreatePayload,
    StockPutawayRuleDeletePayload,
    StockPutawayRulesListPayload,
    StockPutawayRuleUpdatePayload,
    StockQuantInventoryApplyPayload,
    StockQuantInventorySetPayload,
    StockQuantsListPayload,
    StockReorderRuleCreatePayload,
    StockReorderRulesListPayload,
    StockReorderRuleUpdatePayload,
    StockResourceCreatePayload,
    StockResourceLoginPayload,
    StockResourceLogoutPayload,
    StockResourcesListPayload,
    StockResourceTypeCreatePayload,
    StockResourceTypesListPayload,
    StockRouteCreatePayload,
    StockRouteIdPayload,
    StockRoutesListPayload,
    StockScanCommitPayload,
    StockScanCountCommitPayload,
    StockScanCountCommitResponse,
    StockScanExpected,
    StockScanQuantityPayload,
    StockScanStepPayload,
    StockScanStepResponse,
    StockStorageTypeCreatePayload,
    StockStorageTypesListPayload,
    StockTransferCreatePayload,
    StockTransferDetail,
    StockTransferIdPayload,
    StockTransferReturnPayload,
    StockTransfersListPayload,
    StockTransferValidatePayload,
    StockValuationCorrectionPayload,
    StockValuationLayersPayload,
    StockValuationProductValuePayload,
    StockValuationRevaluePayload,
    StockWarehouseCreatePayload,
    StockWarehouseIdPayload,
    StockWarehousePulsePayload,
    StockWarehousePulseResponse,
    StockWarehouseUpdatePayload,
    StockWaveCreatePayload,
    StockWaveIdPayload,
    StockWavesListPayload,
)
from apps.stock.models.resource import StockResourceLogoutResult
from core.authz.errors import AuthzDenied
from core.authz.models import AuthzObject
from core.context.command import current_command_event_id
from core.errors.boundary import PlatformNotFoundError
from core.models import StrictBaseModel
from core.models.identity_models import User
from core.pagination import OffsetPage
from core.request_scope import (
    CompanyScope,
    command_idempotency_key,
    require_company,
    require_company_viewer,
)
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
) -> OffsetPage[StockProduct]:
    _ = user
    scope = await require_company_viewer(di.authz_service)
    return await di.catalog_service.list_products(
        company_id=scope.company_id, limit=payload.limit, offset=payload.offset
    )


async def op_products_item(
    payload: StockProductIdPayload, *, user: User, di: Di
) -> StockProduct:
    _ = user
    scope = await require_company_viewer(di.authz_service)
    return await di.catalog_service.get_product(
        company_id=scope.company_id, product_id=payload.product_id
    )


async def op_products_create(
    payload: StockProductCreatePayload, *, user: User, di: Di
) -> StockProduct:
    _ = user
    scope = await _company_editor(di)
    return await di.catalog_service.create_product(
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
        weight=payload.weight,
        volume=payload.volume,
        use_expiration=payload.use_expiration,
        expiration_days=payload.expiration_days,
        best_before_days=payload.best_before_days,
        removal_days=payload.removal_days,
        alert_days=payload.alert_days,
        removal_strategy=payload.removal_strategy,
    )


async def op_products_update(
    payload: StockProductUpdatePayload, *, user: User, di: Di
) -> StockProduct:
    _ = user
    scope = await _company_editor(di)
    return await di.catalog_service.update_product(
        company_id=scope.company_id,
        product_id=payload.product_id,
        name=payload.name,
        sku=payload.sku,
        barcode=payload.barcode,
        is_active=payload.is_active,
        valuation_method=payload.valuation_method,
        standard_price=payload.standard_price,
        tracking=payload.tracking,
        category=payload.category,
        weight=payload.weight,
        volume=payload.volume,
        use_expiration=payload.use_expiration,
        expiration_days=payload.expiration_days,
        best_before_days=payload.best_before_days,
        removal_days=payload.removal_days,
        alert_days=payload.alert_days,
        removal_strategy=payload.removal_strategy,
    )


# --- Локации ---


async def op_locations_list(
    payload: StockLocationsListPayload, *, user: User, di: Di
) -> StockItemsResponse[StockLocation]:
    _ = user
    scope = await require_company_viewer(di.authz_service)
    return StockItemsResponse(
        items=await di.topology_service.list_locations(
            company_id=scope.company_id, warehouse_id=payload.warehouse_id
        )
    )


async def op_locations_item(
    payload: StockLocationIdPayload, *, user: User, di: Di
) -> StockLocation:
    _ = user
    scope = await require_company_viewer(di.authz_service)
    return await di.topology_service.get_location(
        company_id=scope.company_id, location_id=payload.location_id
    )


async def op_locations_create(
    payload: StockLocationCreatePayload, *, user: User, di: Di
) -> StockLocation:
    _ = user
    scope = require_company()
    await _warehouse_editor(di, scope, payload.warehouse_id)
    return await di.topology_service.create_location(
        company_id=scope.company_id,
        warehouse_id=payload.warehouse_id,
        parent_id=payload.parent_id,
        name=payload.name,
        usage=payload.usage,
        barcode=payload.barcode,
        allow_negative=payload.allow_negative,
        storage_type_id=payload.storage_type_id,
        container_type_id=payload.container_type_id,
        pick_sequence=payload.pick_sequence,
        level=payload.level,
    )


async def op_locations_update(
    payload: StockLocationUpdatePayload, *, user: User, di: Di
) -> StockLocation:
    _ = user
    scope = require_company()
    location = await di.topology_service.get_location(
        company_id=scope.company_id, location_id=payload.location_id
    )
    if location.warehouse_id is not None:
        await _warehouse_editor(di, scope, location.warehouse_id)
    else:
        _ = await _company_editor(di)
    return await di.topology_service.update_location(
        company_id=scope.company_id,
        location_id=payload.location_id,
        name=payload.name,
        barcode=payload.barcode,
        is_active=payload.is_active,
        allow_negative=payload.allow_negative,
        storage_type_id=payload.storage_type_id,
        pick_sequence=payload.pick_sequence,
        putaway_blocked=payload.putaway_blocked,
        removal_blocked=payload.removal_blocked,
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
        layout_preset=payload.layout_preset,
        removal_strategy=payload.removal_strategy,
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
        priority=payload.priority,
        date_deadline=payload.date_deadline,
        idempotency_key=command_idempotency_key(payload.idempotency_key),
        actor_user_id=scope.user_id,
        command_type="stock/transfers/create_requested",
    )


async def op_transfers_confirm(
    payload: StockTransferIdPayload, *, user: User, di: Di
) -> StockTransfer:
    _ = user
    scope = require_company()
    warehouse_id = await _warehouse_of_transfer(scope, payload.transfer_id)
    await _warehouse_editor(di, scope, warehouse_id)
    return await di.move_engine.confirm_transfer(
        company_id=scope.company_id,
        transfer_id=payload.transfer_id,
        idempotency_key=command_idempotency_key(payload.idempotency_key),
        actor_user_id=scope.user_id,
        command_type="stock/transfers/confirm_requested",
    )


async def op_transfers_assign(
    payload: StockTransferIdPayload, *, user: User, di: Di
) -> StockTransfer:
    _ = user
    scope = require_company()
    warehouse_id = await _warehouse_of_transfer(scope, payload.transfer_id)
    await _warehouse_editor(di, scope, warehouse_id)
    return await di.move_engine.assign_transfer(
        company_id=scope.company_id,
        transfer_id=payload.transfer_id,
        idempotency_key=command_idempotency_key(payload.idempotency_key),
        actor_user_id=scope.user_id,
        command_type="stock/transfers/assign_requested",
    )


async def op_transfers_validate(
    payload: StockTransferValidatePayload, *, user: User, di: Di
) -> StockTransfer:
    _ = user
    scope = require_company()
    warehouse_id = await _warehouse_of_transfer(scope, payload.transfer_id)
    await _warehouse_editor(di, scope, warehouse_id)
    return await di.move_engine.validate_transfer(
        company_id=scope.company_id,
        transfer_id=payload.transfer_id,
        create_backorder=payload.create_backorder,
        idempotency_key=command_idempotency_key(payload.idempotency_key),
        actor_user_id=scope.user_id,
        command_type="stock/transfers/validate_requested",
        causation_id=current_command_event_id(),
    )


async def op_transfers_cancel(
    payload: StockTransferIdPayload, *, user: User, di: Di
) -> StockTransfer:
    _ = user
    scope = require_company()
    warehouse_id = await _warehouse_of_transfer(scope, payload.transfer_id)
    await _warehouse_editor(di, scope, warehouse_id)
    return await di.move_engine.cancel_transfer(
        company_id=scope.company_id,
        transfer_id=payload.transfer_id,
        idempotency_key=command_idempotency_key(payload.idempotency_key),
        actor_user_id=scope.user_id,
        command_type="stock/transfers/cancel_requested",
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
        idempotency_key=command_idempotency_key(payload.idempotency_key),
        actor_user_id=scope.user_id,
        command_type="stock/transfers/return_requested",
        causation_id=current_command_event_id(),
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
    return await di.task_service.update_move_line(
        company_id=scope.company_id,
        move_line_id=payload.move_line_id,
        done_quantity=payload.done_quantity,
        picked=payload.picked,
        lot_id=payload.lot_id,
        location_dest_id=payload.location_dest_id,
        idempotency_key=command_idempotency_key(payload.idempotency_key),
        actor_user_id=scope.user_id,
        command_type="stock/move_lines/update_requested",
    )


async def op_move_lines_queue(
    payload: StockMoveLinesQueuePayload, *, user: User, di: Di
) -> StockItemsResponse[StockMoveLine]:
    _ = user
    scope = require_company()
    await _warehouse_viewer(di, scope, payload.warehouse_id)
    items = await di.task_service.queue(
        company_id=scope.company_id,
        warehouse_id=payload.warehouse_id,
        assigned_user_id=payload.assigned_user_id,
        zone_location_id=payload.zone_location_id,
        limit=payload.limit,
    )
    return StockItemsResponse(items=items)


async def op_move_lines_next(
    payload: StockMoveLineNextPayload, *, user: User, di: Di
) -> StockMoveLineNextResponse:
    _ = user
    scope = require_company()
    await _warehouse_editor(di, scope, payload.warehouse_id)
    line = await di.task_service.next_line(
        company_id=scope.company_id,
        warehouse_id=payload.warehouse_id,
        user_id=scope.user_id,
        resource_id=payload.resource_id,
        zone_location_id=payload.zone_location_id,
        claim=payload.claim,
    )
    return StockMoveLineNextResponse(line=line)


async def op_move_lines_claim(
    payload: StockMoveLinesClaimPayload, *, user: User, di: Di
) -> StockMoveLineClaimResult:
    _ = user
    scope = require_company()
    await _warehouse_editor(di, scope, payload.warehouse_id)
    return await di.task_service.claim(
        company_id=scope.company_id,
        warehouse_id=payload.warehouse_id,
        move_line_ids=payload.move_line_ids,
        user_id=scope.user_id,
        resource_id=payload.resource_id,
        idempotency_key=command_idempotency_key(payload.idempotency_key),
    )


async def op_move_lines_assign(
    payload: StockMoveLinesAssignPayload, *, user: User, di: Di
) -> StockMoveLineClaimResult:
    _ = user
    scope = require_company()
    await _warehouse_editor(di, scope, payload.warehouse_id)
    return await di.task_service.assign(
        company_id=scope.company_id,
        warehouse_id=payload.warehouse_id,
        move_line_ids=payload.move_line_ids,
        assignee_user_id=payload.assignee_user_id,
        resource_id=payload.resource_id,
        actor_user_id=scope.user_id,
        idempotency_key=command_idempotency_key(payload.idempotency_key),
    )


async def op_move_lines_release(
    payload: StockMoveLinesReleasePayload, *, user: User, di: Di
) -> StockMoveLineClaimResult:
    _ = user
    scope = require_company()
    await _warehouse_editor(di, scope, payload.warehouse_id)
    return await di.task_service.release(
        company_id=scope.company_id,
        warehouse_id=payload.warehouse_id,
        move_line_ids=payload.move_line_ids,
        user_id=scope.user_id,
        actor_user_id=scope.user_id,
        idempotency_key=command_idempotency_key(payload.idempotency_key),
    )


async def op_move_lines_report_exception(
    payload: StockMoveLineExceptionPayload, *, user: User, di: Di
) -> StockMoveLineExceptionResult:
    _ = user
    scope = require_company()
    await _warehouse_editor(di, scope, payload.warehouse_id)
    return await di.task_service.report_exception(
        company_id=scope.company_id,
        warehouse_id=payload.warehouse_id,
        move_line_id=payload.move_line_id,
        shortage=payload.shortage,
        reason=payload.reason,
        actor_user_id=scope.user_id,
        idempotency_key=command_idempotency_key(payload.idempotency_key),
    )


async def op_waves_list(
    payload: StockWavesListPayload, *, user: User, di: Di
) -> StockItemsResponse[StockWave]:
    _ = user
    scope = require_company()
    await _warehouse_viewer(di, scope, payload.warehouse_id)
    items = await di.wave_service.list(
        company_id=scope.company_id,
        warehouse_id=payload.warehouse_id,
        state=payload.state,
        limit=payload.limit,
        offset=payload.offset,
    )
    return StockItemsResponse(items=items)


async def op_waves_create(
    payload: StockWaveCreatePayload, *, user: User, di: Di
) -> StockWave:
    """Сформировать волну из открытых строк — сменный наряд бригаде."""
    _ = user
    scope = require_company()
    await _warehouse_editor(di, scope, payload.warehouse_id)
    return await di.wave_service.create(
        company_id=scope.company_id,
        warehouse_id=payload.warehouse_id,
        name=payload.name,
        move_line_ids=payload.move_line_ids,
        move_ids=payload.move_ids,
        priority=payload.priority,
        user_id=payload.user_id,
        stop_transfer_ids=payload.stop_transfer_ids,
        idempotency_key=command_idempotency_key(payload.idempotency_key),
        actor_user_id=scope.user_id,
    )


async def op_waves_release(
    payload: StockWaveIdPayload, *, user: User, di: Di
) -> StockWave:
    _ = user
    scope = require_company()
    wave = await StockWave.by_id(scope.company_id, payload.wave_id)
    if wave is None:
        raise PlatformNotFoundError(
            "Wave not found", error_code="wave_not_found"
        )
    await _warehouse_editor(di, scope, wave.warehouse_id)
    return await di.wave_service.release(
        company_id=scope.company_id,
        warehouse_id=wave.warehouse_id,
        wave_id=payload.wave_id,
        idempotency_key=command_idempotency_key(payload.idempotency_key),
        actor_user_id=scope.user_id,
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
    return await di.placement_service.apply_decision(
        company_id=scope.company_id,
        move_id=payload.move_id,
        location_id=payload.location_id,
        idempotency_key=command_idempotency_key(payload.idempotency_key),
        actor_user_id=scope.user_id,
        command_type="stock/move/apply_decision_requested",
    )


# --- Остатки / инвентаризация ---


async def op_quants_list(
    payload: StockQuantsListPayload, *, user: User, di: Di
) -> OffsetPage[StockQuant]:
    _ = user
    scope = await require_company_viewer(di.authz_service)
    return await di.placement_service.list_quants(
        company_id=scope.company_id,
        location_id=payload.location_id,
        product_id=payload.product_id,
        owner_entity_id=payload.owner_entity_id,
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
        idempotency_key=command_idempotency_key(payload.idempotency_key),
        actor_user_id=scope.user_id,
        command_type="stock/quants/inventory_set_requested",
    )


async def op_quants_inventory_apply(
    payload: StockQuantInventoryApplyPayload, *, user: User, di: Di
) -> StockMove:
    _ = user
    scope = await _company_editor(di)
    return await di.move_engine.inventory_apply(
        company_id=scope.company_id,
        quant_id=payload.quant_id,
        idempotency_key=command_idempotency_key(payload.idempotency_key),
        actor_user_id=scope.user_id,
        command_type="stock/quants/inventory_apply_requested",
        causation_id=current_command_event_id(),
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
    return await di.valuation_service.revalue(
        company_id=scope.company_id,
        product_id=payload.product_id,
        value_delta=payload.value_delta,
        new_price=payload.new_price,
        description=payload.description,
        idempotency_key=command_idempotency_key(payload.idempotency_key),
        actor_user_id=scope.user_id,
        command_type="stock/valuation/revalue_requested",
        causation_id=current_command_event_id(),
    )


async def op_valuation_correction(
    payload: StockValuationCorrectionPayload, *, user: User, di: Di
) -> StockValueLayer:
    _ = user
    scope = await _company_editor(di)
    return await di.valuation_service.correction(
        company_id=scope.company_id,
        origin_layer_id=payload.origin_layer_id,
        quantity_delta=payload.quantity_delta,
        value_delta=payload.value_delta,
        description=payload.description,
        idempotency_key=command_idempotency_key(payload.idempotency_key),
        actor_user_id=scope.user_id,
        command_type="stock/valuation/correction_requested",
        causation_id=current_command_event_id(),
    )


# --- Lots / packages ---


async def op_lots_list(
    payload: StockLotsListPayload, *, user: User, di: Di
) -> StockItemsResponse[StockLot]:
    _ = user
    scope = await require_company_viewer(di.authz_service)
    return StockItemsResponse(
        items=await di.catalog_service.list_lots(
            company_id=scope.company_id, product_id=payload.product_id
        )
    )


async def op_lots_create(
    payload: StockLotCreatePayload, *, user: User, di: Di
) -> StockLot:
    _ = user
    scope = await _company_editor(di)
    return await di.catalog_service.create_lot(
        company_id=scope.company_id,
        product_id=payload.product_id,
        name=payload.name,
        barcode=payload.barcode,
        expiration_at=payload.expiration_at,
    )


# --- Топология: storage/container types, ресурсы, контейнеры, упаковки ---


async def op_storage_types_list(
    payload: StockStorageTypesListPayload, *, user: User, di: Di
) -> StockItemsResponse[StockStorageType]:
    _ = user
    scope = require_company()
    await _warehouse_viewer(di, scope, payload.warehouse_id)
    return StockItemsResponse(
        items=await di.topology_service.list_storage_types(
            company_id=scope.company_id, warehouse_id=payload.warehouse_id
        )
    )


async def op_storage_types_create(
    payload: StockStorageTypeCreatePayload, *, user: User, di: Di
) -> StockStorageType:
    _ = user
    scope = require_company()
    await _warehouse_editor(di, scope, payload.warehouse_id)
    return await di.topology_service.create_storage_type(
        company_id=scope.company_id,
        warehouse_id=payload.warehouse_id,
        name=payload.name,
        putaway_strategies=payload.putaway_strategies,
        allowed_container_type_ids=payload.allowed_container_type_ids,
        container_policy=payload.container_policy,
        max_containers=payload.max_containers,
        product_mixing=payload.product_mixing,
        allow_mixed_lots=payload.allow_mixed_lots,
        max_weight=payload.max_weight,
        max_volume=payload.max_volume,
        removal_strategy=payload.removal_strategy,
    )


async def op_container_types_list(
    payload: StockContainerTypesListPayload, *, user: User, di: Di
) -> StockItemsResponse[StockContainerType]:
    _ = user
    scope = require_company()
    await _warehouse_viewer(di, scope, payload.warehouse_id)
    return StockItemsResponse(
        items=await di.topology_service.list_container_types(
            company_id=scope.company_id, warehouse_id=payload.warehouse_id
        )
    )


# --- Маршруты ---


# --- Правила пополнения ---


async def op_reorder_rules_list(
    payload: StockReorderRulesListPayload, *, user: User, di: Di
) -> StockItemsResponse[StockReorderRule]:
    _ = user
    scope = require_company()
    if payload.warehouse_id is not None:
        await _warehouse_viewer(di, scope, payload.warehouse_id)
    else:
        _ = await require_company_viewer(di.authz_service)
    return StockItemsResponse(
        items=await di.rule_service.list_reorder_rules(
            company_id=scope.company_id, warehouse_id=payload.warehouse_id
        )
    )


async def op_reorder_rules_create(
    payload: StockReorderRuleCreatePayload, *, user: User, di: Di
) -> StockReorderRule:
    """Правило «полка не должна пустеть»: min/max + куда пополнять."""
    _ = user
    scope = require_company()
    await _warehouse_editor(di, scope, payload.warehouse_id)
    return await di.rule_service.create_reorder_rule(
        company_id=scope.company_id,
        warehouse_id=payload.warehouse_id,
        product_id=payload.product_id,
        location_id=payload.location_id,
        min_qty=payload.min_qty,
        max_qty=payload.max_qty,
        operation_type_id=payload.operation_type_id,
        route_id=payload.route_id,
    )


async def op_reorder_rules_update(
    payload: StockReorderRuleUpdatePayload, *, user: User, di: Di
) -> StockReorderRule:
    """Пауза/возобновление правила пополнения."""
    _ = user
    scope = require_company()
    rule = await StockReorderRule.by_id(scope.company_id, payload.rule_id)
    if rule is None:
        raise PlatformNotFoundError(
            "Reorder rule not found", error_code="reorder_rule_not_found"
        )
    await _warehouse_editor(di, scope, rule.warehouse_id)
    return await di.rule_service.set_reorder_rule_active(
        company_id=scope.company_id,
        rule_id=payload.rule_id,
        is_active=payload.is_active,
    )


async def op_putaway_rules_list(
    payload: StockPutawayRulesListPayload, *, user: User, di: Di
) -> StockItemsResponse[StockPutawayRule]:
    """Справочник правил размещения склада."""
    _ = user
    scope = require_company()
    await _warehouse_viewer(di, scope, payload.warehouse_id)
    rules = await di.rule_service.list_putaway_rules(
        company_id=scope.company_id, warehouse_id=payload.warehouse_id
    )
    return StockItemsResponse[StockPutawayRule](items=rules)


async def op_putaway_rules_create(
    payload: StockPutawayRuleCreatePayload, *, user: User, di: Di
) -> StockPutawayRule:
    """Правило «этот товар — в ту зону»: фильтры + sequence."""
    _ = user
    scope = require_company()
    await _warehouse_editor(di, scope, payload.warehouse_id)
    return await di.rule_service.create_putaway_rule(
        company_id=scope.company_id,
        warehouse_id=payload.warehouse_id,
        location_in_id=payload.location_in_id,
        location_out_id=payload.location_out_id,
        product_id=payload.product_id,
        category=payload.category,
        owner_entity_id=payload.owner_entity_id,
        sequence=payload.sequence,
    )


async def op_putaway_rules_update(
    payload: StockPutawayRuleUpdatePayload, *, user: User, di: Di
) -> StockPutawayRule:
    """Правка полей правила и/или пауза-возобновление."""
    _ = user
    scope = require_company()
    rule = await StockPutawayRule.by_id(scope.company_id, payload.rule_id)
    if rule is None:
        raise PlatformNotFoundError(
            "Putaway rule not found", error_code="putaway_rule_not_found"
        )
    await _warehouse_editor(di, scope, rule.warehouse_id)
    if payload.is_active is not None:
        _ = await di.rule_service.set_putaway_rule_active(
            company_id=scope.company_id,
            rule_id=payload.rule_id,
            is_active=payload.is_active,
        )
    return await di.rule_service.update_putaway_rule(
        company_id=scope.company_id,
        rule_id=payload.rule_id,
        location_in_id=payload.location_in_id,
        location_out_id=payload.location_out_id,
        product_id=payload.product_id,
        category=payload.category,
        owner_entity_id=payload.owner_entity_id,
        sequence=payload.sequence,
    )


async def op_putaway_rules_delete(
    payload: StockPutawayRuleDeletePayload, *, user: User, di: Di
) -> StockPutawayRule:
    """Удаление правила размещения."""
    _ = user
    scope = require_company()
    rule = await StockPutawayRule.by_id(scope.company_id, payload.rule_id)
    if rule is None:
        raise PlatformNotFoundError(
            "Putaway rule not found", error_code="putaway_rule_not_found"
        )
    await _warehouse_editor(di, scope, rule.warehouse_id)
    return await di.rule_service.delete_putaway_rule(
        company_id=scope.company_id, rule_id=payload.rule_id
    )


async def op_routes_list(
    payload: StockRoutesListPayload, *, user: User, di: Di
) -> StockItemsResponse[StockRoute]:
    _ = user
    scope = require_company()
    if payload.warehouse_id is not None:
        await _warehouse_viewer(di, scope, payload.warehouse_id)
    else:
        _ = await require_company_viewer(di.authz_service)
    return StockItemsResponse(
        items=await di.rule_service.list_routes(
            company_id=scope.company_id,
            warehouse_id=payload.warehouse_id,
            limit=payload.limit,
            offset=payload.offset,
        )
    )


async def op_routes_get(
    payload: StockRouteIdPayload, *, user: User, di: Di
) -> StockRoute:
    """Маршрут с плечами — «карта дороги» товара по складу."""
    _ = user
    scope = require_company()
    result = await di.rule_service.get_route(
        company_id=scope.company_id, route_id=payload.route_id
    )
    if result.warehouse_id is not None:
        await _warehouse_viewer(di, scope, result.warehouse_id)
    else:
        _ = await require_company_viewer(di.authz_service)
    return result


async def op_routes_create(
    payload: StockRouteCreatePayload, *, user: User, di: Di
) -> StockRoute:
    """Завести маршрут: «приёмка → QC → хранение» в одну цепочку."""
    _ = user
    scope = require_company()
    if payload.warehouse_id is not None:
        await _warehouse_editor(di, scope, payload.warehouse_id)
    else:
        _ = await _company_editor(di)
    return await di.rule_service.create_route(
        company_id=scope.company_id,
        warehouse_id=payload.warehouse_id,
        name=payload.name,
        code=payload.code,
        steps=payload.steps,
    )


async def op_container_types_create(
    payload: StockContainerTypeCreatePayload, *, user: User, di: Di
) -> StockContainerType:
    _ = user
    scope = require_company()
    await _warehouse_editor(di, scope, payload.warehouse_id)
    return await di.topology_service.create_container_type(
        company_id=scope.company_id,
        warehouse_id=payload.warehouse_id,
        name=payload.name,
        kind=payload.kind,
        max_weight=payload.max_weight,
        tare_weight=payload.tare_weight,
        max_volume=payload.max_volume,
        length=payload.length,
        width=payload.width,
        height=payload.height,
        is_reusable=payload.is_reusable,
        allowed_parent_type_ids=payload.allowed_parent_type_ids,
    )


async def op_resource_types_list(
    payload: StockResourceTypesListPayload, *, user: User, di: Di
) -> StockItemsResponse[StockResourceType]:
    _ = user
    scope = require_company()
    await _warehouse_viewer(di, scope, payload.warehouse_id)
    return StockItemsResponse(
        items=await di.topology_service.list_resource_types(
            company_id=scope.company_id, warehouse_id=payload.warehouse_id
        )
    )


async def op_resource_types_create(
    payload: StockResourceTypeCreatePayload, *, user: User, di: Di
) -> StockResourceType:
    _ = user
    scope = require_company()
    await _warehouse_editor(di, scope, payload.warehouse_id)
    return await di.topology_service.create_resource_type(
        company_id=scope.company_id,
        warehouse_id=payload.warehouse_id,
        name=payload.name,
        allowed_container_type_ids=payload.allowed_container_type_ids,
        handles_loose=payload.handles_loose,
        max_level=payload.max_level,
        max_load_weight=payload.max_load_weight,
        storage_type_ids=payload.storage_type_ids,
    )


async def op_resources_list(
    payload: StockResourcesListPayload, *, user: User, di: Di
) -> StockItemsResponse[StockResource]:
    _ = user
    scope = require_company()
    await _warehouse_viewer(di, scope, payload.warehouse_id)
    return StockItemsResponse(
        items=await di.topology_service.list_resources(
            company_id=scope.company_id, warehouse_id=payload.warehouse_id
        )
    )


async def op_resources_create(
    payload: StockResourceCreatePayload, *, user: User, di: Di
) -> StockResource:
    _ = user
    scope = require_company()
    await _warehouse_editor(di, scope, payload.warehouse_id)
    return await di.topology_service.create_resource(
        company_id=scope.company_id,
        warehouse_id=payload.warehouse_id,
        resource_type_id=payload.resource_type_id,
        code=payload.code,
        barcode=payload.barcode,
    )


async def op_resources_login(
    payload: StockResourceLoginPayload, *, user: User, di: Di
) -> StockResource:
    _ = user
    scope = require_company()
    await _warehouse_viewer(di, scope, payload.warehouse_id)
    return await di.topology_service.resource_login(
        company_id=scope.company_id,
        warehouse_id=payload.warehouse_id,
        resource_id=payload.resource_id,
        barcode=payload.barcode,
        user_id=scope.user_id,
        idempotency_key=payload.idempotency_key,
    )


async def op_resources_logout(
    payload: StockResourceLogoutPayload, *, user: User, di: Di
) -> StockResourceLogoutResult:
    _ = user
    scope = require_company()
    await _warehouse_viewer(di, scope, payload.warehouse_id)
    return await di.topology_service.resource_logout(
        company_id=scope.company_id,
        warehouse_id=payload.warehouse_id,
        user_id=scope.user_id,
        idempotency_key=payload.idempotency_key,
    )


async def op_containers_list(
    payload: StockContainersListPayload, *, user: User, di: Di
) -> StockItemsResponse[StockLocation]:
    _ = user
    scope = require_company()
    if payload.warehouse_id is not None:
        await _warehouse_viewer(di, scope, payload.warehouse_id)
    else:
        _ = await require_company_viewer(di.authz_service)
    return StockItemsResponse(
        items=await di.topology_service.list_containers(
            company_id=scope.company_id,
            warehouse_id=payload.warehouse_id,
            parent_location_id=payload.parent_location_id,
        )
    )


async def op_containers_create(
    payload: StockContainerCreatePayload, *, user: User, di: Di
) -> StockLocation:
    _ = user
    scope = require_company()
    await _warehouse_editor(di, scope, payload.warehouse_id)
    return await di.topology_service.create_container(
        company_id=scope.company_id,
        warehouse_id=payload.warehouse_id,
        parent_location_id=payload.parent_location_id,
        container_type_id=payload.container_type_id,
        name=payload.name,
        barcode=payload.barcode,
    )


async def op_containers_item(
    payload: StockContainerIdPayload, *, user: User, di: Di
) -> StockContainerContentsResponse:
    _ = user
    scope = require_company()
    contents = await di.topology_service.container_contents(
        company_id=scope.company_id, container_id=payload.container_id
    )
    if contents.container.warehouse_id is not None:
        await _warehouse_viewer(di, scope, contents.container.warehouse_id)
    return StockContainerContentsResponse(
        container=contents.container,
        quants=contents.quants,
        children=contents.children,
    )


async def op_containers_move(
    payload: StockContainerMovePayload, *, user: User, di: Di
) -> StockLocation:
    _ = user
    scope = require_company()
    container = await StockLocation.by_id(scope.company_id, payload.container_id)
    if container is None:
        raise PlatformNotFoundError(
            "Container not found", error_code="container_not_found"
        )
    if container.warehouse_id is not None:
        await _warehouse_editor(di, scope, container.warehouse_id)
    return await di.topology_service.move_container(
        company_id=scope.company_id,
        container_id=payload.container_id,
        dest_location_id=payload.dest_location_id,
        user_id=scope.user_id,
        idempotency_key=payload.idempotency_key,
    )


async def op_packagings_list(
    payload: StockPackagingsListPayload, *, user: User, di: Di
) -> StockItemsResponse[StockPackagingView]:
    _ = user
    scope = await require_company_viewer(di.authz_service)
    return StockItemsResponse(
        items=await di.catalog_service.list_packagings(
            company_id=scope.company_id, product_id=payload.product_id
        )
    )


async def op_packagings_create(
    payload: StockPackagingCreatePayload, *, user: User, di: Di
) -> StockPackagingView:
    _ = user
    scope = await _company_editor(di)
    return await di.catalog_service.create_packaging(
        company_id=scope.company_id,
        product_id=payload.product_id,
        name=payload.name,
        quantity=payload.quantity,
        barcode=payload.barcode,
        container_type_id=payload.container_type_id,
        weight=payload.weight,
        volume=payload.volume,
    )


async def op_packagings_delete(
    payload: StockPackagingIdPayload, *, user: User, di: Di
) -> StockPackagingView:
    _ = user
    scope = await _company_editor(di)
    return await di.catalog_service.delete_packaging(
        company_id=scope.company_id, packaging_id=payload.packaging_id
    )


# --- ЕИ ---


async def op_uoms_list(
    payload: EmptyPayload, *, user: User, di: Di
) -> StockItemsResponse[UnitOfMeasure]:
    _ = user
    _ = payload
    scope = await require_company_viewer(di.authz_service)
    return StockItemsResponse(
        items=await di.catalog_service.list_uoms(company_id=scope.company_id)
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
    parsed = result.parsed
    return StockBarcodeResolveResponse(
        entity_type=result.entity_type,
        entity_id=result.entity_id,
        is_gs1=parsed.is_gs1,
        gtin=parsed.gtin,
        sscc=parsed.sscc,
        lot_name=parsed.lot_name,
        serial=parsed.serial,
        quantity=parsed.quantity,
        weight_kg=parsed.weight_kg,
        expiration_date=(
            parsed.expiration_date.isoformat()
            if parsed.expiration_date is not None
            else None
        ),
    )


# --- Скан-сессии ТСД ---


async def _warehouse_of_move(scope: CompanyScope, move_id: str) -> str:
    move = await StockMove.by_id(scope.company_id, move_id)
    if move is None or move.warehouse_id is None:
        raise PlatformNotFoundError(
            "Move not found", error_code="move_not_found"
        )
    return move.warehouse_id


async def _scan_expected(
    company_id: str, warehouse_id: str, move_id: str | None
) -> StockScanExpected | None:
    """Подсказка экрану из первой открытой строки документа."""
    if move_id is None:
        return None
    move = await StockMove.by_id(company_id, move_id)
    if move is None or move.warehouse_id != warehouse_id:
        raise PlatformNotFoundError(
            "Move not found", error_code="move_not_found"
        )
    lines = await StockMoveLine.list_for_move(company_id, move_id)
    if not lines:
        return None
    first = lines[0]
    return StockScanExpected(
        location_id=first.location_id,
        product_id=first.product_id,
        quantity=first.quantity - first.done_quantity,
        location_dest_id=first.location_dest_id,
    )


async def op_scan_step(
    payload: StockScanStepPayload, *, user: User, di: Di
) -> StockScanStepResponse:
    """Шаг скан-сессии: штрихкод → резолв → переход машины.

    Одно обращение ТСД делает и «что за код» (индекс + GS1), и
    переход потока — оператор не ждёт двух round-trip'ов. Контекст
    stateless: живёт в памяти терминала и приезжает обратно.
    """
    _ = user
    scope = require_company()
    await _warehouse_editor(di, scope, payload.warehouse_id)
    resolution = await di.scan_service.resolve(
        company_id=scope.company_id, barcode=payload.barcode
    )
    result = di.scan_service.step(
        context=payload.context, resolution=resolution
    )
    return StockScanStepResponse(
        context=result.context,
        resolution=resolution,
        error=result.error.value if result.error is not None else None,
        hint=result.hint,
        expected=await _scan_expected(
            scope.company_id, payload.warehouse_id, payload.move_id
        ),
    )


async def op_scan_quantity(
    payload: StockScanQuantityPayload, *, user: User, di: Di
) -> StockScanStepResponse:
    """Числовой ввод на шаге количества — «ввёл 5 вместо 5 сканов»."""
    _ = user
    scope = require_company()
    await _warehouse_editor(di, scope, payload.warehouse_id)
    result = di.scan_service.quantity(
        context=payload.context, quantity=payload.quantity
    )
    return StockScanStepResponse(
        context=result.context,
        error=result.error.value if result.error is not None else None,
        hint=result.hint,
        expected=await _scan_expected(
            scope.company_id, payload.warehouse_id, payload.move_id
        ),
    )


async def op_scan_commit(
    payload: StockScanCommitPayload, *, user: User, di: Di
) -> StockMove:
    """Атомарная проводка набранного: строки контекста → леджер.

    Одна транзакция полосы склада: сплит резервных строк, движение
    остатков, слои оценки, `move → done` при закрытии — всё или ничего.
    """
    _ = user
    scope = require_company()
    warehouse_id = await _warehouse_of_move(scope, payload.move_id)
    await _warehouse_editor(di, scope, warehouse_id)
    return await di.scan_service.commit(
        company_id=scope.company_id,
        move_id=payload.move_id,
        context=payload.context,
        idempotency_key=command_idempotency_key(payload.idempotency_key),
        actor_user_id=scope.user_id,
        command_type="stock/scan/commit_requested",
        causation_id=current_command_event_id(),
    )


async def op_scan_count_commit(
    payload: StockScanCountCommitPayload, *, user: User, di: Di
) -> StockScanCountCommitResponse:
    """Коммит инвентаризации: факт-строки → `inventory_quantity` на quant."""
    _ = user
    scope = require_company()
    await _warehouse_editor(di, scope, payload.warehouse_id)
    quant_ids = await di.scan_service.inventory_count_commit(
        company_id=scope.company_id,
        warehouse_id=payload.warehouse_id,
        context=payload.context,
        idempotency_key=command_idempotency_key(payload.idempotency_key),
        actor_user_id=scope.user_id,
        command_type="stock/scan/count_commit_requested",
    )
    return StockScanCountCommitResponse(quant_ids=quant_ids)


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
