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

type WsHandler = ((event: { data?: string; code?: number; reason?: string }) => void) | null;

export class MockWebSocket {
    static CONNECTING = 0;
    static OPEN = 1;
    static CLOSING = 2;
    static CLOSED = 3;
    static instances: MockWebSocket[] = [];
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
        this.readyState = MockWebSocket.CONNECTING;
        MockWebSocket.instances.push(this);
        if (MockWebSocket.openSync) {
            this.open();
        }
    }

    open(): void {
        if (this.readyState === MockWebSocket.OPEN) return;
        this.readyState = MockWebSocket.OPEN;
        if (this.onopen) this.onopen({});
    }

    send(data: unknown): void {
        if (this.readyState !== MockWebSocket.OPEN) {
            throw new Error('MockWebSocket.send: socket is not open');
        }
        this.sent.push(data);
    }

    serverFrame(obj: unknown): void {
        if (!this.onmessage) return;
        const data = typeof obj === 'string' ? obj : JSON.stringify(obj);
        this.onmessage({ data });
    }

    close(code = 1000, reason = ''): void {
        if (this.readyState === MockWebSocket.CLOSED) return;
        this.readyState = MockWebSocket.CLOSED;
        if (this.onclose) this.onclose({ code, reason });
    }

    serverClose(code = 1006, reason = 'server'): void {
        this.close(code, reason);
    }
}

export function installMockWebSocket(opts: { openSync?: boolean } = {}) {
    MockWebSocket.openSync = opts.openSync !== false;
    MockWebSocket.instances = [];
    const prev = globalThis.WebSocket;
    Object.defineProperty(globalThis, 'WebSocket', { value: MockWebSocket, configurable: true, writable: true });
    return {
        get instances(): MockWebSocket[] { return MockWebSocket.instances; },
        latest(): MockWebSocket | undefined { return MockWebSocket.instances.at(-1); },
        uninstall(): void {
            Object.defineProperty(globalThis, 'WebSocket', { value: prev, configurable: true, writable: true });
            MockWebSocket.instances = [];
        },
    };
}
