/**
 * Мерж исходов команд и push-событий в state фабрик.
 *
 * Страницы и компоненты не перезагружают данные по событию: коллекция мержит
 * элемент через `upsertItem`/`removeItem` в `extraReducer`, а то, что смержить
 * нельзя (граф, агрегаты, вложения с асинхронной обработкой), повторно загружает
 * фабрика в `onSuccess`/`extraEffect` через `rerunLastRequest`/`reloadLastList`:
 * state хранит последний payload (`lastRequest` у async-op, `lastListQuery` у
 * коллекции), ничего не угадывается. Фабрика, которая ещё не запускалась, не трогается.
 */

import type { EffectCtx, PlatformEvent } from '../contract.js';
import type { PlatformFactory } from '../factory-registry.js';
import { isPlainRecord } from '../payload.js';
import type { AsyncOpFactory } from './async-op.js';

interface CollectionStateLike extends Record<string, unknown> {
    items: readonly (Record<string, unknown> | null)[];
    byId: Readonly<Record<string, Record<string, unknown> | null>>;
    lastListQuery?: { payload?: unknown } | null;
}

interface AsyncOpFactoryLike extends PlatformFactory {
    kind: 'async-op';
    sliceKey: string;
    events: { REQUESTED: string };
}

/** Результат `createAsyncOp` по его фабрике — с `commandType` это wire-тип из `PlatformCommandMap`. */
export type AsyncOpResultOf<F> = F extends AsyncOpFactory<infer R, infer _S, infer _A> ? R : never;

/**
 * Типизированный `result` локального `<op>/succeeded`-события фабрики.
 * `null` — событие другого типа или payload без `result` (сломанный контракт
 * отсекает _baseReducer фабрики до extraReducer).
 */
export function opSucceededResult<F extends { events: { SUCCEEDED: string } }>(
    event: PlatformEvent,
    op: F,
): AsyncOpResultOf<F> | null {
    if (event.type !== op.events.SUCCEEDED) return null;
    if (!isPlainRecord(event.payload)) return null;
    const result = event.payload.result;
    return result === undefined || result === null ? null : (result as AsyncOpResultOf<F>);
}

interface ResourceCollectionFactoryLike extends PlatformFactory {
    kind: 'resource-collection';
    sliceKey: string;
    events: { LIST_REQUESTED: string };
}

function isRebuiltState<S extends CollectionStateLike>(value: Record<string, unknown>, state: S): value is S {
    if (!Array.isArray(value.items) || !isPlainRecord(value.byId)) return false;
    for (const key of Object.keys(state)) {
        if (!Object.prototype.hasOwnProperty.call(value, key)) return false;
    }
    return true;
}

function replaceCollection<S extends CollectionStateLike>(
    state: S,
    items: CollectionStateLike['items'],
    byId: CollectionStateLike['byId'],
): S {
    const next: Record<string, unknown> = {};
    for (const [key, value] of Object.entries(state)) next[key] = value;
    next.items = items;
    next.byId = byId;
    if (!isRebuiltState(next, state)) {
        throw new Error('merge: rebuilt collection state is incomplete');
    }
    return next;
}

function busSlice(state: unknown, sliceKey: string, label: string): Record<string, unknown> | null {
    if (!isPlainRecord(state)) {
        throw new Error(`${label}: bus state must be an object`);
    }
    const slice = state[sliceKey];
    if (slice === undefined || slice === null) return null;
    if (!isPlainRecord(slice)) {
        throw new Error(`${label}: slice ${sliceKey} must be an object`);
    }
    return slice;
}

function storedPayload(slice: Record<string, unknown>, field: string, label: string): { present: true; payload: unknown } | { present: false } {
    const request = slice[field];
    if (request === undefined || request === null) return { present: false };
    if (!isPlainRecord(request)) {
        throw new Error(`${label}: ${field} must be an object`);
    }
    return { present: true, payload: request.payload };
}

export function upsertItem<S extends CollectionStateLike>(state: S, item: Record<string, unknown>, idField: string): S {
    const id = item[idField];
    if (id === undefined || id === null || id === '') {
        throw new Error(`upsertItem: item.${idField} required`);
    }
    const idx = state.items.findIndex((existing) => existing && existing[idField] === id);
    const items = idx === -1
        ? [...state.items, item]
        : state.items.map((existing, i) => (i === idx ? item : existing));
    const byId = { ...state.byId, [String(id)]: item };
    return replaceCollection(state, items, byId);
}

export function removeItem<S extends CollectionStateLike>(state: S, id: unknown, idField: string): S {
    if (!state.items.some((existing) => existing && existing[idField] === id)) {
        return state;
    }
    const byId = { ...state.byId };
    delete byId[String(id)];
    const items = state.items.filter((existing) => !existing || existing[idField] !== id);
    return replaceCollection(state, items, byId);
}

export function rerunLastRequest(ctx: EffectCtx, op: AsyncOpFactoryLike, { when }: { when?: (payload: unknown) => boolean } = {}): boolean {
    if (!op || op.kind !== 'async-op') {
        throw new Error('rerunLastRequest: async-op factory required');
    }
    const slice = busSlice(ctx.getState(), op.sliceKey, 'rerunLastRequest');
    if (slice === null) return false;
    const stored = storedPayload(slice, 'lastRequest', 'rerunLastRequest');
    if (!stored.present) return false;
    if (typeof when === 'function' && when(stored.payload) !== true) return false;
    ctx.dispatch(op.events.REQUESTED, stored.payload);
    return true;
}

export function reloadLastList(ctx: EffectCtx, resource: ResourceCollectionFactoryLike, { when }: { when?: (payload: unknown) => boolean } = {}): boolean {
    if (!resource || resource.kind !== 'resource-collection') {
        throw new Error('reloadLastList: resource-collection factory required');
    }
    const slice = busSlice(ctx.getState(), resource.sliceKey, 'reloadLastList');
    if (slice === null) return false;
    const stored = storedPayload(slice, 'lastListQuery', 'reloadLastList');
    if (!stored.present) return false;
    if (typeof when === 'function' && when(stored.payload) !== true) return false;
    ctx.dispatch(resource.events.LIST_REQUESTED, stored.payload);
    return true;
}
