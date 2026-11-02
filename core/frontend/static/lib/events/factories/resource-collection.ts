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
import { isPlainRecord } from '../payload.js';
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
import type { EffectCtx, PlatformEvent } from '../contract.js';
import type { ActionMap, PlatformFactory } from '../factory-registry.js';
import type { SliceDef } from '../reducers/index.js';
import type { PlatformCommandMap } from '../wire/index.js';
import type { FactoryTransport, RestMirrorEntry } from './_transport.js';

const MUTATING_OPERATIONS = new Set(['create', 'update', 'remove']);
const _REQUESTED_SUFFIX = '_requested';

function _deriveCommandReplyType(commandType: string, replySuffix: string): string {
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
    lastListQuery: null,
});

export type ResourceOperation = 'list' | 'get' | 'create' | 'update' | 'remove';

function isResourceOperation(value: string): value is ResourceOperation {
    return value === 'list' || value === 'get' || value === 'create' || value === 'update' || value === 'remove';
}

function resourceItems(items: readonly unknown[], label: string): ResourceItem[] {
    return items.map((item, index) => {
        if (!isPlainRecord(item)) {
            throw new Error(`${label}[${index}] must be an object`);
        }
        return item;
    });
}

function listResponse(value: unknown, label: string): { items: ResourceItem[]; total: unknown } {
    if (!isPlainRecord(value) || !Array.isArray(value.items)) {
        throw new Error(`${label}: items must be an array`);
    }
    return { items: resourceItems(value.items, label), total: value.total };
}

function queryRecord(value: unknown, label: string): Record<string, unknown> {
    if (!isPlainRecord(value)) {
        throw new Error(`${label} must return object`);
    }
    return value;
}

function httpQueryFields(
    value: Record<string, unknown>,
    label: string,
): Record<string, string | number | boolean | null | undefined> {
    const query: Record<string, string | number | boolean | null | undefined> = {};
    for (const [key, field] of Object.entries(value)) {
        if (
            field === undefined
            || field === null
            || typeof field === 'string'
            || typeof field === 'number'
            || typeof field === 'boolean'
        ) {
            query[key] = field;
            continue;
        }
        throw new Error(`${label}: query.${key} must be a scalar`);
    }
    return query;
}

export interface ResourceItem {
    [key: string]: unknown;
}

export interface ResourceCollectionSlice<TItem = ResourceItem> {
    items: readonly TItem[];
    byId: Readonly<Record<string, TItem>>;
    loading: boolean;
    refreshing: boolean;
    listTotal: number | null;
    error: string | null;
    busyIds: Readonly<Record<string, boolean>>;
    lastError: Readonly<Record<string, string | null>>;
    createInFlight: boolean;
    createLockEventId: string | null;
    lastListQuery: { payload: unknown } | null;
    [key: string]: unknown;
}

export interface ResourceCollectionOptions<
    TItem extends ResourceItem = ResourceItem,
    S extends ResourceCollectionSlice<TItem> = ResourceCollectionSlice<TItem>,
    A extends ActionMap = ActionMap,
> {
    name: string;
    baseUrl: string;
    idField: string;
    operations?: ResourceOperation[];
    toastKeys?: Record<string, string>;
    restMirror?: Record<string, RestMirrorEntry | { method: string; path: string }>;
    transport?: FactoryTransport;
    wsTimeoutMs?: number;
    itemPathTemplate?: string;
    listQuery?: (payload: Record<string, unknown>) => Record<string, unknown>;
    mapItem?: (item: TItem) => TItem;
    listFetchAllPages?: boolean;
    listPreserveItemsOnRefresh?: boolean;
    buildItemUrl?: (id: string | number) => string;
    reloadAfterMutation?: boolean;
    requestHeaders?: (args: { ctx: EffectCtx; payload: unknown; op: string }) => Record<string, string>;
    sliceKey?: string;
    extraInitial?: Record<string, unknown>;
    extraReducer?: (state: S, event: PlatformEvent, events: Readonly<Record<string, string>>) => NoInfer<S> | null | undefined;
    extraEffect?: (event: PlatformEvent, ctx: EffectCtx, events: Readonly<Record<string, string>>) => boolean | void | Promise<boolean | void>;
    extraEvents?: Record<string, string>;
    actions?: A;
}

interface _OpSpec {
    commandType: string;
    succeeded?: string;
    failed?: string;
    wsPayload?: unknown;
    method?: 'GET' | 'POST' | 'PUT' | 'PATCH' | 'DELETE';
    url?: string;
    httpBody?: unknown;
    httpQuery?: Record<string, string | number | boolean | null | undefined>;
    op: string;
    headersPayload?: unknown;
}

export interface ResourceCollectionFactory<
    S extends ResourceCollectionSlice<unknown> = ResourceCollectionSlice,
    A extends ActionMap = ActionMap,
> extends PlatformFactory {
    kind: 'resource-collection';
    name: string;
    sliceKey: string;
    idField: string;
    baseUrl: string;
    transport: FactoryTransport;
    restMirror: Readonly<Record<string, RestMirrorEntry>>;
    operations: readonly string[];
    events: Readonly<Record<string, string>> & {
        LIST_REQUESTED: string; LIST_LOADED: string; LIST_FAILED: string;
        ITEM_REQUESTED: string; ITEM_LOADED: string; ITEM_FAILED: string;
        CREATE_REQUESTED: string; CREATED: string; CREATE_FAILED: string;
        UPDATE_REQUESTED: string; UPDATED: string; UPDATE_FAILED: string;
        REMOVE_REQUESTED: string; REMOVED: string; REMOVE_FAILED: string;
    };
    actions: Readonly<A>;
    reducer(state: S | undefined, event: PlatformEvent): S;
    slice: SliceDef<S>;
    selectors: {
        slice: (state: Record<string, unknown>) => S;
        all: (state: Record<string, unknown>) => S['items'];
        byId: (state: Record<string, unknown>) => S['byId'];
        loading: (state: Record<string, unknown>) => boolean;
        refreshing: (state: Record<string, unknown>) => boolean;
        listTotal: (state: Record<string, unknown>) => number | null;
        error: (state: Record<string, unknown>) => string | null;
        busyIds: (state: Record<string, unknown>) => Readonly<Record<string, boolean>>;
        lastError: (state: Record<string, unknown>) => Readonly<Record<string, string | null>>;
        isBusy: (id: string | number) => (state: Record<string, unknown>) => boolean;
        createInFlight: (state: Record<string, unknown>) => boolean;
    };
    effect: (event: PlatformEvent, ctx: EffectCtx) => Promise<void>;
}

/**
 * Wire-тип элемента коллекции по `name`: `<name>/list_requested` →
 * `result.items[number]`. Нет в `PlatformCommandMap` — `ResourceItem` (как раньше).
 */
type WireListItem<N extends string> =
    `${N}/list_requested` extends keyof PlatformCommandMap
        ? NonNullable<PlatformCommandMap[`${N}/list_requested`]['result']> extends { items?: infer Items }
            ? NonNullable<Items> extends readonly (infer I)[]
                ? I extends ResourceItem ? I : ResourceItem
                : ResourceItem
            : ResourceItem
        : ResourceItem;

export function createResourceCollection<
    N extends string,
    S extends ResourceCollectionSlice<WireListItem<N>> = ResourceCollectionSlice<WireListItem<N>>,
    A extends ActionMap = Record<never, string>,
>(options: ResourceCollectionOptions<WireListItem<N>, S, A> & { name: N }): ResourceCollectionFactory<S, A>;
export function createResourceCollection<
    TItem extends ResourceItem = ResourceItem,
    S extends ResourceCollectionSlice<TItem> = ResourceCollectionSlice<TItem>,
    A extends ActionMap = Record<never, string>,
>(options: ResourceCollectionOptions<TItem, S, A>): ResourceCollectionFactory<S, A>;
export function createResourceCollection<
    TItem extends ResourceItem = ResourceItem,
    S extends ResourceCollectionSlice<TItem> = ResourceCollectionSlice<TItem>,
    A extends ActionMap = Record<never, string>,
>(options: ResourceCollectionOptions<TItem, S, A>): ResourceCollectionFactory<S, A> {
    if (!options || typeof options !== 'object') {
        throw new Error('createResourceCollection: options object required');
    }
    const name = requireField(options, 'name', 'createResourceCollection');
    assertResourceName(name);
    const baseUrl = requireField(options, 'baseUrl', `createResourceCollection(${name})`);
    const idField = requireField(options, 'idField', `createResourceCollection(${name})`);
    const requestedOperations = Array.isArray(options.operations) && options.operations.length > 0
        ? options.operations
        : ['list'];
    const operations: ResourceOperation[] = [];
    for (const op of requestedOperations) {
        if (!isResourceOperation(op)) {
            throw new Error(`createResourceCollection(${name}): unknown operation "${op}"`);
        }
        operations.push(op);
    }
    const toastKeys = options.toastKeys === undefined ? {} : options.toastKeys;
    for (const op of operations) {
        if (MUTATING_OPERATIONS.has(op)) {
            requireI18nKey(toastKeys[op], `createResourceCollection(${name}).toastKeys.${op}`);
        }
    }

    const transport = normalizeTransport(options.transport, `createResourceCollection(${name})`);
    const wsTimeoutMs = normalizeWsTimeout(options.wsTimeoutMs, transport, `createResourceCollection(${name})`);

    const itemPathTemplate = options.itemPathTemplate || `${baseUrl}/:${idField}`;
    const defaultRestMirror: Record<ResourceOperation, { method: string; path: string }> = {
        list:   { method: 'GET',    path: baseUrl },
        get:    { method: 'GET',    path: itemPathTemplate },
        create: { method: 'POST',   path: baseUrl },
        update: { method: 'PATCH',  path: itemPathTemplate },
        remove: { method: 'DELETE', path: itemPathTemplate },
    };
    const restMirrorInput = options.restMirror === undefined ? {} : options.restMirror;
    const mergedRestMirror: Record<string, RestMirrorEntry | { method: string; path: string }> = {};
    for (const op of operations) {
        const provided = restMirrorInput[op];
        if (provided) {
            mergedRestMirror[op] = provided;
        } else {
            const fallback = defaultRestMirror[op];
            if (fallback === undefined) {
                throw new Error(`createResourceCollection(${name}): rest mirror for ${op} missing`);
            }
            mergedRestMirror[op] = fallback;
        }
    }
    const restMirror = normalizeRestMirrorCollection(
        mergedRestMirror,
        operations,
        undefined,
        `createResourceCollection(${name})`,
    );

    const sliceKey = options.sliceKey || deriveSliceKey(name);
    const listQuery = options.listQuery || (() => ({ limit: 200 }));
    const mapItem: (item: TItem) => TItem = options.mapItem || ((x) => x);
    const listFetchAllPages = options.listFetchAllPages === true;
    const listPreserveItemsOnRefresh = options.listPreserveItemsOnRefresh === true;
    const buildItemUrl = options.buildItemUrl || ((id) => `${baseUrl}/${encodeURIComponent(id)}`);
    const reloadAfterMutation = options.reloadAfterMutation !== false;
    const requestHeaders = typeof options.requestHeaders === 'function' ? options.requestHeaders : null;
    const extraInitial = options.extraInitial && typeof options.extraInitial === 'object'
        ? options.extraInitial
        : null;
    const extraReducer = typeof options.extraReducer === 'function' ? options.extraReducer : null;
    const extraEffect = typeof options.extraEffect === 'function' ? options.extraEffect : null;
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
    const extraEvents: Record<string, string> = {};
    if (extraEventsConfig) {
        for (const [key, verb] of Object.entries(extraEventsConfig)) {
            if (typeof verb !== 'string' || verb.length === 0) {
                throw new Error(`createResourceCollection(${name}): extraEvents.${key} must be non-empty verb`);
            }
            extraEvents[key] = buildEventType(name, verb);
        }
    }
    const actionsMap: Record<string, string> = {};
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
    // Ключи actionsMap — ключи options.actions (A); значения — полные типы событий.
    function isBuiltActionMap(value: Record<string, string>): value is A {
        if (actionsConfig === null) {
            return Object.keys(value).length === 0;
        }
        return Object.keys(actionsConfig).every((key) => {
            const eventType = value[key];
            return typeof eventType === 'string' && eventType.length > 0;
        });
    }

    function isCollectionSlice(value: unknown): value is S {
        return isPlainRecord(value)
            && Array.isArray(value.items)
            && isPlainRecord(value.byId)
            && typeof value.loading === 'boolean';
    }

    if (!isBuiltActionMap(actionsMap)) {
        throw new Error(`createResourceCollection(${name}): actions map does not match options.actions`);
    }
    const actions = freeze(actionsMap);
    const baseSlice: ResourceCollectionSlice<TItem> = { ...INITIAL_SLICE };
    const mergedSlice = extraInitial ? { ...baseSlice, ...extraInitial } : baseSlice;
    if (!isCollectionSlice(mergedSlice)) {
        throw new Error(`createResourceCollection(${name}): initial slice must be an object with items`);
    }
    const initialSlice = freeze(mergedSlice);

    const hasCreate = operations.includes('create');

    function _withItems(state: S, items: ResourceItem[], listTotal?: number): S {
        const list = (items as TItem[]).map(mapItem);
        const byId: Record<string, TItem> = {};
        for (const item of list) {
            byId[String(item[idField])] = item;
        }
        const next: S = {
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

    function _withItem(state: S, item: ResourceItem): S {
        const mapped = mapItem(item as TItem);
        const id = String(mapped[idField]);
        const idx = state.items.findIndex((x) => x[idField] === mapped[idField]);
        const items = idx === -1 ? [...state.items, mapped] : state.items.map((x, i) => (i === idx ? mapped : x));
        const byId = { ...state.byId, [id]: mapped };
        return freeze({
            ...state,
            items: freeze(items),
            byId: freeze(byId),
            busyIds: _clearBusy(state.busyIds, id),
        });
    }

    function _withoutItem(state: S, id: string | number): S {
        const items = state.items.filter((x) => x[idField] !== id);
        const byId = { ...state.byId };
        delete byId[String(id)];
        return freeze({
            ...state,
            items: freeze(items),
            byId: freeze(byId),
            busyIds: _clearBusy(state.busyIds, id),
        });
    }

    function _setBusy(state: S, id: string | number | null | undefined): S {
        if (!id) return state;
        const next = { ...state.busyIds, [id]: true };
        return freeze({ ...state, busyIds: freeze(next) });
    }

    function _clearBusy(busyIds: Readonly<Record<string, boolean>>, id: string | number | null | undefined): Readonly<Record<string, boolean>> {
        if (!id || !busyIds[String(id)]) return busyIds;
        const next = { ...busyIds };
        delete next[String(id)];
        return freeze(next);
    }

    function _setLastError(state: S, op: string, message: string | null): S {
        return freeze({ ...state, lastError: freeze({ ...state.lastError, [op]: message }) });
    }

    function reducer(state: S = initialSlice, event: PlatformEvent): S {
        const next = _baseReducer(state, event);
        if (extraReducer) {
            const extended = extraReducer(next, event, events);
            if (extended && extended !== next) {
                return freeze(extended);
            }
        }
        return next;
    }

    function _requireItem(event: PlatformEvent, eventKey: string): ResourceItem {
        const p = event.payload;
        if (!isPlainRecord(p) || !isPlainRecord(p.item)) {
            throw new Error(`createResourceCollection(${name}): ${eventKey} payload.item required`);
        }
        return p.item;
    }

    function _requireId(event: PlatformEvent, eventKey: string): string | number {
        const p = event.payload;
        if (!isPlainRecord(p)) {
            throw new Error(`createResourceCollection(${name}): ${eventKey} payload.${idField} required`);
        }
        const id = p[idField];
        if ((typeof id !== 'string' && typeof id !== 'number') || id === '' || id === 0) {
            throw new Error(`createResourceCollection(${name}): ${eventKey} payload.${idField} required`);
        }
        return id;
    }

    function _requireMessage(event: PlatformEvent, eventKey: string): string {
        const p = event.payload;
        if (!isPlainRecord(p) || typeof p.message !== 'string') {
            throw new Error(`createResourceCollection(${name}): ${eventKey} payload.message required (string)`);
        }
        return p.message;
    }

    function _baseReducer(state: S, event: PlatformEvent): S {
        switch (event.type) {
            case events.LIST_REQUESTED: {
                const lastListQuery = freeze({ payload: event.payload === undefined ? null : event.payload });
                if (listPreserveItemsOnRefresh && state.items.length > 0) {
                    return freeze({ ...state, refreshing: true, error: null, lastListQuery });
                }
                return freeze({ ...state, loading: true, refreshing: false, error: null, lastListQuery });
            }
            case events.LIST_LOADED: {
                const page = listResponse(event.payload, `createResourceCollection(${name}): LIST_LOADED`);
                const resolvedTotal = typeof page.total === 'number' ? page.total : undefined;
                return _withItems(state, page.items, resolvedTotal);
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

    function _readSlice(state: Record<string, unknown>): S {
        // Корневое состояние шины хранит slices разных фабрик; slice этой фабрики кладёт её reducer.
        const slice = state[sliceKey];
        if (!isCollectionSlice(slice)) {
            throw new Error(`createResourceCollection(${name}): slice "${sliceKey}" not registered in bus`);
        }
        return slice;
    }

    const selectors = freeze({
        slice:    (state: Record<string, unknown>) => _readSlice(state),
        all:      (state: Record<string, unknown>) => _readSlice(state).items,
        byId:     (state: Record<string, unknown>) => _readSlice(state).byId,
        loading:  (state: Record<string, unknown>) => Boolean(_readSlice(state).loading),
        refreshing: (state: Record<string, unknown>) => Boolean(_readSlice(state).refreshing),
        listTotal: (state: Record<string, unknown>) => {
            const total = _readSlice(state).listTotal;
            return typeof total === 'number' ? total : null;
        },
        error:    (state: Record<string, unknown>) => _readSlice(state).error,
        busyIds:  (state: Record<string, unknown>) => _readSlice(state).busyIds,
        lastError:(state: Record<string, unknown>) => _readSlice(state).lastError,
        isBusy:   (id: string | number) => (state: Record<string, unknown>) => Boolean(_readSlice(state).busyIds[String(id)]),
        createInFlight: (state: Record<string, unknown>) => Boolean(_readSlice(state).createInFlight),
    });

    function _requestPayload(event: PlatformEvent): Record<string, unknown> {
        if (event.payload === null || event.payload === undefined) return {};
        if (!isPlainRecord(event.payload)) {
            throw new Error(`createResourceCollection(${name}): event.payload for ${event.type} must be object|null`);
        }
        return event.payload;
    }

    async function _doRequest(opSpec: _OpSpec, event: PlatformEvent, ctx: EffectCtx): Promise<unknown> {
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
        const url = opSpec.url;
        if (url === undefined || url === null) {
            throw new Error(`createResourceCollection: ${opSpec.op} url required`);
        }
        return httpRequest({
            method: opSpec.method,
            url,
            body: opSpec.httpBody,
            query: opSpec.httpQuery,
            headers,
        });
    }

    function _isTransportError(err: unknown): err is HttpError | WsTransportError {
        return err instanceof HttpError || err instanceof WsTransportError;
    }

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
        switch (event.type) {
            case events.LIST_REQUESTED: {
                if (!operations.includes('list')) return;
                const payload = _requestPayload(event);
                let data;
                try {
                    if (listFetchAllPages) {
                        const baseQuery = queryRecord(listQuery(payload), `createResourceCollection(${name}): listQuery`);
                        const pageLimit = typeof baseQuery.limit === 'number' ? baseQuery.limit : 200;
                        let off = typeof baseQuery.offset === 'number' ? baseQuery.offset : 0;
                        const mergedItems: ResourceItem[] = [];
                        let total = 0;
                        for (;;) {
                            const pageQuery = httpQueryFields(
                                { ...baseQuery, ...payload, limit: pageLimit, offset: off },
                                `createResourceCollection(${name})`,
                            );
                            const pageData = await _doRequest({
                                commandType: events.LIST_REQUESTED,
                                succeeded: events.LIST_LOADED,
                                failed: events.LIST_FAILED,
                                wsPayload: pageQuery,
                                method: 'GET',
                                url: baseUrl,
                                httpQuery: pageQuery,
                                op: 'list',
                                headersPayload: payload,
                            }, event, ctx);
                            const pd = listResponse(pageData, `createResourceCollection(${name}): list response`);
                            if (typeof pd.total !== 'number') {
                                throw new Error(`createResourceCollection(${name}): list response.total must be number when listFetchAllPages is true`);
                            }
                            total = pd.total;
                            mergedItems.push(...pd.items);
                            if (mergedItems.length >= total) {
                                break;
                            }
                            if (pd.items.length < pageLimit) {
                                break;
                            }
                            off += pageLimit;
                        }
                        ctx.dispatch(events.LIST_LOADED, { items: mergedItems, total }, { causation_id: event.id, source: _transportSource() });
                        return;
                    }
                    const singleQuery = queryRecord(listQuery(payload), `createResourceCollection(${name}): listQuery`);
                    data = await _doRequest({
                        commandType: events.LIST_REQUESTED,
                        succeeded: events.LIST_LOADED,
                        failed: events.LIST_FAILED,
                        wsPayload: { ...singleQuery, ...payload },
                        method: 'GET',
                        url: baseUrl,
                        httpQuery: httpQueryFields(singleQuery, `createResourceCollection(${name})`),
                        op: 'list',
                        headersPayload: payload,
                    }, event, ctx);
                } catch (err) {
                    if (!_isTransportError(err)) throw err;
                    ctx.dispatch(events.LIST_FAILED, { message: err.message }, { causation_id: event.id, source: _transportSource() });
                    return;
                }
                const d = listResponse(data, `createResourceCollection(${name}): list response`);
                ctx.dispatch(
                    events.LIST_LOADED,
                    {
                        items: d.items,
                        total: typeof d.total === 'number' ? d.total : undefined,
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
                    if (!isPlainRecord(item)) {
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
                const rawSlice = isPlainRecord(st) ? st[sliceKey] : undefined;
                if (isPlainRecord(rawSlice)) {
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
                    if (!isPlainRecord(item) || !item[idField]) {
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
                            { type: 'error', i18n_key: toastKeys.create_error, i18n_vars: { detail: err.message } },
                            { causation_id: event.id },
                        );
                    }
                }
                return;
            }
            case events.UPDATE_REQUESTED: {
                if (!operations.includes('update')) return;
                const payload = _requestPayload(event);
                const id = payload[idField] as string | number;
                if (!id) throw new Error(`${name}: ${idField} required for update_requested`);
                const { [idField]: _drop, ...body } = payload;
                void _drop;
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
                    const finalItem = isPlainRecord(response) && response[idField]
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
