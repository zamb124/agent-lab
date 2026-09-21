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

export function upsertItem(state, item, idField) {
    const id = item[idField];
    if (id === undefined || id === null || id === '') {
        throw new Error(`upsertItem: item.${idField} required`);
    }
    const idx = state.items.findIndex((existing) => existing && existing[idField] === id);
    const items = idx === -1
        ? [...state.items, item]
        : state.items.map((existing, i) => (i === idx ? item : existing));
    return { ...state, items, byId: { ...state.byId, [id]: item } };
}

export function removeItem(state, id, idField) {
    if (!state.items.some((existing) => existing && existing[idField] === id)) {
        return state;
    }
    const byId = { ...state.byId };
    delete byId[id];
    return { ...state, items: state.items.filter((existing) => !existing || existing[idField] !== id), byId };
}

export function rerunLastRequest(ctx, op, { when } = {}) {
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

export function reloadLastList(ctx, resource, { when } = {}) {
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
