/**
 * Фабрики событий склада: каждая команда — `op_*` через WS RPC + REST-зеркало.
 *
 * Имена ресурсов/опов совпадают с доменными сущностями; `commandType` —
 * канонический `<svc>/<entity>/<verb>_requested`.
 */

import { createAsyncOp, createResourceCollection } from '@platform/lib/events/index.js';
import { isPlainRecord } from '@platform/lib/events/payload.js';

export const stockProductsResource = createResourceCollection({
    name: 'stock/products',
    baseUrl: '/stock/api/v1/products',
    idField: 'product_id',
    operations: ['list'],
    transport: 'ws',
    wsTimeoutMs: 8_000,
    listQuery: () => ({}),
    extraReducer: (state, event) => state,
});

export const stockLocationsResource = createResourceCollection({
    name: 'stock/locations',
    baseUrl: '/stock/api/v1/locations',
    idField: 'location_id',
    operations: ['list'],
    transport: 'ws',
    wsTimeoutMs: 8_000,
    listQuery: () => ({}),
    extraReducer: (state, event) => {
        if (event.type !== 'stock/container/moved' || !isPlainRecord(event.payload)) return state;
        const payload = event.payload;
        const index = state.items.findIndex((row) => row && row.location_id === payload.container_id);
        if (index === -1) return state;
        const items = state.items.map((row, position) => (
            position === index ? { ...row, parent_id: payload.to_parent_id } : row
        ));
        return { ...state, items };
    },
});

export const stockWarehousesResource = createResourceCollection({
    name: 'stock/warehouses',
    baseUrl: '/stock/api/v1/warehouses',
    idField: 'warehouse_id',
    operations: ['list'],
    transport: 'ws',
    wsTimeoutMs: 8_000,
    listQuery: () => ({}),
    extraReducer: (state, event) => state,
});

export const stockTransfersResource = createResourceCollection({
    name: 'stock/transfers',
    baseUrl: '/stock/api/v1/transfers',
    idField: 'transfer_id',
    operations: ['list'],
    transport: 'ws',
    wsTimeoutMs: 8_000,
    listQuery: () => ({}),
    extraReducer: (state, event) => {
        if (event.type === 'stock/transfer/done' && isPlainRecord(event.payload) && event.payload.transfer_id) {
            const donePayload = event.payload;
            const id = donePayload.transfer_id;
            const index = state.items.findIndex((row) => row && row.transfer_id === id);
            if (index === -1) return state;
            const items = state.items.map((row, position) => (
                position === index ? { ...row, state: 'done' } : row
            ));
            return { ...state, items };
        }
        return state;
    },
});

export const stockQuantsResource = createResourceCollection({
    name: 'stock/quants',
    baseUrl: '/stock/api/v1/quants',
    idField: 'quant_id',
    operations: ['list'],
    transport: 'ws',
    wsTimeoutMs: 8_000,
    listQuery: () => ({}),
    extraReducer: (state, event) => {
        if (event.type !== 'stock/quant/changed' || !isPlainRecord(event.payload)) return state;
        const payload = event.payload;
        const index = state.items.findIndex((row) => row && row.quant_id === payload.quant_id);
        if (index === -1) return state;
        const items = state.items.map((row, position) => (
            position === index
                ? { ...row, quantity: payload.quantity, reserved_quantity: payload.reserved_quantity }
                : row
        ));
        return { ...state, items };
    },
});

export const stockQueueResource = createResourceCollection({
    name: 'stock/queue',
    baseUrl: '/stock/api/v1/move-lines/queue',
    idField: 'move_line_id',
    operations: ['list'],
    transport: 'ws',
    wsTimeoutMs: 8_000,
    listQuery: () => ({}),
    restMirror: {
        list: { method: 'POST', path: '/stock/api/v1/move-lines/queue' },
    },
    extraReducer: (state, event) => {
        if (!isPlainRecord(event.payload) || !event.payload.move_line_id) return state;
        const movePayload = event.payload;
        if (event.type === 'stock/move_line/assigned') {
            const payload = movePayload;
            const index = state.items.findIndex((row) => row && row.move_line_id === payload.move_line_id);
            const patch = {
                assigned_user_id: payload.assigned_user_id,
                resource_id: payload.resource_id,
            };
            const items = index === -1
                ? [...state.items, payload]
                : state.items.map((row, position) => (position === index ? { ...row, ...patch } : row));
            return { ...state, items };
        }
        if (event.type === 'stock/move_line/exception') {
            const items = state.items.filter(
                (row) => row && row.move_line_id !== movePayload.move_line_id,
            );
            return { ...state, items };
        }
        return state;
    },
});

export const stockWavesResource = createResourceCollection({
    name: 'stock/waves',
    baseUrl: '/stock/api/v1/waves/list',
    idField: 'wave_id',
    operations: ['list'],
    transport: 'ws',
    wsTimeoutMs: 8_000,
    listQuery: () => ({}),
    restMirror: {
        list: { method: 'POST', path: '/stock/api/v1/waves/list' },
    },
    extraReducer: (state, event) => {
        if (event.type !== 'stock/wave/released' || !isPlainRecord(event.payload)) return state;
        const payload = event.payload;
        const index = state.items.findIndex((row) => row && row.wave_id === payload.wave_id);
        if (index === -1) return state;
        const items = state.items.map((row, position) => (
            position === index
                ? { ...row, state: 'released', released_at: payload.released_at }
                : row
        ));
        return { ...state, items };
    },
});

export const stockValuationResource = createResourceCollection({
    name: 'stock/valuation',
    baseUrl: '/stock/api/v1/valuation/layers',
    idField: 'layer_id',
    operations: ['list'],
    transport: 'ws',
    wsTimeoutMs: 8_000,
    listQuery: () => ({}),
    extraReducer: (state, event) => {
        if (event.type !== 'stock/valuation/changed' || !event.payload) return state;
        return state;
    },
});

// --- ops ---

export const stockProductCreateOp = createAsyncOp({
    name: 'stock/product_create',
    successToastKey: 'stock:toast.product_created',
    errorToastKey: 'stock:toast.product_create_failed',
    commandType: 'stock/products/create_requested',
    transport: 'ws',
    wsTimeoutMs: 8_000,
    restMirror: { method: 'POST', path: '/stock/api/v1/products' },
});

export const stockProductUpdateOp = createAsyncOp({
    name: 'stock/product_update',
    successToastKey: 'stock:toast.product_updated',
    errorToastKey: 'stock:toast.product_update_failed',
    commandType: 'stock/products/update_requested',
    transport: 'ws',
    wsTimeoutMs: 8_000,
    restMirror: { method: 'PATCH', path: '/stock/api/v1/products/:product_id' },
});

export const stockLocationCreateOp = createAsyncOp({
    name: 'stock/location_create',
    successToastKey: 'stock:toast.location_created',
    errorToastKey: 'stock:toast.location_create_failed',
    commandType: 'stock/locations/create_requested',
    transport: 'ws',
    wsTimeoutMs: 8_000,
    restMirror: { method: 'POST', path: '/stock/api/v1/locations' },
});

export const stockLocationUpdateOp = createAsyncOp({
    name: 'stock/location_update',
    successToastKey: 'stock:toast.location_updated',
    errorToastKey: 'stock:toast.location_update_failed',
    commandType: 'stock/locations/update_requested',
    transport: 'ws',
    wsTimeoutMs: 8_000,
    restMirror: { method: 'PATCH', path: '/stock/api/v1/locations/:location_id' },
});

export const stockWarehouseCreateOp = createAsyncOp({
    name: 'stock/warehouse_create',
    successToastKey: 'stock:toast.warehouse_created',
    errorToastKey: 'stock:toast.warehouse_create_failed',
    commandType: 'stock/warehouses/create_requested',
    transport: 'ws',
    wsTimeoutMs: 8_000,
    restMirror: { method: 'POST', path: '/stock/api/v1/warehouses' },
});

export const stockWarehousePulseOp = createAsyncOp({
    name: 'stock/warehouse_pulse',
    silent: true,
    commandType: 'stock/warehouse/pulse_requested',
    transport: 'ws',
    wsTimeoutMs: 10_000,
    restMirror: { method: 'GET', path: '/stock/api/v1/warehouses/:warehouse_id/pulse' },
});

export const stockOperationTypesListOp = createAsyncOp({
    name: 'stock/operation_types_list',
    silent: true,
    commandType: 'stock/operation_types/list_requested',
    transport: 'ws',
    wsTimeoutMs: 8_000,
    restMirror: { method: 'GET', path: '/stock/api/v1/operation-types' },
});

export const stockOperationTypeUpdateOp = createAsyncOp({
    name: 'stock/operation_type_update',
    successToastKey: 'stock:toast.operation_type_updated',
    errorToastKey: 'stock:toast.operation_type_update_failed',
    commandType: 'stock/operation_types/update_requested',
    transport: 'ws',
    wsTimeoutMs: 8_000,
    restMirror: { method: 'PATCH', path: '/stock/api/v1/operation-types/:operation_type_id' },
});

export const stockTransferCreateOp = createAsyncOp({
    name: 'stock/transfer_create',
    successToastKey: 'stock:toast.transfer_created',
    errorToastKey: 'stock:toast.transfer_create_failed',
    commandType: 'stock/transfers/create_requested',
    transport: 'ws',
    wsTimeoutMs: 8_000,
    restMirror: { method: 'POST', path: '/stock/api/v1/transfers' },
});

export const stockTransferItemOp = createAsyncOp({
    name: 'stock/transfer_item',
    silent: true,
    commandType: 'stock/transfers/item_requested',
    transport: 'ws',
    wsTimeoutMs: 8_000,
    restMirror: { method: 'GET', path: '/stock/api/v1/transfers/:transfer_id' },
});

export const stockTransferConfirmOp = createAsyncOp({
    name: 'stock/transfer_confirm',
    successToastKey: 'stock:toast.transfer_confirmed',
    errorToastKey: 'stock:toast.transfer_confirm_failed',
    commandType: 'stock/transfers/confirm_requested',
    transport: 'ws',
    wsTimeoutMs: 15_000,
    restMirror: { method: 'POST', path: '/stock/api/v1/transfers/:transfer_id/confirm' },
});

export const stockTransferAssignOp = createAsyncOp({
    name: 'stock/transfer_assign',
    successToastKey: 'stock:toast.transfer_assigned',
    errorToastKey: 'stock:toast.transfer_assign_failed',
    commandType: 'stock/transfers/assign_requested',
    transport: 'ws',
    wsTimeoutMs: 15_000,
    restMirror: { method: 'POST', path: '/stock/api/v1/transfers/:transfer_id/assign' },
});

export const stockTransferValidateOp = createAsyncOp({
    name: 'stock/transfer_validate',
    successToastKey: 'stock:toast.transfer_validated',
    errorToastKey: 'stock:toast.transfer_validate_failed',
    commandType: 'stock/transfers/validate_requested',
    transport: 'ws',
    wsTimeoutMs: 20_000,
    restMirror: { method: 'POST', path: '/stock/api/v1/transfers/:transfer_id/validate' },
});

export const stockTransferCancelOp = createAsyncOp({
    name: 'stock/transfer_cancel',
    successToastKey: 'stock:toast.transfer_cancelled',
    errorToastKey: 'stock:toast.transfer_cancel_failed',
    commandType: 'stock/transfers/cancel_requested',
    transport: 'ws',
    wsTimeoutMs: 15_000,
    restMirror: { method: 'POST', path: '/stock/api/v1/transfers/:transfer_id/cancel' },
});

export const stockTransferReturnOp = createAsyncOp({
    name: 'stock/transfer_return',
    successToastKey: 'stock:toast.transfer_returned',
    errorToastKey: 'stock:toast.transfer_return_failed',
    commandType: 'stock/transfers/return_requested',
    transport: 'ws',
    wsTimeoutMs: 20_000,
    restMirror: { method: 'POST', path: '/stock/api/v1/transfers/:transfer_id/return' },
});

export const stockMoveLineUpdateOp = createAsyncOp({
    name: 'stock/move_line_update',
    successToastKey: 'stock:toast.move_line_updated',
    errorToastKey: 'stock:toast.move_line_update_failed',
    commandType: 'stock/move_lines/update_requested',
    transport: 'ws',
    wsTimeoutMs: 8_000,
    restMirror: { method: 'PATCH', path: '/stock/api/v1/move-lines/:move_line_id' },
});

export const stockMoveApplyDecisionOp = createAsyncOp({
    name: 'stock/move_apply_decision',
    successToastKey: 'stock:toast.move_decision_applied',
    errorToastKey: 'stock:toast.move_decision_apply_failed',
    commandType: 'stock/move/apply_decision_requested',
    transport: 'ws',
    wsTimeoutMs: 8_000,
    restMirror: { method: 'POST', path: '/stock/api/v1/moves/apply-decision' },
});

export const stockQuantInventorySetOp = createAsyncOp({
    name: 'stock/quant_inventory_set',
    successToastKey: 'stock:toast.inventory_set',
    errorToastKey: 'stock:toast.inventory_set_failed',
    commandType: 'stock/quants/inventory_set_requested',
    transport: 'ws',
    wsTimeoutMs: 8_000,
    restMirror: { method: 'POST', path: '/stock/api/v1/quants/inventory-set' },
});

export const stockQuantInventoryApplyOp = createAsyncOp({
    name: 'stock/quant_inventory_apply',
    successToastKey: 'stock:toast.inventory_applied',
    errorToastKey: 'stock:toast.inventory_apply_failed',
    commandType: 'stock/quants/inventory_apply_requested',
    transport: 'ws',
    wsTimeoutMs: 15_000,
    restMirror: { method: 'POST', path: '/stock/api/v1/quants/inventory-apply' },
});

export const stockValuationProductValueOp = createAsyncOp({
    name: 'stock/valuation_product_value',
    silent: true,
    commandType: 'stock/valuation/product_value_requested',
    transport: 'ws',
    wsTimeoutMs: 8_000,
    restMirror: { method: 'GET', path: '/stock/api/v1/valuation/product-value' },
});

export const stockValuationRevalueOp = createAsyncOp({
    name: 'stock/valuation_revalue',
    successToastKey: 'stock:toast.valuation_revalued',
    errorToastKey: 'stock:toast.valuation_revalue_failed',
    commandType: 'stock/valuation/revalue_requested',
    transport: 'ws',
    wsTimeoutMs: 10_000,
    restMirror: { method: 'POST', path: '/stock/api/v1/valuation/revalue' },
});

export const stockValuationCorrectionOp = createAsyncOp({
    name: 'stock/valuation_correction',
    successToastKey: 'stock:toast.valuation_correction_done',
    errorToastKey: 'stock:toast.valuation_correction_failed',
    commandType: 'stock/valuation/correction_requested',
    transport: 'ws',
    wsTimeoutMs: 10_000,
    restMirror: { method: 'POST', path: '/stock/api/v1/valuation/correction' },
});

export const stockBarcodeResolveOp = createAsyncOp({
    name: 'stock/barcode_resolve',
    silent: true,
    commandType: 'stock/barcode/resolve_requested',
    transport: 'ws',
    wsTimeoutMs: 8_000,
    restMirror: { method: 'GET', path: '/stock/api/v1/barcode/:barcode' },
});

export const stockLotsListOp = createAsyncOp({
    name: 'stock/lots_list',
    silent: true,
    commandType: 'stock/lots/list_requested',
    transport: 'ws',
    wsTimeoutMs: 8_000,
    restMirror: { method: 'GET', path: '/stock/api/v1/lots' },
});

export const stockLotCreateOp = createAsyncOp({
    name: 'stock/lot_create',
    successToastKey: 'stock:toast.lot_created',
    errorToastKey: 'stock:toast.lot_create_failed',
    commandType: 'stock/lots/create_requested',
    transport: 'ws',
    wsTimeoutMs: 8_000,
    restMirror: { method: 'POST', path: '/stock/api/v1/lots' },
});

export const stockUomsListOp = createAsyncOp({
    name: 'stock/uoms_list',
    silent: true,
    commandType: 'stock/uoms/list_requested',
    transport: 'ws',
    wsTimeoutMs: 8_000,
    restMirror: { method: 'GET', path: '/stock/api/v1/uoms' },
});

declare module '@platform/lib/events/factory-registry.js' {
    interface PlatformFactoryRegistry {
        'stock/products': typeof stockProductsResource;
        'stock/locations': typeof stockLocationsResource;
        'stock/warehouses': typeof stockWarehousesResource;
        'stock/transfers': typeof stockTransfersResource;
        'stock/quants': typeof stockQuantsResource;
        'stock/queue': typeof stockQueueResource;
        'stock/waves': typeof stockWavesResource;
        'stock/valuation': typeof stockValuationResource;
        'stock/product_create': typeof stockProductCreateOp;
        'stock/product_update': typeof stockProductUpdateOp;
        'stock/location_create': typeof stockLocationCreateOp;
        'stock/location_update': typeof stockLocationUpdateOp;
        'stock/warehouse_create': typeof stockWarehouseCreateOp;
        'stock/warehouse_pulse': typeof stockWarehousePulseOp;
        'stock/operation_types_list': typeof stockOperationTypesListOp;
        'stock/operation_type_update': typeof stockOperationTypeUpdateOp;
        'stock/transfer_create': typeof stockTransferCreateOp;
        'stock/transfer_item': typeof stockTransferItemOp;
        'stock/transfer_confirm': typeof stockTransferConfirmOp;
        'stock/transfer_assign': typeof stockTransferAssignOp;
        'stock/transfer_validate': typeof stockTransferValidateOp;
        'stock/transfer_cancel': typeof stockTransferCancelOp;
        'stock/transfer_return': typeof stockTransferReturnOp;
        'stock/move_line_update': typeof stockMoveLineUpdateOp;
        'stock/move_apply_decision': typeof stockMoveApplyDecisionOp;
        'stock/quant_inventory_set': typeof stockQuantInventorySetOp;
        'stock/quant_inventory_apply': typeof stockQuantInventoryApplyOp;
        'stock/valuation_product_value': typeof stockValuationProductValueOp;
        'stock/valuation_revalue': typeof stockValuationRevalueOp;
        'stock/valuation_correction': typeof stockValuationCorrectionOp;
        'stock/barcode_resolve': typeof stockBarcodeResolveOp;
        'stock/lots_list': typeof stockLotsListOp;
        'stock/lot_create': typeof stockLotCreateOp;
        'stock/uoms_list': typeof stockUomsListOp;
    }
}
