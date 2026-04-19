/**
 * Sessions — сессии чата (history по flow).
 * REST: `apps/flows/src/api/v1/sessions.py`.
 */

import { createResourceCollection, createAsyncOp } from '@platform/lib/events/index.js';
import { httpRequest } from '@platform/lib/events/http.js';

export const sessionsResource = createResourceCollection({
    name: 'flows/sessions',
    baseUrl: '/flows/api/v1/sessions',
    idField: 'session_id',
    operations: ['list', 'remove'],
    toastKeys: {
        remove: 'flows:toast.session_removed',
        remove_error: 'flows:toast.session_remove_error',
    },
    listQuery: (payload) => {
        const query = {};
        if (payload && typeof payload === 'object') {
            if (typeof payload.flow_id === 'string' && payload.flow_id.length > 0) {
                query.flow_id = payload.flow_id;
            }
            if (typeof payload.limit === 'number') query.limit = payload.limit;
            if (typeof payload.offset === 'number') query.offset = payload.offset;
        }
        return query;
    },
});

export const sessionStateOp = createAsyncOp({
    name: 'flows/session_state',
    silent: true,
    restMirror: { method: 'GET', path: '/flows/api/v1/tasks/state' },
    request: async ({ payload }) => {
        if (!payload || typeof payload.session_id !== 'string' || payload.session_id.length === 0) {
            throw new Error('sessionStateOp: { session_id } required');
        }
        const params = new URLSearchParams({ session_id: payload.session_id });
        return httpRequest({
            method: 'GET',
            url: `/flows/api/v1/tasks/state?${params.toString()}`,
        });
    },
});
