/**
 * Утилиты создания и комбинирования селекторов.
 *
 * Селектор — чистая функция `state => value`. Используется компонентами
 * через `this.select(selectorFn)` и `bus.subscribeSelector`.
 *
 * createSelector — мемоизация по входам (как reselect): пересчитывает результат
 * только если хотя бы один из входов изменился по reference.
 */

import { isPlainRecord } from './payload.js';

function _identityEqual(a: unknown, b: unknown): boolean {
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
export function createSelector<S, R>(
    inputs: Array<(state: S) => unknown>,
    projector: (...args: unknown[]) => R,
): (state: S) => R {
    if (!Array.isArray(inputs) || inputs.length === 0) {
        throw new Error('createSelector: inputs must be a non-empty array');
    }
    if (typeof projector !== 'function') {
        throw new Error('createSelector: projector must be a function');
    }
    let lastArgs: unknown[] | null = null;
    let cached: { result: R } | null = null;
    return function memoized(state: S): R {
        const args = inputs.map((sel) => sel(state));
        if (
            cached
            && lastArgs
            && lastArgs.length === args.length
            && lastArgs.every((value, index) => _identityEqual(value, args[index]))
        ) {
            return cached.result;
        }
        const result = projector(...args);
        lastArgs = args;
        cached = { result };
        return result;
    };
}

/**
 * Семейство селекторов с параметром (например: selectChannelById(channelId)).
 * Кеш — `Map<string, selector>`; ключ строится через keyFn(arg).
 */
export function selectorFamily<A, Sel>({ key, build }: {
    key: (arg: A) => string;
    build: (arg: A) => Sel;
}): (arg: A) => Sel {
    if (typeof key !== 'function' || typeof build !== 'function') {
        throw new Error('selectorFamily: { key, build } required');
    }
    const cache = new Map<string, Sel>();
    return function family(arg: A): Sel {
        const k = key(arg);
        if (!cache.has(k)) {
            cache.set(k, build(arg));
        }
        const cached = cache.get(k);
        if (cached === undefined) {
            throw new Error('selectorFamily: cached selector missing');
        }
        return cached;
    };
}

/**
 * Хелпер: селектор поля по пути 'a.b.c'. Не мемоизирован — для простых выборов.
 */
export function pluck(path: string): (state: unknown) => unknown {
    const segs = path.split('.');
    return function pluckSelector(state) {
        let cur: unknown = state;
        for (const s of segs) {
            if (!isPlainRecord(cur)) return undefined;
            cur = cur[s];
        }
        return cur;
    };
}
