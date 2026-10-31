/**
 * Низкоуровневый HTTP-клиент для использования внутри effects.
 *
 * НЕ предоставляет UI/event API напрямую — все вызовы инкапсулируются
 * в domain effects, которые реагируют на события и диспатчат новые.
 * Компоненты НЕ должны вызывать httpRequest напрямую — это делает effect,
 * подписанный на доменное событие.
 */

import { formatPlatformError } from '../utils/platform-error-message.js';
import { isPlainRecord } from './payload.js';

function scalarParams(value: unknown): Record<string, string | number | boolean> | null {
    if (value === undefined || value === null) return null;
    if (!isPlainRecord(value)) return null;
    const params: Record<string, string | number | boolean> = {};
    for (const [key, field] of Object.entries(value)) {
        if (typeof field !== 'string' && typeof field !== 'number' && typeof field !== 'boolean') {
            throw new Error(`http: error_params.${key} must be a scalar`);
        }
        params[key] = field;
    }
    return params;
}

function _errorParams(errorData: unknown): Record<string, string | number | boolean> | null {
    if (!isPlainRecord(errorData)) return null;
    return scalarParams(errorData.error_params);
}

function detailMessage(err: unknown): string {
    if (!isPlainRecord(err)) {
        throw new Error('http: error detail item must be an object');
    }
    if (typeof err.field === 'string' && err.field.length > 0 && err.error != null && err.error !== '') {
        return `${err.field}: ${String(err.error)}`;
    }
    const field = Array.isArray(err.loc) ? err.loc.slice(1).map((part) => String(part)).join('.') : 'field';
    return `${field}: ${String(err.msg)}`;
}

function _formatError(errorData: unknown, status: number): string {
    const rec = isPlainRecord(errorData) ? errorData : null;
    if (rec === null) return `HTTP ${status}`;

    if (typeof rec.error_code === 'string' && rec.error_code.length > 0) {
        return formatPlatformError(rec.error_code, _errorParams(rec));
    }

    if (Array.isArray(rec.detail)) {
        return rec.detail.map(detailMessage).join('; ');
    }
    if (typeof rec.detail === 'string') return rec.detail;
    if (typeof rec.message === 'string') return rec.message;
    return `HTTP ${status}`;
}

function _buildQuery(params: Record<string, string | number | boolean | null | undefined> | undefined): string {
    if (!params) return '';
    const entries = Object.entries(params).filter(([, v]) => v !== null && v !== undefined);
    if (entries.length === 0) return '';
    const qs = entries
        .map(([k, v]) => `${encodeURIComponent(k)}=${encodeURIComponent(String(v))}`)
        .join('&');
    return `?${qs}`;
}

function _headersObject(headers: Headers): Record<string, string> {
    const out: Record<string, string> = {};
    headers.forEach((value, key) => {
        out[key] = value;
    });
    return out;
}

function _parseResponseBody(raw: string, contentType: string): unknown {
    if (!raw || raw.trim() === '') return {};
    if (contentType.includes('application/json')) return JSON.parse(raw);
    if (contentType.includes('text/markdown') || contentType.includes('text/plain')) return raw;
    const trimmed = raw.trim();
    if (trimmed.startsWith('{') || trimmed.startsWith('[')) return JSON.parse(raw);
    return raw;
}

/** Тело отказа: JSON по первому символу, как и у успешного ответа; нетекстовое или не-JSON тело даёт `null`. */
async function _readErrorBody(response: Response): Promise<unknown> {
    const raw = await response.text();
    const trimmed = raw.trim();
    if (trimmed.startsWith('{') || trimmed.startsWith('[')) return JSON.parse(raw);
    return null;
}

export interface HttpResponseEnvelope {
    status: number;
    statusText: string;
    headers: Record<string, string>;
    raw: string;
    body: unknown;
}

function _responseEnvelope(response: Response, raw: string, body: unknown): HttpResponseEnvelope {
    return {
        status: response.status,
        statusText: response.statusText,
        headers: _headersObject(response.headers),
        raw,
        body,
    };
}

/**
 * Извлекает поля платформы из JSON тела ошибки (request_id / trace_id / service / observability).
 */
interface PlatformErrorEnvelope {
    request_id: string | null;
    trace_id: string | null;
    service: string | null;
    observability: { logs_explore_url: string } | null;
}

function _platformErrorEnvelopeFromBody(body: unknown): PlatformErrorEnvelope {
    if (!isPlainRecord(body)) {
        return {
            request_id: null,
            trace_id: null,
            service: null,
            observability: null,
        };
    }
    const request_id =
        typeof body.request_id === 'string' && body.request_id.length > 0 ? body.request_id : null;
    const trace_id =
        typeof body.trace_id === 'string' && body.trace_id.length > 0 ? body.trace_id : null;
    const service =
        typeof body.service === 'string' && body.service.length > 0 ? body.service : null;

    let observability: { logs_explore_url: string } | null = null;
    const rawObs = body.observability;
    if (
        isPlainRecord(rawObs) &&
        typeof rawObs.logs_explore_url === 'string' &&
        rawObs.logs_explore_url.length > 0
    ) {
        observability = Object.freeze({ logs_explore_url: rawObs.logs_explore_url });
    }

    return { request_id, trace_id, service, observability };
}

export class HttpError extends Error {
    status: number;
    body: unknown;
    request_id: string | null;
    trace_id: string | null;
    service: string | null;
    observability: { logs_explore_url: string } | null;
    error_code: string | null;
    error_params: Record<string, unknown> | null;

    constructor(message: string, status: number, body: unknown) {
        super(message);
        this.name = 'HttpError';
        this.status = status;
        this.body = body;
        const env = _platformErrorEnvelopeFromBody(body);
        this.request_id = env.request_id;
        this.trace_id = env.trace_id;
        this.service = env.service;
        this.observability = env.observability;
        const rec = isPlainRecord(body) ? body : null;
        this.error_code =
            rec !== null && typeof rec.error_code === 'string' && rec.error_code.length > 0
                ? rec.error_code
                : null;
        this.error_params = _errorParams(body);
    }
}

/**
 * Выполнить HTTP-запрос. Бросает HttpError при ответе !ok.
 *
 * @param {{
 *   method?: 'GET'|'POST'|'PUT'|'PATCH'|'DELETE',
 *   url: string,
 *   query?: Record<string, string|number|boolean|null|undefined>,
 *   body?: unknown,
 *   headers?: Record<string, string>,
 *   signal?: AbortSignal,
 *   credentials?: RequestCredentials,
 * }} req
 */
export interface HttpRequestSpec {
    method?: 'GET' | 'POST' | 'PUT' | 'PATCH' | 'DELETE' | undefined;
    url: string;
    query?: Record<string, string | number | boolean | null | undefined> | undefined;
    body?: unknown;
    headers?: Record<string, string> | undefined;
    signal?: AbortSignal | undefined;
    credentials?: RequestCredentials | undefined;
    returnMeta?: boolean;
    captureRaw?: boolean;
}

export async function httpRequest(req: HttpRequestSpec): Promise<unknown> {
    if (!req || typeof req.url !== 'string') {
        throw new Error('httpRequest: { url } required');
    }
    const method = req.method || 'GET';
    const requestBody = req.body;
    const isFormData = typeof FormData !== 'undefined' && requestBody instanceof FormData;
    const hasBody = requestBody !== undefined && requestBody !== null;
    const headers = {
        ...(hasBody && !isFormData ? { 'Content-Type': 'application/json' } : {}),
        ...(req.headers === undefined ? {} : req.headers),
    };
    const url = `${req.url}${_buildQuery(req.query)}`;
    const init: RequestInit = {
        method,
        headers,
        credentials: req.credentials || 'include',
        signal: req.signal ?? null,
    };
    if (hasBody) {
        if (typeof FormData !== 'undefined' && requestBody instanceof FormData) {
            init.body = requestBody;
        } else {
            init.body = JSON.stringify(requestBody);
        }
    }

    const response = await fetch(url, init);

    if (!response.ok) {
        const body = await _readErrorBody(response);
        throw new HttpError(_formatError(body, response.status), response.status, body);
    }

    if (response.status === 204 || response.status === 205) {
        if (req.returnMeta === true) {
            return _responseEnvelope(response, '', {});
        }
        return {};
    }

    const contentType = response.headers.get('content-type');
    const ct = contentType === null ? '' : contentType;
    const raw = await response.text();
    const body = _parseResponseBody(raw, ct);
    if (req.returnMeta === true) {
        return _responseEnvelope(response, raw, body);
    }
    return body;
}

/**
 * Чтение SSE-потока с вызовом onEvent для каждой data-строки.
 * Используется effects, которым нужны streaming ответы (LLM, A2A).
 */
export async function httpStream(req: HttpRequestSpec, onEvent: (data: unknown) => void): Promise<HttpResponseEnvelope | undefined> {
    if (typeof onEvent !== 'function') {
        throw new Error('httpStream: onEvent function required');
    }
    const init = {
        method: req.method || 'POST',
        headers: { 'Content-Type': 'application/json', ...(req.headers === undefined ? {} : req.headers) },
        credentials: req.credentials || 'include',
        signal: req.signal ?? null,
        body: req.body !== undefined && req.body !== null ? JSON.stringify(req.body) : null,
    };
    const response = await fetch(req.url, init);
    if (!response.ok) {
        const body = await _readErrorBody(response);
        throw new HttpError(_formatError(body, response.status), response.status, body);
    }
    if (!response.body) {
        throw new HttpError('httpStream: response.body is null', response.status, null);
    }
    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    let buffer = '';
    let raw = '';
    while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        const decoded = decoder.decode(value, { stream: true });
        if (req.captureRaw === true) {
            raw += decoded;
        }
        buffer += decoded;
        const lines = buffer.split('\n');
        const tail = lines.pop();
        buffer = tail === undefined ? '' : tail;
        for (const line of lines) {
            if (line.startsWith('data: ')) {
                const data = line.slice(6);
                if (data === '[DONE]') {
                    if (req.returnMeta === true) {
                        return _responseEnvelope(response, raw, {});
                    }
                    return undefined;
                }
                onEvent(JSON.parse(data));
            }
        }
    }
    if (req.returnMeta === true) {
        return _responseEnvelope(response, raw, {});
    }
    return undefined;
}
