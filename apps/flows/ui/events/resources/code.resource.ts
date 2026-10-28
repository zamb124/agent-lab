/**
 * Code — служебные операции для редактора (docs, validate, execute, source).
 * LSP session — HTTP bootstrap (JSON-RPC кадры идут отдельным WS, не command-router).
 */

import { createAsyncOp } from '@platform/lib/events/index.js';
import { httpRequest } from '@platform/lib/events/http.js';

export const codeLspSessionOp = createAsyncOp({
    name: 'flows/code_lsp_session',
    silent: true,
    restMirror: { method: 'POST', path: '/flows/api/v1/code/lsp/session' },
    request: async ({ payload }) => {
        if (!payload || typeof payload !== 'object') {
            throw new Error('codeLspSessionOp: payload required');
        }
        return httpRequest({
            method: 'POST',
            url: '/flows/api/v1/code/lsp/session',
            body: payload,
        });
    },
});

export const codeDocumentationOp = createAsyncOp({
    name: 'flows/code_documentation',
    silent: true,
    transport: 'ws',
    commandType: 'flows/code/documentation_requested',
    restMirror: { method: 'GET', path: '/flows/api/v1/code/documentation' },
    wsTimeoutMs: 20000,
});

export const codeTemplatesOp = createAsyncOp({
    name: 'flows/code_templates',
    silent: true,
    transport: 'ws',
    commandType: 'flows/code/templates_requested',
    restMirror: { method: 'GET', path: '/flows/api/v1/code/templates' },
    wsTimeoutMs: 20000,
});

export const codeEditorStateOp = createAsyncOp({
    name: 'flows/code_editor_state',
    silent: true,
    transport: 'ws',
    commandType: 'flows/code/editor_state_requested',
    restMirror: { method: 'GET', path: '/flows/api/v1/code/editor-state' },
    wsTimeoutMs: 20000,
});

export const codeSourceOp = createAsyncOp({
    name: 'flows/code_source',
    silent: true,
    transport: 'ws',
    commandType: 'flows/code/source_requested',
    restMirror: { method: 'GET', path: '/flows/api/v1/code/source' },
    wsTimeoutMs: 20000,
});

export const codeFlowFunctionsOp = createAsyncOp({
    name: 'flows/code_flow_functions',
    silent: true,
    transport: 'ws',
    commandType: 'flows/code/flow_functions_requested',
    restMirror: { method: 'GET', path: '/flows/api/v1/code/flow-functions' },
    wsTimeoutMs: 20000,
});

export const codeToolSourceOp = createAsyncOp({
    name: 'flows/code_tool_source',
    silent: true,
    transport: 'ws',
    commandType: 'flows/code/tool_source_requested',
    restMirror: { method: 'GET', path: '/flows/api/v1/code/tool-source' },
    wsTimeoutMs: 20000,
});

export const codeParseSignatureOp = createAsyncOp({
    name: 'flows/code_parse_signature',
    silent: true,
    transport: 'ws',
    commandType: 'flows/code/parse_signature_requested',
    restMirror: { method: 'POST', path: '/flows/api/v1/code/parse-signature' },
    wsTimeoutMs: 20000,
});

export const codeValidateOp = createAsyncOp({
    name: 'flows/code_validate',
    silent: true,
    transport: 'ws',
    commandType: 'flows/code/validate_requested',
    restMirror: { method: 'POST', path: '/flows/api/v1/code/validate' },
    wsTimeoutMs: 30000,
});

export const codeExecuteOp = createAsyncOp({
    name: 'flows/code_execute',
    silent: true,
    transport: 'ws',
    commandType: 'flows/code/execute_requested',
    restMirror: { method: 'POST', path: '/flows/api/v1/code/execute' },
    wsTimeoutMs: 60000,
});

declare module '@platform/lib/events/factory-registry.js' {
    interface PlatformFactoryRegistry {
        'flows/code_lsp_session': typeof codeLspSessionOp;
        'flows/code_documentation': typeof codeDocumentationOp;
        'flows/code_templates': typeof codeTemplatesOp;
        'flows/code_editor_state': typeof codeEditorStateOp;
        'flows/code_source': typeof codeSourceOp;
        'flows/code_flow_functions': typeof codeFlowFunctionsOp;
        'flows/code_tool_source': typeof codeToolSourceOp;
        'flows/code_parse_signature': typeof codeParseSignatureOp;
        'flows/code_validate': typeof codeValidateOp;
        'flows/code_execute': typeof codeExecuteOp;
    }
}
