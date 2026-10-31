import { describe, it, expect, beforeEach, afterEach } from 'vitest';
import { createNetworkEffect } from '@platform/lib/events/effects/network.effect.js';
import { CoreEvents } from '@platform/lib/events/contract.js';
import { installDomShim } from '../../helpers/dom-shim.js';
import { buildCtx } from '../../helpers/bus-fixtures.js';

let dom;
beforeEach(() => { dom = installDomShim(); });
afterEach(() => dom.uninstall());

const ev = (type, payload = null) => ({ id: `id_${type}`, type, payload, meta: { ts: 0, source: 'system' } });

describe('networkEffect', () => {
    it('не реагирует пока не пришёл APP_BOOTSTRAP_STARTED', async () => {
        const dispatched = [];
        await createNetworkEffect()(ev('foo/bar/baz'), buildCtx(() => ({}), dispatched));
        expect(dispatched).toHaveLength(0);
    });

    it('навешивает window listeners online/offline', async () => {
        const dispatched = [];
        await createNetworkEffect()(ev(CoreEvents.APP_BOOTSTRAP_STARTED), buildCtx(() => ({}), dispatched));
        dom.fireWindowEvent('online');
        dom.fireWindowEvent('offline');
        const types = dispatched.map((d) => d.type);
        expect(types).toContain(CoreEvents.NETWORK_ONLINE);
        expect(types).toContain(CoreEvents.NETWORK_OFFLINE);
    });

    it('повторный bootstrap не привязывает дважды', async () => {
        const dispatched = [];
        const effect = createNetworkEffect();
        await effect(ev(CoreEvents.APP_BOOTSTRAP_STARTED), buildCtx(() => ({}), dispatched));
        await effect(ev(CoreEvents.APP_BOOTSTRAP_STARTED), buildCtx(() => ({}), dispatched));
        dom.fireWindowEvent('online');
        const onlineCount = dispatched.filter((d) => d.type === CoreEvents.NETWORK_ONLINE).length;
        expect(onlineCount).toBe(1);
    });
});
