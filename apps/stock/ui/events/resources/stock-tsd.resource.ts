/**
 * Фабрики ТСД-терминала склада (`/stock/tsd`).
 *
 * `stock/tsd_context` — клиентский контекст оператора: выбранный склад, к
 * которому адресуются очередь заданий и скан-сессии. Сетевого транспорта
 * нет — slice живёт в bus между экранами приложения.
 */

import { createAsyncOp, createSlice } from '@platform/lib/events/index.js';
import { isPlainRecord } from '@platform/lib/events/payload.js';
import type {
    ScanContext,
    ScanResolution,
    StockLocation,
    StockMove,
    StockMoveLineClaimResult,
    StockMoveLineNextResponse,
    StockProductView,
    StockResource,
    StockScanCountCommitResponse,
    StockScanExpected,
    StockScanOpenResponse,
    StockScanStepResponse,
} from '@platform/lib/events/wire/stock.gen.js';

export interface StockOperatorLoginResult {
    user_id: string;
    company_id: string;
    display_name: string;
}

export const stockOperatorLoginOp = createAsyncOp<StockOperatorLoginResult>({
    name: 'stock/operator_login',
    silent: true,
    transport: 'http',
    restMirror: { method: 'POST', path: '/stock/api/auth/login/badge' },
});

export const stockScanStepOp = createAsyncOp<StockScanStepResponse>({
    name: 'stock/scan_step',
    silent: true,
    transport: 'ws',
    wsTimeoutMs: 8_000,
    commandType: 'stock/scan/step_requested',
    restMirror: { method: 'POST', path: '/stock/api/v1/scan/step' },
});

export const stockScanQuantityOp = createAsyncOp<StockScanStepResponse>({
    name: 'stock/scan_quantity',
    silent: true,
    transport: 'ws',
    wsTimeoutMs: 8_000,
    commandType: 'stock/scan/quantity_requested',
    restMirror: { method: 'POST', path: '/stock/api/v1/scan/quantity' },
});

export const stockScanCommitOp = createAsyncOp<StockMove>({
    name: 'stock/scan_commit',
    silent: true,
    transport: 'ws',
    wsTimeoutMs: 15_000,
    commandType: 'stock/scan/commit_requested',
    restMirror: { method: 'POST', path: '/stock/api/v1/scan/commit' },
});

export const stockScanCountCommitOp = createAsyncOp<StockScanCountCommitResponse>({
    name: 'stock/scan_count_commit',
    silent: true,
    transport: 'ws',
    wsTimeoutMs: 15_000,
    commandType: 'stock/scan/count_commit_requested',
    restMirror: { method: 'POST', path: '/stock/api/v1/scan/count-commit' },
});

export const stockMoveLinesNextOp = createAsyncOp<StockMoveLineNextResponse>({
    name: 'stock/move_lines_next',
    silent: true,
    transport: 'ws',
    wsTimeoutMs: 10_000,
    commandType: 'stock/move_lines/next_requested',
    restMirror: { method: 'POST', path: '/stock/api/v1/move-lines/next' },
});

export const stockMoveLinesClaimOp = createAsyncOp<StockMoveLineClaimResult>({
    name: 'stock/move_lines_claim',
    silent: true,
    transport: 'ws',
    wsTimeoutMs: 10_000,
    commandType: 'stock/move_lines/claim_requested',
    restMirror: { method: 'POST', path: '/stock/api/v1/move-lines/claim' },
});

export const stockMoveLinesReleaseOp = createAsyncOp<StockMoveLineClaimResult>({
    name: 'stock/move_lines_release',
    silent: true,
    transport: 'ws',
    wsTimeoutMs: 10_000,
    commandType: 'stock/move_lines/release_requested',
    restMirror: { method: 'POST', path: '/stock/api/v1/move-lines/release' },
});

export const stockMoveLinesAssignOp = createAsyncOp<StockMoveLineClaimResult>({
    name: 'stock/move_lines_assign',
    silent: true,
    transport: 'ws',
    wsTimeoutMs: 10_000,
    commandType: 'stock/move_lines/assign_requested',
    restMirror: { method: 'POST', path: '/stock/api/v1/move-lines/assign' },
});

export const stockScanOpenOp = createAsyncOp<StockScanOpenResponse>({
    name: 'stock/scan_open',
    silent: true,
    transport: 'ws',
    wsTimeoutMs: 8_000,
    commandType: 'stock/scan/open_requested',
    restMirror: { method: 'POST', path: '/stock/api/v1/scan/open' },
});

export const stockProductItemOp = createAsyncOp<StockProductView>({
    name: 'stock/product_item',
    silent: true,
    transport: 'ws',
    wsTimeoutMs: 8_000,
    commandType: 'stock/products/item_requested',
    restMirror: { method: 'GET', path: '/stock/api/v1/products/{product_id}' },
});

export const stockLocationItemOp = createAsyncOp<StockLocation>({
    name: 'stock/location_item',
    silent: true,
    transport: 'ws',
    wsTimeoutMs: 8_000,
    commandType: 'stock/locations/item_requested',
    restMirror: { method: 'GET', path: '/stock/api/v1/locations/{location_id}' },
});

export interface StockTsdSessionState extends Record<string, unknown> {
    context: ScanContext | null;
    resolution: ScanResolution | null;
    last_barcode: string;
    outcome: '' | 'ok' | 'error';
    hint: string;
    move_id: string;
    expected: StockScanExpected | null;
}

function _requireScanContext(payload: Record<string, unknown>, action: string): ScanContext {
    const context = payload.context;
    if (!isPlainRecord(context)) {
        throw new Error(`stock/tsd_session.${action}: context required`);
    }
    return context as unknown as ScanContext;
}

export const stockTsdSessionSlice = createSlice<StockTsdSessionState, {
    stepApplied: string;
    scanRejected: string;
    runOpened: string;
    sessionCleared: string;
}>({
    name: 'stock/tsd_session',
    extraInitial: {
        context: null,
        resolution: null,
        last_barcode: '',
        outcome: '',
        hint: '',
        move_id: '',
        expected: null,
    },
    extraEvents: {
        STEP_APPLIED: 'step_applied',
        SCAN_REJECTED: 'scan_rejected',
        RUN_OPENED: 'run_opened',
        SESSION_CLEARED: 'session_cleared',
    },
    actions: {
        stepApplied: 'step_applied',
        scanRejected: 'scan_rejected',
        runOpened: 'run_opened',
        sessionCleared: 'session_cleared',
    },
    extraReducer: (state, event, events) => {
        if (event.type === events.STEP_APPLIED) {
            const payload = event.payload;
            if (!isPlainRecord(payload)) {
                throw new Error('stock/tsd_session.stepApplied: payload required');
            }
            const context = _requireScanContext(payload, 'stepApplied');
            const resolution = isPlainRecord(payload.resolution) ? (payload.resolution as unknown as ScanResolution) : null;
            const barcode = typeof payload.barcode === 'string' ? payload.barcode : '';
            const error = typeof payload.error === 'string' ? payload.error : null;
            const hint = typeof payload.hint === 'string' ? payload.hint : '';
            const expected = isPlainRecord(payload.expected) ? (payload.expected as unknown as StockScanExpected) : state.expected;
            return {
                ...state,
                context,
                resolution,
                last_barcode: barcode,
                outcome: error !== null ? 'error' : 'ok',
                hint: error ?? hint,
                expected,
            };
        }
        if (event.type === events.SCAN_REJECTED) {
            const payload = event.payload;
            if (!isPlainRecord(payload)) {
                throw new Error('stock/tsd_session.scanRejected: payload required');
            }
            const barcode = typeof payload.barcode === 'string' ? payload.barcode : '';
            const hint = typeof payload.hint === 'string' ? payload.hint : '';
            return { ...state, last_barcode: barcode, outcome: 'error', hint };
        }
        if (event.type === events.RUN_OPENED) {
            const payload = event.payload;
            if (!isPlainRecord(payload)) {
                throw new Error('stock/tsd_session.runOpened: payload required');
            }
            const context = _requireScanContext(payload, 'runOpened');
            const moveId = payload.move_id;
            if (typeof moveId !== 'string' || moveId === '') {
                throw new Error('stock/tsd_session.runOpened: move_id required');
            }
            const expected = isPlainRecord(payload.expected) ? (payload.expected as unknown as StockScanExpected) : null;
            return {
                ...state,
                context,
                resolution: null,
                last_barcode: '',
                outcome: '',
                hint: '',
                move_id: moveId,
                expected,
            };
        }
        if (event.type === events.SESSION_CLEARED) {
            return { ...state, context: null, resolution: null, last_barcode: '', outcome: '', hint: '', move_id: '', expected: null };
        }
        return null;
    },
});

export const stockResourceLoginOp = createAsyncOp<StockResource>({
    name: 'stock/resource_login',
    silent: true,
    transport: 'ws',
    wsTimeoutMs: 8_000,
    commandType: 'stock/resources/login_requested',
    restMirror: { method: 'POST', path: '/stock/api/v1/resources/login' },
});

export interface StockTsdContextState extends Record<string, unknown> {
    warehouse_id: string;
    warehouse_name: string;
    zone_location_id: string;
    zone_code: string;
    resource_id: string;
    resource_code: string;
}

function _requireString(payload: Record<string, unknown>, field: string, action: string): string {
    const value = payload[field];
    if (typeof value !== 'string' || value === '') {
        throw new Error(`stock/tsd_context.${action}: ${field} required`);
    }
    return value;
}

export const stockTsdContextSlice = createSlice<StockTsdContextState, {
    setWarehouse: string;
    setZone: string;
    setResource: string;
    resetContext: string;
}>({
    name: 'stock/tsd_context',
    extraInitial: {
        warehouse_id: '',
        warehouse_name: '',
        zone_location_id: '',
        zone_code: '',
        resource_id: '',
        resource_code: '',
    },
    extraEvents: {
        WAREHOUSE_SET: 'warehouse_set',
        ZONE_SET: 'zone_set',
        RESOURCE_SET: 'resource_set',
        CONTEXT_RESET: 'context_reset',
    },
    actions: {
        setWarehouse: 'warehouse_set',
        setZone: 'zone_set',
        setResource: 'resource_set',
        resetContext: 'context_reset',
    },
    extraReducer: (state, event, events) => {
        if (event.type === events.WAREHOUSE_SET) {
            const payload = event.payload;
            if (!isPlainRecord(payload)) {
                throw new Error('stock/tsd_context.setWarehouse: payload required');
            }
            return {
                ...state,
                warehouse_id: _requireString(payload, 'warehouse_id', 'setWarehouse'),
                warehouse_name: _requireString(payload, 'warehouse_name', 'setWarehouse'),
                zone_location_id: '',
                zone_code: '',
                resource_id: '',
                resource_code: '',
            };
        }
        if (event.type === events.ZONE_SET) {
            const payload = event.payload;
            if (!isPlainRecord(payload)) {
                throw new Error('stock/tsd_context.setZone: payload required');
            }
            return {
                ...state,
                zone_location_id: _requireString(payload, 'zone_location_id', 'setZone'),
                zone_code: _requireString(payload, 'zone_code', 'setZone'),
            };
        }
        if (event.type === events.RESOURCE_SET) {
            const payload = event.payload;
            if (!isPlainRecord(payload)) {
                throw new Error('stock/tsd_context.setResource: payload required');
            }
            return {
                ...state,
                resource_id: _requireString(payload, 'resource_id', 'setResource'),
                resource_code: _requireString(payload, 'resource_code', 'setResource'),
            };
        }
        if (event.type === events.CONTEXT_RESET) {
            return {
                ...state,
                warehouse_id: '',
                warehouse_name: '',
                zone_location_id: '',
                zone_code: '',
                resource_id: '',
                resource_code: '',
            };
        }
        return null;
    },
});

declare module '@platform/lib/events/factory-registry.js' {
    interface PlatformFactoryRegistry {
        'stock/tsd_context': typeof stockTsdContextSlice;
        'stock/tsd_session': typeof stockTsdSessionSlice;
        'stock/operator_login': typeof stockOperatorLoginOp;
        'stock/resource_login': typeof stockResourceLoginOp;
        'stock/move_lines_next': typeof stockMoveLinesNextOp;
        'stock/move_lines_claim': typeof stockMoveLinesClaimOp;
        'stock/move_lines_release': typeof stockMoveLinesReleaseOp;
        'stock/move_lines_assign': typeof stockMoveLinesAssignOp;
        'stock/scan_open': typeof stockScanOpenOp;
        'stock/product_item': typeof stockProductItemOp;
        'stock/location_item': typeof stockLocationItemOp;
        'stock/scan_step': typeof stockScanStepOp;
        'stock/scan_quantity': typeof stockScanQuantityOp;
        'stock/scan_commit': typeof stockScanCommitOp;
        'stock/scan_count_commit': typeof stockScanCountCommitOp;
    }
}
