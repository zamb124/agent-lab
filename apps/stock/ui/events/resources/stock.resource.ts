/**
 * Фабрики событий склада: каждая команда — `op_*` через WS RPC + REST-зеркало.
 *
 * Имена ресурсов/опов совпадают с доменными сущностями; `commandType` —
 * канонический `<svc>/<entity>/<verb>_requested`.
 */

import { createAsyncOp, createCursorList, createForm, createResourceCollection, reloadLastList, rerunLastRequest } from '@platform/lib/events/index.js';
import { isPlatformEventType } from '@platform/lib/events/payload.js';
import type { ResourceCollectionFactory, ResourceCollectionSlice } from '@platform/lib/events/factories/resource-collection.js';
import type { StockMove, StockMoveLine, StockQuant, StockTransfer, StockWave } from '@platform/lib/events/wire/stock.gen.js';

export const stockProductsResource = createResourceCollection({
    name: 'stock/products',
    baseUrl: '/stock/api/v1/products',
    idField: 'product_id',
    operations: ['list'],
    transport: 'ws',
    wsTimeoutMs: 8_000,
    listQuery: () => ({}),
    extraReducer: (state, event) => state,
    extraEffect: (event, ctx): boolean => {
        if (
            isPlatformEventType(event, 'catalog/product/created')
            || isPlatformEventType(event, 'catalog/product/updated')
            || isPlatformEventType(event, 'catalog/product_overlay/changed')
        ) {
            return reloadLastList(ctx, stockProductsResource);
        }
        if (isPlatformEventType(event, 'catalog/product_facet/changed')) {
            return event.payload.facet === 'stock'
                && reloadLastList(ctx, stockProductsResource);
        }
        return false;
    },
});

export const stockLocationsResource = createResourceCollection({
    name: 'stock/locations',
    baseUrl: '/stock/api/v1/locations',
    idField: 'location_id',
    operations: ['list'],
    transport: 'ws',
    wsTimeoutMs: 8_000,
    listQuery: (payload) => payload,
    extraReducer: (state, event) => {
        if (!isPlatformEventType(event, 'stock/container/moved')) return state;
        const payload = event.payload;
        const toParentId = payload.to_parent_id;
        const index = state.items.findIndex((row) => row && row.location_id === payload.container_id);
        if (index === -1) return state;
        const items = state.items.map((row, position) => (
            position === index ? { ...row, parent_id: toParentId } : row
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
        if (!isPlatformEventType(event, 'stock/transfer/done')) return state;
        const index = state.items.findIndex((row) => row && row.transfer_id === event.payload.transfer_id);
        if (index === -1) return state;
        const items = state.items.map((row, position): StockTransfer => (
            position === index ? { ...row, state: 'done' } : row
        ));
        return { ...state, items };
    },
});

export const stockQuantsResource = createResourceCollection({
    name: 'stock/quants',
    baseUrl: '/stock/api/v1/quants',
    idField: 'quant_id',
    operations: ['list'],
    transport: 'ws',
    wsTimeoutMs: 8_000,
    listQuery: (payload) => payload,
    extraReducer: (state, event) => {
        if (!isPlatformEventType(event, 'stock/quant/changed')) return state;
        const payload = event.payload;
        const index = state.items.findIndex((row) => row && row.quant_id === payload.quant_id);
        if (index === -1) return state;
        const items = state.items.map((row, position): StockQuant => (
            position === index
                ? { ...row, quantity: payload.quantity, reserved_quantity: payload.reserved_quantity }
                : row
        ));
        return { ...state, items };
    },
});

export const stockQueueResource: ResourceCollectionFactory<ResourceCollectionSlice<StockMoveLine>> = createResourceCollection<StockMoveLine>({
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
        if (isPlatformEventType(event, 'stock/move_line/assigned')) {
            const payload = event.payload;
            const index = state.items.findIndex((row) => row && row.move_line_id === payload.move_line_id);
            // `stock/move_line/assigned` — лёгкое уведомление (9 полей), не полная
            // строка: новая позиция очереди дозагружается списком в extraEffect,
            // существующая мержит только поля назначения.
            if (index === -1) return state;
            const items = state.items.map((row, position): StockMoveLine => (
                position === index
                    ? {
                        ...row,
                        assigned_user_id: payload.assigned_user_id,
                        resource_id: payload.resource_id,
                    }
                    : row
            ));
            return { ...state, items };
        }
        if (isPlatformEventType(event, 'stock/move_line/exception')) {
            const items = state.items.filter(
                (row) => row && row.move_line_id !== event.payload.move_line_id,
            );
            return { ...state, items };
        }
        return state;
    },
    extraEffect: (event, ctx): boolean => {
        if (isPlatformEventType(event, 'stock/move_line/assigned')) {
            return reloadLastList(ctx, stockQueueResource);
        }
        return false;
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
        if (!isPlatformEventType(event, 'stock/wave/released')) return state;
        const payload = event.payload;
        const index = state.items.findIndex((row) => row && row.wave_id === payload.wave_id);
        if (index === -1) return state;
        const items = state.items.map((row, position): StockWave => (
            position === index
                ? { ...row, state: 'released', released_at: payload.released_at }
                : row
        ));
        return { ...state, items };
    },
});

export const stockValuationLayersListOp = createAsyncOp({
    name: 'stock/valuation_layers_list',
    silent: true,
    commandType: 'stock/valuation/layers_list_requested',
    transport: 'ws',
    wsTimeoutMs: 8_000,
    restMirror: { method: 'GET', path: '/stock/api/v1/valuation/layers' },
});

export const stockValuationReportOp = createAsyncOp({
    name: 'stock/valuation_report',
    silent: true,
    commandType: 'stock/valuation/report_requested',
    transport: 'ws',
    wsTimeoutMs: 8_000,
    restMirror: { method: 'GET', path: '/stock/api/v1/valuation/report' },
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
    onSuccess: (ctx) => { reloadLastList(ctx, stockProductsResource); },
});

export const stockCatalogProductsSuggestOp = createAsyncOp({
    name: 'stock/catalog_products_suggest',
    silent: true,
    commandType: 'stock/catalog_products/suggest_requested',
    transport: 'ws',
    wsTimeoutMs: 8_000,
    restMirror: { method: 'GET', path: '/stock/api/v1/catalog-products/suggest' },
});

export const stockCatalogProductUpdateOp = createAsyncOp({
    name: 'stock/catalog_product_update',
    successToastKey: 'stock:toast.product_updated',
    errorToastKey: 'stock:toast.product_update_failed',
    commandType: 'stock/catalog_products/update_requested',
    transport: 'ws',
    wsTimeoutMs: 8_000,
    restMirror: { method: 'PATCH', path: '/stock/api/v1/catalog-products/:product_id' },
    onSuccess: (ctx) => { reloadLastList(ctx, stockProductsResource); },
});

export const stockProductUpdateOp = createAsyncOp({
    name: 'stock/product_update',
    successToastKey: 'stock:toast.product_updated',
    errorToastKey: 'stock:toast.product_update_failed',
    commandType: 'stock/products/update_requested',
    transport: 'ws',
    wsTimeoutMs: 8_000,
    restMirror: { method: 'PATCH', path: '/stock/api/v1/products/:product_id' },
    onSuccess: (ctx) => { reloadLastList(ctx, stockProductsResource); },
});

export const stockLocationCreateOp = createAsyncOp({
    name: 'stock/location_create',
    successToastKey: 'stock:toast.location_created',
    errorToastKey: 'stock:toast.location_create_failed',
    commandType: 'stock/locations/create_requested',
    transport: 'ws',
    wsTimeoutMs: 8_000,
    restMirror: { method: 'POST', path: '/stock/api/v1/locations' },
    onSuccess: (ctx) => { reloadLastList(ctx, stockLocationsResource); },
});

export const stockLocationUpdateOp = createAsyncOp({
    name: 'stock/location_update',
    successToastKey: 'stock:toast.location_updated',
    errorToastKey: 'stock:toast.location_update_failed',
    commandType: 'stock/locations/update_requested',
    transport: 'ws',
    wsTimeoutMs: 8_000,
    restMirror: { method: 'PATCH', path: '/stock/api/v1/locations/:location_id' },
    onSuccess: (ctx) => { reloadLastList(ctx, stockLocationsResource); },
});

export const stockWarehouseCreateOp = createAsyncOp({
    name: 'stock/warehouse_create',
    successToastKey: 'stock:toast.warehouse_created',
    errorToastKey: 'stock:toast.warehouse_create_failed',
    commandType: 'stock/warehouses/create_requested',
    transport: 'ws',
    wsTimeoutMs: 8_000,
    restMirror: { method: 'POST', path: '/stock/api/v1/warehouses' },
    onSuccess: (ctx) => { reloadLastList(ctx, stockWarehousesResource); },
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
    onSuccess: (ctx) => { rerunLastRequest(ctx, stockOperationTypesListOp); },
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
    onSuccess: (ctx) => {
        reloadLastList(ctx, stockQuantsResource);
        rerunLastRequest(ctx, stockLocationCountDueOp);
    },
});

export const stockQuantInventoryApplyOp = createAsyncOp({
    name: 'stock/quant_inventory_apply',
    successToastKey: 'stock:toast.inventory_applied',
    errorToastKey: 'stock:toast.inventory_apply_failed',
    commandType: 'stock/quants/inventory_apply_requested',
    transport: 'ws',
    wsTimeoutMs: 15_000,
    restMirror: { method: 'POST', path: '/stock/api/v1/quants/inventory-apply' },
    onSuccess: (ctx) => {
        reloadLastList(ctx, stockQuantsResource);
        rerunLastRequest(ctx, stockLocationCountDueOp);
    },
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
    onSuccess: (ctx) => {
        rerunLastRequest(ctx, stockValuationLayersListOp);
        rerunLastRequest(ctx, stockValuationReportOp);
    },
});

export const stockValuationCorrectionOp = createAsyncOp({
    name: 'stock/valuation_correction',
    successToastKey: 'stock:toast.valuation_correction_done',
    errorToastKey: 'stock:toast.valuation_correction_failed',
    commandType: 'stock/valuation/correction_requested',
    transport: 'ws',
    wsTimeoutMs: 10_000,
    restMirror: { method: 'POST', path: '/stock/api/v1/valuation/correction' },
    onSuccess: (ctx) => {
        rerunLastRequest(ctx, stockValuationLayersListOp);
        rerunLastRequest(ctx, stockValuationReportOp);
    },
});

export const stockValuationRevalueForm = createForm({
    name: 'stock/valuation_revalue_form',
    schema: {
        product_id: { required: true },
        mode: { required: true },
        value_delta: {},
        new_price: {},
        description: { maxLength: 512 },
    },
    initial: { product_id: '', mode: 'delta', value_delta: null, new_price: null, description: '' },
    submitEvent: stockValuationRevalueOp.events.REQUESTED,
    submittingClearOnEventTypes: [
        stockValuationRevalueOp.events.SUCCEEDED,
        stockValuationRevalueOp.events.FAILED,
    ],
    buildPayload: (draft) => ({
        product_id: typeof draft.product_id === 'string' ? draft.product_id : '',
        value_delta: draft.mode === 'delta' && typeof draft.value_delta === 'number' ? draft.value_delta : null,
        new_price: draft.mode === 'price' && typeof draft.new_price === 'number' ? draft.new_price : null,
        description: typeof draft.description === 'string' ? draft.description : '',
    }),
});

export const stockValuationCorrectionForm = createForm({
    name: 'stock/valuation_correction_form',
    schema: {
        origin_layer_id: { required: true },
        quantity_delta: { required: true },
        value_delta: { required: true },
        description: { maxLength: 512 },
    },
    initial: { origin_layer_id: '', quantity_delta: 0, value_delta: null, description: '' },
    submitEvent: stockValuationCorrectionOp.events.REQUESTED,
    submittingClearOnEventTypes: [
        stockValuationCorrectionOp.events.SUCCEEDED,
        stockValuationCorrectionOp.events.FAILED,
    ],
    buildPayload: (draft) => ({
        origin_layer_id: typeof draft.origin_layer_id === 'string' ? draft.origin_layer_id : '',
        quantity_delta: typeof draft.quantity_delta === 'number' ? draft.quantity_delta : 0,
        value_delta: typeof draft.value_delta === 'number' ? draft.value_delta : null,
        description: typeof draft.description === 'string' ? draft.description : '',
    }),
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

export const stockMovesList = createCursorList<StockMove>({
    name: 'stock/moves',
    baseUrl: '/stock/api/v1/moves',
    commandType: 'stock/moves/list_requested',
    transport: 'ws',
    wsTimeoutMs: 8_000,
    pageSize: 50,
    restMirror: { method: 'GET', path: '/stock/api/v1/moves' },
    buildQuery: (filters) => filters,
});

export const stockContainersListOp = createAsyncOp({
    name: 'stock/containers_list',
    silent: true,
    commandType: 'stock/containers/list_requested',
    transport: 'ws',
    wsTimeoutMs: 8_000,
    restMirror: { method: 'GET', path: '/stock/api/v1/containers' },
});

export const stockContainerItemOp = createAsyncOp({
    name: 'stock/container_item',
    silent: true,
    commandType: 'stock/containers/item_requested',
    transport: 'ws',
    wsTimeoutMs: 8_000,
    restMirror: { method: 'GET', path: '/stock/api/v1/containers/{container_id}' },
});

export const stockContainerCreateOp = createAsyncOp({
    name: 'stock/container_create',
    successToastKey: 'stock:toast.container_created',
    errorToastKey: 'stock:toast.container_create_failed',
    commandType: 'stock/containers/create_requested',
    transport: 'ws',
    wsTimeoutMs: 8_000,
    restMirror: { method: 'POST', path: '/stock/api/v1/containers' },
    onSuccess: (ctx) => {
        rerunLastRequest(ctx, stockContainersListOp);
        reloadLastList(ctx, stockLocationsResource);
    },
});

export const stockContainerMoveOp = createAsyncOp({
    name: 'stock/container_move',
    successToastKey: 'stock:toast.container_moved',
    errorToastKey: 'stock:toast.container_move_failed',
    commandType: 'stock/containers/move_requested',
    transport: 'ws',
    wsTimeoutMs: 8_000,
    restMirror: { method: 'POST', path: '/stock/api/v1/containers/{container_id}/move' },
    onSuccess: (ctx) => {
        rerunLastRequest(ctx, stockContainersListOp);
        rerunLastRequest(ctx, stockContainerItemOp);
        reloadLastList(ctx, stockLocationsResource);
    },
});

export const stockLocationCountDueOp = createAsyncOp({
    name: 'stock/locations_count_due',
    silent: true,
    commandType: 'stock/locations/count_due_requested',
    transport: 'ws',
    wsTimeoutMs: 8_000,
    restMirror: { method: 'GET', path: '/stock/api/v1/locations/count-due' },
});

export const stockStorageTypesListOp = createAsyncOp({
    name: 'stock/storage_types_list',
    silent: true,
    commandType: 'stock/storage_types/list_requested',
    transport: 'ws',
    wsTimeoutMs: 8_000,
    restMirror: { method: 'GET', path: '/stock/api/v1/storage-types' },
});

export const stockStorageTypeCreateOp = createAsyncOp({
    name: 'stock/storage_type_create',
    successToastKey: 'stock:toast.storage_type_created',
    errorToastKey: 'stock:toast.storage_type_create_failed',
    commandType: 'stock/storage_types/create_requested',
    transport: 'ws',
    wsTimeoutMs: 8_000,
    restMirror: { method: 'POST', path: '/stock/api/v1/storage-types' },
    onSuccess: (ctx) => { rerunLastRequest(ctx, stockStorageTypesListOp); },
});

export const stockStorageTypeUpdateOp = createAsyncOp({
    name: 'stock/storage_type_update',
    successToastKey: 'stock:toast.storage_type_updated',
    errorToastKey: 'stock:toast.storage_type_update_failed',
    commandType: 'stock/storage_types/update_requested',
    transport: 'ws',
    wsTimeoutMs: 8_000,
    restMirror: { method: 'PATCH', path: '/stock/api/v1/storage-types/{storage_type_id}' },
    onSuccess: (ctx) => { rerunLastRequest(ctx, stockStorageTypesListOp); },
});

export const stockContainerTypesListOp = createAsyncOp({
    name: 'stock/container_types_list',
    silent: true,
    commandType: 'stock/container_types/list_requested',
    transport: 'ws',
    wsTimeoutMs: 8_000,
    restMirror: { method: 'GET', path: '/stock/api/v1/container-types' },
});

export const stockContainerTypeCreateOp = createAsyncOp({
    name: 'stock/container_type_create',
    successToastKey: 'stock:toast.container_type_created',
    errorToastKey: 'stock:toast.container_type_create_failed',
    commandType: 'stock/container_types/create_requested',
    transport: 'ws',
    wsTimeoutMs: 8_000,
    restMirror: { method: 'POST', path: '/stock/api/v1/container-types' },
    onSuccess: (ctx) => { rerunLastRequest(ctx, stockContainerTypesListOp); },
});

export const stockContainerTypeUpdateOp = createAsyncOp({
    name: 'stock/container_type_update',
    successToastKey: 'stock:toast.container_type_updated',
    errorToastKey: 'stock:toast.container_type_update_failed',
    commandType: 'stock/container_types/update_requested',
    transport: 'ws',
    wsTimeoutMs: 8_000,
    restMirror: { method: 'PATCH', path: '/stock/api/v1/container-types/{container_type_id}' },
    onSuccess: (ctx) => { rerunLastRequest(ctx, stockContainerTypesListOp); },
});

export const stockResourceTypesListOp = createAsyncOp({
    name: 'stock/resource_types_list',
    silent: true,
    commandType: 'stock/resource_types/list_requested',
    transport: 'ws',
    wsTimeoutMs: 8_000,
    restMirror: { method: 'GET', path: '/stock/api/v1/resource-types' },
});

export const stockResourceTypeCreateOp = createAsyncOp({
    name: 'stock/resource_type_create',
    successToastKey: 'stock:toast.resource_type_created',
    errorToastKey: 'stock:toast.resource_type_create_failed',
    commandType: 'stock/resource_types/create_requested',
    transport: 'ws',
    wsTimeoutMs: 8_000,
    restMirror: { method: 'POST', path: '/stock/api/v1/resource-types' },
    onSuccess: (ctx) => { rerunLastRequest(ctx, stockResourceTypesListOp); },
});

export const stockResourceTypeUpdateOp = createAsyncOp({
    name: 'stock/resource_type_update',
    successToastKey: 'stock:toast.resource_type_updated',
    errorToastKey: 'stock:toast.resource_type_update_failed',
    commandType: 'stock/resource_types/update_requested',
    transport: 'ws',
    wsTimeoutMs: 8_000,
    restMirror: { method: 'PATCH', path: '/stock/api/v1/resource-types/{resource_type_id}' },
    onSuccess: (ctx) => { rerunLastRequest(ctx, stockResourceTypesListOp); },
});

export const stockResourcesListOp = createAsyncOp({
    name: 'stock/resources_list',
    silent: true,
    commandType: 'stock/resources/list_requested',
    transport: 'ws',
    wsTimeoutMs: 8_000,
    restMirror: { method: 'GET', path: '/stock/api/v1/resources' },
});

export const stockResourceCreateOp = createAsyncOp({
    name: 'stock/resource_create',
    successToastKey: 'stock:toast.resource_created',
    errorToastKey: 'stock:toast.resource_create_failed',
    commandType: 'stock/resources/create_requested',
    transport: 'ws',
    wsTimeoutMs: 8_000,
    restMirror: { method: 'POST', path: '/stock/api/v1/resources' },
    onSuccess: (ctx) => { rerunLastRequest(ctx, stockResourcesListOp); },
});

export const stockResourceUpdateOp = createAsyncOp({
    name: 'stock/resource_update',
    successToastKey: 'stock:toast.resource_updated',
    errorToastKey: 'stock:toast.resource_update_failed',
    commandType: 'stock/resources/update_requested',
    transport: 'ws',
    wsTimeoutMs: 8_000,
    restMirror: { method: 'PATCH', path: '/stock/api/v1/resources/{resource_id}' },
    onSuccess: (ctx) => { rerunLastRequest(ctx, stockResourcesListOp); },
});

export const stockPutawayRulesListOp = createAsyncOp({
    name: 'stock/putaway_rules_list',
    silent: true,
    commandType: 'stock/putaway_rules/list_requested',
    transport: 'ws',
    wsTimeoutMs: 8_000,
    restMirror: { method: 'POST', path: '/stock/api/v1/putaway-rules/list' },
});

export const stockPutawayRuleCreateOp = createAsyncOp({
    name: 'stock/putaway_rule_create',
    successToastKey: 'stock:toast.putaway_rule_created',
    errorToastKey: 'stock:toast.putaway_rule_create_failed',
    commandType: 'stock/putaway_rules/create_requested',
    transport: 'ws',
    wsTimeoutMs: 8_000,
    restMirror: { method: 'POST', path: '/stock/api/v1/putaway-rules' },
    onSuccess: (ctx) => { rerunLastRequest(ctx, stockPutawayRulesListOp); },
});

export const stockPutawayRuleUpdateOp = createAsyncOp({
    name: 'stock/putaway_rule_update',
    successToastKey: 'stock:toast.putaway_rule_updated',
    errorToastKey: 'stock:toast.putaway_rule_update_failed',
    commandType: 'stock/putaway_rules/update_requested',
    transport: 'ws',
    wsTimeoutMs: 8_000,
    restMirror: { method: 'PATCH', path: '/stock/api/v1/putaway-rules/{rule_id}' },
    onSuccess: (ctx) => { rerunLastRequest(ctx, stockPutawayRulesListOp); },
});

export const stockPutawayRuleDeleteOp = createAsyncOp({
    name: 'stock/putaway_rule_delete',
    successToastKey: 'stock:toast.putaway_rule_deleted',
    errorToastKey: 'stock:toast.putaway_rule_delete_failed',
    commandType: 'stock/putaway_rules/delete_requested',
    transport: 'ws',
    wsTimeoutMs: 8_000,
    restMirror: { method: 'POST', path: '/stock/api/v1/putaway-rules/{rule_id}/delete' },
    onSuccess: (ctx) => { rerunLastRequest(ctx, stockPutawayRulesListOp); },
});

export const stockReorderRulesListOp = createAsyncOp({
    name: 'stock/reorder_rules_list',
    silent: true,
    commandType: 'stock/reorder_rules/list_requested',
    transport: 'ws',
    wsTimeoutMs: 8_000,
    restMirror: { method: 'POST', path: '/stock/api/v1/reorder-rules/list' },
});

export const stockReorderRuleCreateOp = createAsyncOp({
    name: 'stock/reorder_rule_create',
    successToastKey: 'stock:toast.reorder_rule_created',
    errorToastKey: 'stock:toast.reorder_rule_create_failed',
    commandType: 'stock/reorder_rules/create_requested',
    transport: 'ws',
    wsTimeoutMs: 8_000,
    restMirror: { method: 'POST', path: '/stock/api/v1/reorder-rules' },
    onSuccess: (ctx) => { rerunLastRequest(ctx, stockReorderRulesListOp); },
});

export const stockReorderRuleUpdateOp = createAsyncOp({
    name: 'stock/reorder_rule_update',
    successToastKey: 'stock:toast.reorder_rule_updated',
    errorToastKey: 'stock:toast.reorder_rule_update_failed',
    commandType: 'stock/reorder_rules/update_requested',
    transport: 'ws',
    wsTimeoutMs: 8_000,
    restMirror: { method: 'PATCH', path: '/stock/api/v1/reorder-rules/{rule_id}/active' },
    onSuccess: (ctx) => { rerunLastRequest(ctx, stockReorderRulesListOp); },
});

export const stockRoutesListOp = createAsyncOp({
    name: 'stock/routes_list',
    silent: true,
    commandType: 'stock/routes/list_requested',
    transport: 'ws',
    wsTimeoutMs: 8_000,
    restMirror: { method: 'POST', path: '/stock/api/v1/routes/list' },
});

export const stockRouteCreateOp = createAsyncOp({
    name: 'stock/route_create',
    successToastKey: 'stock:toast.route_created',
    errorToastKey: 'stock:toast.route_create_failed',
    commandType: 'stock/routes/create_requested',
    transport: 'ws',
    wsTimeoutMs: 8_000,
    restMirror: { method: 'POST', path: '/stock/api/v1/routes' },
    onSuccess: (ctx) => { rerunLastRequest(ctx, stockRoutesListOp); },
});

export const stockWarehouseUpdateOp = createAsyncOp({
    name: 'stock/warehouse_update',
    successToastKey: 'stock:toast.warehouse_updated',
    errorToastKey: 'stock:toast.warehouse_update_failed',
    commandType: 'stock/warehouses/update_requested',
    transport: 'ws',
    wsTimeoutMs: 8_000,
    restMirror: { method: 'PATCH', path: '/stock/api/v1/warehouses/{warehouse_id}' },
    onSuccess: (ctx) => { reloadLastList(ctx, stockWarehousesResource); },
});

export const stockLocationCreateForm = createForm({
    name: 'stock/location_create_form',
    schema: {
        warehouse_id: { required: true },
        name: { required: true, maxLength: 255 },
        usage: { required: true },
        parent_id: {},
        barcode: { maxLength: 128 },
        pick_sequence: {},
        level: {},
        allow_negative: {},
        storage_type_id: {},
        container_type_id: {},
    },
    initial: {
        warehouse_id: '', name: '', usage: 'bin', parent_id: null,
        barcode: '', pick_sequence: 0, level: 0,
        allow_negative: false, storage_type_id: null, container_type_id: null,
    },
    submitEvent: stockLocationCreateOp.events.REQUESTED,
    submittingClearOnEventTypes: [stockLocationCreateOp.events.SUCCEEDED, stockLocationCreateOp.events.FAILED],
    buildPayload: (draft) => ({
        warehouse_id: typeof draft.warehouse_id === 'string' ? draft.warehouse_id : '',
        name: typeof draft.name === 'string' ? draft.name : '',
        usage: draft.usage === 'view' || draft.usage === 'container' ? draft.usage : 'bin',
        parent_id: typeof draft.parent_id === 'string' && draft.parent_id !== '' ? draft.parent_id : null,
        barcode: typeof draft.barcode === 'string' && draft.barcode !== '' ? draft.barcode : null,
        pick_sequence: Number(draft.pick_sequence) || 0,
        level: Number(draft.level) || 0,
        allow_negative: draft.allow_negative === true,
        storage_type_id: typeof draft.storage_type_id === 'string' && draft.storage_type_id !== '' ? draft.storage_type_id : null,
        container_type_id: draft.usage === 'container' && typeof draft.container_type_id === 'string' && draft.container_type_id !== '' ? draft.container_type_id : null,
    }),
});

export const stockLocationUpdateForm = createForm({
    name: 'stock/location_update_form',
    schema: {
        location_id: { required: true },
        name: { required: true, maxLength: 255 },
        barcode: { maxLength: 128 },
        pick_sequence: {},
        allow_negative: {},
        putaway_blocked: {},
        removal_blocked: {},
        is_active: {},
    },
    initial: {
        location_id: '', name: '', barcode: '', pick_sequence: 0,
        allow_negative: false, putaway_blocked: false, removal_blocked: false, is_active: true,
    },
    submitEvent: stockLocationUpdateOp.events.REQUESTED,
    submittingClearOnEventTypes: [stockLocationUpdateOp.events.SUCCEEDED, stockLocationUpdateOp.events.FAILED],
    buildPayload: (draft) => ({
        location_id: typeof draft.location_id === 'string' ? draft.location_id : '',
        name: typeof draft.name === 'string' ? draft.name : '',
        barcode: typeof draft.barcode === 'string' && draft.barcode !== '' ? draft.barcode : null,
        pick_sequence: Number(draft.pick_sequence) || 0,
        allow_negative: draft.allow_negative === true,
        putaway_blocked: draft.putaway_blocked === true,
        removal_blocked: draft.removal_blocked === true,
        is_active: draft.is_active !== false,
    }),
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
        'stock/valuation_layers_list': typeof stockValuationLayersListOp;
        'stock/valuation_report': typeof stockValuationReportOp;
        'stock/valuation_revalue_form': typeof stockValuationRevalueForm;
        'stock/valuation_correction_form': typeof stockValuationCorrectionForm;
        'stock/product_create': typeof stockProductCreateOp;
        'stock/catalog_products_suggest': typeof stockCatalogProductsSuggestOp;
        'stock/catalog_product_update': typeof stockCatalogProductUpdateOp;
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
        'stock/moves': typeof stockMovesList;
        'stock/containers_list': typeof stockContainersListOp;
        'stock/container_item': typeof stockContainerItemOp;
        'stock/container_create': typeof stockContainerCreateOp;
        'stock/container_move': typeof stockContainerMoveOp;
        'stock/locations_count_due': typeof stockLocationCountDueOp;
        'stock/storage_types_list': typeof stockStorageTypesListOp;
        'stock/storage_type_create': typeof stockStorageTypeCreateOp;
        'stock/storage_type_update': typeof stockStorageTypeUpdateOp;
        'stock/container_types_list': typeof stockContainerTypesListOp;
        'stock/container_type_create': typeof stockContainerTypeCreateOp;
        'stock/container_type_update': typeof stockContainerTypeUpdateOp;
        'stock/resource_types_list': typeof stockResourceTypesListOp;
        'stock/resource_type_create': typeof stockResourceTypeCreateOp;
        'stock/resource_type_update': typeof stockResourceTypeUpdateOp;
        'stock/resources_list': typeof stockResourcesListOp;
        'stock/resource_create': typeof stockResourceCreateOp;
        'stock/resource_update': typeof stockResourceUpdateOp;
        'stock/putaway_rules_list': typeof stockPutawayRulesListOp;
        'stock/putaway_rule_create': typeof stockPutawayRuleCreateOp;
        'stock/putaway_rule_update': typeof stockPutawayRuleUpdateOp;
        'stock/putaway_rule_delete': typeof stockPutawayRuleDeleteOp;
        'stock/reorder_rules_list': typeof stockReorderRulesListOp;
        'stock/reorder_rule_create': typeof stockReorderRuleCreateOp;
        'stock/reorder_rule_update': typeof stockReorderRuleUpdateOp;
        'stock/routes_list': typeof stockRoutesListOp;
        'stock/route_create': typeof stockRouteCreateOp;
        'stock/warehouse_update': typeof stockWarehouseUpdateOp;
        'stock/location_create_form': typeof stockLocationCreateForm;
        'stock/location_update_form': typeof stockLocationUpdateForm;
    }
}
