/**
 * Спецификация Flow UI для редактора интерфейса: JSON Schema грамматики блоков,
 * галерея шаблонов и AI-помощник (structured output по той же грамматике).
 */

import { createAsyncOp } from '@platform/lib/events/index.js';
import { httpRequest } from '@platform/lib/events/http.js';

export const flowUiSchemaOp = createAsyncOp({
    name: 'flows/flow_ui_schema',
    silent: true,
    transport: 'http',
    restMirror: { method: 'GET', path: '/flows/api/v1/flow-ui/schema' },
    request: async () => httpRequest({ method: 'GET', url: '/flows/api/v1/flow-ui/schema' }),
});

export const flowUiTemplatesOp = createAsyncOp({
    name: 'flows/flow_ui_templates',
    silent: true,
    transport: 'http',
    restMirror: { method: 'GET', path: '/flows/api/v1/flow-ui/templates' },
    request: async () => httpRequest({ method: 'GET', url: '/flows/api/v1/flow-ui/templates?limit=200&offset=0' }),
});

/**
 * ``{ flow_id, branch_id, instruction, document, page_id, block_id | null }`` →
 * ``{ scope: 'page' | 'block', page | blocks }``: новая страница или замена выбранного блока.
 */
export const flowUiAssistOp = createAsyncOp({
    name: 'flows/flow_ui_assist',
    successToastKey: 'flows:interface_editor.assist_applied',
    errorToastKey: 'flows:interface_editor.assist_error',
    transport: 'http',
    restMirror: { method: 'POST', path: '/flows/api/v1/flow-ui/assist' },
    request: async ({ payload }) => {
        if (!payload || typeof payload.flow_id !== 'string' || payload.flow_id === '') {
            throw new Error('flowUiAssistOp: flow_id required');
        }
        if (typeof payload.instruction !== 'string' || payload.instruction.trim() === '') {
            throw new Error('flowUiAssistOp: instruction required');
        }
        if (!payload.document || typeof payload.document !== 'object') {
            throw new Error('flowUiAssistOp: document required');
        }
        if (typeof payload.page_id !== 'string' || payload.page_id === '') {
            throw new Error('flowUiAssistOp: page_id required');
        }
        if (payload.block_id !== null && typeof payload.block_id !== 'string') {
            throw new Error('flowUiAssistOp: block_id must be string or null');
        }
        return httpRequest({
            method: 'POST',
            url: '/flows/api/v1/flow-ui/assist',
            body: {
                flow_id: payload.flow_id,
                branch_id: payload.branch_id,
                instruction: payload.instruction.trim(),
                document: payload.document,
                page_id: payload.page_id,
                block_id: payload.block_id,
            },
        });
    },
});
