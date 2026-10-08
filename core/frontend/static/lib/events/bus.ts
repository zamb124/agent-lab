/**
 * EventBus — единая точка входа для всех событий платформы.
 *
 * Поток dispatch:
 *   1. Нормализация: если передана пара (type, payload) — упаковываем в Event через createEvent.
 *   2. Middleware (предобработка/валидация/телеметрия).
 *   3. Append в EventLog.
 *   4. Reducers: синхронно собираем новый projection snapshot.
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
import type { PlatformEvent, EventMetaInput, EventSource, EffectCtx } from './contract.js';

export type Reducer<S> = (state: S, event: PlatformEvent) => S;
export type EventMiddleware<S> = (event: PlatformEvent, ctx: { getState: () => S }) => PlatformEvent | null | void;
/**
 * Effect-функция. `S = never` — эффект объявляет собственный view на state
 * (платформенные эффекты видят только нужные слайсы), EventBus не может
 * статически проверить композитное состояние: слайсы сервисов подключаются
 * динамически в bootstrap.
 */
export type EventEffect<S = never> = (event: PlatformEvent, ctx: EffectCtx<S>) => void | Promise<void>;
interface EventLogLike { append: (event: PlatformEvent) => void }

function _shallowEqual(a: unknown, b: unknown): boolean {
    if (a === b) return true;
    if (a === null || b === null || a === undefined || b === undefined) return false;
    if (typeof a !== 'object' || typeof b !== 'object') return false;
    const ak = Object.keys(a);
    const bk = Object.keys(b);
    if (ak.length !== bk.length) return false;
    for (const k of ak) {
        if ((a as Record<string, unknown>)[k] !== (b as Record<string, unknown>)[k]) return false;
    }
    return true;
}

export class EventBus<S extends object = Record<string, unknown>> {
    private _reducer: Reducer<S>;
    private _state: Readonly<S>;
    private _log: EventLogLike;
    private _middleware: Array<EventMiddleware<S>>;
    private _effects: Array<EventEffect>;
    private _stateSubscribers: Set<(state: S, prev: S, event: PlatformEvent) => void>;
    private _typeSubscribers: Map<string, Set<(event: PlatformEvent) => void>>;
    private _anyEventSubscribers: Set<(event: PlatformEvent) => void>;
    private _inDispatch: boolean;
    private _effectQueue: PlatformEvent[];
    private _effectQueueScheduled: boolean;

    constructor({ reducer, initialState, log, middleware = [] }: {
        reducer: Reducer<S>;
        initialState: S;
        log: EventLogLike;
        middleware?: Array<EventMiddleware<S>>;
    }) {
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

    getState(): Readonly<S> {
        return this._state;
    }

    /**
     * Зарегистрировать middleware. Вызывается до append в лог.
     * Возврат null отменяет событие; возврат другого event — заменяет.
     */
    registerMiddleware(mw: EventMiddleware<S>): () => void {
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
    registerEffect(effect: EventEffect): () => void {
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
    subscribeState(callback: (state: S, prev: S, event: PlatformEvent) => void): () => void {
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
    subscribeType(type: string, callback: (event: PlatformEvent) => void): () => void {
        assertEventType(type);
        if (!this._typeSubscribers.has(type)) {
            this._typeSubscribers.set(type, new Set());
        }
        this._typeSubscribers.get(type)!.add(callback);
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
    subscribeAny(callback: (event: PlatformEvent) => void): () => void {
        this._anyEventSubscribers.add(callback);
        return () => this._anyEventSubscribers.delete(callback);
    }

    /**
     * Подписка на срез state через селектор. Колбэк вызывается только при изменении.
     * @param {(state: object) => any} selector
     * @param {(value: any, prevValue: any) => void} callback
     * @param {{equality?: (a: any, b: any) => boolean}} [opts]
     */
    subscribeSelector<V>(selector: (state: S) => V, callback: (value: V, prevValue: V | undefined) => void, opts?: { equality?: (a: V, b: V) => boolean }): () => void {
        if (typeof selector !== 'function' || typeof callback !== 'function') {
            throw new Error('EventBus.subscribeSelector: selector and callback required');
        }
        const equality: (a: V, b: V) => boolean = (opts && opts.equality) || _shallowEqual;
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
    dispatch(typeOrEvent: string | PlatformEvent, payload?: unknown, meta?: EventMetaInput): PlatformEvent | null {
        let event: PlatformEvent;
        if (typeOrEvent && typeof typeOrEvent === 'object' && typeof typeOrEvent.type === 'string') {
            event = typeOrEvent;
            assertEventType(event.type);
            if (!event.id || !event.meta) {
                event = createEvent(event.type, event.payload, (event.meta || {}) as EventMetaInput);
            }
        } else {
            event = createEvent(typeOrEvent as string, payload, meta || {});
        }

        for (const mw of this._middleware) {
            const result = mw(event, { getState: () => this._state });
            if (result === null) {
                return null;
            }
            if (result && typeof result === 'object') {
                event = result as PlatformEvent;
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

    private _scheduleEffects(): void {
        if (this._effectQueueScheduled) return;
        this._effectQueueScheduled = true;
        queueMicrotask(() => {
            this._effectQueueScheduled = false;
            const queue = this._effectQueue;
            this._effectQueue = [];
            const ctx = {
                dispatch: (t: string | PlatformEvent, p?: unknown, m?: EventMetaInput) => this.dispatch(t, p, m),
                getState: () => this._state,
            };
            for (const event of queue) {
                for (const effect of this._effects) {
                    Promise.resolve()
                        .then(() => effect(event, ctx as never))
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
