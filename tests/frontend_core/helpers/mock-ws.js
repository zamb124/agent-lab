/**
 * MockWebSocket — детерминированная имитация window.WebSocket для unit-тестов
 * ws.effect.
 *
 * Контракт:
 *   - new MockWebSocket(url) — сразу OPEN (если cfg.openSync), либо OPEN после
 *     `instance.open()` руками.
 *   - instance.send(data) — пушит в `instance.sent` массив отправленных фреймов.
 *   - instance.serverFrame(obj) — диспатчит onmessage с JSON.stringify(obj).
 *   - instance.serverClose(code, reason) — вызывает onclose.
 *
 * Состояния как у настоящего WebSocket: 0/CONNECTING, 1/OPEN, 2/CLOSING, 3/CLOSED.
 */

export class MockWebSocket {
    constructor(url) {
        this.url = url;
        this.readyState = MockWebSocket.CONNECTING;
        this.sent = [];
        this.onopen = null;
        this.onmessage = null;
        this.onerror = null;
        this.onclose = null;
        MockWebSocket.instances.push(this);
        if (MockWebSocket.openSync) {
            this.open();
        }
    }

    open() {
        if (this.readyState === MockWebSocket.OPEN) return;
        this.readyState = MockWebSocket.OPEN;
        if (this.onopen) this.onopen({});
    }

    send(data) {
        if (this.readyState !== MockWebSocket.OPEN) {
            throw new Error('MockWebSocket.send: socket is not open');
        }
        this.sent.push(data);
    }

    serverFrame(obj) {
        if (!this.onmessage) return;
        const data = typeof obj === 'string' ? obj : JSON.stringify(obj);
        this.onmessage({ data });
    }

    close(code = 1000, reason = '') {
        if (this.readyState === MockWebSocket.CLOSED) return;
        this.readyState = MockWebSocket.CLOSED;
        if (this.onclose) this.onclose({ code, reason });
    }

    serverClose(code = 1006, reason = 'server') {
        this.close(code, reason);
    }
}

MockWebSocket.CONNECTING = 0;
MockWebSocket.OPEN = 1;
MockWebSocket.CLOSING = 2;
MockWebSocket.CLOSED = 3;
MockWebSocket.instances = [];
MockWebSocket.openSync = true;

export function installMockWebSocket(opts = {}) {
    MockWebSocket.openSync = opts.openSync !== false;
    MockWebSocket.instances = [];
    const prev = globalThis.WebSocket;
    globalThis.WebSocket = MockWebSocket;
    return {
        get instances() { return MockWebSocket.instances; },
        latest() { return MockWebSocket.instances.at(-1); },
        uninstall() { globalThis.WebSocket = prev; MockWebSocket.instances = []; },
    };
}
