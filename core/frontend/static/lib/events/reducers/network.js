/**
 * Network slice.
 *
 * Поля state.network:
 *   online:        boolean
 *   ws:            { status: 'idle'|'connecting'|'open'|'closed', lastError: string|null, attempts: number }
 *   pendingHttp:   number  - счётчик активных HTTP-запросов (для глобального индикатора)
 */

import { CoreEvents } from '../contract.js';

export const initialNetworkState = Object.freeze({
    online: typeof navigator !== 'undefined' ? Boolean(navigator.onLine) : true,
    ws: { status: 'idle', lastError: null, attempts: 0 },
    pendingHttp: 0,
});

export function networkReducer(state = initialNetworkState, event) {
    switch (event.type) {
        case CoreEvents.NETWORK_ONLINE:
            return state.online ? state : { ...state, online: true };
        case CoreEvents.NETWORK_OFFLINE:
            return !state.online ? state : { ...state, online: false };
        case CoreEvents.WS_CONNECT_REQUESTED:
            return { ...state, ws: { ...state.ws, status: 'connecting', attempts: state.ws.attempts + 1 } };
        case CoreEvents.WS_CONNECTED:
            return { ...state, ws: { status: 'open', lastError: null, attempts: 0 } };
        case CoreEvents.WS_DISCONNECTED: {
            const reason = event.payload && event.payload.reason ? String(event.payload.reason) : null;
            return { ...state, ws: { ...state.ws, status: 'closed', lastError: reason } };
        }
        case CoreEvents.HTTP_REQUEST_STARTED:
            return { ...state, pendingHttp: state.pendingHttp + 1 };
        case CoreEvents.HTTP_REQUEST_SUCCEEDED:
        case CoreEvents.HTTP_REQUEST_FAILED:
            return { ...state, pendingHttp: Math.max(0, state.pendingHttp - 1) };
        default:
            return state;
    }
}
