/**
 * Logs — записи логов flows из Loki по whitelist-ключам observability.
 * REST: `apps/flows/src/api/v1/observability_logs.py` — тот же `op_*`, что WS.
 */

import { createAsyncOp } from '@platform/lib/events/index.js';

export const logsByTraceOp = createAsyncOp({
    name: 'flows/logs_by_trace',
    silent: true,
    transport: 'ws',
    wsTimeoutMs: 15_000,
    commandType: 'flows/logs/by_trace_requested',
    restMirror: { method: 'GET', path: '/flows/api/v1/observability/logs/by-trace/{trace_id}' },
});

export const logsBySessionOp = createAsyncOp({
    name: 'flows/logs_by_session',
    silent: true,
    transport: 'ws',
    wsTimeoutMs: 15_000,
    commandType: 'flows/logs/by_session_requested',
    restMirror: { method: 'GET', path: '/flows/api/v1/observability/logs/by-session/{session_id}' },
});

export const logsByRequestOp = createAsyncOp({
    name: 'flows/logs_by_request',
    silent: true,
    transport: 'ws',
    wsTimeoutMs: 15_000,
    commandType: 'flows/logs/by_request_requested',
    restMirror: { method: 'GET', path: '/flows/api/v1/observability/logs/by-request/{request_id}' },
});

export const logsBySpanOp = createAsyncOp({
    name: 'flows/logs_by_span',
    silent: true,
    transport: 'ws',
    wsTimeoutMs: 15_000,
    commandType: 'flows/logs/by_span_requested',
    restMirror: { method: 'GET', path: '/flows/api/v1/observability/logs/by-span/{span_id}' },
});

export const logsByUserOp = createAsyncOp({
    name: 'flows/logs_by_user',
    silent: true,
    transport: 'ws',
    wsTimeoutMs: 15_000,
    commandType: 'flows/logs/by_user_requested',
    restMirror: { method: 'GET', path: '/flows/api/v1/observability/logs/by-user/{user_id}' },
});
