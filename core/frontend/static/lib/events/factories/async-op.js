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
 *   - extraReducer(state, event, events) — вызывается ПОСЛЕ базового reducer'а;
 *     возвращает новое состояние или то же ссылочно (no-op).
 *   - extraEvents: { KEY: 'verb' } — дополнительные события scope namespace.
 *   - actions: { methodName: 'verb' } — дополнительные именованные действия,
 *     которые OpController обязан выставить как методы (`ctl.methodName()`).
 */

import { CoreEvents, assertEventType } from '../contract.js';
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

const _REQUESTED_SUFFIX = '_requested';

function _normalizeCommandType(value, ownerLabel) {
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

function _deriveSucceededType(commandType) {
    return commandType.slice(0, -_REQUESTED_SUFFIX.length) + '_succeeded';
}

function _deriveFailedType(commandType) {
    return commandType.slice(0, -_REQUESTED_SUFFIX.length) + '_failed';
}
import {
    WsTransportError,
    normalizeRestMirrorSingle,
    normalizeTransport,
    normalizeWsTimeout,
    transportRequest,
} from './_transport.js';

const INITIAL_SLICE = freeze({
    busy: false,
    error: null,
    lastResult: null,
    lastRequestId: null,
});

export function createAsyncOp(options) {
    if (!options || typeof options !== 'object') {
        throw new Error('createAsyncOp: options object required');
    }
    const name = requireField(options, 'name', 'createAsyncOp');
    assertResourceName(name);

    const transport = normalizeTransport(options.transport, `createAsyncOp(${name})`);
    const wsTimeoutMs = normalizeWsTimeout(options.wsTimeoutMs, transport, `createAsyncOp(${name})`);
    let restMirror = null;
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

    let request = null;
    if (typeof options.request === 'function') {
        request = options.request;
    } else if (transport !== 'ws') {
        // HTTP-режим: request обязателен (без него непонятно куда ходить).
        request = requireFunction(requireField(options, 'request', 'createAsyncOp'), 'createAsyncOp.request');
    }

    const silent = options.silent === true;
    const successToastKey = options.successToastKey || null;
    const errorToastKey = options.errorToastKey || null;
    if (silent) {
        if (successToastKey || errorToastKey) {
            throw new Error(`createAsyncOp(${name}): silent: true is mutually exclusive with successToastKey/errorToastKey`);
        }
    } else {
        requireI18nKey(successToastKey, `createAsyncOp(${name}).successToastKey`);
        requireI18nKey(errorToastKey, `createAsyncOp(${name}).errorToastKey`);
    }

    const onSuccess = options.onSuccess ? requireFunction(options.onSuccess, `createAsyncOp(${name}).onSuccess`) : null;
    const onFailure = options.onFailure ? requireFunction(options.onFailure, `createAsyncOp(${name}).onFailure`) : null;

    const sliceKey = options.sliceKey || deriveSliceKey(name);
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

    registerResourceName(name, 'async-op');

    const baseEvents = {
        REQUESTED: buildEventType(name, 'requested'),
        SUCCEEDED: buildEventType(name, 'succeeded'),
        FAILED:    buildEventType(name, 'failed'),
    };
    const extraEvents = {};
    if (extraEventsConfig) {
        for (const [key, verb] of Object.entries(extraEventsConfig)) {
            if (typeof verb !== 'string' || verb.length === 0) {
                throw new Error(`createAsyncOp(${name}): extraEvents.${key} must be non-empty verb`);
            }
            extraEvents[key] = buildEventType(name, verb);
        }
    }
    const actionsMap = {};
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
    const actions = freeze(actionsMap);
    const initialSlice = freeze(extraInitial ? { ...INITIAL_SLICE, ...extraInitial } : { ...INITIAL_SLICE });

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

    function _baseReducer(state, event) {
        switch (event.type) {
            case events.REQUESTED:
                return freeze({ ...state, busy: true, error: null, lastRequestId: event.id });
            case events.SUCCEEDED: {
                if (!event.payload || !('result' in event.payload)) {
                    throw new Error(`createAsyncOp(${name}): SUCCEEDED payload must include "result"`);
                }
                return freeze({ ...state, busy: false, error: null, lastResult: event.payload.result });
            }
            case events.FAILED: {
                if (!event.payload || typeof event.payload.message !== 'string') {
                    throw new Error(`createAsyncOp(${name}): FAILED payload must include "message" (string)`);
                }
                return freeze({ ...state, busy: false, error: event.payload.message, lastResult: null });
            }
            default:
                return state;
        }
    }

    function _readSlice(state) {
        const slice = state[sliceKey];
        if (slice === undefined) {
            throw new Error(`createAsyncOp(${name}): slice "${sliceKey}" not registered in bus`);
        }
        return slice;
    }

    const selectors = freeze({
        slice:        (state) => _readSlice(state),
        busy:         (state) => Boolean(_readSlice(state).busy),
        error:        (state) => _readSlice(state).error,
        lastResult:   (state) => _readSlice(state).lastResult,
        lastRequestId:(state) => _readSlice(state).lastRequestId,
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

    function effect(event, ctx) {
        return _runEffect(event, ctx, opCtx);
    }

    return freeze({
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
        run: (payload, ctx) => _runEffect(
            { type: events.REQUESTED, payload, id: ctx && ctx.causationId, meta: {} },
            ctx,
            opCtx,
        ),
    });
}

async function _runEffect(event, ctx, opts) {
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
            result = await opts.request({ payload, ctx, event });
        }
    } catch (err) {
        if (!(err instanceof HttpError) && !(err instanceof WsTransportError)) throw err;
        const message = err.message;
        const failurePayload = err instanceof HttpError
            ? { message, status: err.status, body: err.body }
            : { message, code: err.code };
        ctx.dispatch(
            opts.events.FAILED,
            failurePayload,
            { causation_id: event.id, source: opts.transport === 'ws' ? 'ws' : 'http' },
        );
        if (!opts.silent) {
            ctx.dispatch(
                CoreEvents.UI_TOAST_SHOW,
                { type: 'error', i18n_key: opts.errorToastKey },
                { causation_id: event.id },
            );
        }
        if (opts.onFailure) {
            opts.onFailure(ctx, err, event);
        }
        return;
    }
    ctx.dispatch(
        opts.events.SUCCEEDED,
        { result },
        { causation_id: event.id, source: opts.transport === 'ws' ? 'ws' : 'http' },
    );
    if (!opts.silent) {
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
