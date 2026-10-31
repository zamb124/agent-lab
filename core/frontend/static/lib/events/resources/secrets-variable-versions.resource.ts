/**
 * История версий переменной компании (offset-пагинация) — `secrets/variables/versions_requested`.
 */

import { createAsyncOp } from '@platform/lib/events/index.js';
import { isPlainRecord } from '@platform/lib/events/payload.js';
import { mapPlatformVariable } from './secrets-variables.resource.js';
import type { OffsetPage_PlatformVariable_ } from '../wire/secrets.gen.js';

/**
 * Страница версий после `mapPlatformVariable`: каркас OffsetPage,
 * items — view-форма, как в `secrets/variables`.
 */
type MappedVariablePage = Omit<OffsetPage_PlatformVariable_, 'items'> & {
    items: ReturnType<typeof mapPlatformVariable>[];
};

export const secretsVariableVersionsLoadOp = createAsyncOp<OffsetPage_PlatformVariable_ | MappedVariablePage>({
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
        if (
            !isPlainRecord(page)
            || !Array.isArray(page.items)
            || typeof page.total !== 'number'
            || typeof page.limit !== 'number'
            || typeof page.offset !== 'number'
        ) {
            throw new Error('secrets/variable_versions_load: OffsetPage result required');
        }
        const items = [];
        for (const entry of page.items) {
            items.push(mapPlatformVariable(entry));
        }
        const lastResult: MappedVariablePage = {
            total: page.total,
            limit: page.limit,
            offset: page.offset,
            items,
        };
        return { ...state, lastResult };
    },
});

declare module '@platform/lib/events/factory-registry.js' {
    interface PlatformFactoryRegistry {
        'secrets/variable_versions_load': typeof secretsVariableVersionsLoadOp;
    }
}
