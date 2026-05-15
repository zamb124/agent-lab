/**
 * Tools — реестр inline tool'ов flow'ов.
 * REST: `apps/flows/src/api/v1/tools.py`.
 */

import { createResourceCollection, createAsyncOp } from '@platform/lib/events/index.js';
import { httpRequest } from '@platform/lib/events/http.js';

const toolItemUrl = (id) => `/flows/api/v1/tools/${encodeURIComponent(id)}`;

export const toolsResource = createResourceCollection({
    name: 'flows/tools',
    baseUrl: '/flows/api/v1/tools/',
    idField: 'tool_id',
    buildItemUrl: toolItemUrl,
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
    restMirror: { method: 'GET', path: '/flows/api/v1/tools/all' },
    request: async ({ payload }) => {
        const src = payload && typeof payload === 'object' ? payload : {};
        const limit = typeof src.limit === 'number' && src.limit > 0 ? src.limit : 2000;
        const offset = typeof src.offset === 'number' && src.offset >= 0 ? src.offset : 0;
        const q = new URLSearchParams();
        q.set('limit', String(limit));
        q.set('offset', String(offset));
        return httpRequest({
            method: 'GET',
            url: `/flows/api/v1/tools/all?${q.toString()}`,
        });
    },
});
