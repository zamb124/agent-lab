import { describe, it, expect } from 'vitest';
import { pwaReducer, initialPwaState } from '@platform/lib/events/reducers/pwa.js';
import { CoreEvents } from '@platform/lib/events/contract.js';
import { PWA_EVENTS } from '@platform/lib/events/effects/pwa.effect.js';

const ev = (type, payload = null) => ({ id: `id_${type}`, type, payload, meta: { ts: 0, source: 'local' } });

describe('pwaReducer', () => {
    it('initial', () => {
        expect(initialPwaState.pushPermission).toBe('default');
        expect(initialPwaState.pushRegistered).toBe(false);
        expect(initialPwaState.installed).toBe(false);
    });

    it('PWA_PUSH_PERMISSION_REQUESTED обновляет permission', () => {
        const next = pwaReducer(initialPwaState, ev(CoreEvents.PWA_PUSH_PERMISSION_REQUESTED, { permission: 'granted' }));
        expect(next.pushPermission).toBe('granted');
    });

    it('PWA_PUSH_PERMISSION_REQUESTED невалидный perm → no-op', () => {
        const next = pwaReducer(initialPwaState, ev(CoreEvents.PWA_PUSH_PERMISSION_REQUESTED, { permission: 'maybe' }));
        expect(next).toBe(initialPwaState);
    });

    it('PWA_PUSH_REGISTERED ставит endpoint', () => {
        const next = pwaReducer(initialPwaState, ev(CoreEvents.PWA_PUSH_REGISTERED, { endpoint: 'https://example.com/push' }));
        expect(next.pushRegistered).toBe(true);
        expect(next.pushEndpoint).toBe('https://example.com/push');
    });

    it('PUSH_UNSUBSCRIBED обнуляет', () => {
        const seeded = pwaReducer(initialPwaState, ev(CoreEvents.PWA_PUSH_REGISTERED, { endpoint: 'x' }));
        const next = pwaReducer(seeded, ev(PWA_EVENTS.PUSH_UNSUBSCRIBED));
        expect(next.pushRegistered).toBe(false);
        expect(next.pushEndpoint).toBeNull();
    });

    it('PWA_INSTALL_AVAILABLE и PWA_INSTALLED', () => {
        const a = pwaReducer(initialPwaState, ev(CoreEvents.PWA_INSTALL_AVAILABLE));
        expect(a.installAvailable).toBe(true);
        const b = pwaReducer(a, ev(CoreEvents.PWA_INSTALLED));
        expect(b.installed).toBe(true);
        expect(b.installAvailable).toBe(false);
    });

    it('PWA_UPDATE_AVAILABLE', () => {
        const next = pwaReducer(initialPwaState, ev(CoreEvents.PWA_UPDATE_AVAILABLE));
        expect(next.updateAvailable).toBe(true);
    });

    it('DEPLOYMENT_VERSION_LOADED', () => {
        const next = pwaReducer(initialPwaState, ev(PWA_EVENTS.DEPLOYMENT_VERSION_LOADED, { version: 'abc123' }));
        expect(next.deploymentVersion).toBe('abc123');
    });
});
