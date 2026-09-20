/**
 * Code agent: дерево исходников ноды и rebuild на ферме guest_runtime.
 * REST: `apps/flows/src/api/v1/code_agent.py` — тот же `op_*`, что WS.
 */

import { createAsyncOp } from '@platform/lib/events/index.js';

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

export const flowsCodeAgentEnsureSourceOp = createAsyncOp({
    name: 'flows/code_agent_ensure_source',
    transport: 'ws',
    wsTimeoutMs: 15_000,
    commandType: 'flows/code_agent/ensure_source_requested',
    restMirror: {
        method: 'POST',
        path: '/flows/api/v1/flows/{flow_id}/nodes/{node_id}/code-agent/ensure-source',
    },
    successToastKey: 'flows:code_agent_editor.toast_ensure',
    errorToastKey: 'flows:code_agent_editor.toast_ensure_failed',
});

export const flowsCodeAgentImportGitOp = createAsyncOp({
    name: 'flows/code_agent_import_git',
    transport: 'ws',
    wsTimeoutMs: 30_000,
    commandType: 'flows/code_agent/import_git_requested',
    restMirror: {
        method: 'POST',
        path: '/flows/api/v1/flows/{flow_id}/nodes/{node_id}/code-agent/import-git',
    },
    successToastKey: 'flows:code_agent_editor.toast_import_git',
    errorToastKey: 'flows:code_agent_editor.toast_import_git_failed',
});

export const flowsCodeAgentImportArchiveOp = createAsyncOp({
    name: 'flows/code_agent_import_archive',
    transport: 'ws',
    wsTimeoutMs: 30_000,
    commandType: 'flows/code_agent/import_archive_requested',
    restMirror: {
        method: 'POST',
        path: '/flows/api/v1/flows/{flow_id}/nodes/{node_id}/code-agent/import-archive',
    },
    successToastKey: 'flows:code_agent_editor.toast_import_archive',
    errorToastKey: 'flows:code_agent_editor.toast_import_archive_failed',
});

export const flowsCodeAgentCopyTreeOp = createAsyncOp({
    name: 'flows/code_agent_copy_tree',
    transport: 'ws',
    wsTimeoutMs: 30_000,
    commandType: 'flows/code_agent/copy_tree_requested',
    restMirror: {
        method: 'POST',
        path: '/flows/api/v1/flows/{flow_id}/nodes/{node_id}/code-agent/copy-tree',
    },
    successToastKey: 'flows:code_agent_editor.toast_copy',
    errorToastKey: 'flows:code_agent_editor.toast_copy_failed',
});

export const flowsCodeAgentRebuildOp = createAsyncOp({
    name: 'flows/code_agent_rebuild',
    transport: 'ws',
    wsTimeoutMs: 30_000,
    commandType: 'flows/code_agent/rebuild_requested',
    restMirror: {
        method: 'POST',
        path: '/flows/api/v1/flows/{flow_id}/nodes/{node_id}/code-agent/rebuild',
    },
    successToastKey: 'flows:code_agent_editor.toast_rebuild',
    errorToastKey: 'flows:code_agent_editor.toast_rebuild_failed',
});

export const flowsCodeAgentStatusOp = createAsyncOp({
    name: 'flows/code_agent_status',
    silent: true,
    transport: 'ws',
    wsTimeoutMs: 15_000,
    commandType: 'flows/code_agent/status_requested',
    restMirror: {
        method: 'GET',
        path: '/flows/api/v1/flows/{flow_id}/nodes/{node_id}/code-agent',
    },
});

export const flowsCodeAgentLogsOp = createAsyncOp({
    name: 'flows/code_agent_logs',
    silent: true,
    transport: 'ws',
    wsTimeoutMs: 15_000,
    commandType: 'flows/code_agent/logs_requested',
    restMirror: {
        method: 'GET',
        path: '/flows/api/v1/flows/{flow_id}/nodes/{node_id}/code-agent/logs',
    },
});

export const flowsCodeAgentDeleteOp = createAsyncOp({
    name: 'flows/code_agent_delete',
    silent: true,
    transport: 'ws',
    wsTimeoutMs: 15_000,
    commandType: 'flows/code_agent/delete_requested',
    restMirror: {
        method: 'DELETE',
        path: '/flows/api/v1/flows/{flow_id}/nodes/{node_id}/code-agent',
    },
});
