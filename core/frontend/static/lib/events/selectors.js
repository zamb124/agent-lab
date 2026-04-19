/**
 * Утилиты создания и комбинирования селекторов.
 *
 * Селектор — чистая функция `state => value`. Используется компонентами
 * через `this.select(selectorFn)` и `bus.subscribeSelector`.
 *
 * createSelector — мемоизация по входам (как reselect): пересчитывает результат
 * только если хотя бы один из входов изменился по reference.
 */

function _identityEqual(a, b) {
    return a === b;
}

/**
 * Создать мемоизированный селектор.
 *
 * @example
 *   const selectActiveCompany = createSelector(
 *     [(s) => s.auth.user, (s) => s.auth.activeCompanyId],
 *     (user, companyId) => user && user.companies ? user.companies[companyId] : null,
 *   );
 */
export function createSelector(inputs, projector) {
    if (!Array.isArray(inputs) || inputs.length === 0) {
        throw new Error('createSelector: inputs must be a non-empty array');
    }
    if (typeof projector !== 'function') {
        throw new Error('createSelector: projector must be a function');
    }
    let lastArgs = null;
    let lastResult = null;
    return function memoized(state) {
        const args = inputs.map((sel) => sel(state));
        if (lastArgs && lastArgs.length === args.length && lastArgs.every((v, i) => _identityEqual(v, args[i]))) {
            return lastResult;
        }
        lastArgs = args;
        lastResult = projector(...args);
        return lastResult;
    };
}

/**
 * Семейство селекторов с параметром (например: selectChannelById(channelId)).
 * Кеш — `Map<string, selector>`; ключ строится через keyFn(arg).
 */
export function selectorFamily({ key, build }) {
    if (typeof key !== 'function' || typeof build !== 'function') {
        throw new Error('selectorFamily: { key, build } required');
    }
    const cache = new Map();
    return function family(arg) {
        const k = key(arg);
        if (!cache.has(k)) {
            cache.set(k, build(arg));
        }
        return cache.get(k);
    };
}

/**
 * Хелпер: селектор поля по пути 'a.b.c'. Не мемоизирован — для простых выборов.
 */
export function pluck(path) {
    const segs = path.split('.');
    return function pluckSelector(state) {
        let cur = state;
        for (const s of segs) {
            if (cur === null || cur === undefined) return undefined;
            cur = cur[s];
        }
        return cur;
    };
}
