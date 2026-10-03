/**
 * Фабрики событий склада: каждая команда — `op_*` через WS RPC + REST-зеркало.
 *
 * Имена ресурсов/опов совпадают с доменными сущностями; `commandType` —
 * канонический `<svc>/<entity>/<verb>_requested`.
 */

import { createAsyncOp, createResourceCollection } from '@platform/lib/events/index.js';

export const stockProductsResource = createResourceCollection({
    name: 'stock/products',
    baseUrl: '/stock/api/v1/products',
    idField: 'product_id',
    operations: ['list'],
    transport: 'ws',
    wsTimeoutMs: 8_000,
    itemsPath: 'items',
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
    itemsPath: 'items',
    listQuery: () => ({}),
    extraReducer: (state, event) => {
        if (event.type !== 'stock/container/moved' || !event.payload) return state;
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
    itemsPath: 'items',
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
    itemsPath: 'items',
    listQuery: () => ({}),
    extraReducer: (state, event) => {
        if (event.type === 'stock/transfer/done' && event.payload && event.payload.transfer_id) {
            const id = event.payload.transfer_id;
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
    itemsPath: 'items',
    listQuery: () => ({}),
    extraReducer: (state, event) => {
        if (event.type !== 'stock/quant/changed' || !event.payload) return state;
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
    itemsPath: 'items',
    listQuery: () => ({}),
    restMirror: {
        list: { method: 'POST', path: '/stock/api/v1/move-lines/queue' },
    },
    extraReducer: (state, event) => {
        if (!event.payload || !event.payload.move_line_id) return state;
        if (event.type === 'stock/move_line/assigned') {
            const payload = event.payload;
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
                (row) => row && row.move_line_id !== event.payload.move_line_id,
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
    itemsPath: 'items',
    listQuery: () => ({}),
    restMirror: {
        list: { method: 'POST', path: '/stock/api/v1/waves/list' },
    },
    extraReducer: (state, event) => {
        if (event.type !== 'stock/wave/released' || !event.payload) return state;
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
    itemsPath: 'items',
    listQuery: () => ({}),
    extraReducer: (state, event) => {
        if (event.type !== 'stock/valuation/changed' || !event.payload) return state;
        return state;
    },
});

// --- ops ---

export const stockProductCreateOp = createAsyncOp({
    name: 'stock/product_create',
    commandType: 'stock/products/create_requested',
    transport: 'ws',
    wsTimeoutMs: 8_000,
    restMirror: { method: 'POST', path: '/stock/api/v1/products' },
});

export const stockProductUpdateOp = createAsyncOp({
    name: 'stock/product_update',
    commandType: 'stock/products/update_requested',
    transport: 'ws',
    wsTimeoutMs: 8_000,
    restMirror: { method: 'PATCH', path: '/stock/api/v1/products/:product_id' },
});

export const stockLocationCreateOp = createAsyncOp({
    name: 'stock/location_create',
    commandType: 'stock/locations/create_requested',
    transport: 'ws',
    wsTimeoutMs: 8_000,
    restMirror: { method: 'POST', path: '/stock/api/v1/locations' },
});

export const stockLocationUpdateOp = createAsyncOp({
    name: 'stock/location_update',
    commandType: 'stock/locations/update_requested',
    transport: 'ws',
    wsTimeoutMs: 8_000,
    restMirror: { method: 'PATCH', path: '/stock/api/v1/locations/:location_id' },
});

export const stockWarehouseCreateOp = createAsyncOp({
    name: 'stock/warehouse_create',
    commandType: 'stock/warehouses/create_requested',
    transport: 'ws',
    wsTimeoutMs: 8_000,
    restMirror: { method: 'POST', path: '/stock/api/v1/warehouses' },
});

export const stockWarehousePulseOp = createAsyncOp({
    name: 'stock/warehouse_pulse',
    commandType: 'stock/warehouse/pulse_requested',
    transport: 'ws',
    wsTimeoutMs: 10_000,
    restMirror: { method: 'GET', path: '/stock/api/v1/warehouses/:warehouse_id/pulse' },
});

export const stockOperationTypesListOp = createAsyncOp({
    name: 'stock/operation_types_list',
    commandType: 'stock/operation_types/list_requested',
    transport: 'ws',
    wsTimeoutMs: 8_000,
    restMirror: { method: 'GET', path: '/stock/api/v1/operation-types' },
});

export const stockOperationTypeUpdateOp = createAsyncOp({
    name: 'stock/operation_type_update',
    commandType: 'stock/operation_types/update_requested',
    transport: 'ws',
    wsTimeoutMs: 8_000,
    restMirror: { method: 'PATCH', path: '/stock/api/v1/operation-types/:operation_type_id' },
});

export const stockTransferCreateOp = createAsyncOp({
    name: 'stock/transfer_create',
    commandType: 'stock/transfers/create_requested',
    transport: 'ws',
    wsTimeoutMs: 8_000,
    restMirror: { method: 'POST', path: '/stock/api/v1/transfers' },
});

export const stockTransferItemOp = createAsyncOp({
    name: 'stock/transfer_item',
    commandType: 'stock/transfers/item_requested',
    transport: 'ws',
    wsTimeoutMs: 8_000,
    restMirror: { method: 'GET', path: '/stock/api/v1/transfers/:transfer_id' },
});

export const stockTransferConfirmOp = createAsyncOp({
    name: 'stock/transfer_confirm',
    commandType: 'stock/transfers/confirm_requested',
    transport: 'ws',
    wsTimeoutMs: 15_000,
    restMirror: { method: 'POST', path: '/stock/api/v1/transfers/:transfer_id/confirm' },
});

export const stockTransferAssignOp = createAsyncOp({
    name: 'stock/transfer_assign',
    commandType: 'stock/transfers/assign_requested',
    transport: 'ws',
    wsTimeoutMs: 15_000,
    restMirror: { method: 'POST', path: '/stock/api/v1/transfers/:transfer_id/assign' },
});

export const stockTransferValidateOp = createAsyncOp({
    name: 'stock/transfer_validate',
    commandType: 'stock/transfers/validate_requested',
    transport: 'ws',
    wsTimeoutMs: 20_000,
    restMirror: { method: 'POST', path: '/stock/api/v1/transfers/:transfer_id/validate' },
});

export const stockTransferCancelOp = createAsyncOp({
    name: 'stock/transfer_cancel',
    commandType: 'stock/transfers/cancel_requested',
    transport: 'ws',
    wsTimeoutMs: 15_000,
    restMirror: { method: 'POST', path: '/stock/api/v1/transfers/:transfer_id/cancel' },
});

export const stockTransferReturnOp = createAsyncOp({
    name: 'stock/transfer_return',
    commandType: 'stock/transfers/return_requested',
    transport: 'ws',
    wsTimeoutMs: 20_000,
    restMirror: { method: 'POST', path: '/stock/api/v1/transfers/:transfer_id/return' },
});

export const stockMoveLineUpdateOp = createAsyncOp({
    name: 'stock/move_line_update',
    commandType: 'stock/move_lines/update_requested',
    transport: 'ws',
    wsTimeoutMs: 8_000,
    restMirror: { method: 'PATCH', path: '/stock/api/v1/move-lines/:move_line_id' },
});

export const stockMoveApplyDecisionOp = createAsyncOp({
    name: 'stock/move_apply_decision',
    commandType: 'stock/move/apply_decision_requested',
    transport: 'ws',
    wsTimeoutMs: 8_000,
    restMirror: { method: 'POST', path: '/stock/api/v1/moves/apply-decision' },
});

export const stockQuantInventorySetOp = createAsyncOp({
    name: 'stock/quant_inventory_set',
    commandType: 'stock/quants/inventory_set_requested',
    transport: 'ws',
    wsTimeoutMs: 8_000,
    restMirror: { method: 'POST', path: '/stock/api/v1/quants/inventory-set' },
});

export const stockQuantInventoryApplyOp = createAsyncOp({
    name: 'stock/quant_inventory_apply',
    commandType: 'stock/quants/inventory_apply_requested',
    transport: 'ws',
    wsTimeoutMs: 15_000,
    restMirror: { method: 'POST', path: '/stock/api/v1/quants/inventory-apply' },
});

export const stockValuationProductValueOp = createAsyncOp({
    name: 'stock/valuation_product_value',
    commandType: 'stock/valuation/product_value_requested',
    transport: 'ws',
    wsTimeoutMs: 8_000,
    restMirror: { method: 'GET', path: '/stock/api/v1/valuation/product-value' },
});

export const stockValuationRevalueOp = createAsyncOp({
    name: 'stock/valuation_revalue',
    commandType: 'stock/valuation/revalue_requested',
    transport: 'ws',
    wsTimeoutMs: 10_000,
    restMirror: { method: 'POST', path: '/stock/api/v1/valuation/revalue' },
});

export const stockValuationCorrectionOp = createAsyncOp({
    name: 'stock/valuation_correction',
    commandType: 'stock/valuation/correction_requested',
    transport: 'ws',
    wsTimeoutMs: 10_000,
    restMirror: { method: 'POST', path: '/stock/api/v1/valuation/correction' },
});

export const stockBarcodeResolveOp = createAsyncOp({
    name: 'stock/barcode_resolve',
    commandType: 'stock/barcode/resolve_requested',
    transport: 'ws',
    wsTimeoutMs: 8_000,
    restMirror: { method: 'GET', path: '/stock/api/v1/barcode/:barcode' },
});

export const stockLotsListOp = createAsyncOp({
    name: 'stock/lots_list',
    commandType: 'stock/lots/list_requested',
    transport: 'ws',
    wsTimeoutMs: 8_000,
    restMirror: { method: 'GET', path: '/stock/api/v1/lots' },
});

export const stockLotCreateOp = createAsyncOp({
    name: 'stock/lot_create',
    commandType: 'stock/lots/create_requested',
    transport: 'ws',
    wsTimeoutMs: 8_000,
    restMirror: { method: 'POST', path: '/stock/api/v1/lots' },
});

export const stockUomsListOp = createAsyncOp({
    name: 'stock/uoms_list',
    commandType: 'stock/uoms/list_requested',
    transport: 'ws',
    wsTimeoutMs: 8_000,
    restMirror: { method: 'GET', path: '/stock/api/v1/uoms' },
});
