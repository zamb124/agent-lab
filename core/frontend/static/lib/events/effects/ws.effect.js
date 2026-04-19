/**
 * WebSocket-effect платформы. Один сокет на страницу
 * `/<svc>/api/ws/notifications` (канон). Если `baseUrl` уже содержит
 * сегмент `/api` (напр. `/sync/api`), вторично добавлять не нужно;
 * иначе (`/crm`, `/frontend`, `/rag`, `/office`) `/api` добавляется.
 *
 * Транспортирует два потока через одно соединение:
 *
 *   - **Push** (server -> client): входящий кадр без поля `request_id`.
 *     Если у фрейма есть валидный `type` — диспатчится в bus как обычное
 *     событие (`source: 'ws'`).
 *
 *   - **RPC request-reply** (client -> server -> client): фабрика вызывает
 *     `platformWs.request({ type, payload, timeoutMs })`. Effect генерирует
 *     `request_id`, отправляет фрейм `{ request_id, type, payload }`,
 *     регистрирует pending Promise. Серверный reply-фрейм
 *     `{ request_id, type, payload }` (с тем же `request_id` и type
 *     `*_succeeded` / `*_failed`) резолвит/реджектит Promise — в bus reply
 *     **не диспатчится** (фабрика сама диспатчит локальные `*_succeeded`
 *     / `*_failed` в bus после resolve через `_runEffect`). Это исключает
 *     дублирование событий. Кадры с неизвестным `request_id` (нет в
 *     `_pending`) обрабатываются как push-события (с предупреждением в
 *     консоли при невалидном `type`).
 *
 * No-fallback: если WS не подключён или истёк timeout, request падает с
 * `WsTransportError`. На HTTP не переключается.
 */

import { CoreEvents, assertEventType } from '../contract.js';

const BASE_DELAY_MS = 600;
const MAX_DELAY_MS = 60_000;
const BACKOFF_FACTOR = 1.7;

let _socket = null;
let _attempt = 0;
let _pingTimer = null;
let _reconnectTimer = null;
let _intentionalClose = false;
let _baseUrl = null;
let _ctxRef = null;
let _requestSeq = 0;
const _pending = new Map();

export class WsTransportError extends Error {
    constructor(message, code) {
        super(message);
        this.name = 'WsTransportError';
        this.code = code;
    }
}

function _wsUrl() {
    const proto = location.protocol === 'https:' ? 'wss:' : 'ws:';
    // Канон бэка: `/<svc>/api/ws/notifications` (см. core/app/factory.py
    // и architecture.mdc, раздел про единый WS). `_baseUrl` приходит из
    // PlatformApp.getBaseUrl() и по контракту всегда вида `/<svc>` (один
    // сегмент); префикс `/api` добавляем здесь, чтобы UI не дублировал его
    // в getBaseUrl. Пустой baseUrl допустим для landing-shell без сервиса.
    const base = _baseUrl || '';
    const wsPrefix = base === '' ? '' : `${base}/api`;
    return `${proto}//${location.host}${wsPrefix}/ws/notifications`;
}

function _clearReconnect() {
    if (_reconnectTimer) {
        clearTimeout(_reconnectTimer);
        _reconnectTimer = null;
    }
}

function _scheduleReconnect() {
    _clearReconnect();
    const delayBase = Math.min(MAX_DELAY_MS, BASE_DELAY_MS * Math.pow(BACKOFF_FACTOR, _attempt));
    const jitter = Math.random() * delayBase * 0.3;
    const delay = Math.floor(delayBase + jitter);
    _reconnectTimer = setTimeout(() => _open(), delay);
}

function _open() {
    if (_socket && (_socket.readyState === WebSocket.OPEN || _socket.readyState === WebSocket.CONNECTING)) {
        return;
    }
    _intentionalClose = false;
    _attempt += 1;
    _ctxRef.dispatch(CoreEvents.WS_CONNECT_REQUESTED, { url: _wsUrl() }, { source: 'system' });
    _socket = new WebSocket(_wsUrl());
    _socket.onopen = () => {
        _attempt = 0;
        _ctxRef.dispatch(CoreEvents.WS_CONNECTED, { url: _wsUrl() }, { source: 'ws' });
        if (_pingTimer) clearInterval(_pingTimer);
        _pingTimer = setInterval(() => {
            if (_socket && _socket.readyState === WebSocket.OPEN) {
                try { _socket.send('ping'); } catch { /* ignored */ }
            }
        }, 25_000);
    };
    _socket.onmessage = (msg) => _onFrame(msg);
    _socket.onerror = (err) => {
        console.warn('[ws.effect] error', err);
    };
    _socket.onclose = (ev) => {
        if (_pingTimer) { clearInterval(_pingTimer); _pingTimer = null; }
        _ctxRef.dispatch(CoreEvents.WS_DISCONNECTED, { reason: ev.reason || `code_${ev.code}` }, { source: 'ws' });
        _rejectAllPending(new WsTransportError('WebSocket disconnected', 'ws_disconnected'));
        if (!_intentionalClose) {
            _scheduleReconnect();
        }
    };
}

function _close() {
    _intentionalClose = true;
    _clearReconnect();
    if (_pingTimer) { clearInterval(_pingTimer); _pingTimer = null; }
    if (_socket && _socket.readyState !== WebSocket.CLOSED) {
        try { _socket.close(1000, 'client_close'); } catch { /* ignored */ }
    }
    _socket = null;
    _attempt = 0;
    _rejectAllPending(new WsTransportError('WebSocket closed', 'ws_disconnected'));
}

function _rejectAllPending(error) {
    for (const [, entry] of _pending) {
        clearTimeout(entry.timeoutHandle);
        entry.reject(error);
    }
    _pending.clear();
}

function _onFrame(msg) {
    const data = msg.data;
    if (typeof data !== 'string') return;
    if (data === 'pong') return;
    let parsed;
    try {
        parsed = JSON.parse(data);
    } catch {
        _ctxRef.dispatch(CoreEvents.WS_FRAME_RECEIVED, { raw: data }, { source: 'ws' });
        return;
    }
    _ctxRef.dispatch(CoreEvents.WS_FRAME_RECEIVED, { frame: parsed }, { source: 'ws' });

    if (!parsed || typeof parsed.type !== 'string') {
        return;
    }

    const requestId = typeof parsed.request_id === 'string' ? parsed.request_id : null;
    if (requestId !== null && _pending.has(requestId)) {
        const entry = _pending.get(requestId);
        _pending.delete(requestId);
        clearTimeout(entry.timeoutHandle);
        if (entry.expectedSucceeded === parsed.type) {
            entry.resolve(parsed.payload === undefined ? null : parsed.payload);
        } else if (entry.expectedFailed === parsed.type) {
            const failurePayload = parsed.payload && typeof parsed.payload === 'object' ? parsed.payload : {};
            const message = typeof failurePayload.error_detail === 'string'
                ? failurePayload.error_detail
                : (typeof failurePayload.message === 'string' ? failurePayload.message : 'WS command failed');
            const code = typeof failurePayload.error_code === 'string' ? failurePayload.error_code : 'ws_command_failed';
            entry.reject(new WsTransportError(message, code));
        } else {
            entry.reject(new WsTransportError(
                `reply type "${parsed.type}" does not match expected ${entry.expectedSucceeded} | ${entry.expectedFailed}`,
                'ws_unexpected_reply',
            ));
        }
        return;
    }

    try {
        assertEventType(parsed.type);
        _ctxRef.dispatch(parsed.type, parsed.payload === undefined ? null : parsed.payload, {
            source: 'ws',
            correlation_id: parsed.meta && parsed.meta.correlation_id,
            causation_id: parsed.meta && parsed.meta.causation_id,
            trace_id: parsed.meta && parsed.meta.trace_id,
        });
    } catch (err) {
        console.warn('[ws.effect] dropped frame: invalid event type', parsed.type, err);
    }
}

function _generateRequestId() {
    _requestSeq = (_requestSeq + 1) & 0xffffffff;
    const ts = Date.now().toString(36);
    const seq = _requestSeq.toString(36);
    const rnd = Math.floor(Math.random() * 0xffffff).toString(36);
    return `r_${ts}_${seq}_${rnd}`;
}

/**
 * Singleton-контроллер платформенного WS. Используется фабриками с
 * `transport: 'ws'`. Никогда не вызывается из pages/components/modals
 * напрямую — только из effect-ов фабрик.
 */
export const platformWs = {
    isOpen() {
        return Boolean(_socket && _socket.readyState === WebSocket.OPEN);
    },

    /**
     * Отправить command-фрейм по WS, дождаться reply с тем же request_id.
     * Фабрика передаёт собственные `expectedSucceeded`/`expectedFailed` —
     * имена событий, которыми сервер обязан ответить.
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
            if (!this.isOpen()) {
                reject(new WsTransportError('WebSocket is not connected', 'ws_disconnected'));
                return;
            }
            const requestId = _generateRequestId();
            const frame = {
                request_id: requestId,
                type: opts.type,
                payload: opts.payload === undefined ? null : opts.payload,
            };
            const timeoutHandle = setTimeout(() => {
                if (_pending.has(requestId)) {
                    _pending.delete(requestId);
                    reject(new WsTransportError(`WS command "${opts.type}" timed out after ${opts.timeoutMs}ms`, 'ws_timeout'));
                }
            }, opts.timeoutMs);
            _pending.set(requestId, {
                resolve,
                reject,
                timeoutHandle,
                expectedSucceeded: opts.expectedSucceeded,
                expectedFailed: opts.expectedFailed,
                causationEventId: opts.causationEventId || null,
            });
            try {
                _socket.send(JSON.stringify(frame));
            } catch (err) {
                _pending.delete(requestId);
                clearTimeout(timeoutHandle);
                reject(new WsTransportError(`WS send failed: ${err && err.message ? err.message : String(err)}`, 'ws_send_failed'));
            }
        });
    },
};

export function createPlatformWsEffect({ baseUrl }) {
    _baseUrl = baseUrl || '';

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

/**
 * Тестовый сброс модульного состояния (между тестами Web Test Runner).
 */
export function _resetPlatformWsForTests() {
    _close();
    _socket = null;
    _attempt = 0;
    _pingTimer = null;
    _reconnectTimer = null;
    _intentionalClose = false;
    _baseUrl = null;
    _ctxRef = null;
    _requestSeq = 0;
    _pending.clear();
}
