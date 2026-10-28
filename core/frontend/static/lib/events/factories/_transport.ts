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
import { isPlainRecord } from '../payload.js';
import type { PlatformEvent } from '../contract.js';
import { HttpError, httpRequest } from '../http.js';

const VALID_TRANSPORTS = new Set(['http', 'ws']);
const HTTP_METHODS = new Set(['GET', 'POST', 'PUT', 'PATCH', 'DELETE']);

/**
 * Провалидировать значение `transport`. По умолчанию 'http'.
 */
export type FactoryTransport = 'http' | 'ws';

function isFactoryTransport(value: string): value is FactoryTransport {
    return VALID_TRANSPORTS.has(value);
}

export function normalizeTransport(value: unknown, ownerLabel: string): FactoryTransport {
    if (value === undefined || value === null) return 'http';
    if (typeof value !== 'string' || !isFactoryTransport(value)) {
        throw new Error(`${ownerLabel}: transport must be 'http' or 'ws', got ${JSON.stringify(value)}`);
    }
    return value;
}

/**
 * Провалидировать `wsTimeoutMs`. Обязателен при transport === 'ws'.
 */
export function normalizeWsTimeout(value: unknown, transport: FactoryTransport, ownerLabel: string): number | null {
    if (transport !== 'ws') return null;
    if (typeof value !== 'number' || !Number.isFinite(value) || value <= 0) {
        throw new Error(`${ownerLabel}: wsTimeoutMs (positive number) is required when transport='ws'`);
    }
    return value;
}

export interface RestMirrorEntry {
    method: string;
    path: string;
    /** Опционально: cross-service вызов или 'ui-only' — читается гейтом check_command_rest_mirror. */
    service?: string;
}

function _assertRestMirrorEntry(entry: unknown, ownerLabel: string): RestMirrorEntry {
    if (!isPlainRecord(entry)) {
        throw new Error(`${ownerLabel}: restMirror entry must be { method, path } object`);
    }
    const method = entry.method;
    const path = entry.path;
    if (typeof method !== 'string' || !HTTP_METHODS.has(method.toUpperCase())) {
        throw new Error(`${ownerLabel}: restMirror.method must be one of ${[...HTTP_METHODS].join('|')}`);
    }
    if (typeof path !== 'string' || path.length === 0 || !path.startsWith('/')) {
        throw new Error(`${ownerLabel}: restMirror.path must be non-empty string starting with "/"`);
    }
    const service = entry.service;
    if (service !== undefined && typeof service !== 'string') {
        throw new Error(`${ownerLabel}: restMirror.service must be a string when present`);
    }
    const normalized: RestMirrorEntry = { method: method.toUpperCase(), path };
    if (typeof service === 'string') normalized.service = service;
    return Object.freeze(normalized);
}

/**
 * Нормализовать `restMirror` для одиночной операции (createAsyncOp / createКурсорList).
 * Бросает Error если поле невалидно. null/undefined — допустимы (caller сам решает).
 */
export function normalizeRestMirrorSingle(value: unknown, ownerLabel: string): Readonly<RestMirrorEntry> {
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
export function normalizeRestMirrorCollection(
    value: unknown,
    operations: string[],
    extraActionOps: string[] | undefined,
    ownerLabel: string,
): Readonly<Record<string, RestMirrorEntry>> {
    if (!isPlainRecord(value)) {
        throw new Error(`${ownerLabel}: restMirror is required ({ <op>: { method, path }, ... })`);
    }
    const v = value;
    const required = new Set(operations);
    if (extraActionOps) {
        for (const op of extraActionOps) required.add(op);
    }
    const normalized: Record<string, RestMirrorEntry> = {};
    for (const op of required) {
        if (!(op in v)) {
            throw new Error(`${ownerLabel}: restMirror.${op} is required for declared operation/action`);
        }
        normalized[op] = _assertRestMirrorEntry(v[op], `${ownerLabel}.restMirror.${op}`);
    }
    return Object.freeze(normalized);
}

/**
 * Превратить HTTP-стиль ошибки `httpRequest` в общий шейп, понятный фабрикам.
 * `HttpError` остаётся как есть; `WsTransportError` оборачивается.
 */
export function isTransportError(err: unknown): err is HttpError | WsTransportError {
    return err instanceof HttpError || err instanceof WsTransportError;
}

/**
 * Унифицированный фасад: сделать запрос либо по HTTP, либо по WS.
 *
 * Для transport='http' — вызывает `httpRequest`. Для transport='ws' —
 * вызывает `platformWs.request` с `expectedSucceeded`/`expectedFailed`.
 */
export interface TransportRequestOpts {
    transport: FactoryTransport;
    commandType?: string;
    expectedSucceeded?: string;
    expectedFailed?: string;
    payload?: unknown;
    wsTimeoutMs?: number | null;
    causationEventId?: string | null;
    method?: 'GET' | 'POST' | 'PUT' | 'PATCH' | 'DELETE';
    url?: string;
    body?: unknown;
    query?: Record<string, string | number | boolean | null | undefined>;
    headers?: Record<string, string>;
}

export async function transportRequest(opts: TransportRequestOpts): Promise<unknown> {
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
            timeoutMs: opts.wsTimeoutMs as number,
            causationEventId: typeof opts.causationEventId === 'string' && opts.causationEventId.length > 0 ? opts.causationEventId : null,
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
