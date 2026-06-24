/**
 * Редирект устаревшего URL `/documents/catalogs` на explorer (`documents_list`).
 */

import { CoreEvents } from '@platform/lib/events/contract.js';

export function createOfficeCatalogsLegacyRoutesEffect() {
    return async function officeCatalogsLegacyRoutesEffect(event, ctx) {
        if (event.type !== CoreEvents.ROUTER_ROUTE_CHANGED) {
            return;
        }
        const payload = event.payload;
        if (!payload || typeof payload !== 'object') {
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
