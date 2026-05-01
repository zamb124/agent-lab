/**
 * Низкоуровневый HTTP-клиент для использования внутри effects.
 *
 * НЕ предоставляет UI/event API напрямую — все вызовы инкапсулируются
 * в domain effects, которые реагируют на события и диспатчат новые.
 * Компоненты НЕ должны вызывать httpRequest напрямую — это делает effect,
 * подписанный на доменное событие.
 */

function _formatError(errorData, status) {
    if (!errorData) return `HTTP ${status}`;

    if (Array.isArray(errorData.detail)) {
        const messages = errorData.detail.map((err) => {
            if (err.field && err.error) return `${err.field}: ${err.error}`;
            const field = err.loc && Array.isArray(err.loc) ? err.loc.slice(1).join('.') : 'field';
            return `${field}: ${err.msg}`;
        });
        return messages.join('; ');
    }
    if (typeof errorData.detail === 'string') return errorData.detail;
    if (typeof errorData.message === 'string') return errorData.message;
    return `HTTP ${status}`;
}

function _buildQuery(params) {
    if (!params) return '';
    const entries = Object.entries(params).filter(([, v]) => v !== null && v !== undefined);
    if (entries.length === 0) return '';
    const qs = entries
        .map(([k, v]) => `${encodeURIComponent(k)}=${encodeURIComponent(v)}`)
        .join('&');
    return `?${qs}`;
}

/**
 * Извлекает поля платформы из JSON тела ошибки (request_id / trace_id / service / observability).
 */
function _platformErrorEnvelopeFromBody(body) {
    if (body === null || typeof body !== 'object' || Array.isArray(body)) {
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

    let observability = null;
    const rawObs = body.observability;
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
    constructor(message, status, body) {
        super(message);
        this.name = 'HttpError';
        this.status = status;
        this.body = body;
        const env = _platformErrorEnvelopeFromBody(body);
        this.request_id = env.request_id;
        this.trace_id = env.trace_id;
        this.service = env.service;
        this.observability = env.observability;
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
export async function httpRequest(req) {
    if (!req || typeof req.url !== 'string') {
        throw new Error('httpRequest: { url } required');
    }
    const method = req.method || 'GET';
    const isFormData = typeof FormData !== 'undefined' && req.body instanceof FormData;
    const headers = {
        ...(isFormData ? {} : { 'Content-Type': 'application/json' }),
        ...(req.headers || {}),
    };
    const url = `${req.url}${_buildQuery(req.query)}`;
    const init = {
        method,
        headers,
        credentials: req.credentials || 'include',
        signal: req.signal,
    };
    if (req.body !== undefined && req.body !== null) {
        init.body = isFormData ? req.body : JSON.stringify(req.body);
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
        return {};
    }

    const ct = response.headers.get('content-type') || '';
    const raw = await response.text();
    if (!raw || raw.trim() === '') return {};
    if (ct.includes('application/json')) return JSON.parse(raw);
    if (ct.includes('text/markdown') || ct.includes('text/plain')) return raw;
    const trimmed = raw.trim();
    if (trimmed.startsWith('{') || trimmed.startsWith('[')) return JSON.parse(raw);
    return raw;
}

/**
 * Чтение SSE-потока с вызовом onEvent для каждой data-строки.
 * Используется effects, которым нужны streaming ответы (LLM, A2A).
 */
export async function httpStream(req, onEvent) {
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
    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    let buffer = '';
    while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split('\n');
        buffer = lines.pop() || '';
        for (const line of lines) {
            if (line.startsWith('data: ')) {
                const data = line.slice(6);
                if (data === '[DONE]') return;
                onEvent(JSON.parse(data));
            }
        }
    }
}
