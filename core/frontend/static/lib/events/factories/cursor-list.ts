/**
 * createКурсорList — фабрика cursor-paginated списка.
 *
 * Назначение: tracing/spans, leads list, usage-report и любые другие домены,
 * где BE возвращает `{ items, next_cursor, has_more }` и фильтры формируются
 * клиентом.
 *
 * Контракт:
 *   - name: 'scope/entity'
 *   - baseUrl: HTTP-префикс (без trailing slash). Для transport='ws'
 *     используется как идентификатор ресурса, не как URL.
 *   - buildQuery(filters): обязательно, чистая функция → query-объект
 *   - pageSize: обязательное число
 *   - restMirror: { method: 'GET', path } — обязательный платформенный
 *     инвариант REST-зеркала.
 *   - transport: 'http' | 'ws' (default 'http'). Для 'ws' обязателен
 *     wsTimeoutMs (положительное число). WS-payload команды — тот же плоский
 *     query, что уходит в REST-зеркало (`{ ...buildQuery(filters), limit, cursor? }`);
 *     `append` — клиентский флаг и на бэкенд не передаётся.
 *   - commandType: '<scope>/<entity>/<verb>_requested' — тип WS-команды
 *     (default `${name}/load_requested`); reply-типы выводятся как
 *     `<commandType без _requested>_succeeded` / `_failed`.
 *   - statusMap: { 403: 'forbidden', 503: 'unavailable', ... } — опционально;
 *     каждый код → имя терминального события (генерируется как
 *     `${name}/${terminalKey}`). Для transport='ws' `*_failed` несёт
 *     `error_code` (`forbidden`, `unavailable`, ...) — фабрика мапит его на
 *     тот же терминальный ключ.
 *   - errorToastKey: опционально; если задан — на FAILED показываем toast.
 *   - extraReducer(state, event, events) — после базового reducer (push merge).
 *   - extraEffect(event, ctx, events) — до базового effect; return true = handled.
 */

import { CoreEvents } from '../contract.js';
import { httpRequest, HttpError } from '../http.js';
import {
    assertResourceName,
    deriveSliceKey,
    buildEventType,
    registerResourceName,
    freeze,
    requireField,
    requireFunction,
    requireI18nKey,
} from './_internal.js';
import {
    WsTransportError,
    normalizeRestMirrorSingle,
    normalizeTransport,
    normalizeWsTimeout,
    transportRequest,
} from './_transport.js';
import type { EffectCtx, PlatformEvent } from '../contract.js';
import type { PlatformFactory } from '../factory-registry.js';
import type { SliceDef } from '../reducers/index.js';
import type { FactoryTransport, RestMirrorEntry } from './_transport.js';

const _REQUESTED_SUFFIX = '_requested';

// Соответствие HTTP-статусов REST-зеркала кодам `error_code` WS `*_failed`
// (`WS_COMMAND_ERROR_HTTP_STATUS` в core/websocket/operation.py).
const _WS_CODE_BY_HTTP_STATUS: Readonly<Record<string, string>> = freeze({
    400: 'ws_invalid_payload',
    403: 'forbidden',
    404: 'not_found',
    409: 'conflict',
    500: 'internal',
    502: 'upstream',
    503: 'unavailable',
});

function _normalizeCommandType(value: unknown, name: string, transport: FactoryTransport): string {
    if (value === undefined || value === null) {
        return buildEventType(name, 'load_requested');
    }
    if (transport !== 'ws') {
        throw new Error(`createCursorList(${name}): commandType is allowed only with transport='ws'`);
    }
    if (typeof value !== 'string' || !value.endsWith(_REQUESTED_SUFFIX)) {
        throw new Error(`createCursorList(${name}): commandType must be a string ending with "_requested"`);
    }
    return value;
}

function _deriveReplyType(commandType: string, replySuffix: string): string {
    return commandType.slice(0, -_REQUESTED_SUFFIX.length) + replySuffix;
}

export interface CursorListSlice {
    items: readonly unknown[];
    nextCursor: string | null;
    hasMore: boolean;
    loading: boolean;
    loadingMore: boolean;
    error: string | null;
    terminal: string | null;
    filters: Readonly<Record<string, unknown>>;
    [key: string]: unknown;
}

interface _ListPayload {
    items: unknown[];
    next_cursor: string | null;
    has_more: boolean;
    [key: string]: unknown;
}

export interface CursorListOptions {
    name: string;
    baseUrl: string;
    buildQuery: (filters: Record<string, unknown>) => Record<string, unknown>;
    pageSize: number;
    restMirror?: RestMirrorEntry | { method: string; path: string };
    transport?: FactoryTransport;
    wsTimeoutMs?: number;
    commandType?: string | null;
    httpMethod?: string;
    statusMap?: Record<string, string>;
    initialFilters?: Record<string, unknown>;
    errorToastKey?: string | null;
    extraReducer?: (state: CursorListSlice, event: PlatformEvent, events: Readonly<Record<string, string>>) => CursorListSlice | null | undefined;
    extraEffect?: (event: PlatformEvent, ctx: EffectCtx, events: Readonly<Record<string, string>>) => boolean | void | Promise<boolean | void>;
    sliceKey?: string;
}

export interface CursorListFactory extends PlatformFactory {
    kind: 'cursor-list';
    name: string;
    sliceKey: string;
    baseUrl: string;
    transport: FactoryTransport;
    restMirror: Readonly<RestMirrorEntry>;
    commandType: string;
    pageSize: number;
    events: Readonly<Record<string, string>> & { LOAD_REQUESTED: string; LOADED: string; PAGE_LOADED: string; FAILED: string; FILTERS_CHANGED: string; FILTERS_RESET: string };
    reducer: (state: CursorListSlice | undefined, event: PlatformEvent) => CursorListSlice;
    slice: SliceDef<CursorListSlice>;
    selectors: {
        slice: (state: Record<string, unknown>) => CursorListSlice;
        items: (state: Record<string, unknown>) => readonly unknown[];
        nextCursor: (state: Record<string, unknown>) => string | null;
        hasMore: (state: Record<string, unknown>) => boolean;
        loading: (state: Record<string, unknown>) => boolean;
        loadingMore: (state: Record<string, unknown>) => boolean;
        error: (state: Record<string, unknown>) => string | null;
        terminal: (state: Record<string, unknown>) => string | null;
        filters: (state: Record<string, unknown>) => Readonly<Record<string, unknown>>;
    };
    effect: (event: PlatformEvent, ctx: EffectCtx) => Promise<void>;
}

export function createCursorList(options: CursorListOptions): CursorListFactory {
    if (!options || typeof options !== 'object') {
        throw new Error('createCursorList: options object required');
    }
    const name = requireField(options, 'name', 'createCursorList');
    assertResourceName(name);
    const baseUrl = requireField(options, 'baseUrl', `createCursorList(${name})`);
    const buildQuery = requireFunction<CursorListOptions['buildQuery']>(requireField(options, 'buildQuery', `createCursorList(${name})`), `createCursorList(${name}).buildQuery`);
    const pageSize = requireField(options, 'pageSize', `createCursorList(${name})`);
    if (typeof pageSize !== 'number' || pageSize <= 0) {
        throw new Error(`createCursorList(${name}): pageSize must be positive number`);
    }
    const transport = normalizeTransport(options.transport, `createCursorList(${name})`);
    const wsTimeoutMs = normalizeWsTimeout(options.wsTimeoutMs, transport, `createCursorList(${name})`);
    const commandType = _normalizeCommandType(options.commandType, name, transport);
    const httpMethod = typeof options.httpMethod === 'string' ? options.httpMethod.toUpperCase() : 'GET';
    if (httpMethod !== 'GET' && httpMethod !== 'POST') {
        throw new Error(`createCursorList(${name}): httpMethod must be 'GET' or 'POST'`);
    }
    const restMirrorInput = options.restMirror || { method: httpMethod, path: baseUrl };
    const restMirror = normalizeRestMirrorSingle(restMirrorInput, `createCursorList(${name})`);
    if (restMirror.method !== 'GET' && restMirror.method !== 'POST') {
        throw new Error(`createCursorList(${name}): restMirror.method must be GET or POST (cursor lists are read-only)`);
    }
    const statusMap: Record<string, string> = options.statusMap && typeof options.statusMap === 'object' ? options.statusMap : {};
    const initialFilters = options.initialFilters && typeof options.initialFilters === 'object'
        ? options.initialFilters
        : {};
    const errorToastKey = options.errorToastKey || null;
    if (errorToastKey) {
        requireI18nKey(errorToastKey, `createCursorList(${name}).errorToastKey`);
    }
    const extraReducer = typeof options.extraReducer === 'function' ? options.extraReducer : null;
    const extraEffect = typeof options.extraEffect === 'function' ? options.extraEffect : null;

    const sliceKey = options.sliceKey || deriveSliceKey(name);
    registerResourceName(name, 'cursor-list');

    const baseEvents = {
        LOAD_REQUESTED:    buildEventType(name, 'load_requested'),
        LOADED:            buildEventType(name, 'loaded'),
        PAGE_LOADED:       buildEventType(name, 'page_loaded'),
        FAILED:            buildEventType(name, 'failed'),
        FILTERS_CHANGED:   buildEventType(name, 'filters_changed'),
        FILTERS_RESET:     buildEventType(name, 'filters_reset'),
    };
    const terminalEvents: Record<string, string> = {};
    const wsCodeTerminalKeys: Record<string, string> = {};
    for (const [code, key] of Object.entries(statusMap)) {
        if (typeof key !== 'string' || key.length === 0) {
            throw new Error(`createCursorList(${name}): statusMap[${code}] must be non-empty string`);
        }
        terminalEvents[key.toUpperCase()] = buildEventType(name, `${key}`);
        const wsCode = _WS_CODE_BY_HTTP_STATUS[code];
        if (wsCode) wsCodeTerminalKeys[wsCode] = key;
    }
    const events = freeze({ ...baseEvents, ...terminalEvents });

    const initialSlice: CursorListSlice = freeze({
        items: freeze([] as unknown[]),
        nextCursor: null,
        hasMore: false,
        loading: false,
        loadingMore: false,
        error: null,
        terminal: null,
        filters: freeze({ ...initialFilters }),
    });

    function _baseReducer(state: CursorListSlice, event: PlatformEvent): CursorListSlice {
        switch (event.type) {
            case events.LOAD_REQUESTED: {
                _assertObjectPayload(event, 'LOAD_REQUESTED');
                const append = (event.payload as Record<string, unknown>).append === true;
                return freeze({
                    ...state,
                    loading: !append,
                    loadingMore: append,
                    error: null,
                    terminal: null,
                });
            }
            case events.LOADED: {
                _assertListPayload(event, 'LOADED');
                const p = event.payload as unknown as _ListPayload;
                return freeze({
                    ...state,
                    items: freeze(p.items),
                    nextCursor: p.next_cursor,
                    hasMore: p.has_more === true,
                    loading: false,
                    loadingMore: false,
                    error: null,
                    terminal: null,
                });
            }
            case events.PAGE_LOADED: {
                _assertListPayload(event, 'PAGE_LOADED');
                const p = event.payload as unknown as _ListPayload;
                return freeze({
                    ...state,
                    items: freeze([...state.items, ...p.items]),
                    nextCursor: p.next_cursor,
                    hasMore: p.has_more === true,
                    loadingMore: false,
                });
            }
            case events.FAILED: {
                const p = event.payload as { message?: unknown } | null;
                if (!p || typeof p.message !== 'string') {
                    throw new Error(`createCursorList(${name}): FAILED payload must include "message" (string)`);
                }
                return freeze({
                    ...state,
                    loading: false,
                    loadingMore: false,
                    error: p.message,
                });
            }
            case events.FILTERS_CHANGED: {
                const p = event.payload as { filters?: unknown } | null;
                if (!p || !p.filters || typeof p.filters !== 'object') {
                    throw new Error(`createCursorList(${name}): FILTERS_CHANGED payload.filters required (object)`);
                }
                return freeze({ ...state, filters: freeze({ ...state.filters, ...(p.filters as Record<string, unknown>) }) });
            }
            case events.FILTERS_RESET:
                return freeze({ ...state, filters: freeze({ ...initialFilters }) });
            default:
                if (Object.values(terminalEvents).includes(event.type)) {
                    const terminalKey = Object.entries(terminalEvents).find(([, t]) => t === event.type)![0].toLowerCase();
                    return freeze({
                        ...state,
                        loading: false,
                        loadingMore: false,
                        items: freeze([]),
                        nextCursor: null,
                        hasMore: false,
                        terminal: terminalKey,
                        error: null,
                    });
                }
                return state;
        }
    }

    function reducer(state: CursorListSlice = initialSlice, event: PlatformEvent): CursorListSlice {
        const next = _baseReducer(state, event);
        if (extraReducer) {
            const extended = extraReducer(next, event, events);
            if (extended && extended !== next) {
                return freeze(extended);
            }
        }
        return next;
    }

    function _assertObjectPayload(event: PlatformEvent, eventKey: string): void {
        if (event.payload === undefined || event.payload === null || typeof event.payload !== 'object') {
            throw new Error(`createCursorList(${name}): ${eventKey} payload must be object`);
        }
    }

    function _assertListPayload(event: PlatformEvent, eventKey: string): void {
        const p = event.payload as { items?: unknown } | null;
        if (!p || !Array.isArray(p.items)) {
            throw new Error(`createCursorList(${name}): ${eventKey} payload.items must be array`);
        }
        if (!('next_cursor' in p)) {
            throw new Error(`createCursorList(${name}): ${eventKey} payload.next_cursor required (string|null)`);
        }
        if (!('has_more' in p)) {
            throw new Error(`createCursorList(${name}): ${eventKey} payload.has_more required (boolean)`);
        }
    }

    function _readSlice(state: Record<string, unknown>): CursorListSlice {
        const slice = state[sliceKey] as CursorListSlice | undefined;
        if (slice === undefined) {
            throw new Error(`createCursorList(${name}): slice "${sliceKey}" not registered in bus`);
        }
        return slice;
    }

    const selectors = freeze({
        slice:       (state: Record<string, unknown>) => _readSlice(state),
        items:       (state: Record<string, unknown>) => _readSlice(state).items,
        nextCursor:  (state: Record<string, unknown>) => _readSlice(state).nextCursor,
        hasMore:     (state: Record<string, unknown>) => _readSlice(state).hasMore,
        loading:     (state: Record<string, unknown>) => Boolean(_readSlice(state).loading),
        loadingMore: (state: Record<string, unknown>) => Boolean(_readSlice(state).loadingMore),
        error:       (state: Record<string, unknown>) => _readSlice(state).error,
        terminal:    (state: Record<string, unknown>) => _readSlice(state).terminal,
        filters:     (state: Record<string, unknown>) => _readSlice(state).filters,
    });

    function _transportSource(): 'ws' | 'http' {
        return transport === 'ws' ? 'ws' : 'http';
    }

    async function effect(event: PlatformEvent, ctx: EffectCtx): Promise<void> {
        if (extraEffect) {
            const handled = await extraEffect(event, ctx, events);
            if (handled === true) {
                return;
            }
        }
        if (event.type !== events.LOAD_REQUESTED) return;
        if (!event.payload || typeof event.payload !== 'object') {
            throw new Error(`createCursorList(${name}): LOAD_REQUESTED payload must be object`);
        }
        const p = event.payload as { filters?: unknown; cursor?: unknown; append?: unknown; limit?: unknown };
        const filters = p.filters && typeof p.filters === 'object' ? p.filters as Record<string, unknown> : {};
        const cursor = typeof p.cursor === 'string' ? p.cursor : null;
        const append = p.append === true;
        const limit = typeof p.limit === 'number' && p.limit > 0 ? p.limit : pageSize;
        const params: Record<string, unknown> = { ...buildQuery(filters), limit };
        if (cursor !== null) params.cursor = cursor;
        try {
            const data = (transport === 'ws'
                ? await transportRequest({
                    transport: 'ws',
                    commandType,
                    payload: params,
                    wsTimeoutMs,
                    causationEventId: event.id,
                    expectedSucceeded: _deriveReplyType(commandType, '_succeeded'),
                    expectedFailed: _deriveReplyType(commandType, '_failed'),
                })
                : httpMethod === 'POST'
                    ? await httpRequest({ method: 'POST', url: baseUrl, body: params })
                    : await httpRequest({ method: 'GET', url: baseUrl, query: params as Record<string, string | number | boolean | null | undefined> })) as { items?: unknown; next_cursor?: unknown; has_more?: unknown } | null;
            if (!data || !Array.isArray(data.items)) {
                throw new Error(`createCursorList(${name}): response.items missing or not array`);
            }
            ctx.dispatch(
                append ? events.PAGE_LOADED : events.LOADED,
                {
                    items: data.items,
                    next_cursor: typeof data.next_cursor === 'string' ? data.next_cursor : null,
                    has_more: data.has_more === true,
                },
                { causation_id: event.id, source: _transportSource() },
            );
        } catch (err) {
            if (!(err instanceof HttpError) && !(err instanceof WsTransportError)) throw err;
            const httpStatus = err instanceof HttpError ? err.status : null;
            const terminalKey = httpStatus !== null
                ? statusMap[httpStatus]
                : (err instanceof WsTransportError && err.code ? wsCodeTerminalKeys[err.code] : undefined);
            if (terminalKey) {
                ctx.dispatch((events as Record<string, string>)[terminalKey.toUpperCase()]!, null, { causation_id: event.id, source: _transportSource() });
                return;
            }
            ctx.dispatch(
                events.FAILED,
                { message: err.message, status: httpStatus, code: err instanceof WsTransportError ? err.code : null },
                { causation_id: event.id, source: _transportSource() },
            );
            if (errorToastKey) {
                ctx.dispatch(
                    CoreEvents.UI_TOAST_SHOW,
                    { type: 'error', i18n_key: errorToastKey },
                    { causation_id: event.id },
                );
            }
        }
    }

    return freeze({
        kind: 'cursor-list',
        name,
        sliceKey,
        baseUrl,
        transport,
        restMirror,
        commandType,
        pageSize,
        events,
        reducer,
        slice: freeze({ reducer, initial: initialSlice }),
        selectors,
        effect,
    });
}
