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

type MatchInput = string | RegExp | ((url: string) => boolean);

interface MockResponseInit {
    status?: number;
    headers?: Record<string, string>;
    body?: unknown;
}

interface HandlerEntry {
    method: string;
    match: MatchInput;
    response?: MockResponseInit;
    error?: unknown;
}

export interface FetchCallRecord {
    url: string;
    method: string;
    init: RequestInit;
}

class MockResponse {
    readonly ok: boolean;
    readonly status: number;
    readonly headers: { get(name: string): string | null };
    private readonly _headersRaw: Record<string, string>;
    private readonly _body: unknown;

    constructor({ status = 200, headers = {}, body = null }: MockResponseInit = {}) {
        this.ok = status >= 200 && status < 300;
        this.status = status;
        this.headers = {
            get(name: string) {
                return headers[name.toLowerCase()] ?? null;
            },
        };
        this._headersRaw = Object.fromEntries(
            Object.entries(headers).map(([k, v]) => [k.toLowerCase(), v]),
        );
        this._body = body;
    }

    async text(): Promise<string> {
        if (this._body === null || this._body === undefined) return '';
        if (typeof this._body === 'string') return this._body;
        return JSON.stringify(this._body);
    }

    async json(): Promise<unknown> {
        if (typeof this._body === 'string') return JSON.parse(this._body);
        return this._body;
    }
}

export function installFetchMock() {
    const handlers: HandlerEntry[] = [];
    const calls: FetchCallRecord[] = [];

    function _resolve(method: string, url: string): HandlerEntry | null {
        for (let i = handlers.length - 1; i >= 0; i -= 1) {
            const h = handlers[i];
            if (!h) continue;
            if (h.method !== method) continue;
            if (typeof h.match === 'function' ? h.match(url) : h.match === url) {
                return h;
            }
            if (h.match instanceof RegExp && h.match.test(url)) return h;
        }
        return null;
    }

    const fetchFn = async (rawUrl: string | URL | Request, init: RequestInit = {}) => {
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
    Object.defineProperty(globalThis, 'fetch', { value: fetchFn, configurable: true, writable: true });

    return {
        respondJson(method: string, match: MatchInput, body: unknown, status = 200): void {
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
        respondText(method: string, match: MatchInput, body: string, status = 200, contentType = 'text/plain'): void {
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
        respondError(method: string, match: MatchInput, error: unknown): void {
            handlers.push({ method, match, error });
        },
        respondStatus(method: string, match: MatchInput, status: number, body: unknown = null): void {
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
        uninstall(): void {
            Object.defineProperty(globalThis, 'fetch', { value: prevFetch, configurable: true, writable: true });
        },
    };
}
