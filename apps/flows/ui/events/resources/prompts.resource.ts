/**
 * Preview-рендер шаблона промпта (LLM node editor).
 * REST: `apps/flows/src/api/v1/prompts.py`.
 */

import { createAsyncOp } from '@platform/lib/events/index.js';

export const promptRenderOp = createAsyncOp({
    name: 'flows/prompt_render',
    silent: true,
    transport: 'ws',
    wsTimeoutMs: 15_000,
    commandType: 'flows/prompts/render_requested',
    restMirror: { method: 'POST', path: '/flows/api/v1/prompts/render' },
});

declare module '@platform/lib/events/factory-registry.js' {
    interface PlatformFactoryRegistry {
        'flows/prompt_render': typeof promptRenderOp;
    }
}
