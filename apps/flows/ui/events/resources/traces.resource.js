/**
 * Traces — OTEL trace tree для tracing-modal/span-details-modal.
 * REST: `apps/flows/src/api/v1/traces.py`.
 */

import { createAsyncOp } from '@platform/lib/events/index.js';
import { httpRequest } from '@platform/lib/events/http.js';

export const tracesBySessionOp = createAsyncOp({
    name: 'flows/traces_by_session',
    silent: true,
    restMirror: { method: 'GET', path: '/flows/api/v1/traces/session/{session_id}' },
    request: async ({ payload }) => {
        if (!payload || typeof payload.session_id !== 'string' || payload.session_id.length === 0) {
            throw new Error('tracesBySessionOp: { session_id } required');
        }
        return httpRequest({
            method: 'GET',
            url: `/flows/api/v1/traces/session/${encodeURIComponent(payload.session_id)}`,
        });
    },
});

export const tracesByTaskOp = createAsyncOp({
    name: 'flows/traces_by_task',
    silent: true,
    restMirror: { method: 'GET', path: '/flows/api/v1/traces/task/{task_id}' },
    request: async ({ payload }) => {
        if (!payload || typeof payload.task_id !== 'string' || payload.task_id.length === 0) {
            throw new Error('tracesByTaskOp: { task_id } required');
        }
        return httpRequest({
            method: 'GET',
            url: `/flows/api/v1/traces/task/${encodeURIComponent(payload.task_id)}`,
        });
    },
});

export const tracesByTraceOp = createAsyncOp({
    name: 'flows/traces_by_trace',
    silent: true,
    restMirror: { method: 'GET', path: '/flows/api/v1/traces/trace/{trace_id}' },
    request: async ({ payload }) => {
        if (!payload || typeof payload.trace_id !== 'string' || payload.trace_id.length === 0) {
            throw new Error('tracesByTraceOp: { trace_id } required');
        }
        return httpRequest({
            method: 'GET',
            url: `/flows/api/v1/traces/trace/${encodeURIComponent(payload.trace_id)}`,
        });
    },
});
