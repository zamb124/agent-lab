/**
 * Каталог нод — каталог пользовательских кастом-нод компании.
 * REST: `apps/flows/src/api/v1/nodes.py`.
 */

import { createResourceCollection, createAsyncOp } from '@platform/lib/events/index.js';
import { httpRequest } from '@platform/lib/events/http.js';

export const nodesCatalogResource = createResourceCollection({
    name: 'flows/nodes_catalog',
    baseUrl: '/flows/api/v1/nodes',
    idField: 'node_id',
    operations: ['list', 'get', 'create', 'remove'],
    toastKeys: {
        create: 'flows:toast.custom_node_created',
        create_error: 'flows:toast.custom_node_create_error',
        remove: 'flows:toast.custom_node_removed',
        remove_error: 'flows:toast.custom_node_remove_error',
    },
});

// Backend требует PUT.
export const nodeCatalogUpdateOp = createAsyncOp({
    name: 'flows/nodes_catalog_update',
    successToastKey: 'flows:toast.custom_node_updated',
    errorToastKey: 'flows:toast.custom_node_update_error',
    restMirror: { method: 'PUT', path: '/flows/api/v1/nodes/{node_id}' },
    request: async ({ payload }) => {
        if (!payload || typeof payload.node_id !== 'string' || !payload.body) {
            throw new Error('nodeCatalogUpdateOp: { node_id, body } required');
        }
        return httpRequest({
            method: 'PUT',
            url: `/flows/api/v1/nodes/${encodeURIComponent(payload.node_id)}`,
            body: payload.body,
        });
    },
});
