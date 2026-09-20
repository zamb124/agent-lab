/**
 * Models — capability-specific список доступных LLM-моделей (по провайдеру).
 * REST: `apps/flows/src/api/v1/registry.py` (`/api/v1/registry/models/values`).
 */

import { createAsyncOp } from '@platform/lib/events/index.js';

export const modelsListOp = createAsyncOp({
    name: 'flows/models_list',
    silent: true,
    transport: 'ws',
    wsTimeoutMs: 15_000,
    commandType: 'flows/registry/models_list_requested',
    restMirror: { method: 'GET', path: '/flows/api/v1/registry/models/values' },
});
