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

import type { EffectCtx } from '../contract.js';
import type { PlatformFactory } from '../factory-registry.js';

interface CollectionStateLike extends Record<string, unknown> {
    items: readonly (Record<string, unknown> | null)[];
    byId: Readonly<Record<string, Record<string, unknown> | null>>;
    lastListQuery?: { payload?: unknown } | null;
}

interface OpSliceLike extends Record<string, unknown> {
    lastRequest?: { payload?: unknown } | null;
}

interface AsyncOpFactoryLike extends PlatformFactory {
    kind: 'async-op';
    sliceKey: string;
    events: { REQUESTED: string };
}

interface ResourceCollectionFactoryLike extends PlatformFactory {
    kind: 'resource-collection';
    sliceKey: string;
    events: { LIST_REQUESTED: string };
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
    return { ...state, items, byId: { ...state.byId, [String(id)]: item } } as S;
}

export function removeItem<S extends CollectionStateLike>(state: S, id: unknown, idField: string): S {
    if (!state.items.some((existing) => existing && existing[idField] === id)) {
        return state;
    }
    const byId = { ...state.byId };
    delete byId[String(id)];
    return { ...state, items: state.items.filter((existing) => !existing || existing[idField] !== id), byId } as S;
}

export function rerunLastRequest(ctx: EffectCtx<Record<string, OpSliceLike>>, op: AsyncOpFactoryLike, { when }: { when?: (payload: unknown) => boolean } = {}): boolean {
    if (!op || op.kind !== 'async-op') {
        throw new Error('rerunLastRequest: async-op factory required');
    }
    const slice = ctx.getState()[op.sliceKey];
    if (!slice || !slice.lastRequest) {
        return false;
    }
    if (typeof when === 'function' && when(slice.lastRequest.payload) !== true) {
        return false;
    }
    ctx.dispatch(op.events.REQUESTED, slice.lastRequest.payload);
    return true;
}

export function reloadLastList(ctx: EffectCtx<Record<string, CollectionStateLike>>, resource: ResourceCollectionFactoryLike, { when }: { when?: (payload: unknown) => boolean } = {}): boolean {
    if (!resource || resource.kind !== 'resource-collection') {
        throw new Error('reloadLastList: resource-collection factory required');
    }
    const slice = ctx.getState()[resource.sliceKey];
    if (!slice || !slice.lastListQuery) {
        return false;
    }
    if (typeof when === 'function' && when(slice.lastListQuery.payload) !== true) {
        return false;
    }
    ctx.dispatch(resource.events.LIST_REQUESTED, slice.lastListQuery.payload);
    return true;
}
