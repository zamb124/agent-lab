/**
 * Access Requests — запросы на доступ к чужим сущностям/namespace.
 *
 * Backend (`/crm/api/v1/access-requests`):
 *   GET  /                 → OffsetPage[AccessRequestResponse]
 *   GET  /{request_id}     → AccessRequestResponse
 *   POST /                 → AccessRequestResponse  (create)
 *   PUT  /{request_id}     → AccessRequestResponse  (approve/reject через PUT)
 *
 * `update` отдельным `accessRequestUpdateOp` (PUT).
 */

import {
    createResourceCollection,
    createAsyncOp,
} from '@platform/lib/events/index.js';
import { httpRequest } from '@platform/lib/events/http.js';

export const accessRequestsResource = createResourceCollection({
    name: 'crm/access_requests',
    baseUrl: '/crm/api/v1/access-requests',
    idField: 'request_id',
    operations: ['list', 'get', 'create'],
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
    request: async ({ payload }) => {
        if (!payload || typeof payload.request_id !== 'string' || !payload.body) {
            throw new Error('accessRequestUpdateOp: { request_id, body } required');
        }
        return await httpRequest({
            method: 'PUT',
            url: `/crm/api/v1/access-requests/${encodeURIComponent(payload.request_id)}`,
            body: payload.body,
        });
    },
});
