/**
 * Редирект устаревшего URL `/documents/catalogs` на explorer (`documents_list`).
 */

import { CoreEvents } from '@platform/lib/events/contract.js';
import type { PlatformEvent, EffectCtx } from '@platform/lib/events/contract.js';
import type { EventEffect } from '@platform/lib/events/bus.js';
import { isPlainRecord } from '@platform/lib/events/payload.js';

export function createOfficeCatalogsLegacyRoutesEffect(): EventEffect {
    return async function officeCatalogsLegacyRoutesEffect(event: PlatformEvent, ctx: EffectCtx) {
        if (event.type !== CoreEvents.ROUTER_ROUTE_CHANGED) {
            return;
        }
        const payload = event.payload;
        if (!isPlainRecord(payload)) {
            return;
        }
        const routeKey = typeof payload.routeKey === 'string' ? payload.routeKey : '';
        if (routeKey !== 'documents_catalogs') {
            return;
        }
        ctx.dispatch(
            CoreEvents.ROUTER_NAVIGATE_REQUESTED,
            {
                routeKey: 'documents_list',
                params: {},
                replace: true,
            },
            { source: 'system' },
        );
    };
}
