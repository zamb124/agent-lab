/**
 * Спецификация Flow UI для редактора интерфейса: JSON Schema грамматики блоков,
 * галерея шаблонов и AI-помощник (structured output по той же грамматике).
 */

import { createAsyncOp } from '@platform/lib/events/index.js';

export const flowUiSchemaOp = createAsyncOp({
    name: 'flows/flow_ui_schema',
    silent: true,
    transport: 'ws',
    wsTimeoutMs: 15_000,
    commandType: 'flows/flow_ui/schema_requested',
    restMirror: { method: 'GET', path: '/flows/api/v1/flow-ui/schema' },
});

export const flowUiTemplatesOp = createAsyncOp({
    name: 'flows/flow_ui_templates',
    silent: true,
    transport: 'ws',
    wsTimeoutMs: 15_000,
    commandType: 'flows/flow_ui/templates_requested',
    restMirror: { method: 'GET', path: '/flows/api/v1/flow-ui/templates' },
});

/**
 * ``{ flow_id, branch_id, instruction, document, page_id, block_id | null }`` →
 * ``{ scope: 'page' | 'block', page | blocks }``: новая страница или замена выбранного блока.
 */
export const flowUiAssistOp = createAsyncOp({
    name: 'flows/flow_ui_assist',
    successToastKey: 'flows:interface_editor.assist_applied',
    errorToastKey: 'flows:interface_editor.assist_error',
    transport: 'ws',
    wsTimeoutMs: 60_000,
    commandType: 'flows/flow_ui/assist_requested',
    restMirror: { method: 'POST', path: '/flows/api/v1/flow-ui/assist' },
});
