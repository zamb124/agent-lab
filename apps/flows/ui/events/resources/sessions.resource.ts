/**
 * Сессии — сессии чата (history по flow).
 * REST: `apps/flows/src/api/v1/sessions.py`.
 * Канон префикса: `FLOWS_PUBLIC_API_PREFIX` в `apps/flows/config.py` (`/flows/api/v1`).
 */

import { createResourceCollection, createAsyncOp } from '@platform/lib/events/index.js';

const FLOWS_API_V1 = '/flows/api/v1';

export const sessionsResource = createResourceCollection({
    name: 'flows/sessions',
    baseUrl: '/flows/api/v1/sessions/',
    idField: 'session_id',
    buildItemUrl: (id) => `${FLOWS_API_V1}/sessions/${encodeURIComponent(id)}`,
    operations: ['list', 'remove'],
    transport: 'ws',
    wsTimeoutMs: 15_000,
    restMirror: {
        list: { method: 'GET', path: '/flows/api/v1/sessions/' },
        remove: { method: 'DELETE', path: '/flows/api/v1/sessions/:session_id' },
    },
    toastKeys: {
        remove: 'flows:toast.session_removed',
        remove_error: 'flows:toast.session_remove_error',
    },
    listQuery: (payload) => {
        const query: any = { limit: 200 };
        if (payload && typeof payload === 'object') {
            if (typeof payload.user_id === 'string' && payload.user_id.length > 0) {
                query.user_id = payload.user_id;
            }
            if (typeof payload.flow_id === 'string' && payload.flow_id.length > 0) {
                query.flow_id = payload.flow_id;
            }
            if (typeof payload.branch_id === 'string' && payload.branch_id.length > 0) {
                query.branch_id = payload.branch_id;
            }
            if (typeof payload.date_from === 'string' && payload.date_from.length > 0) {
                query.date_from = payload.date_from;
            }
            if (typeof payload.date_to === 'string' && payload.date_to.length > 0) {
                query.date_to = payload.date_to;
            }
            if (typeof payload.limit === 'number') {
                query.limit = payload.limit;
            }
            if (typeof payload.offset === 'number') {
                query.offset = payload.offset;
            }
        }
        return query;
    },
});

export const sessionStateOp = createAsyncOp({
    name: 'flows/session_state',
    silent: true,
    transport: 'ws',
    wsTimeoutMs: 15_000,
    commandType: 'flows/sessions/state_requested',
    restMirror: { method: 'GET', path: '/flows/api/v1/tasks/state' },
});

declare module '@platform/lib/events/factory-registry.js' {
    interface PlatformFactoryRegistry {
        'flows/sessions': typeof sessionsResource;
        'flows/session_state': typeof sessionStateOp;
    }
}
