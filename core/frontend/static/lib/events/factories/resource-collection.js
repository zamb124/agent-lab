/**
 * createResourceCollection — фабрика CRUD-коллекции.
 *
 * Описывает домен в декларативном стиле; внутри разворачивает события, slice,
 * effect и селекторы. Это единственный канонический способ описать список
 * сущностей с операциями create/update/remove/get.
 *
 * Контракт:
 *   - name: 'scope/entity' (lowercase, snake_case)
 *   - baseUrl: HTTP-префикс ресурса (без trailing slash) — используется для
 *     transport='http'; для transport='ws' игнорируется в качестве URL,
 *     но всё равно требуется как идентификатор ресурса.
 *   - idField: имя поля идентификатора в модели (`id`, `key_id`, `embed_id`...)
 *   - operations: массив из ['list', 'create', 'update', 'remove', 'get'] —
 *     обязательно непустой; 'list' включён по умолчанию.
 *   - toastKeys: { create, update, remove, ... } — обязательно для каждой
 *     mutating операции, иначе `throw`.
 *   - restMirror: { list?, get?, create?, update?, remove? } —
 *     платформенный инвариант REST-зеркала команд. На каждую operation в
 *     `operations` обязательна запись `{ method, path }`.
 *   - transport: 'http' | 'ws' (default 'http'). Для 'ws' обязателен
 *     wsTimeoutMs (положительное число).
 *   - listQuery / mapItem / extraInitial / extraReducer / extraEvents /
 *     actions — см. предыдущую версию.
 *   - requestHeaders: ({ ctx, payload, op }) => Record<string, string> —
 *     опционально; если задан, результат подмешивается в `headers` каждого
 *     httpRequest. Используется сервисами, которым нужен сквозной заголовок
 *     (например `X-Platform-Namespace` для office BFF).
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
    requireI18nKey,
} from './_internal.js';
import {
    WsTransportError,
    normalizeRestMirrorCollection,
    normalizeTransport,
    normalizeWsTimeout,
    transportRequest,
} from './_transport.js';

const VALID_OPERATIONS = new Set(['list', 'get', 'create', 'update', 'remove']);
const MUTATING_OPERATIONS = new Set(['create', 'update', 'remove']);
const _REQUESTED_SUFFIX = '_requested';

function _deriveCommandReplyType(commandType, replySuffix) {
    if (typeof commandType !== 'string' || !commandType.endsWith(_REQUESTED_SUFFIX)) {
        throw new Error(`createResourceCollection: commandType must end with "_requested", got "${commandType}"`);
    }
    return commandType.slice(0, -_REQUESTED_SUFFIX.length) + replySuffix;
}

const INITIAL_SLICE = freeze({
    items: freeze([]),
    byId: freeze({}),
    loading: false,
    refreshing: false,
    listTotal: null,
    error: null,
    busyIds: freeze({}),
    lastError: freeze({}),
    createInFlight: false,
    createLockEventId: null,
});

export function createResourceCollection(options) {
    if (!options || typeof options !== 'object') {
        throw new Error('createResourceCollection: options object required');
    }
    const name = requireField(options, 'name', 'createResourceCollection');
    assertResourceName(name);
    const baseUrl = requireField(options, 'baseUrl', `createResourceCollection(${name})`);
    const idField = requireField(options, 'idField', `createResourceCollection(${name})`);
    const operations = Array.isArray(options.operations) && options.operations.length > 0
        ? options.operations
        : ['list'];
    for (const op of operations) {
        if (!VALID_OPERATIONS.has(op)) {
            throw new Error(`createResourceCollection(${name}): unknown operation "${op}"`);
        }
    }
    const toastKeys = options.toastKeys || {};
    for (const op of operations) {
        if (MUTATING_OPERATIONS.has(op)) {
            requireI18nKey(toastKeys[op], `createResourceCollection(${name}).toastKeys.${op}`);
        }
    }

    const transport = normalizeTransport(options.transport, `createResourceCollection(${name})`);
    const wsTimeoutMs = normalizeWsTimeout(options.wsTimeoutMs, transport, `createResourceCollection(${name})`);

    const itemPathTemplate = options.itemPathTemplate || `${baseUrl}/:${idField}`;
    const defaultRestMirror = {
        list:   { method: 'GET',    path: baseUrl },
        get:    { method: 'GET',    path: itemPathTemplate },
        create: { method: 'POST',   path: baseUrl },
        update: { method: 'PATCH',  path: itemPathTemplate },
        remove: { method: 'DELETE', path: itemPathTemplate },
    };
    const restMirrorInput = options.restMirror || {};
    const mergedRestMirror = {};
    for (const op of operations) {
        mergedRestMirror[op] = restMirrorInput[op] || defaultRestMirror[op];
    }
    const restMirror = normalizeRestMirrorCollection(
        mergedRestMirror,
        operations,
        null,
        `createResourceCollection(${name})`,
    );

    const sliceKey = options.sliceKey || deriveSliceKey(name);
    const listQuery = options.listQuery || (() => ({ limit: 200 }));
    const mapItem = options.mapItem || ((x) => x);
    const listFetchAllPages = options.listFetchAllPages === true;
    const listPreserveItemsOnRefresh = options.listPreserveItemsOnRefresh === true;
    const buildItemUrl = options.buildItemUrl || ((id) => `${baseUrl}/${encodeURIComponent(id)}`);
    const reloadAfterMutation = options.reloadAfterMutation !== false;
    const requestHeaders = typeof options.requestHeaders === 'function' ? options.requestHeaders : null;
    const extraInitial = options.extraInitial && typeof options.extraInitial === 'object'
        ? options.extraInitial
        : null;
    const extraReducer = typeof options.extraReducer === 'function' ? options.extraReducer : null;
    const extraEventsConfig = options.extraEvents && typeof options.extraEvents === 'object'
        ? options.extraEvents
        : null;
    const actionsConfig = options.actions && typeof options.actions === 'object'
        ? options.actions
        : null;

    registerResourceName(name, 'resource-collection');

    const baseEvents = {
        LIST_REQUESTED:   buildEventType(name, 'list_requested'),
        LIST_LOADED:      buildEventType(name, 'list_loaded'),
        LIST_FAILED:      buildEventType(name, 'list_failed'),
        ITEM_REQUESTED:   buildEventType(name, 'item_requested'),
        ITEM_LOADED:      buildEventType(name, 'item_loaded'),
        ITEM_FAILED:      buildEventType(name, 'item_failed'),
        CREATE_REQUESTED: buildEventType(name, 'create_requested'),
        CREATED:          buildEventType(name, 'created'),
        CREATE_FAILED:    buildEventType(name, 'create_failed'),
        UPDATE_REQUESTED: buildEventType(name, 'update_requested'),
        UPDATED:          buildEventType(name, 'updated'),
        UPDATE_FAILED:    buildEventType(name, 'update_failed'),
        REMOVE_REQUESTED: buildEventType(name, 'remove_requested'),
        REMOVED:          buildEventType(name, 'removed'),
        REMOVE_FAILED:    buildEventType(name, 'remove_failed'),
    };
    const extraEvents = {};
    if (extraEventsConfig) {
        for (const [key, verb] of Object.entries(extraEventsConfig)) {
            if (typeof verb !== 'string' || verb.length === 0) {
                throw new Error(`createResourceCollection(${name}): extraEvents.${key} must be non-empty verb`);
            }
            extraEvents[key] = buildEventType(name, verb);
        }
    }
    const actionsMap = {};
    if (actionsConfig) {
        for (const [methodName, verb] of Object.entries(actionsConfig)) {
            if (typeof methodName !== 'string' || methodName.length === 0) {
                throw new Error(`createResourceCollection(${name}): actions key must be non-empty method name`);
            }
            if (typeof verb !== 'string' || verb.length === 0) {
                throw new Error(`createResourceCollection(${name}): actions.${methodName} must be non-empty verb`);
            }
            const eventType = buildEventType(name, verb);
            const eventKey = verb.toUpperCase();
            extraEvents[eventKey] = eventType;
            actionsMap[methodName] = eventType;
        }
    }
    const events = freeze({ ...baseEvents, ...extraEvents });
    const actions = freeze(actionsMap);
    const initialSlice = freeze(extraInitial ? { ...INITIAL_SLICE, ...extraInitial } : { ...INITIAL_SLICE });

    const hasCreate = operations.includes('create');

    function _withItems(state, items, listTotal) {
        const list = items.map(mapItem);
        const byId = {};
        for (const item of list) {
            byId[item[idField]] = item;
        }
        const next = {
            ...state,
            items: freeze(list),
            byId: freeze(byId),
            loading: false,
            refreshing: false,
            error: null,
        };
        if (typeof listTotal === 'number') {
            next.listTotal = listTotal;
        }
        return freeze(next);
    }

    function _withItem(state, item) {
        const mapped = mapItem(item);
        const id = mapped[idField];
        const idx = state.items.findIndex((x) => x[idField] === id);
        const items = idx === -1 ? [...state.items, mapped] : state.items.map((x, i) => (i === idx ? mapped : x));
        const byId = { ...state.byId, [id]: mapped };
        return freeze({
            ...state,
            items: freeze(items),
            byId: freeze(byId),
            busyIds: _clearBusy(state.busyIds, id),
        });
    }

    function _withoutItem(state, id) {
        const items = state.items.filter((x) => x[idField] !== id);
        const byId = { ...state.byId };
        delete byId[id];
        return freeze({
            ...state,
            items: freeze(items),
            byId: freeze(byId),
            busyIds: _clearBusy(state.busyIds, id),
        });
    }

    function _setBusy(state, id) {
        if (!id) return state;
        const next = { ...state.busyIds, [id]: true };
        return freeze({ ...state, busyIds: freeze(next) });
    }

    function _clearBusy(busyIds, id) {
        if (!id || !busyIds[id]) return busyIds;
        const next = { ...busyIds };
        delete next[id];
        return freeze(next);
    }

    function _setLastError(state, op, message) {
        return freeze({ ...state, lastError: freeze({ ...state.lastError, [op]: message }) });
    }

    function reducer(state = initialSlice, event) {
        const next = _baseReducer(state, event);
        if (extraReducer) {
            const extended = extraReducer(next, event, events);
            if (extended && extended !== next) {
                return freeze(extended);
            }
        }
        return next;
    }

    function _requireItem(event, eventKey) {
        if (!event.payload || !event.payload.item) {
            throw new Error(`createResourceCollection(${name}): ${eventKey} payload.item required`);
        }
        return event.payload.item;
    }

    function _requireId(event, eventKey) {
        if (!event.payload || !event.payload[idField]) {
            throw new Error(`createResourceCollection(${name}): ${eventKey} payload.${idField} required`);
        }
        return event.payload[idField];
    }

    function _requireMessage(event, eventKey) {
        if (!event.payload || typeof event.payload.message !== 'string') {
            throw new Error(`createResourceCollection(${name}): ${eventKey} payload.message required (string)`);
        }
        return event.payload.message;
    }

    function _baseReducer(state, event) {
        switch (event.type) {
            case events.LIST_REQUESTED:
                if (listPreserveItemsOnRefresh && state.items.length > 0) {
                    return freeze({ ...state, refreshing: true, error: null });
                }
                return freeze({ ...state, loading: true, refreshing: false, error: null });
            case events.LIST_LOADED: {
                if (!event.payload || !Array.isArray(event.payload.items)) {
                    throw new Error(`createResourceCollection(${name}): LIST_LOADED payload.items required (array)`);
                }
                const listTotal = event.payload.total;
                const resolvedTotal = typeof listTotal === 'number' ? listTotal : undefined;
                return _withItems(state, event.payload.items, resolvedTotal);
            }
            case events.LIST_FAILED:
                return freeze({ ...state, loading: false, refreshing: false, error: _requireMessage(event, 'LIST_FAILED') });
            case events.ITEM_LOADED:
                return _withItem(state, _requireItem(event, 'ITEM_LOADED'));
            case events.CREATE_REQUESTED: {
                const next = _setLastError(state, 'create', null);
                if (!hasCreate) {
                    return freeze(next);
                }
                if (state.createInFlight) {
                    return freeze(next);
                }
                return freeze({
                    ...next,
                    createInFlight: true,
                    createLockEventId: event.id,
                });
            }
            case events.CREATED: {
                const withItem = _withItem(state, _requireItem(event, 'CREATED'));
                if (!hasCreate) {
                    return withItem;
                }
                return freeze({
                    ...withItem,
                    createInFlight: false,
                    createLockEventId: null,
                });
            }
            case events.CREATE_FAILED: {
                const next = _setLastError(state, 'create', _requireMessage(event, 'CREATE_FAILED'));
                if (!hasCreate) {
                    return next;
                }
                return freeze({
                    ...next,
                    createInFlight: false,
                    createLockEventId: null,
                });
            }
            case events.UPDATE_REQUESTED:
                return _setLastError(_setBusy(state, _requireId(event, 'UPDATE_REQUESTED')), 'update', null);
            case events.UPDATED:
                return _withItem(state, _requireItem(event, 'UPDATED'));
            case events.UPDATE_FAILED: {
                const id = _requireId(event, 'UPDATE_FAILED');
                const next = _setLastError(state, 'update', _requireMessage(event, 'UPDATE_FAILED'));
                return freeze({ ...next, busyIds: _clearBusy(state.busyIds, id) });
            }
            case events.REMOVE_REQUESTED:
                return _setLastError(_setBusy(state, _requireId(event, 'REMOVE_REQUESTED')), 'remove', null);
            case events.REMOVED:
                return _withoutItem(state, _requireId(event, 'REMOVED'));
            case events.REMOVE_FAILED: {
                const id = _requireId(event, 'REMOVE_FAILED');
                const next = _setLastError(state, 'remove', _requireMessage(event, 'REMOVE_FAILED'));
                return freeze({ ...next, busyIds: _clearBusy(state.busyIds, id) });
            }
            case events.ITEM_FAILED:
                return _setLastError(state, 'get', _requireMessage(event, 'ITEM_FAILED'));
            default:
                return state;
        }
    }

    function _readSlice(state) {
        const slice = state[sliceKey];
        if (slice === undefined) {
            throw new Error(`createResourceCollection(${name}): slice "${sliceKey}" not registered in bus`);
        }
        return slice;
    }

    const selectors = freeze({
        slice:    (state) => _readSlice(state),
        all:      (state) => _readSlice(state).items,
        byId:     (state) => _readSlice(state).byId,
        loading:  (state) => Boolean(_readSlice(state).loading),
        refreshing: (state) => Boolean(_readSlice(state).refreshing),
        listTotal: (state) => {
            const total = _readSlice(state).listTotal;
            return typeof total === 'number' ? total : null;
        },
        error:    (state) => _readSlice(state).error,
        busyIds:  (state) => _readSlice(state).busyIds,
        lastError:(state) => _readSlice(state).lastError,
        item:     (id) => (state) => {
            const slice = _readSlice(state);
            return slice.byId[id] === undefined ? null : slice.byId[id];
        },
        isBusy:   (id) => (state) => Boolean(_readSlice(state).busyIds[id]),
        createInFlight: (state) => Boolean(_readSlice(state).createInFlight),
    });

    function _requestPayload(event) {
        if (event.payload === null || event.payload === undefined) return {};
        if (typeof event.payload !== 'object') {
            throw new Error(`createResourceCollection(${name}): event.payload for ${event.type} must be object|null`);
        }
        return event.payload;
    }

    async function _doRequest(opSpec, event, ctx) {
        if (transport === 'ws') {
            // Канонический бэкенд reply типы выводятся из commandType (`<...>_requested`):
            //   succeeded -> `<...>_succeeded`, failed -> `<...>_failed`.
            // Внутренние события фабрики (`events.LIST_LOADED`, `events.CREATED`, ...) —
            // отдельное имя, на которое подписан reducer; диспатчится после успешного
            // получения reply (см. effect-ветки ниже).
            return transportRequest({
                transport: 'ws',
                commandType: opSpec.commandType,
                payload: opSpec.wsPayload,
                wsTimeoutMs,
                causationEventId: event.id,
                expectedSucceeded: _deriveCommandReplyType(opSpec.commandType, '_succeeded'),
                expectedFailed: _deriveCommandReplyType(opSpec.commandType, '_failed'),
            });
        }
        const headers = requestHeaders
            ? requestHeaders({ ctx, payload: opSpec.headersPayload, op: opSpec.op })
            : undefined;
        return httpRequest({
            method: opSpec.method,
            url: opSpec.url,
            body: opSpec.httpBody,
            query: opSpec.httpQuery,
            headers,
        });
    }

    function _isTransportError(err) {
        return err instanceof HttpError || err instanceof WsTransportError;
    }

    function _transportSource() {
        return transport === 'ws' ? 'ws' : 'http';
    }

    async function effect(event, ctx) {
        switch (event.type) {
            case events.LIST_REQUESTED: {
                if (!operations.includes('list')) return;
                const payload = _requestPayload(event);
                let data;
                try {
                    if (listFetchAllPages) {
                        const baseQuery = listQuery(payload);
                        if (!baseQuery || typeof baseQuery !== 'object') {
                            throw new Error(`createResourceCollection(${name}): listQuery must return object`);
                        }
                        const pageLimit = typeof baseQuery.limit === 'number' ? baseQuery.limit : 200;
                        let off = typeof baseQuery.offset === 'number' ? baseQuery.offset : 0;
                        const mergedItems = [];
                        let total = 0;
                        for (;;) {
                            const pageData = await _doRequest({
                                commandType: events.LIST_REQUESTED,
                                succeeded: events.LIST_LOADED,
                                failed: events.LIST_FAILED,
                                wsPayload: payload,
                                method: 'GET',
                                url: baseUrl,
                                httpQuery: { ...baseQuery, limit: pageLimit, offset: off },
                                op: 'list',
                                headersPayload: payload,
                            }, event, ctx);
                            if (!pageData || !Array.isArray(pageData.items)) {
                                throw new Error(`createResourceCollection(${name}): list response.items missing or not array`);
                            }
                            if (typeof pageData.total !== 'number') {
                                throw new Error(`createResourceCollection(${name}): list response.total must be number when listFetchAllPages is true`);
                            }
                            total = pageData.total;
                            mergedItems.push(...pageData.items);
                            if (mergedItems.length >= total) {
                                break;
                            }
                            if (pageData.items.length < pageLimit) {
                                break;
                            }
                            off += pageLimit;
                        }
                        ctx.dispatch(events.LIST_LOADED, { items: mergedItems, total }, { causation_id: event.id, source: _transportSource() });
                        return;
                    }
                    data = await _doRequest({
                        commandType: events.LIST_REQUESTED,
                        succeeded: events.LIST_LOADED,
                        failed: events.LIST_FAILED,
                        wsPayload: payload,
                        method: 'GET',
                        url: baseUrl,
                        httpQuery: listQuery(payload),
                        op: 'list',
                        headersPayload: payload,
                    }, event, ctx);
                } catch (err) {
                    if (!_isTransportError(err)) throw err;
                    ctx.dispatch(events.LIST_FAILED, { message: err.message }, { causation_id: event.id, source: _transportSource() });
                    return;
                }
                if (!data || !Array.isArray(data.items)) {
                    throw new Error(`createResourceCollection(${name}): list response.items missing or not array`);
                }
                ctx.dispatch(
                    events.LIST_LOADED,
                    {
                        items: data.items,
                        total: typeof data.total === 'number' ? data.total : undefined,
                    },
                    { causation_id: event.id, source: _transportSource() },
                );
                return;
            }
            case events.ITEM_REQUESTED: {
                if (!operations.includes('get')) return;
                const id = _requireId(event, 'ITEM_REQUESTED');
                try {
                    const item = await _doRequest({
                        commandType: events.ITEM_REQUESTED,
                        succeeded: events.ITEM_LOADED,
                        failed: events.ITEM_FAILED,
                        wsPayload: { [idField]: id },
                        method: 'GET',
                        url: buildItemUrl(id),
                        op: 'get',
                        headersPayload: { [idField]: id },
                    }, event, ctx);
                    if (!item || typeof item !== 'object') {
                        throw new Error(`createResourceCollection(${name}): get response must be object`);
                    }
                    ctx.dispatch(events.ITEM_LOADED, { item }, { causation_id: event.id, source: _transportSource() });
                } catch (err) {
                    if (!_isTransportError(err)) throw err;
                    ctx.dispatch(events.ITEM_FAILED, { [idField]: id, message: err.message }, { causation_id: event.id, source: _transportSource() });
                }
                return;
            }
            case events.CREATE_REQUESTED: {
                if (!operations.includes('create')) return;
                const st = ctx.getState();
                const rawSlice = st[sliceKey];
                if (rawSlice != null) {
                    const lock = rawSlice.createLockEventId;
                    if (lock != null && lock !== event.id) {
                        return;
                    }
                }
                const payload = _requestPayload(event);
                try {
                    const item = await _doRequest({
                        commandType: events.CREATE_REQUESTED,
                        succeeded: events.CREATED,
                        failed: events.CREATE_FAILED,
                        wsPayload: payload,
                        method: 'POST',
                        url: baseUrl,
                        httpBody: payload,
                        op: 'create',
                        headersPayload: payload,
                    }, event, ctx);
                    if (!item || typeof item !== 'object' || !item[idField]) {
                        throw new Error(`createResourceCollection(${name}): create response missing ${idField}`);
                    }
                    ctx.dispatch(events.CREATED, { item }, { causation_id: event.id, source: _transportSource() });
                    ctx.dispatch(
                        CoreEvents.UI_TOAST_SHOW,
                        { type: 'success', i18n_key: toastKeys.create },
                        { causation_id: event.id },
                    );
                } catch (err) {
                    if (!_isTransportError(err)) throw err;
                    ctx.dispatch(events.CREATE_FAILED, { message: err.message }, { causation_id: event.id, source: _transportSource() });
                    if (toastKeys.create_error) {
                        ctx.dispatch(
                            CoreEvents.UI_TOAST_SHOW,
                            { type: 'error', i18n_key: toastKeys.create_error },
                            { causation_id: event.id },
                        );
                    }
                }
                return;
            }
            case events.UPDATE_REQUESTED: {
                if (!operations.includes('update')) return;
                const payload = _requestPayload(event);
                const id = payload[idField];
                if (!id) throw new Error(`${name}: ${idField} required for update_requested`);
                const { [idField]: _drop, ...body } = payload;
                try {
                    const response = await _doRequest({
                        commandType: events.UPDATE_REQUESTED,
                        succeeded: events.UPDATED,
                        failed: events.UPDATE_FAILED,
                        wsPayload: payload,
                        method: 'PATCH',
                        url: buildItemUrl(id),
                        httpBody: body,
                        op: 'update',
                        headersPayload: payload,
                    }, event, ctx);
                    const finalItem = response && typeof response === 'object' && response[idField]
                        ? response
                        : { [idField]: id, ...body };
                    ctx.dispatch(events.UPDATED, { item: finalItem }, { causation_id: event.id, source: _transportSource() });
                    ctx.dispatch(
                        CoreEvents.UI_TOAST_SHOW,
                        { type: 'success', i18n_key: toastKeys.update },
                        { causation_id: event.id },
                    );
                    if (reloadAfterMutation && operations.includes('list')) {
                        ctx.dispatch(events.LIST_REQUESTED, null, { causation_id: event.id });
                    }
                } catch (err) {
                    if (!_isTransportError(err)) throw err;
                    ctx.dispatch(events.UPDATE_FAILED, { [idField]: id, message: err.message }, { causation_id: event.id, source: _transportSource() });
                }
                return;
            }
            case events.REMOVE_REQUESTED: {
                if (!operations.includes('remove')) return;
                const id = _requireId(event, 'REMOVE_REQUESTED');
                try {
                    await _doRequest({
                        commandType: events.REMOVE_REQUESTED,
                        succeeded: events.REMOVED,
                        failed: events.REMOVE_FAILED,
                        wsPayload: { [idField]: id },
                        method: 'DELETE',
                        url: buildItemUrl(id),
                        op: 'remove',
                        headersPayload: { [idField]: id },
                    }, event, ctx);
                    ctx.dispatch(events.REMOVED, { [idField]: id }, { causation_id: event.id, source: _transportSource() });
                    ctx.dispatch(
                        CoreEvents.UI_TOAST_SHOW,
                        { type: 'success', i18n_key: toastKeys.remove },
                        { causation_id: event.id },
                    );
                    if (reloadAfterMutation && operations.includes('list')) {
                        ctx.dispatch(events.LIST_REQUESTED, null, { causation_id: event.id });
                    }
                } catch (err) {
                    if (!_isTransportError(err)) throw err;
                    ctx.dispatch(events.REMOVE_FAILED, { [idField]: id, message: err.message }, { causation_id: event.id, source: _transportSource() });
                }
                return;
            }
            default:
                return;
        }
    }

    return freeze({
        kind: 'resource-collection',
        name,
        sliceKey,
        idField,
        baseUrl,
        transport,
        restMirror,
        operations: freeze(operations.slice()),
        events,
        actions,
        reducer,
        slice: freeze({ reducer, initial: initialSlice }),
        selectors,
        effect,
    });
}
