/**
 * Редирект устаревших URL `/crm/mindmap` и `/crm/mindmap/:id` на единый graph workspace.
 */

import { CoreEvents } from '@platform/lib/events/contract.js';
import { buildGraphWorkspaceSearch } from '../utils/graph-view-mode.js';

export function createCrmGraphLegacyRoutesEffect() {
    return async function crmGraphLegacyRoutesEffect(event, ctx) {
        if (event.type !== CoreEvents.ROUTER_NOT_FOUND) {
            return;
        }
        const p = event.payload;
        if (!p || typeof p !== 'object') {
            return;
        }
        const pathname = typeof p.pathname === 'string' ? p.pathname : '';
        if (!pathname.startsWith('/crm/mindmap')) {
            return;
        }
        const tail = pathname.slice('/crm/mindmap'.length);
        let root = null;
        if (tail.startsWith('/')) {
            const seg = tail.slice(1).split('/')[0];
            if (typeof seg === 'string' && seg.length > 0) {
                root = decodeURIComponent(seg);
            }
        }
        const search = buildGraphWorkspaceSearch({
            view: 'mindmap',
            root,
            depth: null,
            query: '',
        });
        ctx.dispatch(
            CoreEvents.ROUTER_NAVIGATE_REQUESTED,
            {
                routeKey: 'graph',
                params: {},
                search,
                replace: true,
            },
            { source: 'system' },
        );
    };
}
