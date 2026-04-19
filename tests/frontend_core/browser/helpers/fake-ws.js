/**
 * Браузерный MockWebSocket — параллель Node-версии. Подменяет window.WebSocket.
 */

export class BrowserMockWebSocket {
    constructor(url) {
        this.url = url;
        this.readyState = BrowserMockWebSocket.CONNECTING;
        this.sent = [];
        this.onopen = null;
        this.onmessage = null;
        this.onerror = null;
        this.onclose = null;
        BrowserMockWebSocket.instances.push(this);
        if (BrowserMockWebSocket.openSync) {
            queueMicrotask(() => this.open());
        }
    }
    open() {
        if (this.readyState === BrowserMockWebSocket.OPEN) return;
        this.readyState = BrowserMockWebSocket.OPEN;
        if (this.onopen) this.onopen({});
    }
    send(data) {
        if (this.readyState !== BrowserMockWebSocket.OPEN) throw new Error('Mock WS not open');
        this.sent.push(data);
    }
    serverFrame(obj) {
        if (!this.onmessage) return;
        const data = typeof obj === 'string' ? obj : JSON.stringify(obj);
        this.onmessage({ data });
    }
    close(code = 1000, reason = '') {
        if (this.readyState === BrowserMockWebSocket.CLOSED) return;
        this.readyState = BrowserMockWebSocket.CLOSED;
        if (this.onclose) this.onclose({ code, reason });
    }
}

BrowserMockWebSocket.CONNECTING = 0;
BrowserMockWebSocket.OPEN = 1;
BrowserMockWebSocket.CLOSING = 2;
BrowserMockWebSocket.CLOSED = 3;
BrowserMockWebSocket.instances = [];
BrowserMockWebSocket.openSync = true;

export function installMockWebSocket(opts = {}) {
    BrowserMockWebSocket.openSync = opts.openSync !== false;
    BrowserMockWebSocket.instances = [];
    const prev = window.WebSocket;
    window.WebSocket = BrowserMockWebSocket;
    return {
        get instances() { return BrowserMockWebSocket.instances; },
        latest() { return BrowserMockWebSocket.instances.at(-1); },
        uninstall() { window.WebSocket = prev; BrowserMockWebSocket.instances = []; },
    };
}
