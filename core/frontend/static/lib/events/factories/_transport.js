/**
 * Транспортный слой фабрик. Скрывает выбор HTTP / WS от тела фабрики.
 *
 * Любая фабрика (`createAsyncOp` / `createResourceCollection` /
 * `createКурсорList`) объявляет `transport: 'http' | 'ws'` и обязательное
 * `restMirror` (для платформенного инварианта «REST-зеркало команд»).
 *
 * При `transport: 'http'` effect делает обычный `httpRequest`. При
 * `transport: 'ws'` effect делает `platformWs.request` (request-reply
 * по WS, см. `effects/ws.effect.js`). Никакого fallback с WS на HTTP
 * нет — если WS недоступен, op падает в `*_failed`.
 */

import { platformWs, WsTransportError } from '../effects/ws.effect.js';
import { HttpError, httpRequest } from '../http.js';

const VALID_TRANSPORTS = new Set(['http', 'ws']);
const HTTP_METHODS = new Set(['GET', 'POST', 'PUT', 'PATCH', 'DELETE']);

/**
 * Провалидировать значение `transport`. По умолчанию 'http'.
 */
export function normalizeTransport(value, ownerLabel) {
    if (value === undefined || value === null) return 'http';
    if (typeof value !== 'string' || !VALID_TRANSPORTS.has(value)) {
        throw new Error(`${ownerLabel}: transport must be 'http' or 'ws', got ${JSON.stringify(value)}`);
    }
    return value;
}

/**
 * Провалидировать `wsTimeoutMs`. Обязателен при transport === 'ws'.
 */
export function normalizeWsTimeout(value, transport, ownerLabel) {
    if (transport !== 'ws') return null;
    if (typeof value !== 'number' || !Number.isFinite(value) || value <= 0) {
        throw new Error(`${ownerLabel}: wsTimeoutMs (positive number) is required when transport='ws'`);
    }
    return value;
}

function _assertRestMirrorEntry(entry, ownerLabel) {
    if (!entry || typeof entry !== 'object') {
        throw new Error(`${ownerLabel}: restMirror entry must be { method, path } object`);
    }
    if (typeof entry.method !== 'string' || !HTTP_METHODS.has(entry.method.toUpperCase())) {
        throw new Error(`${ownerLabel}: restMirror.method must be one of ${[...HTTP_METHODS].join('|')}`);
    }
    if (typeof entry.path !== 'string' || entry.path.length === 0 || !entry.path.startsWith('/')) {
        throw new Error(`${ownerLabel}: restMirror.path must be non-empty string starting with "/"`);
    }
    return Object.freeze({ method: entry.method.toUpperCase(), path: entry.path });
}

/**
 * Нормализовать `restMirror` для одиночной операции (createAsyncOp / createКурсорList).
 * Бросает Error если поле невалидно. null/undefined — допустимы (caller сам решает).
 */
export function normalizeRestMirrorSingle(value, ownerLabel) {
    if (value === undefined || value === null) {
        throw new Error(`${ownerLabel}: restMirror is required ({ method, path })`);
    }
    return _assertRestMirrorEntry(value, ownerLabel);
}

/**
 * Нормализовать `restMirror` для коллекции. На каждую operation в `operations`
 * (включая mutating-actions, если переданы в `extraActionOps`) обязана быть
 * запись с method/path.
 *
 * @param {object} value
 * @param {string[]} operations
 * @param {string[]} [extraActionOps]
 * @param {string} ownerLabel
 */
export function normalizeRestMirrorCollection(value, operations, extraActionOps, ownerLabel) {
    if (!value || typeof value !== 'object') {
        throw new Error(`${ownerLabel}: restMirror is required ({ <op>: { method, path }, ... })`);
    }
    const required = new Set(operations);
    if (extraActionOps) {
        for (const op of extraActionOps) required.add(op);
    }
    const normalized = {};
    for (const op of required) {
        if (!(op in value)) {
            throw new Error(`${ownerLabel}: restMirror.${op} is required for declared operation/action`);
        }
        normalized[op] = _assertRestMirrorEntry(value[op], `${ownerLabel}.restMirror.${op}`);
    }
    return Object.freeze(normalized);
}

/**
 * Превратить HTTP-стиль ошибки `httpRequest` в общий шейп, понятный фабрикам.
 * `HttpError` остаётся как есть; `WsTransportError` оборачивается.
 */
export function isTransportError(err) {
    return err instanceof HttpError || err instanceof WsTransportError;
}

/**
 * Унифицированный фасад: сделать запрос либо по HTTP, либо по WS.
 *
 * Для transport='http' — вызывает `httpRequest`. Для transport='ws' —
 * вызывает `platformWs.request` с `expectedSucceeded`/`expectedFailed`.
 */
export async function transportRequest(opts) {
    if (!opts || typeof opts !== 'object') {
        throw new Error('transportRequest: opts object required');
    }
    if (opts.transport === 'ws') {
        if (typeof opts.commandType !== 'string' || opts.commandType.length === 0) {
            throw new Error('transportRequest: opts.commandType required for transport="ws"');
        }
        if (typeof opts.expectedSucceeded !== 'string' || opts.expectedSucceeded.length === 0) {
            throw new Error('transportRequest: opts.expectedSucceeded required for transport="ws"');
        }
        if (typeof opts.expectedFailed !== 'string' || opts.expectedFailed.length === 0) {
            throw new Error('transportRequest: opts.expectedFailed required for transport="ws"');
        }
        return platformWs.request({
            type: opts.commandType,
            payload: opts.payload === undefined ? null : opts.payload,
            timeoutMs: opts.wsTimeoutMs,
            causationEventId: opts.causationEventId || null,
            expectedSucceeded: opts.expectedSucceeded,
            expectedFailed: opts.expectedFailed,
        });
    }
    if (typeof opts.method !== 'string' || typeof opts.url !== 'string') {
        throw new Error('transportRequest(http): opts.method and opts.url required');
    }
    return httpRequest({
        method: opts.method,
        url: opts.url,
        body: opts.body,
        query: opts.query,
        headers: opts.headers,
    });
}

export { HttpError, WsTransportError };
