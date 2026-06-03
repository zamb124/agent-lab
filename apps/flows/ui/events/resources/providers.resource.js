/**
 * Providers — capability-specific список настроенных LLM-провайдеров из backend AI catalog.
 * REST: `apps/flows/src/api/registry.py` (`/api/v1/registry/providers/values`).
 */

import { createAsyncOp } from '@platform/lib/events/index.js';
import { httpRequest } from '@platform/lib/events/http.js';

export const providersListOp = createAsyncOp({
    name: 'flows/providers_list',
    silent: true,
    restMirror: { method: 'GET', path: '/flows/api/v1/registry/providers/values' },
    request: async ({ payload }) => {
        const params = new URLSearchParams();
        if (payload && typeof payload === 'object' && typeof payload.capability === 'string' && payload.capability.length > 0) {
            params.append('capability', payload.capability);
        }
        const qs = params.toString();
        return httpRequest({
            method: 'GET',
            url: `/flows/api/v1/registry/providers/values${qs ? '?' + qs : ''}`,
        });
    },
});
