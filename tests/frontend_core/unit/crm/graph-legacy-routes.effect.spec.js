import { describe, it, expect } from 'vitest';
import { CoreEvents } from '@platform/lib/events/contract.js';
import { createCrmGraphLegacyRoutesEffect } from '../../../../apps/crm/ui/events/crm-graph-legacy-routes.effect.js';
import { buildCtx } from '../../helpers/bus-fixtures.js';

const ev = (type, payload = null) => ({ id: `id_${type}`, type, payload, meta: { ts: 0, source: 'test' } });

describe('createCrmGraphLegacyRoutesEffect', () => {
    it('ROUTER_NOT_FOUND /crm/mindmap -> NAVIGATE graph with view=mindmap', async () => {
        const dispatched = [];
        const fx = createCrmGraphLegacyRoutesEffect();
        await fx(
            ev(CoreEvents.ROUTER_NOT_FOUND, { pathname: '/crm/mindmap' }),
            buildCtx(() => ({}), dispatched),
        );
        const nav = dispatched.find((d) => d.type === CoreEvents.ROUTER_NAVIGATE_REQUESTED);
        expect(nav).toBeTruthy();
        expect(nav.payload.routeKey).toBe('graph');
        expect(nav.payload.replace).toBe(true);
        expect(nav.payload.search).toContain('view=mindmap');
        expect(nav.payload.search.includes('root=')).toBe(false);
    });

    it('ROUTER_NOT_FOUND /crm/mindmap/:id encodes root', async () => {
        const dispatched = [];
        const fx = createCrmGraphLegacyRoutesEffect();
        await fx(
            ev(CoreEvents.ROUTER_NOT_FOUND, { pathname: '/crm/mindmap/ent%3Aabc' }),
            buildCtx(() => ({}), dispatched),
        );
        const nav = dispatched.find((d) => d.type === CoreEvents.ROUTER_NAVIGATE_REQUESTED);
        expect(nav.payload.search).toContain('root=');
        expect(nav.payload.search).toContain('view=mindmap');
    });

    it('ignores other paths', async () => {
        const dispatched = [];
        const fx = createCrmGraphLegacyRoutesEffect();
        await fx(
            ev(CoreEvents.ROUTER_NOT_FOUND, { pathname: '/crm/other' }),
            buildCtx(() => ({}), dispatched),
        );
        expect(dispatched.length).toBe(0);
    });
});
