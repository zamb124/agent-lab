/**
 * Sessions — сессии чата (history по flow).
 * REST: `apps/flows/src/api/v1/sessions.py`.
 * Канон префикса: `FLOWS_PUBLIC_API_PREFIX` в `apps/flows/config.py` (`/flows/api/v1`).
 */

import { createResourceCollection, createAsyncOp } from '@platform/lib/events/index.js';
import { httpRequest } from '@platform/lib/events/http.js';

const FLOWS_API_V1 = '/flows/api/v1';
const SESSIONS_RESOURCE_BASE = `${FLOWS_API_V1}/sessions/`;

export const sessionsResource = createResourceCollection({
    name: 'flows/sessions',
    baseUrl: SESSIONS_RESOURCE_BASE,
    idField: 'session_id',
    buildItemUrl: (id) => `${FLOWS_API_V1}/sessions/${encodeURIComponent(id)}`,
    restMirror: {
        list: { method: 'GET', path: SESSIONS_RESOURCE_BASE },
        remove: { method: 'DELETE', path: `${FLOWS_API_V1}/sessions/{session_id}` },
    },
    operations: ['list', 'remove'],
    toastKeys: {
        remove: 'flows:toast.session_removed',
        remove_error: 'flows:toast.session_remove_error',
    },
    listQuery: (payload) => {
        const query = { limit: 200 };
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
    restMirror: { method: 'GET', path: `${FLOWS_API_V1}/tasks/state` },
    request: async ({ payload }) => {
        if (!payload || typeof payload.session_id !== 'string' || payload.session_id.length === 0) {
            throw new Error('sessionStateOp: { session_id } required');
        }
        const params = new URLSearchParams({ session_id: payload.session_id });
        return httpRequest({
            method: 'GET',
            url: `${FLOWS_API_V1}/tasks/state?${params.toString()}`,
        });
    },
});
