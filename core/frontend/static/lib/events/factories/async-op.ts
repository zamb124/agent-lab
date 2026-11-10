/**
 * createAsyncOp — фабрика для одиночной асинхронной операции.
 *
 * Назначение: укрыть стандартную тройку REQUESTED/SUCCEEDED/FAILED, slice
 * `{ busy, error, lastResult, lastRequestId }` и effect, мапящий ошибки
 * транспорта в FAILED-событие. Любая ошибка не-transport пробрасывается —
 * никаких фолбеков, никаких тихих проглатываний.
 *
 * Контракт обязательных полей (отсутствие любого — `throw` на старте):
 *   - name: 'scope/entity' (lowercase, snake_case)
 *   - request({ payload, ctx, event }) — функция выполнения. Для
 *     transport='ws' можно опустить (будет автоматически отправлен
 *     wsRequest с типом REQUESTED и payload as-is).
 *   - successToastKey + errorToastKey  ИЛИ  silent: true (взаимоисключающие)
 *   - restMirror: { method, path } — обязательный платформенный инвариант
 *     REST-зеркала команды. См. `architecture.mdc`.
 *
 * Опциональные:
 *   - transport: 'http' | 'ws' (default 'http'). Для 'ws' обязателен
 *     wsTimeoutMs (положительное число).
 *   - commandType: '<scope>/<entity>/<verb>_requested' — переопределяет тип
 *     WS-фрейма (по умолчанию используется events.REQUESTED). Допустим только
 *     при transport='ws'. Reply-типы выводятся автоматически:
 *     `<commandType без _requested>_succeeded` / `_failed`. Полезен, когда
 *     имя фабрики (`sync/calls_invite`) не совпадает с каноничным именем
 *     backend-команды (`sync/calls/invite_requested`).
 *   - extraInitial: { ... } — мерджится в initial slice.
 *   - SUCCEEDED payload = { result, request } (request — payload команды);
 *   - slice.lastRequest = { payload } последнего REQUESTED (null до первого запуска);
 *   - extraReducer(state, event, events) — вызывается ПОСЛЕ базового reducer'а;
 *     возвращает новое состояние или то же ссылочно (no-op).
 *   - extraEffect(event, ctx, events) — до базового effect; return true = handled
 *     (не выполнять REQUESTED transport). Для push → REQUESTED reload/patch.
 *   - extraEvents: { KEY: 'verb' } — дополнительные события scope namespace.
 *   - actions: { methodName: 'verb' } — дополнительные именованные действия,
 *     которые OpController обязан выставить как методы (`ctl.methodName()`).
 */

import { CoreEvents, assertEventType } from '../contract.js';
import { isPlainRecord } from '../payload.js';
import { HttpError } from '../http.js';
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
import type { EffectCtx, PlatformEvent, PlatformEventMeta } from '../contract.js';
import { registerFactory } from '../factory-registry.js';
import type { ActionMap, PlatformFactory } from '../factory-registry.js';
import type { SliceDef } from '../reducers/index.js';
import type { FactoryTransport, RestMirrorEntry } from './_transport.js';

const _REQUESTED_SUFFIX = '_requested';

function _normalizeCommandType(value: unknown, ownerLabel: string): string | null {
    if (value === undefined || value === null) return null;
    if (typeof value !== 'string' || value.length === 0) {
        throw new Error(`${ownerLabel}: commandType must be non-empty string`);
    }
    assertEventType(value);
    if (!value.endsWith(_REQUESTED_SUFFIX)) {
        throw new Error(
            `${ownerLabel}: commandType "${value}" must end with "_requested" `
            + '(reply types are derived as <type without _requested>_succeeded / _failed).',
        );
    }
    return value;
}

function _deriveSucceededType(commandType: string): string {
    return commandType.slice(0, -_REQUESTED_SUFFIX.length) + '_succeeded';
}

function _deriveFailedType(commandType: string): string {
    return commandType.slice(0, -_REQUESTED_SUFFIX.length) + '_failed';
}

function requestedEvent(type: string, payload: unknown, causationId: string): PlatformEvent {
    const meta: PlatformEventMeta = {
        ts: Date.now(),
        source: 'local',
        causation_id: causationId.length > 0 ? causationId : null,
        correlation_id: null,
        trace_id: null,
    };
    return { type, payload, id: causationId, meta };
}

function toastSuppressed(payload: unknown, flag: 'suppressErrorToast' | 'suppressSuccessToast'): boolean {
    return isPlainRecord(payload) && payload[flag] === true;
}
import {
    WsTransportError,
    normalizeRestMirrorSingle,
    normalizeTransport,
    normalizeWsTimeout,
    transportRequest,
} from './_transport.js';
import type { PlatformCommandMap } from '../wire/index.js';

const INITIAL_SLICE = freeze({
    busy: false,
    error: null,
    lastResult: null,
    lastRequestId: null,
    lastRequest: null,
});

export interface AsyncOpSlice<TResult = unknown> {
    busy: boolean;
    error: string | null;
    lastResult: TResult | null;
    lastRequestId: string | null;
    lastRequest: { payload: unknown } | null;
    [key: string]: unknown;
}

export type AsyncOpRequest<TResult = unknown> = (args: { payload: unknown; ctx: EffectCtx; event: PlatformEvent }) => Promise<TResult>;
export type AsyncOpReducer<S extends AsyncOpSlice<unknown> = AsyncOpSlice> = (state: S, event: PlatformEvent, events: Readonly<Record<string, string>>) => NoInfer<S> | null | undefined;
export type AsyncOpEffect = (event: PlatformEvent, ctx: EffectCtx, events: Readonly<Record<string, string>>) => boolean | void | Promise<boolean | void>;

export interface AsyncOpOptions<
    TResult = unknown,
    S extends AsyncOpSlice<unknown> = AsyncOpSlice<TResult>,
    A extends ActionMap = ActionMap,
> {
    name: string;
    transport?: FactoryTransport;
    wsTimeoutMs?: number;
    restMirror?: RestMirrorEntry | { method: string; path: string } | null;
    commandType?: string | null;
    request?: AsyncOpRequest<TResult>;
    silent?: boolean;
    successToastKey?: string | null;
    errorToastKey?: string | null;
    onSuccess?: (ctx: EffectCtx, result: TResult, event: PlatformEvent) => void;
    onFailure?: (ctx: EffectCtx, err: unknown, event: PlatformEvent) => void;
    sliceKey?: string;
    extraInitial?: Record<string, unknown>;
    extraReducer?: AsyncOpReducer<S>;
    extraEffect?: AsyncOpEffect;
    extraEvents?: Record<string, string>;
    actions?: A;
}

export interface AsyncOpFactory<
    TResult = unknown,
    S extends AsyncOpSlice<unknown> = AsyncOpSlice<TResult>,
    A extends ActionMap = ActionMap,
> extends PlatformFactory {
    kind: 'async-op';
    name: string;
    sliceKey: string;
    transport: FactoryTransport;
    restMirror: Readonly<RestMirrorEntry> | null;
    commandType: string | null;
    events: Readonly<Record<string, string>> & { REQUESTED: string; SUCCEEDED: string; FAILED: string };
    actions: Readonly<A>;
    reducer(state: S | undefined, event: PlatformEvent): S;
    slice: SliceDef<S>;
    selectors: {
        slice: (state: Record<string, unknown>) => S;
        busy: (state: Record<string, unknown>) => boolean;
        error: (state: Record<string, unknown>) => string | null;
        lastResult: (state: Record<string, unknown>) => S['lastResult'];
        lastRequestId: (state: Record<string, unknown>) => string | null;
        lastRequest: (state: Record<string, unknown>) => { payload: unknown } | null;
    };
    effect: (event: PlatformEvent, ctx: EffectCtx) => Promise<void>;
    run: (payload: unknown, ctx?: EffectCtx & { causationId?: string }) => Promise<void>;
}

export function createAsyncOp<
    K extends keyof PlatformCommandMap,
    S extends AsyncOpSlice<unknown> = AsyncOpSlice<PlatformCommandMap[K]['result']>,
    A extends ActionMap = Record<never, string>,
>(options: AsyncOpOptions<PlatformCommandMap[K]['result'], S, A> & { commandType: K }): AsyncOpFactory<PlatformCommandMap[K]['result'], S, A>;
export function createAsyncOp<
    TResult = unknown,
    S extends AsyncOpSlice<unknown> = AsyncOpSlice<TResult>,
    A extends ActionMap = Record<never, string>,
>(options: AsyncOpOptions<TResult, S, A>): AsyncOpFactory<TResult, S, A>;
export function createAsyncOp<
    TResult = unknown,
    S extends AsyncOpSlice<unknown> = AsyncOpSlice<TResult>,
    A extends ActionMap = Record<never, string>,
>(options: AsyncOpOptions<TResult, S, A>): AsyncOpFactory<TResult, S, A> {
    if (!options || typeof options !== 'object') {
        throw new Error('createAsyncOp: options object required');
    }
    const name = requireField(options, 'name', 'createAsyncOp');
    assertResourceName(name);

    const transport = normalizeTransport(options.transport, `createAsyncOp(${name})`);
    const wsTimeoutMs = normalizeWsTimeout(options.wsTimeoutMs, transport, `createAsyncOp(${name})`);
    let restMirror: Readonly<RestMirrorEntry> | null = null;
    if (options.restMirror !== undefined && options.restMirror !== null) {
        restMirror = normalizeRestMirrorSingle(options.restMirror, `createAsyncOp(${name})`);
    } else if (transport === 'ws') {
        throw new Error(
            `createAsyncOp(${name}): restMirror is required when transport='ws' `
            + `(no other source of HTTP url; needed for platform invariant and CI).`
        );
    }

    const commandType = _normalizeCommandType(options.commandType, `createAsyncOp(${name})`);
    if (commandType !== null && transport !== 'ws') {
        throw new Error(
            `createAsyncOp(${name}): commandType is allowed only with transport='ws' `
            + `(it overrides the WS frame type; HTTP requests use restMirror.path).`,
        );
    }

    let request: AsyncOpRequest<TResult> | null = null;
    if (typeof options.request === 'function') {
        request = options.request;
    } else if (transport !== 'ws') {
        // HTTP-режим: request обязателен (без него непонятно куда ходить).
        request = requireFunction<AsyncOpRequest<TResult>>(requireField(options, 'request', 'createAsyncOp'), 'createAsyncOp.request');
    }

    const silent = options.silent === true;
    const successToastKey = options.successToastKey === undefined || options.successToastKey === null || options.successToastKey.length === 0
        ? null
        : options.successToastKey;
    const errorToastKey = options.errorToastKey === undefined || options.errorToastKey === null || options.errorToastKey.length === 0
        ? null
        : options.errorToastKey;
    if (silent) {
        if (successToastKey || errorToastKey) {
            throw new Error(`createAsyncOp(${name}): silent: true is mutually exclusive with successToastKey/errorToastKey`);
        }
    } else {
        requireI18nKey(successToastKey, `createAsyncOp(${name}).successToastKey`);
        requireI18nKey(errorToastKey, `createAsyncOp(${name}).errorToastKey`);
    }

    const onSuccess = options.onSuccess ? requireFunction<NonNullable<AsyncOpOptions['onSuccess']>>(options.onSuccess, `createAsyncOp(${name}).onSuccess`) : null;
    const onFailure = options.onFailure ? requireFunction<NonNullable<AsyncOpOptions['onFailure']>>(options.onFailure, `createAsyncOp(${name}).onFailure`) : null;

    const sliceKey = options.sliceKey || deriveSliceKey(name);
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

    registerResourceName(name, 'async-op');

    const baseEvents = {
        REQUESTED: buildEventType(name, 'requested'),
        SUCCEEDED: buildEventType(name, 'succeeded'),
        FAILED:    buildEventType(name, 'failed'),
    };
    const extraEvents: Record<string, string> = {};
    if (extraEventsConfig) {
        for (const [key, verb] of Object.entries(extraEventsConfig)) {
            if (typeof verb !== 'string' || verb.length === 0) {
                throw new Error(`createAsyncOp(${name}): extraEvents.${key} must be non-empty verb`);
            }
            extraEvents[key] = buildEventType(name, verb);
        }
    }
    const actionsMap: Record<string, string> = {};
    if (actionsConfig) {
        for (const [methodName, verb] of Object.entries(actionsConfig)) {
            if (typeof methodName !== 'string' || methodName.length === 0) {
                throw new Error(`createAsyncOp(${name}): actions key must be non-empty method name`);
            }
            if (typeof verb !== 'string' || verb.length === 0) {
                throw new Error(`createAsyncOp(${name}): actions.${methodName} must be non-empty verb`);
            }
            const eventType = buildEventType(name, verb);
            extraEvents[verb.toUpperCase()] = eventType;
            actionsMap[methodName] = eventType;
        }
    }
    const events = freeze({ ...baseEvents, ...extraEvents });

    function isBuiltActionMap(value: Record<string, string>): value is A {
        if (actionsConfig === null) {
            return Object.keys(value).length === 0;
        }
        return Object.keys(actionsConfig).every((key) => {
            const eventType = value[key];
            return typeof eventType === 'string' && eventType.length > 0;
        });
    }

    function isAsyncOpSlice(value: unknown): value is S {
        if (!isPlainRecord(value)) return false;
        if (typeof value.busy !== 'boolean') return false;
        if (value.error !== null && typeof value.error !== 'string') return false;
        if (value.lastRequestId !== null && typeof value.lastRequestId !== 'string') return false;
        if (value.lastRequest !== null && !isPlainRecord(value.lastRequest)) return false;
        return true;
    }

    if (!isBuiltActionMap(actionsMap)) {
        throw new Error(`createAsyncOp(${name}): actions map does not match options.actions`);
    }
    const actions = freeze(actionsMap);
    const baseSlice: AsyncOpSlice<TResult> = { ...INITIAL_SLICE };
    const mergedSlice = extraInitial ? { ...baseSlice, ...extraInitial } : baseSlice;
    if (!isAsyncOpSlice(mergedSlice)) {
        throw new Error(`createAsyncOp(${name}): initial slice must include busy, error and lastRequest`);
    }
    const initialSlice = freeze(mergedSlice);

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

    function _baseReducer(state: S, event: PlatformEvent): S {
        switch (event.type) {
            case events.REQUESTED:
                return freeze({
                    ...state,
                    busy: true,
                    error: null,
                    lastRequestId: event.id,
                    lastRequest: freeze({ payload: event.payload === undefined ? null : event.payload }),
                });
            case events.SUCCEEDED: {
                if (!isPlainRecord(event.payload) || !('result' in event.payload)) {
                    throw new Error(`createAsyncOp(${name}): SUCCEEDED payload must include "result"`);
                }
                return freeze({ ...state, busy: false, error: null, lastResult: event.payload.result });
            }
            case events.FAILED: {
                if (!isPlainRecord(event.payload) || typeof event.payload.message !== 'string') {
                    throw new Error(`createAsyncOp(${name}): FAILED payload must include "message" (string)`);
                }
                return freeze({ ...state, busy: false, error: event.payload.message, lastResult: null });
            }
            default:
                return state;
        }
    }

    function _readSlice(state: Record<string, unknown>): S {
        // Корневое состояние шины хранит slices разных фабрик; slice этой фабрики кладёт её reducer.
        const slice = state[sliceKey];
        if (slice === undefined) {
            throw new Error(`createAsyncOp(${name}): slice "${sliceKey}" not registered in bus`);
        }
        if (!isAsyncOpSlice(slice)) {
            throw new Error(`createAsyncOp(${name}): slice "${sliceKey}" must be an async op`);
        }
        return slice;
    }

    const selectors = freeze({
        slice:        (state: Record<string, unknown>) => _readSlice(state),
        busy:         (state: Record<string, unknown>) => Boolean(_readSlice(state).busy),
        error:        (state: Record<string, unknown>) => _readSlice(state).error,
        lastResult:   (state: Record<string, unknown>) => _readSlice(state).lastResult,
        lastRequestId:(state: Record<string, unknown>) => _readSlice(state).lastRequestId,
        lastRequest:  (state: Record<string, unknown>) => _readSlice(state).lastRequest,
    });

    const wsCommandType = commandType !== null ? commandType : events.REQUESTED;
    const wsExpectedSucceeded = commandType !== null
        ? _deriveSucceededType(commandType)
        : events.SUCCEEDED;
    const wsExpectedFailed = commandType !== null
        ? _deriveFailedType(commandType)
        : events.FAILED;

    const opCtx = {
        events,
        request,
        transport,
        wsTimeoutMs,
        wsCommandType,
        wsExpectedSucceeded,
        wsExpectedFailed,
        silent,
        successToastKey,
        errorToastKey,
        onSuccess,
        onFailure,
    };

    async function effect(event: PlatformEvent, ctx: EffectCtx): Promise<void> {
        if (extraEffect) {
            const handled = await extraEffect(event, ctx, events);
            if (handled === true) {
                return;
            }
        }
        return _runEffect(event, ctx, opCtx);
    }

    return registerFactory(freeze({
        kind: 'async-op',
        name,
        sliceKey,
        transport,
        restMirror,
        commandType,
        events,
        actions,
        reducer,
        slice: freeze({ reducer, initial: initialSlice }),
        selectors,
        effect,
        run: (payload: unknown, ctx?: EffectCtx & { causationId?: string }) => {
            if (ctx === undefined) {
                throw new Error(`createAsyncOp(${name}): run requires an effect context`);
            }
            const causationId = ctx.causationId === undefined ? '' : ctx.causationId;
            return _runEffect(requestedEvent(events.REQUESTED, payload, causationId), ctx, opCtx);
        },
    }));
}

interface _OpCtx {
    events: AsyncOpFactory['events'];
    request: AsyncOpRequest | null;
    transport: FactoryTransport;
    wsTimeoutMs: number | null;
    wsCommandType: string;
    wsExpectedSucceeded: string;
    wsExpectedFailed: string;
    silent: boolean;
    successToastKey: string | null;
    errorToastKey: string | null;
    onSuccess: ((ctx: EffectCtx, result: unknown, event: PlatformEvent) => void) | null;
    onFailure: ((ctx: EffectCtx, err: unknown, event: PlatformEvent) => void) | null;
}

async function _runEffect(event: PlatformEvent, ctx: EffectCtx, opts: _OpCtx): Promise<void> {
    if (event.type !== opts.events.REQUESTED) return;
    const payload = event.payload;
    let result;
    try {
        if (opts.transport === 'ws' && !opts.request) {
            result = await transportRequest({
                transport: 'ws',
                commandType: opts.wsCommandType,
                payload,
                wsTimeoutMs: opts.wsTimeoutMs,
                causationEventId: event.id,
                expectedSucceeded: opts.wsExpectedSucceeded,
                expectedFailed: opts.wsExpectedFailed,
            });
        } else {
            result = await opts.request!({ payload, ctx, event });
        }
    } catch (err) {
        if (!(err instanceof HttpError) && !(err instanceof WsTransportError)) throw err;
        const message: string = err.message;
        const failurePayload = err instanceof HttpError
            ? { message, status: err.status, body: err.body }
            : { message, code: err.code };
        ctx.dispatch(
            opts.events.FAILED,
            failurePayload,
            { causation_id: event.id, source: opts.transport === 'ws' ? 'ws' : 'http' },
        );
        if (!opts.silent && !toastSuppressed(payload, 'suppressErrorToast')) {
            ctx.dispatch(
                CoreEvents.UI_TOAST_SHOW,
                { type: 'error', i18n_key: opts.errorToastKey, i18n_vars: { detail: message } },
                { causation_id: event.id },
            );
        }
        if (opts.onFailure) {
            opts.onFailure(ctx, err, event);
        }
        return;
    }
    // `request` — payload команды: extraReducer других фабрик мержит исход
    // (например, удаление по id, которого нет в result).
    ctx.dispatch(
        opts.events.SUCCEEDED,
        { result, request: payload },
        { causation_id: event.id, source: opts.transport === 'ws' ? 'ws' : 'http' },
    );
    if (!opts.silent && !toastSuppressed(payload, 'suppressSuccessToast')) {
        ctx.dispatch(
            CoreEvents.UI_TOAST_SHOW,
            { type: 'success', i18n_key: opts.successToastKey },
            { causation_id: event.id },
        );
    }
    if (opts.onSuccess) {
        opts.onSuccess(ctx, result, event);
    }
}
