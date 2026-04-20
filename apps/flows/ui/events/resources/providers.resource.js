/**
 * Providers — список настроенных LLM-провайдеров (читается из conf.json на бэке).
 * REST: `apps/flows/src/api/registry.py` (`/api/v1/registry/providers/values`).
 */

import { createAsyncOp } from '@platform/lib/events/index.js';
import { httpRequest } from '@platform/lib/events/http.js';

export const providersListOp = createAsyncOp({
    name: 'flows/providers_list',
    silent: true,
    restMirror: { method: 'GET', path: '/flows/api/v1/registry/providers/values' },
    request: async () => httpRequest({
        method: 'GET',
        url: '/flows/api/v1/registry/providers/values',
    }),
});
