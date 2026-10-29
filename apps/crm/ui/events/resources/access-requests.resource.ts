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
    removeItem,
    upsertItem,
} from '@platform/lib/events/index.js';
import { isPlainRecord } from '@platform/lib/events/payload.js';

const ACCESS_REQUEST_UPDATE_SUCCEEDED = 'crm/access_request_update/succeeded';

export const accessRequestsResource = createResourceCollection({
    name: 'crm/access_requests',
    baseUrl: '/crm/api/v1/access-requests',
    idField: 'access_request_id',
    operations: ['list', 'get', 'create'],
    transport: 'ws',
    wsTimeoutMs: 8_000,
    listQuery: (payload) => {
        const query: Record<string, any> = { limit: 100, offset: 0 };
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
    // Решение по запросу: строка выпадает из списка, отфильтрованного по другому статусу.
    extraReducer: (state, event) => {
        if (event.type !== ACCESS_REQUEST_UPDATE_SUCCEEDED) {
            return state;
        }
        const payload = event.payload;
        if (!isPlainRecord(payload)) {
            throw new Error('crm/access_requests: update payload must be an object');
        }
        const request = payload.result;
        if (!isPlainRecord(request) || typeof request.access_request_id !== 'string') {
            return state;
        }
        const accessRequestId = request.access_request_id;
        const listQuery = state.lastListQuery;
        let listStatus: unknown;
        if (listQuery && listQuery.payload != null) {
            if (!isPlainRecord(listQuery.payload)) {
                throw new Error('crm/access_requests: list query payload must be an object');
            }
            listStatus = listQuery.payload.status;
        }
        if (typeof listStatus === 'string' && listStatus.length > 0 && request.status !== listStatus) {
            return removeItem(state, accessRequestId, 'access_request_id');
        }
        return upsertItem(state, request, 'access_request_id');
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

declare module '@platform/lib/events/factory-registry.js' {
    interface PlatformFactoryRegistry {
        'crm/access_requests': typeof accessRequestsResource;
        'crm/access_request_update': typeof accessRequestUpdateOp;
    }
}
