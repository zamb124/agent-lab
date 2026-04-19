/**
 * Models — список доступных LLM-моделей (по провайдеру).
 * REST: `apps/flows/src/api/registry.py` (`/api/v1/registry/models/values`).
 */

import { createAsyncOp } from '@platform/lib/events/index.js';
import { httpRequest } from '@platform/lib/events/http.js';

export const modelsListOp = createAsyncOp({
    name: 'flows/models_list',
    silent: true,
    restMirror: { method: 'GET', path: '/flows/api/v1/registry/models/values' },
    request: async ({ payload }) => {
        const params = new URLSearchParams();
        if (payload && typeof payload === 'object' && typeof payload.provider === 'string' && payload.provider.length > 0) {
            params.append('provider', payload.provider);
        }
        const qs = params.toString();
        return httpRequest({
            method: 'GET',
            url: `/flows/api/v1/registry/models/values${qs ? '?' + qs : ''}`,
        });
    },
});
