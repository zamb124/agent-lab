/**
 * Durable workflow: history и time-travel.
 * REST: `apps/flows/src/api/v1/tasks.py` — тот же `op_*`, что WS.
 */

import { createAsyncOp } from '@platform/lib/events/index.js';

export const durableHistoryOp = createAsyncOp({
    name: 'flows/durable_history',
    silent: true,
    transport: 'ws',
    wsTimeoutMs: 15_000,
    commandType: 'flows/durable/history_requested',
    restMirror: { method: 'GET', path: '/flows/api/v1/tasks/{session_id}/history' },
});

export const durableBranchesOp = createAsyncOp({
    name: 'flows/durable_branches',
    silent: true,
    transport: 'ws',
    wsTimeoutMs: 15_000,
    commandType: 'flows/durable/branches_requested',
    restMirror: { method: 'GET', path: '/flows/api/v1/tasks/{session_id}/branches' },
});

export const durableStateAtOp = createAsyncOp({
    name: 'flows/durable_state_at',
    silent: true,
    transport: 'ws',
    wsTimeoutMs: 15_000,
    commandType: 'flows/durable/state_at_requested',
    restMirror: { method: 'GET', path: '/flows/api/v1/tasks/{session_id}/state-at/{sequence}' },
});

export const durableForkOp = createAsyncOp({
    name: 'flows/durable_fork',
    silent: true,
    transport: 'ws',
    wsTimeoutMs: 30_000,
    commandType: 'flows/durable/fork_requested',
    restMirror: { method: 'POST', path: '/flows/api/v1/tasks/{session_id}/fork' },
});

export const durableRewindOp = createAsyncOp({
    name: 'flows/durable_rewind',
    silent: true,
    transport: 'ws',
    wsTimeoutMs: 30_000,
    commandType: 'flows/durable/rewind_requested',
    restMirror: { method: 'POST', path: '/flows/api/v1/tasks/{session_id}/rewind' },
});

export const durableRetryFromFailureOp = createAsyncOp({
    name: 'flows/durable_retry_from_failure',
    silent: true,
    transport: 'ws',
    wsTimeoutMs: 30_000,
    commandType: 'flows/durable/retry_from_failure_requested',
    restMirror: { method: 'POST', path: '/flows/api/v1/tasks/{session_id}/retry-from-failure' },
});

export const durableManualPatchOp = createAsyncOp({
    name: 'flows/durable_manual_patch',
    silent: true,
    transport: 'ws',
    wsTimeoutMs: 30_000,
    commandType: 'flows/durable/manual_patch_requested',
    restMirror: { method: 'POST', path: '/flows/api/v1/tasks/{session_id}/manual-patch' },
});
