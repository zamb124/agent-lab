/**
 * Resources — глобальные ресурсы flow'ов (LLM, llm_context, rag, files, data_table).
 * REST: `apps/flows/src/api/v1/resources.py`.
 */

import { createResourceCollection } from '@platform/lib/events/index.js';

export const resourcesBundleResource = createResourceCollection({
    name: 'flows/resources',
    baseUrl: '/flows/api/v1/resources',
    idField: 'resource_id',
    operations: ['list', 'get', 'create', 'update', 'remove'],
    transport: 'ws',
    wsTimeoutMs: 15_000,
    listFetchAllPages: true,
    restMirror: {
        list: { method: 'GET', path: '/flows/api/v1/resources' },
        get: { method: 'GET', path: '/flows/api/v1/resources/:resource_id' },
        create: { method: 'POST', path: '/flows/api/v1/resources' },
        update: { method: 'PUT', path: '/flows/api/v1/resources/:resource_id' },
        remove: { method: 'DELETE', path: '/flows/api/v1/resources/:resource_id' },
    },
    toastKeys: {
        create: 'flows:toast.resource_created',
        create_error: 'flows:toast.resource_create_error',
        update: 'flows:toast.resource_updated',
        update_error: 'flows:toast.resource_update_error',
        remove: 'flows:toast.resource_removed',
        remove_error: 'flows:toast.resource_remove_error',
    },
    listQuery: (payload) => {
        const query = { limit: 200, offset: 0 };
        if (payload && typeof payload === 'object' && typeof payload.type === 'string') {
            query.type = payload.type;
        }
        return query;
    },
});
