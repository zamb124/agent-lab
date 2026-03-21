/**
 * SyncWsService — управление WebSocket подключением к /sync/ws
 *
 * Отличие от sync1: токен НЕ передаётся в query-параметре.
 * Auth проходит через cookie при upgrade-запросе, как у всех сервисов платформы.
 * Reconnect с exponential backoff + jitter по образцу sync1/ws.ts.
 */

const BASE_DELAY_MS = 600;
const MAX_DELAY_MS = 60_000;

function jitter(ms) {
    const spread = 0.2;
    const delta = ms * spread;
    return Math.max(0, Math.round(ms - delta + Math.random() * 2 * delta));
}

export class SyncWsService {
    constructor() {
        this._socket = null;
        this._stopped = false;
        this._attempt = 0;
        this._reconnectTimer = null;
        this._state = 'closed';

        this._onOpenCallbacks = [];
        this._onCloseCallbacks = [];
        this._onMessageCallbacks = [];
        this._onErrorCallbacks = [];
    }

    get state() {
        return this._state;
    }

    onOpen(cb) { this._onOpenCallbacks.push(cb); return this; }
    onClose(cb) { this._onCloseCallbacks.push(cb); return this; }
    onMessage(cb) { this._onMessageCallbacks.push(cb); return this; }
    onError(cb) { this._onErrorCallbacks.push(cb); return this; }

    connect() {
        if (this._stopped || this._socket) {
            return;
        }
        this._state = 'connecting';
        const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
        const wsUrl = `${protocol}//${window.location.host}/sync/ws`;
        const ws = new WebSocket(wsUrl);
        this._socket = ws;

        ws.onopen = () => {
            if (this._socket !== ws) return;
            this._attempt = 0;
            this._state = 'open';
            this._onOpenCallbacks.forEach(cb => cb());
        };

        ws.onmessage = (e) => {
            if (this._socket !== ws) return;
            if (typeof e.data !== 'string') return;
            this._onMessageCallbacks.forEach(cb => cb(e.data));
        };

        ws.onerror = () => {
            if (this._socket !== ws) return;
            this._onErrorCallbacks.forEach(cb => cb());
        };

        ws.onclose = (e) => {
            if (this._socket !== ws) return;
            this._socket = null;
            this._state = 'closed';
            this._onCloseCallbacks.forEach(cb => cb(e));
            this._scheduleReconnect();
        };

        this._boundOnOnline = () => {
            if (this._stopped || this._socket) return;
            this._attempt = Math.max(0, this._attempt - 1);
            this._clearTimer();
            this.connect();
        };
        this._boundOnVisible = () => {
            if (this._stopped || this._socket) return;
            if (document.visibilityState !== 'visible') return;
            this._attempt = Math.max(0, this._attempt - 1);
            this._clearTimer();
            this.connect();
        };

        window.addEventListener('online', this._boundOnOnline);
        document.addEventListener('visibilitychange', this._boundOnVisible);
    }

    sendJson(payload) {
        if (!this._socket || this._socket.readyState !== WebSocket.OPEN) {
            throw new Error('WebSocket не подключен.');
        }
        this._socket.send(JSON.stringify(payload));
    }

    close() {
        this._stopped = true;
        this._clearTimer();
        window.removeEventListener('online', this._boundOnOnline);
        document.removeEventListener('visibilitychange', this._boundOnVisible);
        const ws = this._socket;
        this._socket = null;
        this._state = 'closed';
        try { ws?.close(); } catch { }
    }

    _scheduleReconnect() {
        if (this._stopped) return;
        this._clearTimer();
        this._attempt += 1;
        const exp = Math.min(MAX_DELAY_MS, Math.round(BASE_DELAY_MS * Math.pow(1.7, this._attempt)));
        const delay = jitter(exp);
        this._state = 'connecting';
        this._reconnectTimer = window.setTimeout(() => {
            this._reconnectTimer = null;
            this.connect();
        }, delay);
    }

    _clearTimer() {
        if (this._reconnectTimer !== null) {
            window.clearTimeout(this._reconnectTimer);
            this._reconnectTimer = null;
        }
    }
}
