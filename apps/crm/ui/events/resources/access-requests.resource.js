/**
 * Access Requests — запросы на доступ к чужим сущностям/namespace.
 *
 * Backend (`/crm/api/v1/access-requests`):
 *   GET  /                 → OffsetPage[AccessRequestResponse]
 *   GET  /{access_request_id}     → AccessRequestResponse
 *   POST /                 → AccessRequestResponse
 *   PUT  /{access_request_id}     → AccessRequestResponse
 *
 * Update payload = { access_request_id, status }.
 */

import {
    createResourceCollection,
    createAsyncOp,
} from '@platform/lib/events/index.js';

export const accessRequestsResource = createResourceCollection({
    name: 'crm/access_requests',
    baseUrl: '/crm/api/v1/access-requests',
    idField: 'access_request_id',
    operations: ['list', 'get', 'create'],
    transport: 'ws',
    wsTimeoutMs: 8_000,
    listQuery: (payload) => {
        const query = { limit: 100, offset: 0 };
        if (payload && typeof payload === 'object') {
            if (typeof payload.status === 'string' && payload.status.length > 0) {
                query.status = payload.status;
            }
            if (typeof payload.limit === 'number' && payload.limit > 0) query.limit = payload.limit;
            if (typeof payload.offset === 'number' && payload.offset >= 0) query.offset = payload.offset;
        }
        return query;
    },
    toastKeys: {
        create: 'crm:toast.access_request.created',
    },
});

export const accessRequestUpdateOp = createAsyncOp({
    name: 'crm/access_request_update',
    successToastKey: 'crm:toast.access_request.updated',
    errorToastKey: 'crm:toast.access_request.update_failed',
    transport: 'ws',
    wsTimeoutMs: 8_000,
    commandType: 'crm/access_requests/update_requested',
    restMirror: { method: 'PUT', path: '/crm/api/v1/access-requests/:access_request_id' },
});
