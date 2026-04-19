/**
 * Prompts — рендер шаблона (для preview в редакторе ноды LLM).
 * REST: `apps/flows/src/api/v1/prompts.py`.
 */

import { createAsyncOp } from '@platform/lib/events/index.js';
import { httpRequest } from '@platform/lib/events/http.js';

export const promptRenderOp = createAsyncOp({
    name: 'flows/prompt_render',
    silent: true,
    restMirror: { method: 'POST', path: '/flows/api/v1/prompts/render' },
    request: async ({ payload }) => {
        if (!payload || typeof payload !== 'object') {
            throw new Error('promptRenderOp: payload required');
        }
        return httpRequest({
            method: 'POST',
            url: '/flows/api/v1/prompts/render',
            body: payload,
        });
    },
});
