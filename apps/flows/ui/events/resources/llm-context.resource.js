/**
 * Parent LLM context resolve — platform → company → resource (без node).
 * Для placeholders «Наследовать (…)» в platform-llm-context-editor.
 */

import { createAsyncOp } from '@platform/lib/events/index.js';
import { httpRequest } from '@platform/lib/events/http.js';

export const llmContextResolveParentOp = createAsyncOp({
    name: 'flows/llm_context_resolve_parent',
    silent: true,
    transport: 'http',
    restMirror: { method: 'POST', path: '/flows/api/v1/llm-context/resolve-parent' },
    request: async ({ payload }) => {
        if (!payload || typeof payload !== 'object') {
            throw new Error('llmContextResolveParentOp: payload required');
        }
        return httpRequest({
            method: 'POST',
            url: '/flows/api/v1/llm-context/resolve-parent',
            body: payload,
        });
    },
});
