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
    StockMoveLineExceptionResult,
    StockMoveLineNextResponse,
    StockOperatorPulseResponse,
    StockProductView,
    StockPutawaySuggestResponse,
    StockResource,
    StockScanCountCommitResponse,
    StockScanExpected,
    StockScanOpenResponse,
    StockScanStepResponse,
    StockTransfer,
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
    request: async ({ payload }) => {
        const { httpRequest } = await import('@platform/lib/events/http.js');
        return (await httpRequest({ method: 'POST', url: '/stock/api/auth/login/badge', body: payload })) as StockOperatorLoginResult;
    },
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

export const stockScanAdhocCommitOp = createAsyncOp<StockTransfer>({
    name: 'stock/scan_adhoc_commit',
    silent: true,
    transport: 'ws',
    wsTimeoutMs: 15_000,
    commandType: 'stock/scan/adhoc_commit_requested',
    restMirror: { method: 'POST', path: '/stock/api/v1/scan/adhoc-commit' },
});

export const stockPutawaySuggestOp = createAsyncOp<StockPutawaySuggestResponse>({
    name: 'stock/putaway_suggest',
    silent: true,
    transport: 'ws',
    wsTimeoutMs: 8_000,
    commandType: 'stock/putaway/suggest_requested',
    restMirror: { method: 'POST', path: '/stock/api/v1/putaway/suggest' },
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

export const stockOperatorPulseOp = createAsyncOp<StockOperatorPulseResponse>({
    name: 'stock/operator_pulse',
    silent: true,
    transport: 'ws',
    wsTimeoutMs: 8_000,
    commandType: 'stock/operator/pulse_requested',
    restMirror: { method: 'GET', path: '/stock/api/v1/warehouses/{warehouse_id}/operator-pulse' },
});

export const stockMoveLinesExceptionOp = createAsyncOp<StockMoveLineExceptionResult>({
    name: 'stock/move_lines_exception',
    silent: true,
    transport: 'ws',
    wsTimeoutMs: 8_000,
    commandType: 'stock/move_lines/report_exception_requested',
    restMirror: { method: 'POST', path: '/stock/api/v1/move-lines/report-exception' },
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
    error: string | null;
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
    lineRemoved: string;
    sessionCleared: string;
    sessionHydrated: string;
}>({
    name: 'stock/tsd_session',
    extraInitial: {
        context: null,
        resolution: null,
        last_barcode: '',
        outcome: '',
        hint: '',
        error: null,
        move_id: '',
        expected: null,
    },
    extraEvents: {
        STEP_APPLIED: 'step_applied',
        SCAN_REJECTED: 'scan_rejected',
        RUN_OPENED: 'run_opened',
        LINE_REMOVED: 'line_removed',
        SESSION_CLEARED: 'session_cleared',
        SESSION_HYDRATED: 'session_hydrated',
    },
    actions: {
        stepApplied: 'step_applied',
        scanRejected: 'scan_rejected',
        runOpened: 'run_opened',
        lineRemoved: 'line_removed',
        sessionCleared: 'session_cleared',
        sessionHydrated: 'session_hydrated',
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
                hint,
                error,
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
            return { ...state, last_barcode: barcode, outcome: 'error', hint, error: null };
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
                error: null,
                move_id: moveId,
                expected,
            };
        }
        if (event.type === events.LINE_REMOVED) {
            // Удаление набранной строки на review — контекст живёт
            // в терминале, леджер ещё не тронут: чистая правка сессии.
            const payload = event.payload;
            if (!isPlainRecord(payload) || typeof payload.index !== 'number') {
                throw new Error('stock/tsd_session.lineRemoved: index required');
            }
            const context = state.context;
            if (context === null || context.step !== 'review') return null;
            const lines = Array.isArray(context.lines) ? context.lines : [];
            if (payload.index < 0 || payload.index >= lines.length) return null;
            return {
                ...state,
                context: {
                    ...context,
                    lines: lines.filter((_, idx) => idx !== payload.index),
                },
            };
        }
        if (event.type === events.SESSION_HYDRATED) {
            // Восстановление после перезагрузки терминала: контекст
            // stateless — набранные строки возвращаются как есть,
            // expected пересчитает следующий scan_step.
            const payload = event.payload;
            if (!isPlainRecord(payload)) {
                throw new Error('stock/tsd_session.sessionHydrated: payload required');
            }
            const context = isPlainRecord(payload.context) ? (payload.context as unknown as ScanContext) : null;
            if (context === null) {
                return { ...state, context: null, resolution: null, last_barcode: '', outcome: '', hint: '', error: null, move_id: '', expected: null };
            }
            const moveId = typeof payload.move_id === 'string' ? payload.move_id : '';
            return { ...state, context, resolution: null, last_barcode: '', outcome: '', hint: '', error: null, move_id: moveId, expected: null };
        }
        if (event.type === events.SESSION_CLEARED) {
            return { ...state, context: null, resolution: null, last_barcode: '', outcome: '', hint: '', error: null, move_id: '', expected: null };
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
    wave_id: string;
    wave_name: string;
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
    setWave: string;
    resetContext: string;
    contextHydrated: string;
}>({
    name: 'stock/tsd_context',
    extraInitial: {
        warehouse_id: '',
        warehouse_name: '',
        zone_location_id: '',
        zone_code: '',
        resource_id: '',
        resource_code: '',
        wave_id: '',
        wave_name: '',
    },
    extraEvents: {
        WAREHOUSE_SET: 'warehouse_set',
        ZONE_SET: 'zone_set',
        RESOURCE_SET: 'resource_set',
        WAVE_SET: 'wave_set',
        CONTEXT_RESET: 'context_reset',
        CONTEXT_HYDRATED: 'context_hydrated',
    },
    actions: {
        setWarehouse: 'warehouse_set',
        setZone: 'zone_set',
        setResource: 'resource_set',
        setWave: 'wave_set',
        resetContext: 'context_reset',
        contextHydrated: 'context_hydrated',
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
                wave_id: '',
                wave_name: '',
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
        if (event.type === events.WAVE_SET) {
            const payload = event.payload;
            if (!isPlainRecord(payload)) {
                throw new Error('stock/tsd_context.setWave: payload required');
            }
            return {
                ...state,
                wave_id: _requireString(payload, 'wave_id', 'setWave'),
                wave_name: _requireString(payload, 'wave_name', 'setWave'),
            };
        }
        if (event.type === events.CONTEXT_HYDRATED) {
            // Терминал привязан к месту: склад/зона/техника/волна
            // восстанавливаются после перезагрузки — оператор не
            // выбирает их заново на том же рабочем месте.
            const payload = event.payload;
            if (!isPlainRecord(payload)) {
                throw new Error('stock/tsd_context.contextHydrated: payload required');
            }
            const read = (field: string): string =>
                typeof payload[field] === 'string' ? payload[field] as string : '';
            return {
                ...state,
                warehouse_id: read('warehouse_id'),
                warehouse_name: read('warehouse_name'),
                zone_location_id: read('zone_location_id'),
                zone_code: read('zone_code'),
                resource_id: read('resource_id'),
                resource_code: read('resource_code'),
                wave_id: read('wave_id'),
                wave_name: read('wave_name'),
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
                wave_id: '',
                wave_name: '',
            };
        }
        return null;
    },
});

/**
 * Офлайн-outbox ТСД: команды с леджер-эффектом, поставленные в очередь
 * в мёртвой зоне (подвал, дальний угол). `idempotency_key` фиксируется
 * при постановке — повторы replay и ручные ретраи дедуплируются
 * backend'ом, двойной проводки нет. Персист — `tsd-persist.effect`.
 */
export interface TsdOutboxItem {
    outbox_id: string;
    op: string;
    payload: Record<string, unknown>;
    enqueued_at: string;
    attempts: number;
    last_error: string;
}

export interface StockTsdOutboxState extends Record<string, unknown> {
    items: TsdOutboxItem[];
}

export const TSD_OUTBOX_OPS = new Set([
    'stock/scan_commit',
    'stock/scan_count_commit',
    'stock/scan_adhoc_commit',
    'stock/move_lines_exception',
    'stock/container_move',
]);

export const TSD_OUTBOX_LIMIT = 50;

export function tsdOutboxId(): string {
    return typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function'
        ? crypto.randomUUID()
        : `obx-${Date.now()}-${Math.floor(Math.random() * 1e9)}`;
}

/** Постановка в outbox: ключ идемпотентности фиксируется до первой попытки отправки. */
export function tsdOutboxItem(op: string, payload: Record<string, unknown>): TsdOutboxItem {
    const body = { ...payload };
    if (body.idempotency_key === null || body.idempotency_key === undefined) {
        body.idempotency_key = tsdOutboxId();
    }
    return {
        outbox_id: tsdOutboxId(),
        op,
        payload: body,
        enqueued_at: new Date().toISOString(),
        attempts: 0,
        last_error: '',
    };
}

export function tsdOffline(): boolean {
    return typeof navigator !== 'undefined' && navigator.onLine === false;
}

export const stockTsdOutboxSlice = createSlice<StockTsdOutboxState, {
    enqueued: string;
    delivered: string;
    attemptFailed: string;
    dropped: string;
    hydrated: string;
}>({
    name: 'stock/tsd_outbox',
    extraInitial: { items: [] },
    extraEvents: {
        ENQUEUED: 'outbox_enqueued',
        DELIVERED: 'outbox_delivered',
        ATTEMPT_FAILED: 'outbox_attempt_failed',
        DROPPED: 'outbox_dropped',
        HYDRATED: 'outbox_hydrated',
    },
    actions: {
        enqueued: 'outbox_enqueued',
        delivered: 'outbox_delivered',
        attemptFailed: 'outbox_attempt_failed',
        dropped: 'outbox_dropped',
        hydrated: 'outbox_hydrated',
    },
    extraReducer: (state, event, events) => {
        if (event.type === events.ENQUEUED) {
            const item = event.payload;
            if (!isPlainRecord(item)) {
                throw new Error('stock/tsd_outbox.enqueued: item required');
            }
            if (typeof item.outbox_id !== 'string' || item.outbox_id === '') {
                throw new Error('stock/tsd_outbox.enqueued: outbox_id required');
            }
            if (typeof item.op !== 'string' || !TSD_OUTBOX_OPS.has(item.op)) {
                throw new Error('stock/tsd_outbox.enqueued: op not queueable');
            }
            if (!isPlainRecord(item.payload)) {
                throw new Error('stock/tsd_outbox.enqueued: payload required');
            }
            if (state.items.length >= TSD_OUTBOX_LIMIT) {
                throw new Error('stock/tsd_outbox.enqueued: queue full');
            }
            const next: TsdOutboxItem = {
                outbox_id: item.outbox_id,
                op: item.op,
                payload: item.payload,
                enqueued_at: typeof item.enqueued_at === 'string' ? item.enqueued_at : '',
                attempts: typeof item.attempts === 'number' ? item.attempts : 0,
                last_error: typeof item.last_error === 'string' ? item.last_error : '',
            };
            return { ...state, items: [...state.items, next] };
        }
        if (event.type === events.DELIVERED || event.type === events.DROPPED) {
            const outboxId = event.payload;
            if (typeof outboxId !== 'string' || outboxId === '') {
                throw new Error(`stock/tsd_outbox.${event.type}: outbox_id required`);
            }
            return {
                ...state,
                items: state.items.filter((item) => item.outbox_id !== outboxId),
            };
        }
        if (event.type === events.ATTEMPT_FAILED) {
            const payload = event.payload;
            if (!isPlainRecord(payload)) {
                throw new Error('stock/tsd_outbox.attemptFailed: payload required');
            }
            const outboxId = typeof payload.outbox_id === 'string' ? payload.outbox_id : '';
            const error = typeof payload.error === 'string' ? payload.error : 'unknown';
            return {
                ...state,
                items: state.items.map((item) =>
                    item.outbox_id === outboxId
                        ? { ...item, attempts: item.attempts + 1, last_error: error }
                        : item,
                ),
            };
        }
        if (event.type === events.HYDRATED) {
            const payload = event.payload;
            if (!isPlainRecord(payload) || !Array.isArray(payload.items)) {
                throw new Error('stock/tsd_outbox.hydrated: items required');
            }
            const items = payload.items.filter(
                (entry): entry is TsdOutboxItem =>
                    isPlainRecord(entry)
                    && typeof entry.outbox_id === 'string'
                    && typeof entry.op === 'string'
                    && TSD_OUTBOX_OPS.has(entry.op)
                    && isPlainRecord(entry.payload),
            );
            return { ...state, items: items.slice(0, TSD_OUTBOX_LIMIT) };
        }
        return null;
    },
});

declare module '@platform/lib/events/factory-registry.js' {
    interface PlatformFactoryRegistry {
        'stock/tsd_context': typeof stockTsdContextSlice;
        'stock/tsd_session': typeof stockTsdSessionSlice;
        'stock/tsd_outbox': typeof stockTsdOutboxSlice;
        'stock/operator_login': typeof stockOperatorLoginOp;
        'stock/resource_login': typeof stockResourceLoginOp;
        'stock/move_lines_next': typeof stockMoveLinesNextOp;
        'stock/move_lines_claim': typeof stockMoveLinesClaimOp;
        'stock/move_lines_release': typeof stockMoveLinesReleaseOp;
        'stock/move_lines_assign': typeof stockMoveLinesAssignOp;
        'stock/move_lines_exception': typeof stockMoveLinesExceptionOp;
        'stock/operator_pulse': typeof stockOperatorPulseOp;
        'stock/scan_open': typeof stockScanOpenOp;
        'stock/product_item': typeof stockProductItemOp;
        'stock/location_item': typeof stockLocationItemOp;
        'stock/scan_step': typeof stockScanStepOp;
        'stock/scan_quantity': typeof stockScanQuantityOp;
        'stock/scan_commit': typeof stockScanCommitOp;
        'stock/scan_count_commit': typeof stockScanCountCommitOp;
        'stock/scan_adhoc_commit': typeof stockScanAdhocCommitOp;
        'stock/putaway_suggest': typeof stockPutawaySuggestOp;
    }
}
