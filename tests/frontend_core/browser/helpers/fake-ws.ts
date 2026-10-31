/**
 * Браузерный MockWebSocket — параллель Node-версии. Подменяет window.WebSocket.
 */

type WsHandler = ((event: { data?: string; code?: number; reason?: string }) => void) | null;

export class BrowserMockWebSocket {
    static CONNECTING = 0;
    static OPEN = 1;
    static CLOSING = 2;
    static CLOSED = 3;
    static instances: BrowserMockWebSocket[] = [];
    static openSync = true;

    readonly url: string;
    readyState: number;
    readonly sent: unknown[] = [];
    onopen: WsHandler = null;
    onmessage: WsHandler = null;
    onerror: WsHandler = null;
    onclose: WsHandler = null;

    constructor(url: string) {
        this.url = url;
        this.readyState = BrowserMockWebSocket.CONNECTING;
        BrowserMockWebSocket.instances.push(this);
        if (BrowserMockWebSocket.openSync) {
            queueMicrotask(() => this.open());
        }
    }
    open(): void {
        if (this.readyState === BrowserMockWebSocket.OPEN) return;
        this.readyState = BrowserMockWebSocket.OPEN;
        if (this.onopen) this.onopen({});
    }
    send(data: unknown): void {
        if (this.readyState !== BrowserMockWebSocket.OPEN) throw new Error('Mock WS not open');
        this.sent.push(data);
    }
    serverFrame(obj: unknown): void {
        if (!this.onmessage) return;
        const data = typeof obj === 'string' ? obj : JSON.stringify(obj);
        this.onmessage({ data });
    }
    close(code = 1000, reason = ''): void {
        if (this.readyState === BrowserMockWebSocket.CLOSED) return;
        this.readyState = BrowserMockWebSocket.CLOSED;
        if (this.onclose) this.onclose({ code, reason });
    }
}

export function installMockWebSocket(opts: { openSync?: boolean } = {}) {
    BrowserMockWebSocket.openSync = opts.openSync !== false;
    BrowserMockWebSocket.instances = [];
    const prev = window.WebSocket;
    Object.defineProperty(window, 'WebSocket', { value: BrowserMockWebSocket, configurable: true, writable: true });
    return {
        get instances(): BrowserMockWebSocket[] { return BrowserMockWebSocket.instances; },
        latest(): BrowserMockWebSocket | undefined { return BrowserMockWebSocket.instances.at(-1); },
        uninstall(): void {
            Object.defineProperty(window, 'WebSocket', { value: prev, configurable: true, writable: true });
            BrowserMockWebSocket.instances = [];
        },
    };
}
