/**
 * Parent LLM context resolve — platform → company → resource (без node).
 * Для placeholders «Наследовать (…)» в platform-llm-context-editor.
 */

import { createAsyncOp } from '@platform/lib/events/index.js';

export const llmContextResolveParentOp = createAsyncOp({
    name: 'flows/llm_context_resolve_parent',
    silent: true,
    transport: 'ws',
    wsTimeoutMs: 15_000,
    commandType: 'flows/llm_context/resolve_parent_requested',
    restMirror: { method: 'POST', path: '/flows/api/v1/llm-context/resolve-parent' },
});
