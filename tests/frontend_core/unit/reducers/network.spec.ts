import { describe, it, expect } from 'vitest';
import { networkReducer, initialNetworkState } from '@platform/lib/events/reducers/network.js';
import { CoreEvents } from '@platform/lib/events/contract.js';

const ev = (type, payload = null) => ({ id: `id_${type}`, type, payload, meta: { ts: 0, source: 'local' } });

describe('networkReducer', () => {
    it('initial: ws.status=idle, pendingHttp=0', () => {
        expect(initialNetworkState.ws.status).toBe('idle');
        expect(initialNetworkState.pendingHttp).toBe(0);
    });

    it('NETWORK_OFFLINE → online=false', () => {
        const next = networkReducer(initialNetworkState, ev(CoreEvents.NETWORK_OFFLINE));
        expect(next.online).toBe(false);
    });

    it('NETWORK_ONLINE при уже online → identity', () => {
        const seeded = { ...initialNetworkState, online: true };
        expect(networkReducer(seeded, ev(CoreEvents.NETWORK_ONLINE))).toBe(seeded);
    });

    it('WS_CONNECT_REQUESTED → ws.status=connecting + attempts++', () => {
        const next = networkReducer(initialNetworkState, ev(CoreEvents.WS_CONNECT_REQUESTED));
        expect(next.ws.status).toBe('connecting');
        expect(next.ws.attempts).toBe(1);
    });

    it('WS_CONNECTED обнуляет attempts и lastError', () => {
        const seeded = { ...initialNetworkState, ws: { status: 'connecting', lastError: 'old', attempts: 3 } };
        const next = networkReducer(seeded, ev(CoreEvents.WS_CONNECTED));
        expect(next.ws).toEqual({ status: 'open', lastError: null, attempts: 0 });
    });

    it('WS_DISCONNECTED фиксирует lastError', () => {
        const next = networkReducer(initialNetworkState, ev(CoreEvents.WS_DISCONNECTED, { reason: 'code_1006' }));
        expect(next.ws.status).toBe('closed');
        expect(next.ws.lastError).toBe('code_1006');
    });

    it('HTTP_REQUEST_STARTED ++ pendingHttp; SUCCEEDED/FAILED --', () => {
        const a = networkReducer(initialNetworkState, ev(CoreEvents.HTTP_REQUEST_STARTED));
        expect(a.pendingHttp).toBe(1);
        const b = networkReducer(a, ev(CoreEvents.HTTP_REQUEST_STARTED));
        expect(b.pendingHttp).toBe(2);
        const c = networkReducer(b, ev(CoreEvents.HTTP_REQUEST_SUCCEEDED));
        expect(c.pendingHttp).toBe(1);
        const d = networkReducer(c, ev(CoreEvents.HTTP_REQUEST_FAILED));
        expect(d.pendingHttp).toBe(0);
        const e = networkReducer(d, ev(CoreEvents.HTTP_REQUEST_FAILED));
        expect(e.pendingHttp).toBe(0); // не уходит в минус
    });
});
