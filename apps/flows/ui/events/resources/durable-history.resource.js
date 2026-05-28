/**
 * Операции durable workflow: history и time-travel.
 * REST: `apps/flows/src/api/v1/tasks.py`.
 */

import { createAsyncOp } from '@platform/lib/events/index.js';
import { httpRequest } from '@platform/lib/events/http.js';

const FLOWS_API_V1 = '/flows/api/v1';
const TASKS_BASE = `${FLOWS_API_V1}/tasks`;

function requirePayloadObject(payload, opName) {
    if (payload === null || typeof payload !== 'object' || Array.isArray(payload)) {
        throw new Error(`${opName}: payload object required`);
    }
    return payload;
}

function requireSessionId(payload, opName) {
    const body = requirePayloadObject(payload, opName);
    if (typeof body.session_id !== 'string' || body.session_id.length === 0) {
        throw new Error(`${opName}: { session_id } required`);
    }
    return body.session_id;
}

function requireSequence(payload, opName) {
    const body = requirePayloadObject(payload, opName);
    const sequence = body.sequence;
    if (!Number.isInteger(sequence) || sequence < 0) {
        throw new Error(`${opName}: non-negative integer sequence required`);
    }
    return sequence;
}

function optionalExecutionBranchId(payload) {
    return typeof payload.execution_branch_id === 'string' && payload.execution_branch_id.length > 0
        ? payload.execution_branch_id
        : null;
}

function historyQueryString(payload) {
    const params = new URLSearchParams();
    const limit = Number.isInteger(payload.limit) && payload.limit > 0 ? payload.limit : 200;
    const offset = Number.isInteger(payload.offset) && payload.offset >= 0 ? payload.offset : 0;
    params.set('limit', String(limit));
    params.set('offset', String(offset));
    const executionBranchId = optionalExecutionBranchId(payload);
    if (executionBranchId !== null) {
        params.set('execution_branch_id', executionBranchId);
    }
    return params.toString();
}

function stateAtQueryString(payload) {
    const params = new URLSearchParams();
    const executionBranchId = optionalExecutionBranchId(payload);
    if (executionBranchId !== null) {
        params.set('execution_branch_id', executionBranchId);
    }
    const query = params.toString();
    return query.length > 0 ? `?${query}` : '';
}

function timeTravelBody(payload) {
    const body = {
        sequence: requireSequence(payload, 'durable time-travel op'),
    };
    const executionBranchId = optionalExecutionBranchId(payload);
    if (executionBranchId !== null) {
        body.execution_branch_id = executionBranchId;
    }
    return body;
}

export const durableHistoryOp = createAsyncOp({
    name: 'flows/durable_history',
    silent: true,
    restMirror: { method: 'GET', path: '/flows/api/v1/tasks/{session_id}/history' },
    request: async ({ payload }) => {
        const sessionId = requireSessionId(payload, 'durableHistoryOp');
        const query = historyQueryString(payload);
        return httpRequest({
            method: 'GET',
            url: `${TASKS_BASE}/${encodeURIComponent(sessionId)}/history?${query}`,
        });
    },
});

export const durableBranchesOp = createAsyncOp({
    name: 'flows/durable_branches',
    silent: true,
    restMirror: { method: 'GET', path: '/flows/api/v1/tasks/{session_id}/branches' },
    request: async ({ payload }) => {
        const sessionId = requireSessionId(payload, 'durableBranchesOp');
        return httpRequest({
            method: 'GET',
            url: `${TASKS_BASE}/${encodeURIComponent(sessionId)}/branches`,
        });
    },
});

export const durableStateAtOp = createAsyncOp({
    name: 'flows/durable_state_at',
    silent: true,
    restMirror: { method: 'GET', path: '/flows/api/v1/tasks/{session_id}/state-at/{sequence}' },
    request: async ({ payload }) => {
        const sessionId = requireSessionId(payload, 'durableStateAtOp');
        const sequence = requireSequence(payload, 'durableStateAtOp');
        return httpRequest({
            method: 'GET',
            url: `${TASKS_BASE}/${encodeURIComponent(sessionId)}/state-at/${sequence}${stateAtQueryString(payload)}`,
        });
    },
});

export const durableForkOp = createAsyncOp({
    name: 'flows/durable_fork',
    silent: true,
    restMirror: { method: 'POST', path: '/flows/api/v1/tasks/{session_id}/fork' },
    request: async ({ payload }) => {
        const sessionId = requireSessionId(payload, 'durableForkOp');
        const body = timeTravelBody(payload);
        body.activate = payload.activate === true;
        return httpRequest({
            method: 'POST',
            url: `${TASKS_BASE}/${encodeURIComponent(sessionId)}/fork`,
            body,
        });
    },
});

export const durableRewindOp = createAsyncOp({
    name: 'flows/durable_rewind',
    silent: true,
    restMirror: { method: 'POST', path: '/flows/api/v1/tasks/{session_id}/rewind' },
    request: async ({ payload }) => {
        const sessionId = requireSessionId(payload, 'durableRewindOp');
        return httpRequest({
            method: 'POST',
            url: `${TASKS_BASE}/${encodeURIComponent(sessionId)}/rewind`,
            body: timeTravelBody(payload),
        });
    },
});

export const durableRetryFromFailureOp = createAsyncOp({
    name: 'flows/durable_retry_from_failure',
    silent: true,
    restMirror: { method: 'POST', path: '/flows/api/v1/tasks/{session_id}/retry-from-failure' },
    request: async ({ payload }) => {
        const sessionId = requireSessionId(payload, 'durableRetryFromFailureOp');
        const body = {};
        const executionBranchId = optionalExecutionBranchId(payload);
        if (executionBranchId !== null) {
            body.execution_branch_id = executionBranchId;
        }
        if (Number.isInteger(payload.failed_sequence) && payload.failed_sequence > 0) {
            body.failed_sequence = payload.failed_sequence;
        }
        return httpRequest({
            method: 'POST',
            url: `${TASKS_BASE}/${encodeURIComponent(sessionId)}/retry-from-failure`,
            body,
        });
    },
});

export const durableManualPatchOp = createAsyncOp({
    name: 'flows/durable_manual_patch',
    silent: true,
    restMirror: { method: 'POST', path: '/flows/api/v1/tasks/{session_id}/manual-patch' },
    request: async ({ payload }) => {
        const sessionId = requireSessionId(payload, 'durableManualPatchOp');
        const body = timeTravelBody(payload);
        const state = payload.state;
        if (state === null || typeof state !== 'object' || Array.isArray(state)) {
            throw new Error('durableManualPatchOp: state object required');
        }
        body.state = state;
        body.activate = payload.activate === true;
        return httpRequest({
            method: 'POST',
            url: `${TASKS_BASE}/${encodeURIComponent(sessionId)}/manual-patch`,
            body,
        });
    },
});
