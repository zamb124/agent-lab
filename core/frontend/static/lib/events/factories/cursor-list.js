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
 *     wsTimeoutMs (положительное число).
 *   - statusMap: { 403: 'forbidden', 503: 'unavailable', ... } — опционально;
 *     каждый код → имя терминального события (генерируется как
 *     `${name}/list_${terminalKey}`). Для transport='ws' статусы передаются
 *     в payload `*_failed` как `error_code: 'http_<status>'` или равные
 *     ws-кодам — фабрика мапит по тому же statusMap.
 *   - errorToastKey: опционально; если задан — на FAILED показываем toast.
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

export function createCursorList(options) {
    if (!options || typeof options !== 'object') {
        throw new Error('createCursorList: options object required');
    }
    const name = requireField(options, 'name', 'createCursorList');
    assertResourceName(name);
    const baseUrl = requireField(options, 'baseUrl', `createCursorList(${name})`);
    const buildQuery = requireFunction(requireField(options, 'buildQuery', `createCursorList(${name})`), `createCursorList(${name}).buildQuery`);
    const pageSize = requireField(options, 'pageSize', `createCursorList(${name})`);
    if (typeof pageSize !== 'number' || pageSize <= 0) {
        throw new Error(`createCursorList(${name}): pageSize must be positive number`);
    }
    const transport = normalizeTransport(options.transport, `createCursorList(${name})`);
    const wsTimeoutMs = normalizeWsTimeout(options.wsTimeoutMs, transport, `createCursorList(${name})`);
    const httpMethod = typeof options.httpMethod === 'string' ? options.httpMethod.toUpperCase() : 'GET';
    if (httpMethod !== 'GET' && httpMethod !== 'POST') {
        throw new Error(`createCursorList(${name}): httpMethod must be 'GET' or 'POST'`);
    }
    const restMirrorInput = options.restMirror || { method: httpMethod, path: baseUrl };
    const restMirror = normalizeRestMirrorSingle(restMirrorInput, `createCursorList(${name})`);
    if (restMirror.method !== 'GET' && restMirror.method !== 'POST') {
        throw new Error(`createCursorList(${name}): restMirror.method must be GET or POST (cursor lists are read-only)`);
    }
    const statusMap = options.statusMap && typeof options.statusMap === 'object' ? options.statusMap : {};
    const initialFilters = options.initialFilters && typeof options.initialFilters === 'object'
        ? options.initialFilters
        : {};
    const errorToastKey = options.errorToastKey || null;
    if (errorToastKey) {
        requireI18nKey(errorToastKey, `createCursorList(${name}).errorToastKey`);
    }

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
    const terminalEvents = {};
    for (const [code, key] of Object.entries(statusMap)) {
        if (typeof key !== 'string' || key.length === 0) {
            throw new Error(`createCursorList(${name}): statusMap[${code}] must be non-empty string`);
        }
        terminalEvents[key.toUpperCase()] = buildEventType(name, `${key}`);
    }
    const events = freeze({ ...baseEvents, ...terminalEvents });

    const initialSlice = freeze({
        items: freeze([]),
        nextCursor: null,
        hasMore: false,
        loading: false,
        loadingMore: false,
        error: null,
        terminal: null,
        filters: freeze({ ...initialFilters }),
    });

    function reducer(state = initialSlice, event) {
        switch (event.type) {
            case events.LOAD_REQUESTED: {
                _assertObjectPayload(event, 'LOAD_REQUESTED');
                const append = event.payload.append === true;
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
                return freeze({
                    ...state,
                    items: freeze(event.payload.items),
                    nextCursor: event.payload.next_cursor,
                    hasMore: event.payload.has_more === true,
                    loading: false,
                    loadingMore: false,
                    error: null,
                    terminal: null,
                });
            }
            case events.PAGE_LOADED: {
                _assertListPayload(event, 'PAGE_LOADED');
                return freeze({
                    ...state,
                    items: freeze([...state.items, ...event.payload.items]),
                    nextCursor: event.payload.next_cursor,
                    hasMore: event.payload.has_more === true,
                    loadingMore: false,
                });
            }
            case events.FAILED: {
                if (!event.payload || typeof event.payload.message !== 'string') {
                    throw new Error(`createCursorList(${name}): FAILED payload must include "message" (string)`);
                }
                return freeze({
                    ...state,
                    loading: false,
                    loadingMore: false,
                    error: event.payload.message,
                });
            }
            case events.FILTERS_CHANGED: {
                if (!event.payload || !event.payload.filters || typeof event.payload.filters !== 'object') {
                    throw new Error(`createCursorList(${name}): FILTERS_CHANGED payload.filters required (object)`);
                }
                return freeze({ ...state, filters: freeze({ ...state.filters, ...event.payload.filters }) });
            }
            case events.FILTERS_RESET:
                return freeze({ ...state, filters: freeze({ ...initialFilters }) });
            default:
                if (Object.values(terminalEvents).includes(event.type)) {
                    const terminalKey = Object.entries(terminalEvents).find(([, t]) => t === event.type)[0].toLowerCase();
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

    function _assertObjectPayload(event, eventKey) {
        if (event.payload === undefined || event.payload === null || typeof event.payload !== 'object') {
            throw new Error(`createCursorList(${name}): ${eventKey} payload must be object`);
        }
    }

    function _assertListPayload(event, eventKey) {
        if (!event.payload || !Array.isArray(event.payload.items)) {
            throw new Error(`createCursorList(${name}): ${eventKey} payload.items must be array`);
        }
        if (!('next_cursor' in event.payload)) {
            throw new Error(`createCursorList(${name}): ${eventKey} payload.next_cursor required (string|null)`);
        }
        if (!('has_more' in event.payload)) {
            throw new Error(`createCursorList(${name}): ${eventKey} payload.has_more required (boolean)`);
        }
    }

    function _readSlice(state) {
        const slice = state[sliceKey];
        if (slice === undefined) {
            throw new Error(`createCursorList(${name}): slice "${sliceKey}" not registered in bus`);
        }
        return slice;
    }

    const selectors = freeze({
        slice:       (state) => _readSlice(state),
        items:       (state) => _readSlice(state).items,
        nextCursor:  (state) => _readSlice(state).nextCursor,
        hasMore:     (state) => _readSlice(state).hasMore,
        loading:     (state) => Boolean(_readSlice(state).loading),
        loadingMore: (state) => Boolean(_readSlice(state).loadingMore),
        error:       (state) => _readSlice(state).error,
        terminal:    (state) => _readSlice(state).terminal,
        filters:     (state) => _readSlice(state).filters,
    });

    function _transportSource() {
        return transport === 'ws' ? 'ws' : 'http';
    }

    async function effect(event, ctx) {
        if (event.type !== events.LOAD_REQUESTED) return;
        if (!event.payload || typeof event.payload !== 'object') {
            throw new Error(`createCursorList(${name}): LOAD_REQUESTED payload must be object`);
        }
        const filters = event.payload.filters && typeof event.payload.filters === 'object' ? event.payload.filters : {};
        const cursor = typeof event.payload.cursor === 'string' ? event.payload.cursor : null;
        const append = event.payload.append === true;
        const limit = typeof event.payload.limit === 'number' && event.payload.limit > 0 ? event.payload.limit : pageSize;
        const params = { ...buildQuery(filters), limit };
        if (cursor !== null) params.cursor = cursor;
        try {
            const data = transport === 'ws'
                ? await transportRequest({
                    transport: 'ws',
                    commandType: events.LOAD_REQUESTED,
                    payload: { filters, cursor, limit, append },
                    wsTimeoutMs,
                    causationEventId: event.id,
                    expectedSucceeded: append ? events.PAGE_LOADED : events.LOADED,
                    expectedFailed: events.FAILED,
                })
                : httpMethod === 'POST'
                    ? await httpRequest({ method: 'POST', url: baseUrl, body: params })
                    : await httpRequest({ method: 'GET', url: baseUrl, query: params });
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
            const terminalKey = httpStatus !== null ? statusMap[httpStatus] : null;
            if (terminalKey) {
                ctx.dispatch(events[terminalKey.toUpperCase()], null, { causation_id: event.id, source: _transportSource() });
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
        pageSize,
        events,
        reducer,
        slice: freeze({ reducer, initial: initialSlice }),
        selectors,
        effect,
    });
}
