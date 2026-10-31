import { describe, it, expect, beforeEach, afterEach } from 'vitest';
import { createNetworkEffect } from '@platform/lib/events/effects/network.effect.js';
import { CoreEvents } from '@platform/lib/events/contract.js';
import { installDomShim } from '../../helpers/dom-shim.js';
import { buildCtx } from '../../helpers/bus-fixtures.js';

let dom: ReturnType<typeof installDomShim>;
beforeEach(() => { dom = installDomShim(); });
afterEach(() => dom.uninstall());

import { testEvent as ev } from '../../helpers/bus-fixtures.js';
import type { DispatchedRecord } from '../../helpers/bus-fixtures.js';

describe('networkEffect', () => {
    it('не реагирует пока не пришёл APP_BOOTSTRAP_STARTED', async () => {
        const dispatched: DispatchedRecord[] = [];
        await createNetworkEffect()(ev('foo/bar/baz'), buildCtx(() => ({}), dispatched));
        expect(dispatched).toHaveLength(0);
    });

    it('навешивает window listeners online/offline', async () => {
        const dispatched: DispatchedRecord[] = [];
        await createNetworkEffect()(ev(CoreEvents.APP_BOOTSTRAP_STARTED), buildCtx(() => ({}), dispatched));
        dom.fireWindowEvent('online');
        dom.fireWindowEvent('offline');
        const types = dispatched.map((d) => d.type);
        expect(types).toContain(CoreEvents.NETWORK_ONLINE);
        expect(types).toContain(CoreEvents.NETWORK_OFFLINE);
    });

    it('повторный bootstrap не привязывает дважды', async () => {
        const dispatched: DispatchedRecord[] = [];
        const effect = createNetworkEffect();
        await effect(ev(CoreEvents.APP_BOOTSTRAP_STARTED), buildCtx(() => ({}), dispatched));
        await effect(ev(CoreEvents.APP_BOOTSTRAP_STARTED), buildCtx(() => ({}), dispatched));
        dom.fireWindowEvent('online');
        const onlineCount = dispatched.filter((d) => d.type === CoreEvents.NETWORK_ONLINE).length;
        expect(onlineCount).toBe(1);
    });
});
