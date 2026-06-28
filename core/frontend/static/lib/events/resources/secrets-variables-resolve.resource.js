/**
 * Preview effective company variables for executor context.
 */

import { createAsyncOp } from '@platform/lib/events/index.js';
import { httpRequest } from '@platform/lib/events/http.js';

export const secretsVariablesResolveOp = createAsyncOp({
    name: 'secrets/variables_resolve',
    silent: true,
    restMirror: { method: 'POST', path: '/secrets/api/v1/variables/resolve' },
    request: async ({ payload }) => {
        if (!payload || typeof payload !== 'object') {
            throw new Error('secrets/variables_resolve: payload required');
        }
        return httpRequest({
            method: 'POST',
            url: '/secrets/api/v1/variables/resolve',
            body: payload,
        });
    },
});
