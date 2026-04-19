/**
 * EventBus — единая точка входа для всех событий платформы.
 *
 * Поток dispatch:
 *   1. Нормализация: если передана пара (type, payload) — упаковываем в Event через createEvent.
 *   2. Middleware (предобработка/валидация/телеметрия).
 *   3. Append в EventLog.
 *   4. Reducers: синхронно собираем новый snapshot state.
 *   5. Subscribers (селекторы → Lit-компоненты) — синхронно, чтобы UI обновился в том же тике.
 *   6. Effects: выполняются АСИНХРОННО (queueMicrotask). Любой dispatch внутри
 *      эффекта попадает в этот же bus и проходит весь цикл заново.
 *
 * Принципы:
 *   - State (`getState()`) — иммутабелен; меняется ТОЛЬКО через reducers.
 *   - Никто, кроме reducers, не имеет права писать в state. Прямой setState не существует.
 *   - Эффекты не возвращают state — только dispatch новых событий.
 */

import { createEvent, assertEventType } from './contract.js';

function _shallowEqual(a, b) {
    if (a === b) return true;
    if (a === null || b === null || a === undefined || b === undefined) return false;
    if (typeof a !== 'object' || typeof b !== 'object') return false;
    const ak = Object.keys(a);
    const bk = Object.keys(b);
    if (ak.length !== bk.length) return false;
    for (const k of ak) {
        if (a[k] !== b[k]) return false;
    }
    return true;
}

export class EventBus {
    /**
     * @param {{
     *   reducer: (state: object, event: object) => object,
     *   initialState: object,
     *   log: { append: (event: object) => void },
     *   middleware?: Array<(event: object, ctx: object) => object|null>,
     * }} options
     */
    constructor({ reducer, initialState, log, middleware = [] }) {
        if (typeof reducer !== 'function') {
            throw new Error('EventBus: reducer is required');
        }
        if (!log || typeof log.append !== 'function') {
            throw new Error('EventBus: log with append() is required');
        }
        this._reducer = reducer;
        this._state = Object.freeze(initialState || {});
        this._log = log;
        this._middleware = middleware.slice();
        this._effects = [];
        this._stateSubscribers = new Set();
        this._typeSubscribers = new Map();
        this._anyEventSubscribers = new Set();
        this._inDispatch = false;
        this._effectQueue = [];
        this._effectQueueScheduled = false;
    }

    getState() {
        return this._state;
    }

    /**
     * Зарегистрировать middleware. Вызывается до append в лог.
     * Возврат null отменяет событие; возврат другого event — заменяет.
     */
    registerMiddleware(mw) {
        if (typeof mw !== 'function') {
            throw new Error('EventBus.registerMiddleware: function required');
        }
        this._middleware.push(mw);
        return () => {
            const idx = this._middleware.indexOf(mw);
            if (idx !== -1) this._middleware.splice(idx, 1);
        };
    }

    /**
     * Зарегистрировать effect. Effect — это `(event, ctx) => void|Promise<void>`.
     * ctx содержит { dispatch, getState }.
     */
    registerEffect(effect) {
        if (typeof effect !== 'function') {
            throw new Error('EventBus.registerEffect: function required');
        }
        this._effects.push(effect);
        return () => {
            const idx = this._effects.indexOf(effect);
            if (idx !== -1) this._effects.splice(idx, 1);
        };
    }

    /**
     * Подписка на изменение всего state.
     */
    subscribeState(callback) {
        if (typeof callback !== 'function') {
            throw new Error('EventBus.subscribeState: function required');
        }
        this._stateSubscribers.add(callback);
        return () => this._stateSubscribers.delete(callback);
    }

    /**
     * Подписка на конкретный тип события (для UI-реакций без изменения state).
     * Должна использоваться РЕДКО — основной поток через селекторы.
     */
    subscribeType(type, callback) {
        assertEventType(type);
        if (!this._typeSubscribers.has(type)) {
            this._typeSubscribers.set(type, new Set());
        }
        this._typeSubscribers.get(type).add(callback);
        return () => {
            const set = this._typeSubscribers.get(type);
            if (set) {
                set.delete(callback);
                if (set.size === 0) this._typeSubscribers.delete(type);
            }
        };
    }

    /**
     * Подписка на любое событие (для devtools).
     */
    subscribeAny(callback) {
        this._anyEventSubscribers.add(callback);
        return () => this._anyEventSubscribers.delete(callback);
    }

    /**
     * Подписка на срез state через селектор. Колбэк вызывается только при изменении.
     * @param {(state: object) => any} selector
     * @param {(value: any, prevValue: any) => void} callback
     * @param {{equality?: (a: any, b: any) => boolean}} [opts]
     */
    subscribeSelector(selector, callback, opts) {
        if (typeof selector !== 'function' || typeof callback !== 'function') {
            throw new Error('EventBus.subscribeSelector: selector and callback required');
        }
        const equality = (opts && opts.equality) || _shallowEqual;
        let last = selector(this._state);
        callback(last, undefined);
        const sub = () => {
            const next = selector(this._state);
            if (!equality(next, last)) {
                const prev = last;
                last = next;
                callback(next, prev);
            }
        };
        return this.subscribeState(sub);
    }

    /**
     * Главный метод. Принимает либо готовый event-объект, либо `(type, payload, meta)`.
     */
    dispatch(typeOrEvent, payload, meta) {
        let event;
        if (typeOrEvent && typeof typeOrEvent === 'object' && typeof typeOrEvent.type === 'string') {
            event = typeOrEvent;
            assertEventType(event.type);
            if (!event.id || !event.meta) {
                event = createEvent(event.type, event.payload, event.meta || {});
            }
        } else {
            event = createEvent(typeOrEvent, payload, meta || {});
        }

        for (const mw of this._middleware) {
            const result = mw(event, { getState: () => this._state });
            if (result === null) {
                return null;
            }
            if (result && typeof result === 'object') {
                event = result;
            }
        }

        this._log.append(event);

        const prevState = this._state;
        const nextState = this._reducer(prevState, event);
        if (nextState !== prevState) {
            this._state = Object.freeze(nextState);
            for (const sub of this._stateSubscribers) {
                sub(this._state, prevState, event);
            }
        }

        const typeSubs = this._typeSubscribers.get(event.type);
        if (typeSubs) {
            for (const sub of typeSubs) {
                sub(event);
            }
        }
        for (const sub of this._anyEventSubscribers) {
            sub(event);
        }

        if (this._effects.length > 0) {
            this._effectQueue.push(event);
            this._scheduleEffects();
        }

        return event;
    }

    _scheduleEffects() {
        if (this._effectQueueScheduled) return;
        this._effectQueueScheduled = true;
        queueMicrotask(() => {
            this._effectQueueScheduled = false;
            const queue = this._effectQueue;
            this._effectQueue = [];
            const ctx = {
                dispatch: (t, p, m) => this.dispatch(t, p, m),
                getState: () => this._state,
            };
            for (const event of queue) {
                for (const effect of this._effects) {
                    Promise.resolve()
                        .then(() => effect(event, ctx))
                        .catch((err) => {
                            console.error('[EventBus] Effect failed', { event, err });
                            this.dispatch('ui/effect/failed', {
                                event_type: event.type,
                                event_id: event.id,
                                error: String(err && err.message ? err.message : err),
                            }, { causation_id: event.id, source: 'system' });
                        });
                }
            }
        });
    }
}
