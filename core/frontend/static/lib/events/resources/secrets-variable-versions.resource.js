/**
 * История версий переменной компании (offset-пагинация) — `secrets/variables/versions_requested`.
 */

import { createAsyncOp } from '@platform/lib/events/index.js';
import { mapPlatformVariable } from './secrets-variables.resource.js';

export const secretsVariableVersionsLoadOp = createAsyncOp({
    name: 'secrets/variable_versions_load',
    silent: true,
    transport: 'ws',
    wsTimeoutMs: 8_000,
    commandType: 'secrets/variables/versions_requested',
    restMirror: { method: 'GET', path: '/secrets/api/v1/variables/:variable_key/versions' },
    extraReducer: (state, event, events) => {
        if (event.type !== events.SUCCEEDED) {
            return state;
        }
        const page = event.payload.result;
        if (!page || typeof page !== 'object' || !Array.isArray(page.items)) {
            throw new Error('secrets/variable_versions_load: OffsetPage result required');
        }
        return { ...state, lastResult: { ...page, items: page.items.map((item) => mapPlatformVariable(item)) } };
    },
});
