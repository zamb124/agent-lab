/**
 * Resources — глобальные ресурсы flow'ов (LLM, secret, code, http, files, prompt, rag, cache).
 * REST: `apps/flows/src/api/v1/resources.py`.
 */

import { createResourceCollection, createAsyncOp } from '@platform/lib/events/index.js';
import { httpRequest } from '@platform/lib/events/http.js';

export const resourcesBundleResource = createResourceCollection({
    name: 'flows/resources',
    baseUrl: '/flows/api/v1/resources',
    idField: 'resource_id',
    operations: ['list', 'get', 'create', 'remove'],
    toastKeys: {
        create: 'flows:toast.resource_created',
        create_error: 'flows:toast.resource_create_error',
        remove: 'flows:toast.resource_removed',
        remove_error: 'flows:toast.resource_remove_error',
    },
    listQuery: (payload) => {
        const query = {};
        if (payload && typeof payload === 'object' && typeof payload.type === 'string') {
            query.type = payload.type;
        }
        return query;
    },
});

// Backend требует PUT.
export const resourceUpdateOp = createAsyncOp({
    name: 'flows/resource_update',
    successToastKey: 'flows:toast.resource_updated',
    errorToastKey: 'flows:toast.resource_update_error',
    restMirror: { method: 'PUT', path: '/flows/api/v1/resources/{resource_id}' },
    request: async ({ payload }) => {
        if (!payload || typeof payload.resource_id !== 'string' || !payload.body) {
            throw new Error('resourceUpdateOp: { resource_id, body } required');
        }
        return httpRequest({
            method: 'PUT',
            url: `/flows/api/v1/resources/${encodeURIComponent(payload.resource_id)}`,
            body: payload.body,
        });
    },
});
