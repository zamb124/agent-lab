/**
 * История версий переменной компании (offset-пагинация) — `secrets/variables/versions_requested`.
 */

import { createAsyncOp } from '@platform/lib/events/index.js';
import { isPlainRecord } from '@platform/lib/events/payload.js';
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
        const payload = event.payload;
        const page = isPlainRecord(payload) ? payload.result : undefined;
        if (!isPlainRecord(page) || !Array.isArray(page.items)) {
            throw new Error('secrets/variable_versions_load: OffsetPage result required');
        }
        const items = [];
        for (const entry of page.items) {
            items.push(mapPlatformVariable(entry));
        }
        return { ...state, lastResult: { ...page, items } };
    },
});

declare module '@platform/lib/events/factory-registry.js' {
    interface PlatformFactoryRegistry {
        'secrets/variable_versions_load': typeof secretsVariableVersionsLoadOp;
    }
}
