/**
 * Code — служебные операции для редактора (autocomplete, docs, validate, execute, source).
 * REST: `apps/flows/src/api/v1/code.py`.
 *
 * Все операции — `silent: true` (внутренний инструментарий редактора, тосты не нужны).
 */

import { createAsyncOp } from '@platform/lib/events/index.js';
import { httpRequest } from '@platform/lib/events/http.js';

export function buildCodeQueryUrl(path, payload) {
    const query = payload && typeof payload === 'object' ? payload : {};
    const params = new URLSearchParams();
    for (const [k, v] of Object.entries(query)) {
        if (v === null || v === undefined) continue;
        params.append(k, String(v));
    }
    const qs = params.toString();
    return `${path}${qs ? `?${qs}` : ''}`;
}

export const codeCompletionsOp = createAsyncOp({
    name: 'flows/code_completions',
    silent: true,
    restMirror: { method: 'GET', path: '/flows/api/v1/code/completions' },
    request: async ({ payload }) => {
        return httpRequest({
            method: 'GET',
            url: buildCodeQueryUrl('/flows/api/v1/code/completions', payload),
        });
    },
});

export const codeDocumentationOp = createAsyncOp({
    name: 'flows/code_documentation',
    silent: true,
    restMirror: { method: 'GET', path: '/flows/api/v1/code/documentation' },
    request: async ({ payload }) => {
        return httpRequest({
            method: 'GET',
            url: buildCodeQueryUrl('/flows/api/v1/code/documentation', payload),
        });
    },
});

export const codeTemplatesOp = createAsyncOp({
    name: 'flows/code_templates',
    silent: true,
    restMirror: { method: 'GET', path: '/flows/api/v1/code/templates' },
    request: async ({ payload }) => {
        return httpRequest({
            method: 'GET',
            url: buildCodeQueryUrl('/flows/api/v1/code/templates', payload),
        });
    },
});

export const codeEditorStateOp = createAsyncOp({
    name: 'flows/code_editor_state',
    silent: true,
    restMirror: { method: 'GET', path: '/flows/api/v1/code/editor-state' },
    request: async ({ payload }) => {
        if (!payload || typeof payload.flow_id !== 'string' || payload.flow_id.length === 0) {
            throw new Error('codeEditorStateOp: { flow_id, branch_id? } required');
        }
        const params = new URLSearchParams({
            flow_id: payload.flow_id,
            branch_id: typeof payload.branch_id === 'string' && payload.branch_id.length > 0 ? payload.branch_id : 'default',
        });
        return httpRequest({
            method: 'GET',
            url: `/flows/api/v1/code/editor-state?${params.toString()}`,
        });
    },
});

export const codeSourceOp = createAsyncOp({
    name: 'flows/code_source',
    silent: true,
    restMirror: { method: 'GET', path: '/flows/api/v1/code/source' },
    request: async ({ payload }) => {
        if (!payload || typeof payload !== 'object') {
            throw new Error('codeSourceOp: payload required');
        }
        const params = new URLSearchParams();
        for (const [k, v] of Object.entries(payload)) {
            if (v === null || v === undefined) continue;
            params.append(k, String(v));
        }
        return httpRequest({
            method: 'GET',
            url: `/flows/api/v1/code/source${params.toString() ? '?' + params.toString() : ''}`,
        });
    },
});

export const codeFlowFunctionsOp = createAsyncOp({
    name: 'flows/code_flow_functions',
    silent: true,
    restMirror: { method: 'GET', path: '/flows/api/v1/code/flow-functions' },
    request: async () => {
        return httpRequest({ method: 'GET', url: '/flows/api/v1/code/flow-functions' });
    },
});

export const codeToolSourceOp = createAsyncOp({
    name: 'flows/code_tool_source',
    silent: true,
    restMirror: { method: 'GET', path: '/flows/api/v1/code/tool-source' },
    request: async ({ payload }) => {
        if (!payload || typeof payload !== 'object') {
            throw new Error('codeToolSourceOp: payload object required');
        }
        const toolPath =
            typeof payload.tool_path === 'string' && payload.tool_path.length > 0
                ? payload.tool_path
                : typeof payload.tool_id === 'string' && payload.tool_id.length > 0
                  ? payload.tool_id
                  : null;
        if (toolPath === null) {
            throw new Error('codeToolSourceOp: tool_path (or tool_id as module path) required');
        }
        const params = new URLSearchParams({ tool_path: toolPath });
        return httpRequest({
            method: 'GET',
            url: `/flows/api/v1/code/tool-source?${params.toString()}`,
        });
    },
});

export const codeParseSignatureOp = createAsyncOp({
    name: 'flows/code_parse_signature',
    silent: true,
    restMirror: { method: 'POST', path: '/flows/api/v1/code/parse-signature' },
    request: async ({ payload }) => {
        if (!payload || typeof payload !== 'object') {
            throw new Error('codeParseSignatureOp: payload required');
        }
        return httpRequest({
            method: 'POST',
            url: '/flows/api/v1/code/parse-signature',
            body: payload,
        });
    },
});

export const codeValidateOp = createAsyncOp({
    name: 'flows/code_validate',
    silent: true,
    restMirror: { method: 'POST', path: '/flows/api/v1/code/validate' },
    request: async ({ payload }) => {
        if (!payload || typeof payload !== 'object') {
            throw new Error('codeValidateOp: payload required');
        }
        return httpRequest({
            method: 'POST',
            url: '/flows/api/v1/code/validate',
            body: payload,
        });
    },
});

export const codeExecuteOp = createAsyncOp({
    name: 'flows/code_execute',
    silent: true,
    restMirror: { method: 'POST', path: '/flows/api/v1/code/execute' },
    request: async ({ payload }) => {
        if (!payload || typeof payload !== 'object') {
            throw new Error('codeExecuteOp: payload required');
        }
        return httpRequest({
            method: 'POST',
            url: '/flows/api/v1/code/execute',
            body: payload,
        });
    },
});
