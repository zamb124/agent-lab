/**
 * Tools — реестр inline tool'ов flow'ов.
 * REST: `apps/flows/src/api/v1/tools.py`.
 */

import { createResourceCollection, createAsyncOp } from '@platform/lib/events/index.js';

const toolItemUrl = (id: string | number) => `/flows/api/v1/tools/${encodeURIComponent(id)}`;

export const toolsResource = createResourceCollection({
    name: 'flows/tools',
    baseUrl: '/flows/api/v1/tools/',
    idField: 'tool_id',
    buildItemUrl: toolItemUrl,
    transport: 'ws',
    wsTimeoutMs: 15_000,
    restMirror: {
        list: { method: 'GET', path: '/flows/api/v1/tools/' },
        get: { method: 'GET', path: '/flows/api/v1/tools/:tool_id' },
        create: { method: 'POST', path: '/flows/api/v1/tools/' },
        remove: { method: 'DELETE', path: '/flows/api/v1/tools/:tool_id' },
    },
    operations: ['list', 'get', 'create', 'remove'],
    toastKeys: {
        create: 'flows:toast.tool_created',
        create_error: 'flows:toast.tool_create_error',
        remove: 'flows:toast.tool_removed',
        remove_error: 'flows:toast.tool_remove_error',
    },
});

export const toolsAllOp = createAsyncOp({
    name: 'flows/tools_all',
    silent: true,
    transport: 'ws',
    wsTimeoutMs: 15_000,
    commandType: 'flows/tools/list_all_requested',
    restMirror: { method: 'GET', path: '/flows/api/v1/tools/all' },
});

declare module '@platform/lib/events/factory-registry.js' {
    interface PlatformFactoryRegistry {
        'flows/tools': typeof toolsResource;
        'flows/tools_all': typeof toolsAllOp;
    }
}
