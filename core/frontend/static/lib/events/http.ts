/**
 * Низкоуровневый HTTP-клиент для использования внутри effects.
 *
 * НЕ предоставляет UI/event API напрямую — все вызовы инкапсулируются
 * в domain effects, которые реагируют на события и диспатчат новые.
 * Компоненты НЕ должны вызывать httpRequest напрямую — это делает effect,
 * подписанный на доменное событие.
 */

import { formatPlatformError } from '../utils/platform-error-message.js';

function _errorParams(errorData: unknown): Record<string, string | number | boolean> | null {
    if (
        errorData
        && typeof errorData === 'object'
        && !Array.isArray(errorData)
        && 'error_params' in errorData
        && typeof (errorData as Record<string, unknown>).error_params === 'object'
        && !Array.isArray((errorData as Record<string, unknown>).error_params)
    ) {
        return (errorData as Record<string, unknown>).error_params as Record<string, string | number | boolean>;
    }
    return null;
}

function _formatError(errorData: unknown, status: number): string {
    const rec =
        errorData !== null && typeof errorData === 'object' && !Array.isArray(errorData)
            ? (errorData as Record<string, unknown>)
            : null;
    if (rec === null) return `HTTP ${status}`;

    if (typeof rec.error_code === 'string' && rec.error_code.length > 0) {
        return formatPlatformError(rec.error_code, _errorParams(rec));
    }

    if (Array.isArray(rec.detail)) {
        const messages = (rec.detail as Record<string, unknown>[]).map((err) => {
            if (err.field && err.error) return `${err.field}: ${err.error}`;
            const field = err.loc && Array.isArray(err.loc) ? err.loc.slice(1).join('.') : 'field';
            return `${field}: ${err.msg}`;
        });
        return messages.join('; ');
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
    if (body === null || typeof body !== 'object' || Array.isArray(body)) {
        return {
            request_id: null,
            trace_id: null,
            service: null,
            observability: null,
        };
    }
    const rec = body as Record<string, unknown>;
    const request_id =
        typeof rec.request_id === 'string' && rec.request_id.length > 0 ? rec.request_id : null;
    const trace_id =
        typeof rec.trace_id === 'string' && rec.trace_id.length > 0 ? rec.trace_id : null;
    const service =
        typeof rec.service === 'string' && rec.service.length > 0 ? rec.service : null;

    let observability: { logs_explore_url: string } | null = null;
    const rawObs = rec.observability as Record<string, unknown> | null | undefined;
    if (
        rawObs !== null &&
        typeof rawObs === 'object' &&
        !Array.isArray(rawObs) &&
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
        const rec = body !== null && typeof body === 'object' && !Array.isArray(body)
            ? (body as Record<string, unknown>)
            : null;
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
    method?: 'GET' | 'POST' | 'PUT' | 'PATCH' | 'DELETE';
    url: string;
    query?: Record<string, string | number | boolean | null | undefined>;
    body?: unknown;
    headers?: Record<string, string>;
    signal?: AbortSignal;
    credentials?: RequestCredentials;
    returnMeta?: boolean;
    captureRaw?: boolean;
}

export async function httpRequest(req: HttpRequestSpec): Promise<unknown> {
    if (!req || typeof req.url !== 'string') {
        throw new Error('httpRequest: { url } required');
    }
    const method = req.method || 'GET';
    const isFormData = typeof FormData !== 'undefined' && req.body instanceof FormData;
    const hasBody = req.body !== undefined && req.body !== null;
    const headers = {
        ...(hasBody && !isFormData ? { 'Content-Type': 'application/json' } : {}),
        ...(req.headers || {}),
    };
    const url = `${req.url}${_buildQuery(req.query)}`;
    const init: RequestInit = {
        method,
        headers,
        credentials: req.credentials || 'include',
        signal: req.signal,
    };
    if (hasBody) {
        init.body = isFormData ? (req.body as FormData) : JSON.stringify(req.body);
    }

    const response = await fetch(url, init);

    if (!response.ok) {
        let body = null;
        try {
            body = await response.json();
        } catch {
            body = null;
        }
        throw new HttpError(_formatError(body, response.status), response.status, body);
    }

    if (response.status === 204 || response.status === 205) {
        if (req.returnMeta === true) {
            return _responseEnvelope(response, '', {});
        }
        return {};
    }

    const ct = response.headers.get('content-type') || '';
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
        headers: { 'Content-Type': 'application/json', ...(req.headers || {}) },
        credentials: req.credentials || 'include',
        signal: req.signal,
        body: req.body !== undefined && req.body !== null ? JSON.stringify(req.body) : undefined,
    };
    const response = await fetch(req.url, init);
    if (!response.ok) {
        let body = null;
        try { body = await response.json(); } catch { body = null; }
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
        buffer = lines.pop() || '';
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
