/**
 * Лёгкий mock fetch для unit-тестов. Без MSW (Node-режим Vitest, нам не нужен
 * полный сервер). Контракт совпадает с тем, что ожидает httpRequest:
 * `fetch(url, init)` -> Response-like объект с `ok`, `status`, `headers`,
 * `text()`, `json()`.
 *
 * Использование:
 *   const fetchMock = installFetchMock();
 *   fetchMock.respondJson('GET', '/api/items', { items: [] });
 *   const data = await httpRequest({ method: 'GET', url: '/api/items' });
 *   uninstallFetchMock();
 */

class MockResponse {
    constructor({ status = 200, headers = {}, body = null } = {}) {
        this.ok = status >= 200 && status < 300;
        this.status = status;
        this.headers = {
            get(name) {
                return headers[name.toLowerCase()] ?? null;
            },
        };
        this._headersRaw = Object.fromEntries(
            Object.entries(headers).map(([k, v]) => [k.toLowerCase(), v]),
        );
        this._body = body;
    }
    async text() {
        if (this._body === null || this._body === undefined) return '';
        if (typeof this._body === 'string') return this._body;
        return JSON.stringify(this._body);
    }
    async json() {
        if (typeof this._body === 'string') return JSON.parse(this._body);
        return this._body;
    }
}

export function installFetchMock() {
    const handlers = [];
    const calls = [];

    function _resolve(method, url) {
        for (let i = handlers.length - 1; i >= 0; i -= 1) {
            const h = handlers[i];
            if (h.method !== method) continue;
            if (typeof h.match === 'function' ? h.match(url) : h.match === url) {
                return h;
            }
            if (h.match instanceof RegExp && h.match.test(url)) return h;
        }
        return null;
    }

    const fetchFn = async (rawUrl, init = {}) => {
        const url = String(rawUrl);
        const method = (init.method || 'GET').toUpperCase();
        calls.push({ url, method, init });
        const handler = _resolve(method, url);
        if (!handler) {
            throw new Error(`installFetchMock: no handler registered for ${method} ${url}`);
        }
        if (handler.error) throw handler.error;
        return new MockResponse(handler.response);
    };

    const prevFetch = globalThis.fetch;
    globalThis.fetch = fetchFn;

    return {
        respondJson(method, match, body, status = 200) {
            handlers.push({
                method,
                match,
                response: {
                    status,
                    headers: { 'content-type': 'application/json' },
                    body: typeof body === 'string' ? body : JSON.stringify(body),
                },
            });
        },
        respondText(method, match, body, status = 200, contentType = 'text/plain') {
            handlers.push({
                method,
                match,
                response: {
                    status,
                    headers: { 'content-type': contentType },
                    body,
                },
            });
        },
        respondError(method, match, error) {
            handlers.push({ method, match, error });
        },
        respondStatus(method, match, status, body = null) {
            handlers.push({
                method,
                match,
                response: {
                    status,
                    headers: { 'content-type': 'application/json' },
                    body: body === null ? null : JSON.stringify(body),
                },
            });
        },
        calls,
        uninstall() {
            globalThis.fetch = prevFetch;
        },
    };
}
