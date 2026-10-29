/**
 * Редирект устаревших URL `/crm/mindmap` и `/crm/mindmap/:id` на единый graph workspace.
 */

import { CoreEvents } from '@platform/lib/events/contract.js';
import type { EffectCtx, PlatformEvent } from '@platform/lib/events/contract.js';
import { isPlainRecord } from '@platform/lib/events/payload.js';
import { buildGraphWorkspaceSearch } from '../_helpers/graph-view-mode.js';

export function createCrmGraphLegacyRoutesEffect() {
    return async function crmGraphLegacyRoutesEffect(event: PlatformEvent, ctx: EffectCtx) {
        if (event.type !== CoreEvents.ROUTER_NOT_FOUND) {
            return;
        }
        const p = event.payload;
        if (!isPlainRecord(p)) {
            return;
        }
        const pathname = typeof p.pathname === 'string' ? p.pathname : '';
        if (!pathname.startsWith('/crm/mindmap')) {
            return;
        }
        const tail = pathname.slice('/crm/mindmap'.length);
        let root: string | null = null;
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
