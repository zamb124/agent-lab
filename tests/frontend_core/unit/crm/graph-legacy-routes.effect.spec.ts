import { describe, it, expect } from 'vitest';
import { CoreEvents } from '@platform/lib/events/contract.js';
import { createCrmGraphLegacyRoutesEffect } from '../../../../apps/crm/ui/events/crm-graph-legacy-routes.effect.js';
import { buildCtx, testEvent } from '../../helpers/bus-fixtures.js';
import type { DispatchedRecord } from '../../helpers/bus-fixtures.js';

const ev = testEvent;

interface NavPayload { routeKey: string; search: string; replace?: boolean }
function isNavPayload(p: unknown): p is NavPayload {
    return typeof p === 'object' && p !== null && 'routeKey' in p && 'search' in p;
}

describe('createCrmGraphLegacyRoutesEffect', () => {
    it('ROUTER_NOT_FOUND /crm/mindmap -> NAVIGATE graph with view=mindmap', async () => {
        const dispatched: DispatchedRecord[] = [];
        const fx = createCrmGraphLegacyRoutesEffect();
        await fx(
            ev(CoreEvents.ROUTER_NOT_FOUND, { pathname: '/crm/mindmap' }),
            buildCtx(() => ({}), dispatched),
        );
        const nav = dispatched.find((d) => d.type === CoreEvents.ROUTER_NAVIGATE_REQUESTED);
        const p = isNavPayload(nav?.payload) ? nav?.payload : null;
        if (p === null) throw new Error('NAVIGATE payload expected');
        expect(p.routeKey).toBe('graph');
        expect(p.replace).toBe(true);
        expect(p.search).toContain('view=mindmap');
        expect(p.search.includes('root=')).toBe(false);
    });

    it('ROUTER_NOT_FOUND /crm/mindmap/:id encodes root', async () => {
        const dispatched: DispatchedRecord[] = [];
        const fx = createCrmGraphLegacyRoutesEffect();
        await fx(
            ev(CoreEvents.ROUTER_NOT_FOUND, { pathname: '/crm/mindmap/ent%3Aabc' }),
            buildCtx(() => ({}), dispatched),
        );
        const nav = dispatched.find((d) => d.type === CoreEvents.ROUTER_NAVIGATE_REQUESTED);
        if (!isNavPayload(nav?.payload)) throw new Error('NAVIGATE payload expected');
        expect(nav?.payload.search).toContain('root=');
        expect(nav?.payload.search).toContain('view=mindmap');
    });

    it('ignores other paths', async () => {
        const dispatched: DispatchedRecord[] = [];
        const fx = createCrmGraphLegacyRoutesEffect();
        await fx(
            ev(CoreEvents.ROUTER_NOT_FOUND, { pathname: '/crm/other' }),
            buildCtx(() => ({}), dispatched),
        );
        expect(dispatched.length).toBe(0);
    });
});
