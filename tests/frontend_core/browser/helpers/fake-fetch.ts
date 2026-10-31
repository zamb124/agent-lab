/**
 * Браузерный fake fetch: похож на mock-fetch.js из unit-уровня, но без MSW
 * (тесты браузера не используют real fetch — большинство компонентов
 * подписываются на bus, dispatch которым делает effect, а не сам компонент).
 *
 * Если конкретный тест требует HTTP — оборачивает window.fetch.
 */

type MatchInput = string | ((url: string) => boolean);

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

export interface BrowserFetchCallRecord {
    url: string;
    method: string;
    init: RequestInit;
}

class MockResponse {
    readonly ok: boolean;
    readonly status: number;
    readonly headers: { get(name: string): string | null };
    private readonly _body: unknown;

    constructor({ status = 200, headers = {}, body = null }: MockResponseInit = {}) {
        this.ok = status >= 200 && status < 300;
        this.status = status;
        this.headers = {
            get(name: string) {
                return headers[name.toLowerCase()] ?? null;
            },
        };
        this._body = body;
    }
    async text(): Promise<string> { return typeof this._body === 'string' ? this._body : JSON.stringify(this._body || ''); }
    async json(): Promise<unknown> { return typeof this._body === 'string' ? JSON.parse(this._body) : this._body; }
}

export function installFetchMock() {
    const handlers: HandlerEntry[] = [];
    const calls: BrowserFetchCallRecord[] = [];
    const prev = window.fetch;
    const fetchFn = async (url: string | URL | Request, init: RequestInit = {}) => {
        const method = (init.method || 'GET').toUpperCase();
        const u = String(url);
        calls.push({ url: u, method, init });
        const handler = handlers.find((h) => h.method === method && (typeof h.match === 'function' ? h.match(u) : h.match === u));
        if (!handler) throw new Error(`fake fetch: no handler for ${method} ${u}`);
        if (handler.error) throw handler.error;
        return new MockResponse(handler.response);
    };
    Object.defineProperty(window, 'fetch', { value: fetchFn, configurable: true, writable: true });
    return {
        respondJson(method: string, match: MatchInput, body: unknown, status = 200): void {
            handlers.push({ method, match, response: { status, headers: { 'content-type': 'application/json' }, body: typeof body === 'string' ? body : JSON.stringify(body) } });
        },
        respondStatus(method: string, match: MatchInput, status: number, body: unknown = null): void {
            handlers.push({ method, match, response: { status, headers: { 'content-type': 'application/json' }, body: body ? JSON.stringify(body) : null } });
        },
        calls,
        uninstall(): void { window.fetch = prev; },
    };
}
