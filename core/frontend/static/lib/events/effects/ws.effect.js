/**
 * User WS платформы — один Centrifugo на `/realtime/connection/websocket`.
 *
 * Кадр = `PlatformEvent` (`event_id`, `type`, `company_id`, `meta`, `payload`).
 * Push: `client.on('publication')` по server-side каналам из SESSION JWT.
 * Команда: `centrifuge.rpc('platform.event', PlatformEvent)`. RPC accepted
 * не является исходом бизнеса. Исход — publication `*_succeeded`/`*_failed`
 * с `meta.causation_id = event_id`. Timeout сокета ≠ `*_failed`.
 *
 * В bus диспатчатся только push-факты и терминалы команд; кадры
 * `*_requested` (эхо команды) отбрасываются — команда не является
 * входящим событием клиента.
 *
 * `getToken` читает cookie `auth_token` (SESSION JWT = connection JWT).
 * На localhost SDK ходит на `:8000/connection/websocket` (Centrifugo),
 * не через Granian.
 */

import { CoreEvents, assertEventType } from '../contract.js';
import { getActivePlatformNamespaceName } from '../../utils/platform-namespace.js';
import { formatPlatformError } from '../../utils/platform-error-message.js';
import { Centrifuge, UnauthorizedError } from 'centrifuge';

const BASE_DELAY_MS = 600;
const MAX_DELAY_MS = 60_000;

let _CentrifugeCtor = Centrifuge;
let _UnauthorizedError = UnauthorizedError;

let _client = null;
let _connected = false;
let _intentionalClose = false;
let _ctxRef = null;
let _requestSeq = 0;
const _pending = new Map();
const _preConnectQueue = [];
const PRE_CONNECT_MAX_WAIT_MS = 5_000;

export class WsTransportError extends Error {
    constructor(message, code) {
        super(message);
        this.name = 'WsTransportError';
        this.code = code;
    }
}

function _hostname() {
    if (typeof location.hostname === 'string' && location.hostname.length > 0) {
        return location.hostname;
    }
    const host = location.host;
    if (typeof host !== 'string' || host.length === 0) {
        throw new Error('location.host is required for Centrifugo URL');
    }
    return host.split(':')[0];
}

function _centrifugeUrl() {
    const proto = location.protocol === 'https:' ? 'wss:' : 'ws:';
    const hostname = _hostname();
    if (hostname === 'localhost' || hostname === '127.0.0.1') {
        return `${proto}//${hostname}:8000/connection/websocket`;
    }
    return `${proto}//${location.host}/realtime/connection/websocket`;
}

function _cookieValue(name) {
    if (typeof document === 'undefined' || typeof document.cookie !== 'string') {
        throw new Error(`cookie ${name} is required`);
    }
    const prefix = `${name}=`;
    const parts = document.cookie.split(';');
    for (const part of parts) {
        const trimmed = part.trim();
        if (trimmed.startsWith(prefix)) {
            return decodeURIComponent(trimmed.slice(prefix.length));
        }
    }
    throw new Error(`cookie ${name} is required`);
}

function _decodeJwtPayload(token) {
    const parts = token.split('.');
    if (parts.length !== 3) {
        throw new Error('auth_token is not a JWT');
    }
    const normalized = parts[1].replace(/-/g, '+').replace(/_/g, '/');
    const pad = normalized.length % 4;
    const padded = pad === 0 ? normalized : normalized + '='.repeat(4 - pad);
    const json = atob(padded);
    const payload = JSON.parse(json);
    if (!payload || typeof payload !== 'object') {
        throw new Error('JWT payload is required');
    }
    return payload;
}

function _sessionCompanyId(token) {
    const payload = _decodeJwtPayload(token);
    const companyId = payload.company_id;
    if (typeof companyId !== 'string' || companyId.length === 0) {
        throw new Error('SESSION JWT company_id is required');
    }
    return companyId;
}

async function _getToken() {
    if (typeof document === 'undefined' || typeof document.cookie !== 'string') {
        throw new _UnauthorizedError();
    }
    if (!document.cookie.split(';').some((part) => part.trim().startsWith('auth_token='))) {
        throw new _UnauthorizedError();
    }
    return _cookieValue('auth_token');
}

function _newEventId() {
    _requestSeq = (_requestSeq + 1) & 0xffffffff;
    const ts = Date.now().toString(36);
    const seq = _requestSeq.toString(36);
    const rnd = Math.floor(Math.random() * 0xffffff).toString(36);
    return `e_${ts}_${seq}_${rnd}`;
}

function _dispatchPlatformEvent(frame) {
    if (!frame || typeof frame.type !== 'string') {
        return;
    }
    // Команды (*_requested) — исходящий артефакт клиента, а не входящее событие:
    // серверное эхо команды не попадает в bus, иначе effect фабрики перезапускает
    // запрос и получается бесконечная петля.
    if (frame.type.endsWith('_requested')) {
        return;
    }
    try {
        assertEventType(frame.type);
        _ctxRef.dispatch(frame.type, frame.payload === undefined ? null : frame.payload, {
            source: 'ws',
            correlation_id: frame.meta && frame.meta.correlation_id,
            causation_id: frame.meta && frame.meta.causation_id,
            trace_id: frame.meta && frame.meta.trace_id,
        });
    } catch (err) {
        console.warn('[ws.effect] dropped frame: invalid event type', frame.type, err);
    }
}

function _matchPending(frame) {
    const causationId = frame && frame.meta && typeof frame.meta.causation_id === 'string'
        ? frame.meta.causation_id
        : null;
    if (causationId === null || !_pending.has(causationId)) {
        return false;
    }
    const entry = _pending.get(causationId);
    if (entry.expectedSucceeded === frame.type) {
        _pending.delete(causationId);
        clearTimeout(entry.timeoutHandle);
        entry.resolve(frame.payload === undefined ? null : frame.payload);
        return true;
    }
    if (entry.expectedFailed === frame.type) {
        _pending.delete(causationId);
        clearTimeout(entry.timeoutHandle);
        const failurePayload = frame.payload && typeof frame.payload === 'object' ? frame.payload : {};
        const code = typeof failurePayload.error_code === 'string' && failurePayload.error_code.length > 0
            ? failurePayload.error_code
            : 'unknown';
        const errorParams = failurePayload.error_params
            && typeof failurePayload.error_params === 'object'
            && !Array.isArray(failurePayload.error_params)
            ? failurePayload.error_params
            : null;
        const message = formatPlatformError(code, errorParams);
        entry.reject(new WsTransportError(message, code));
        return true;
    }
    return false;
}

function _onPublication(ctx) {
    const frame = ctx && ctx.data;
    _ctxRef.dispatch(CoreEvents.WS_FRAME_RECEIVED, { frame }, { source: 'ws' });
    if (_matchPending(frame)) {
        return;
    }
    _dispatchPlatformEvent(frame);
}

function _open() {
    if (_client && (_connected || _client.state === 'connecting')) {
        return;
    }
    _intentionalClose = false;
    const url = _centrifugeUrl();
    _ctxRef.dispatch(CoreEvents.WS_CONNECT_REQUESTED, { url }, { source: 'system' });
    _client = new _CentrifugeCtor(url, {
        getToken: _getToken,
        minReconnectDelay: BASE_DELAY_MS,
        maxReconnectDelay: MAX_DELAY_MS,
    });
    _client.on('connected', () => {
        _connected = true;
        _ctxRef.dispatch(CoreEvents.WS_CONNECTED, { url }, { source: 'ws' });
        _flushPreConnectQueue();
    });
    _client.on('disconnected', (ctx) => {
        _connected = false;
        const reason = ctx && ctx.reason ? ctx.reason : 'disconnected';
        _ctxRef.dispatch(CoreEvents.WS_DISCONNECTED, { reason }, { source: 'ws' });
        if (!_intentionalClose) {
            _rejectAllPending(new WsTransportError('WebSocket disconnected', 'ws_disconnected'));
        }
    });
    _client.on('publication', _onPublication);
    _client.connect();
}

function _close() {
    _intentionalClose = true;
    _connected = false;
    if (_client) {
        _client.disconnect();
        _client = null;
    }
    _rejectAllPending(new WsTransportError('WebSocket closed', 'ws_disconnected'));
    _rejectAllPreConnect(new WsTransportError('WebSocket closed', 'ws_disconnected'));
}

function _rejectAllPending(error) {
    for (const [, entry] of _pending) {
        clearTimeout(entry.timeoutHandle);
        entry.reject(error);
    }
    _pending.clear();
}

function _flushPreConnectQueue() {
    while (_preConnectQueue.length > 0) {
        const queued = _preConnectQueue.shift();
        clearTimeout(queued.preTimeoutHandle);
        _sendRpcNow(queued);
    }
}

function _rejectAllPreConnect(error) {
    while (_preConnectQueue.length > 0) {
        const queued = _preConnectQueue.shift();
        clearTimeout(queued.preTimeoutHandle);
        queued.reject(error);
    }
}

function _buildCommandEvent(queued) {
    const token = _cookieValue('auth_token');
    const companyId = _sessionCompanyId(token);
    const eventId = queued.causationEventId || _newEventId();
    return {
        event_id: eventId,
        type: queued.type,
        company_id: companyId,
        payload: queued.payload,
        meta: {
            ts: Date.now(),
            source: 'ws',
            causation_id: eventId,
            namespace: getActivePlatformNamespaceName(companyId),
        },
    };
}

function _sendRpcNow(queued) {
    if (!_client || !_connected) {
        queued.reject(new WsTransportError('WebSocket is not connected', 'ws_disconnected'));
        return;
    }
    const event = _buildCommandEvent(queued);
    const eventId = event.event_id;
    const timeoutHandle = setTimeout(() => {
        void _onCommandTimeout(eventId, queued);
    }, queued.timeoutMs);
    _pending.set(eventId, {
        resolve: queued.resolve,
        reject: queued.reject,
        timeoutHandle,
        expectedSucceeded: queued.expectedSucceeded,
        expectedFailed: queued.expectedFailed,
    });
    queued.eventId = eventId;
    _client.rpc('platform.event', event).then(() => undefined, (err) => {
        if (!_pending.has(eventId)) {
            return;
        }
        const entry = _pending.get(eventId);
        _pending.delete(eventId);
        clearTimeout(entry.timeoutHandle);
        const message = err && typeof err.message === 'string' && err.message.length > 0
            ? err.message
            : 'Centrifugo rpc platform.event failed';
        entry.reject(new WsTransportError(message, 'ws_disconnected'));
    });
}

async function _onCommandTimeout(eventId, queued) {
    if (!_pending.has(eventId)) {
        return;
    }
    try {
        const response = await fetch(
            `/realtime/api/v1/events/${encodeURIComponent(eventId)}/terminal`,
            { credentials: 'include' },
        );
        if (response.ok) {
            const frame = await response.json();
            if (_matchPending(frame)) {
                return;
            }
        } else if (response.status !== 404) {
            throw new Error(`terminal lookup HTTP ${response.status}`);
        }
    } catch (err) {
        const failed = _pending.get(eventId);
        if (!failed) {
            return;
        }
        _pending.delete(eventId);
        clearTimeout(failed.timeoutHandle);
        const message = err instanceof Error && err.message
            ? err.message
            : 'terminal lookup failed';
        failed.reject(new WsTransportError(message, 'ws_disconnected'));
        return;
    }
    const entry = _pending.get(eventId);
    if (!entry) {
        return;
    }
    _pending.delete(eventId);
    clearTimeout(entry.timeoutHandle);
    entry.reject(new WsTransportError(
        `WS command "${queued.type}" timed out after ${queued.timeoutMs}ms`,
        'ws_timeout',
    ));
}

export const platformWs = {
    isOpen() {
        return Boolean(_client && _connected);
    },

    /**
     * Отправить PlatformEvent `_requested` через Centrifugo RPC, дождаться
     * publication `expectedSucceeded` / `expectedFailed` с causation_id.
     *
     * @param {{
     *   type: string,
     *   payload?: unknown,
     *   timeoutMs: number,
     *   causationEventId?: string|null,
     *   expectedSucceeded: string,
     *   expectedFailed: string,
     * }} opts
     * @returns {Promise<unknown>} payload из expectedSucceeded
     */
    request(opts) {
        if (!opts || typeof opts !== 'object') {
            throw new Error('platformWs.request: opts object required');
        }
        if (typeof opts.type !== 'string' || opts.type.length === 0) {
            throw new Error('platformWs.request: opts.type required');
        }
        if (typeof opts.timeoutMs !== 'number' || opts.timeoutMs <= 0) {
            throw new Error('platformWs.request: opts.timeoutMs (positive number) required');
        }
        if (typeof opts.expectedSucceeded !== 'string' || opts.expectedSucceeded.length === 0) {
            throw new Error('platformWs.request: opts.expectedSucceeded required');
        }
        if (typeof opts.expectedFailed !== 'string' || opts.expectedFailed.length === 0) {
            throw new Error('platformWs.request: opts.expectedFailed required');
        }
        assertEventType(opts.type);
        assertEventType(opts.expectedSucceeded);
        assertEventType(opts.expectedFailed);

        return new Promise((resolve, reject) => {
            const queued = {
                type: opts.type,
                payload: opts.payload === undefined ? null : opts.payload,
                timeoutMs: opts.timeoutMs,
                expectedSucceeded: opts.expectedSucceeded,
                expectedFailed: opts.expectedFailed,
                causationEventId: opts.causationEventId || null,
                resolve,
                reject,
                preTimeoutHandle: null,
            };

            if (this.isOpen()) {
                _sendRpcNow(queued);
                return;
            }

            if (_intentionalClose) {
                reject(new WsTransportError('WebSocket is closed (logged out)', 'ws_disconnected'));
                return;
            }

            queued.preTimeoutHandle = setTimeout(() => {
                const idx = _preConnectQueue.indexOf(queued);
                if (idx >= 0) {
                    _preConnectQueue.splice(idx, 1);
                    queued.reject(new WsTransportError(
                        `WS command "${opts.type}" timed out waiting for connection (${PRE_CONNECT_MAX_WAIT_MS}ms)`,
                        'ws_timeout',
                    ));
                }
            }, PRE_CONNECT_MAX_WAIT_MS);
            _preConnectQueue.push(queued);
        });
    },
};

export function createPlatformWsEffect() {
    return async function wsEffect(event, ctx) {
        if (_ctxRef === null) {
            _ctxRef = ctx;
        }
        switch (event.type) {
            case CoreEvents.AUTH_USER_LOADED:
            case CoreEvents.AUTH_LOGIN_SUCCEEDED:
                _open();
                return;
            case CoreEvents.AUTH_LOGGED_OUT:
            case CoreEvents.AUTH_UNAUTHORIZED:
                _close();
                return;
            default:
                return;
        }
    };
}

export function _setCentrifugeForTests(ctor, unauthorizedError) {
    _CentrifugeCtor = ctor;
    _UnauthorizedError = unauthorizedError;
}

export function _resetPlatformWsForTests() {
    _close();
    _client = null;
    _connected = false;
    _intentionalClose = false;
    _ctxRef = null;
    _requestSeq = 0;
    _pending.clear();
    _preConnectQueue.length = 0;
    _CentrifugeCtor = Centrifuge;
    _UnauthorizedError = UnauthorizedError;
}
