/**
 * Каталог нод — каталог пользовательских кастом-нод компании.
 * REST: `apps/flows/src/api/v1/nodes.py`.
 */

import { createResourceCollection } from '@platform/lib/events/index.js';

export const nodesCatalogResource = createResourceCollection({
    name: 'flows/nodes_catalog',
    baseUrl: '/flows/api/v1/nodes',
    idField: 'node_id',
    operations: ['list', 'get', 'create', 'update', 'remove'],
    transport: 'ws',
    wsTimeoutMs: 15_000,
    restMirror: {
        list: { method: 'GET', path: '/flows/api/v1/nodes' },
        get: { method: 'GET', path: '/flows/api/v1/nodes/:node_id' },
        create: { method: 'POST', path: '/flows/api/v1/nodes' },
        update: { method: 'PUT', path: '/flows/api/v1/nodes/:node_id' },
        remove: { method: 'DELETE', path: '/flows/api/v1/nodes/:node_id' },
    },
    toastKeys: {
        create: 'flows:toast.custom_node_created',
        create_error: 'flows:toast.custom_node_create_error',
        update: 'flows:toast.custom_node_updated',
        update_error: 'flows:toast.custom_node_update_error',
        remove: 'flows:toast.custom_node_removed',
        remove_error: 'flows:toast.custom_node_remove_error',
    },
});
