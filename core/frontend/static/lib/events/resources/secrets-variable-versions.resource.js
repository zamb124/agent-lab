/**
 * Version history for a company variable (offset pagination).
 */

import { createAsyncOp } from '@platform/lib/events/index.js';
import { httpRequest } from '@platform/lib/events/http.js';
import { mapPlatformVariable } from './secrets-variables.resource.js';

export const secretsVariableVersionsLoadOp = createAsyncOp({
    name: 'secrets/variable_versions_load',
    silent: true,
    restMirror: { method: 'GET', path: '/secrets/api/v1/variables/:variable_key/versions' },
    request: async ({ payload }) => {
        if (!payload || typeof payload !== 'object') {
            throw new Error('secrets/variable_versions_load: payload required');
        }
        const variableKey = payload.variable_key;
        if (typeof variableKey !== 'string' || variableKey.trim() === '') {
            throw new Error('secrets/variable_versions_load: variable_key required');
        }
        const limit = typeof payload.limit === 'number' ? payload.limit : 50;
        const offset = typeof payload.offset === 'number' ? payload.offset : 0;
        const response = await httpRequest({
            method: 'GET',
            url: `/secrets/api/v1/variables/${encodeURIComponent(variableKey)}/versions?limit=${limit}&offset=${offset}`,
        });
        if (!response || typeof response !== 'object' || !Array.isArray(response.items)) {
            throw new Error('secrets/variable_versions_load: invalid response');
        }
        return {
            ...response,
            items: response.items.map((item) => mapPlatformVariable(item)),
        };
    },
});
