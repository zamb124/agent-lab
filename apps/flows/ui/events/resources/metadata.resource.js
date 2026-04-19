/**
 * Node types и Resource types metadata — каталоги для палитры
 * `flows-node-types-sidebar` (drag-into-canvas).
 *
 * REST: `apps/flows/src/api/v1/metadata.py`.
 */

import { createAsyncOp } from '@platform/lib/events/index.js';
import { httpRequest } from '@platform/lib/events/http.js';

export const nodeTypesOp = createAsyncOp({
    name: 'flows/node_types',
    silent: true,
    restMirror: { method: 'GET', path: '/flows/api/v1/metadata/node-types' },
    request: async () => httpRequest({ method: 'GET', url: '/flows/api/v1/metadata/node-types' }),
});

export const resourceTypesOp = createAsyncOp({
    name: 'flows/resource_types',
    silent: true,
    restMirror: { method: 'GET', path: '/flows/api/v1/metadata/resource-types' },
    request: async () => httpRequest({ method: 'GET', url: '/flows/api/v1/metadata/resource-types' }),
});
