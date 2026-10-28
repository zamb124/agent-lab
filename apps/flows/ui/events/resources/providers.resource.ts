/**
 * Providers — capability-specific список настроенных LLM-провайдеров из backend AI catalog.
 * REST: `apps/flows/src/api/v1/registry.py` (`/api/v1/registry/providers/values`).
 */

import { createAsyncOp } from '@platform/lib/events/index.js';

export const providersListOp = createAsyncOp({
    name: 'flows/providers_list',
    silent: true,
    transport: 'ws',
    wsTimeoutMs: 15_000,
    commandType: 'flows/registry/providers_list_requested',
    restMirror: { method: 'GET', path: '/flows/api/v1/registry/providers/values' },
});

declare module '@platform/lib/events/factory-registry.js' {
    interface PlatformFactoryRegistry {
        'flows/providers_list': typeof providersListOp;
    }
}
