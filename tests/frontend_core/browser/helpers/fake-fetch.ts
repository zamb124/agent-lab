/**
 * Браузерный fake fetch: похож на mock-fetch.js из unit-уровня, но без MSW
 * (тесты браузера не используют real fetch — большинство компонентов
 * подписываются на bus, dispatch которым делает effect, а не сам компонент).
 *
 * Если конкретный тест требует HTTP — оборачивает window.fetch.
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
        this._body = body;
    }
    async text() { return typeof this._body === 'string' ? this._body : JSON.stringify(this._body || ''); }
    async json() { return typeof this._body === 'string' ? JSON.parse(this._body) : this._body; }
}

export function installFetchMock() {
    const handlers = [];
    const calls = [];
    const prev = window.fetch;
    window.fetch = async (url, init = {}) => {
        const method = (init.method || 'GET').toUpperCase();
        const u = String(url);
        calls.push({ url: u, method, init });
        const handler = handlers.find((h) => h.method === method && (typeof h.match === 'function' ? h.match(u) : h.match === u));
        if (!handler) throw new Error(`fake fetch: no handler for ${method} ${u}`);
        if (handler.error) throw handler.error;
        return new MockResponse(handler.response);
    };
    return {
        respondJson(method, match, body, status = 200) {
            handlers.push({ method, match, response: { status, headers: { 'content-type': 'application/json' }, body: typeof body === 'string' ? body : JSON.stringify(body) } });
        },
        respondStatus(method, match, status, body = null) {
            handlers.push({ method, match, response: { status, headers: { 'content-type': 'application/json' }, body: body ? JSON.stringify(body) : null } });
        },
        calls,
        uninstall() { window.fetch = prev; },
    };
}
