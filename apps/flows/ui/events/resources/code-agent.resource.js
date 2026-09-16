/**
 * Code agent: дерево исходников ноды и rebuild на ферме guest_runtime.
 */

import { createAsyncOp } from '@platform/lib/events/index.js';
import { httpRequest } from '@platform/lib/events/http.js';
import { platformNamespaceHeader } from '@platform/lib/utils/platform-namespace-header.js';

function _requireStringList(payload, field, opName) {
    if (!payload || typeof payload !== 'object') {
        throw new Error(`${opName}: payload required`);
    }
    const value = payload[field];
    if (!Array.isArray(value)) {
        throw new Error(`${opName}: ${field} required`);
    }
    if (value.some((item) => typeof item !== 'string' || item.length === 0)) {
        throw new Error(`${opName}: ${field} must be non-empty strings`);
    }
    return value;
}

function _optionalString(payload, field, opName) {
    if (!payload || typeof payload !== 'object') {
        throw new Error(`${opName}: payload required`);
    }
    const value = payload[field];
    if (value === undefined || value === null) {
        return null;
    }
    if (typeof value !== 'string') {
        throw new Error(`${opName}: ${field} must be string or null`);
    }
    return value.length > 0 ? value : null;
}

function _requireId(payload, field, opName) {
    if (!payload || typeof payload !== 'object') {
        throw new Error(`${opName}: payload required`);
    }
    const value = payload[field];
    if (typeof value !== 'string' || value.length === 0) {
        throw new Error(`${opName}: ${field} required`);
    }
    return value;
}

function _branchQuery(payload) {
    const branchId = payload.branch_id;
    if (typeof branchId !== 'string' || branchId.length === 0 || branchId === 'base') {
        return 'default';
    }
    return branchId;
}

function _codeAgentUrl(flowId, nodeId, suffix, branchId) {
    const rest = typeof suffix === 'string' && suffix.length > 0 ? `/${suffix}` : '';
    const params = new URLSearchParams();
    params.set('branch_id', branchId);
    return (
        `/flows/api/v1/flows/${encodeURIComponent(flowId)}`
        + `/nodes/${encodeURIComponent(nodeId)}/code-agent${rest}?${params.toString()}`
    );
}

function _codeAgentHttp(ctx, req) {
    return httpRequest({
        ...req,
        headers: {
            ...(req.headers && typeof req.headers === 'object' ? req.headers : {}),
            ...platformNamespaceHeader(ctx),
        },
    });
}

export const flowsCodeAgentEnsureSourceOp = createAsyncOp({
    name: 'flows/code_agent_ensure_source',
    transport: 'http',
    restMirror: {
        method: 'POST',
        path: '/flows/api/v1/flows/{flow_id}/nodes/{node_id}/code-agent/ensure-source',
    },
    successToastKey: 'flows:code_agent_editor.toast_ensure',
    errorToastKey: 'flows:code_agent_editor.toast_ensure_failed',
    request: async ({ payload, ctx }) => {
        const flowId = _requireId(payload, 'flow_id', 'flows/code_agent_ensure_source');
        const nodeId = _requireId(payload, 'node_id', 'flows/code_agent_ensure_source');
        return _codeAgentHttp(ctx, {
            method: 'POST',
            url: _codeAgentUrl(flowId, nodeId, 'ensure-source', _branchQuery(payload)),
        });
    },
});

export const flowsCodeAgentImportGitOp = createAsyncOp({
    name: 'flows/code_agent_import_git',
    transport: 'http',
    restMirror: {
        method: 'POST',
        path: '/flows/api/v1/flows/{flow_id}/nodes/{node_id}/code-agent/import-git',
    },
    successToastKey: 'flows:code_agent_editor.toast_import_git',
    errorToastKey: 'flows:code_agent_editor.toast_import_git_failed',
    request: async ({ payload, ctx }) => {
        const flowId = _requireId(payload, 'flow_id', 'flows/code_agent_import_git');
        const nodeId = _requireId(payload, 'node_id', 'flows/code_agent_import_git');
        const gitUrl = _requireId(payload, 'git_url', 'flows/code_agent_import_git');
        const sourceSha = payload.source_sha;
        if (typeof sourceSha !== 'string') {
            throw new Error('flows/code_agent_import_git: source_sha string required');
        }
        return _codeAgentHttp(ctx, {
            method: 'POST',
            url: _codeAgentUrl(flowId, nodeId, 'import-git', _branchQuery(payload)),
            body: { git_url: gitUrl, source_sha: sourceSha },
        });
    },
});

export const flowsCodeAgentImportArchiveOp = createAsyncOp({
    name: 'flows/code_agent_import_archive',
    transport: 'http',
    restMirror: {
        method: 'POST',
        path: '/flows/api/v1/flows/{flow_id}/nodes/{node_id}/code-agent/import-archive',
    },
    successToastKey: 'flows:code_agent_editor.toast_import_archive',
    errorToastKey: 'flows:code_agent_editor.toast_import_archive_failed',
    request: async ({ payload, ctx }) => {
        const flowId = _requireId(payload, 'flow_id', 'flows/code_agent_import_archive');
        const nodeId = _requireId(payload, 'node_id', 'flows/code_agent_import_archive');
        const fileId = _requireId(payload, 'file_id', 'flows/code_agent_import_archive');
        return _codeAgentHttp(ctx, {
            method: 'POST',
            url: _codeAgentUrl(flowId, nodeId, 'import-archive', _branchQuery(payload)),
            body: { file_id: fileId },
        });
    },
});

export const flowsCodeAgentCopyTreeOp = createAsyncOp({
    name: 'flows/code_agent_copy_tree',
    transport: 'http',
    restMirror: {
        method: 'POST',
        path: '/flows/api/v1/flows/{flow_id}/nodes/{node_id}/code-agent/copy-tree',
    },
    successToastKey: 'flows:code_agent_editor.toast_copy',
    errorToastKey: 'flows:code_agent_editor.toast_copy_failed',
    request: async ({ payload, ctx }) => {
        const flowId = _requireId(payload, 'flow_id', 'flows/code_agent_copy_tree');
        const nodeId = _requireId(payload, 'node_id', 'flows/code_agent_copy_tree');
        const fromCatalogId = _requireId(payload, 'from_catalog_id', 'flows/code_agent_copy_tree');
        return _codeAgentHttp(ctx, {
            method: 'POST',
            url: _codeAgentUrl(flowId, nodeId, 'copy-tree', _branchQuery(payload)),
            body: { from_catalog_id: fromCatalogId },
        });
    },
});

export const flowsCodeAgentRebuildOp = createAsyncOp({
    name: 'flows/code_agent_rebuild',
    transport: 'http',
    restMirror: {
        method: 'POST',
        path: '/flows/api/v1/flows/{flow_id}/nodes/{node_id}/code-agent/rebuild',
    },
    successToastKey: 'flows:code_agent_editor.toast_rebuild',
    errorToastKey: 'flows:code_agent_editor.toast_rebuild_failed',
    request: async ({ payload, ctx }) => {
        const flowId = _requireId(payload, 'flow_id', 'flows/code_agent_rebuild');
        const nodeId = _requireId(payload, 'node_id', 'flows/code_agent_rebuild');
        const language = _requireId(payload, 'language', 'flows/code_agent_rebuild');
        const invokeKind = _requireId(payload, 'invoke_kind', 'flows/code_agent_rebuild');
        const invokeArgv = _requireStringList(payload, 'invoke_argv', 'flows/code_agent_rebuild');
        if (invokeArgv.length === 0) {
            throw new Error('flows/code_agent_rebuild: invoke_argv required');
        }
        const listenPort = payload.invoke_listen_port;
        if (
            listenPort !== undefined
            && listenPort !== null
            && (typeof listenPort !== 'number' || !Number.isInteger(listenPort))
        ) {
            throw new Error('flows/code_agent_rebuild: invoke_listen_port must be int or null');
        }
        const egressHosts = payload.egress_hosts === undefined
            ? []
            : _requireStringList(payload, 'egress_hosts', 'flows/code_agent_rebuild');
        return _codeAgentHttp(ctx, {
            method: 'POST',
            url: _codeAgentUrl(flowId, nodeId, 'rebuild', _branchQuery(payload)),
            body: {
                language,
                invoke_kind: invokeKind,
                invoke_argv: invokeArgv,
                invoke_listen_port: listenPort === undefined ? null : listenPort,
                egress_hosts: egressHosts,
                git_url: _optionalString(payload, 'git_url', 'flows/code_agent_rebuild'),
                source_sha: _optionalString(payload, 'source_sha', 'flows/code_agent_rebuild'),
            },
        });
    },
});

export const flowsCodeAgentStatusOp = createAsyncOp({
    name: 'flows/code_agent_status',
    silent: true,
    transport: 'http',
    restMirror: {
        method: 'GET',
        path: '/flows/api/v1/flows/{flow_id}/nodes/{node_id}/code-agent',
    },
    request: async ({ payload, ctx }) => {
        const flowId = _requireId(payload, 'flow_id', 'flows/code_agent_status');
        const nodeId = _requireId(payload, 'node_id', 'flows/code_agent_status');
        return _codeAgentHttp(ctx, {
            method: 'GET',
            url: _codeAgentUrl(flowId, nodeId, '', _branchQuery(payload)),
        });
    },
});

export const flowsCodeAgentLogsOp = createAsyncOp({
    name: 'flows/code_agent_logs',
    silent: true,
    transport: 'http',
    restMirror: {
        method: 'GET',
        path: '/flows/api/v1/flows/{flow_id}/nodes/{node_id}/code-agent/logs',
    },
    request: async ({ payload, ctx }) => {
        const flowId = _requireId(payload, 'flow_id', 'flows/code_agent_logs');
        const nodeId = _requireId(payload, 'node_id', 'flows/code_agent_logs');
        const params = new URLSearchParams();
        params.set('branch_id', _branchQuery(payload));
        const taskId = payload.task_id;
        if (typeof taskId === 'string' && taskId.length > 0) {
            params.set('task_id', taskId);
        }
        const sessionId = payload.session_id;
        if (typeof sessionId === 'string' && sessionId.length > 0) {
            params.set('session_id', sessionId);
        }
        const contextId = payload.context_id;
        if (typeof contextId === 'string' && contextId.length > 0) {
            params.set('context_id', contextId);
        }
        return _codeAgentHttp(ctx, {
            method: 'GET',
            url: (
                `/flows/api/v1/flows/${encodeURIComponent(flowId)}`
                + `/nodes/${encodeURIComponent(nodeId)}/code-agent/logs?${params.toString()}`
            ),
        });
    },
});

export const flowsCodeAgentDeleteOp = createAsyncOp({
    name: 'flows/code_agent_delete',
    silent: true,
    transport: 'http',
    restMirror: {
        method: 'DELETE',
        path: '/flows/api/v1/flows/{flow_id}/nodes/{node_id}/code-agent',
    },
    request: async ({ payload, ctx }) => {
        const flowId = _requireId(payload, 'flow_id', 'flows/code_agent_delete');
        const nodeId = _requireId(payload, 'node_id', 'flows/code_agent_delete');
        const params = new URLSearchParams();
        params.set('branch_id', _branchQuery(payload));
        const catalogId = payload.catalog_id;
        if (typeof catalogId === 'string' && catalogId.length > 0) {
            params.set('catalog_id', catalogId);
        }
        return _codeAgentHttp(ctx, {
            method: 'DELETE',
            url: (
                `/flows/api/v1/flows/${encodeURIComponent(flowId)}`
                + `/nodes/${encodeURIComponent(nodeId)}/code-agent?${params.toString()}`
            ),
        });
    },
});

export const flowsCatalogItemsOp = createAsyncOp({
    name: 'flows/catalog_items',
    silent: true,
    transport: 'http',
    restMirror: {
        method: 'GET',
        path: '/documents/api/v1/catalogs/{catalog_id}/items',
        service: 'office',
    },
    request: async ({ payload, ctx }) => {
        const catalogId = _requireId(payload, 'catalog_id', 'flows/catalog_items');
        return _codeAgentHttp(ctx, {
            method: 'GET',
            url: `/documents/api/v1/catalogs/${encodeURIComponent(catalogId)}/items`,
        });
    },
});
