/**
 * Эффективные переменные компании для контекста исполнителя — `secrets/variables/resolve_requested`.
 */

import { createAsyncOp } from '@platform/lib/events/index.js';
import type { VariableResolveResponse } from '../wire/secrets.gen.js';

export const secretsVariablesResolveOp = createAsyncOp<VariableResolveResponse>({
    name: 'secrets/variables_resolve',
    silent: true,
    transport: 'ws',
    wsTimeoutMs: 8_000,
    commandType: 'secrets/variables/resolve_requested',
    restMirror: { method: 'POST', path: '/secrets/api/v1/variables/resolve' },
});

declare module '@platform/lib/events/factory-registry.js' {
    interface PlatformFactoryRegistry {
        'secrets/variables_resolve': typeof secretsVariablesResolveOp;
    }
}
