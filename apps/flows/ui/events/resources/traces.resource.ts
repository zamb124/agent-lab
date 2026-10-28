/**
 * Traces — OTEL trace tree для tracing-modal/span-details-modal.
 * REST: `apps/flows/src/api/v1/traces.py` — тот же `op_*`, что WS.
 */

import { createAsyncOp } from '@platform/lib/events/index.js';

export const tracesBySessionOp = createAsyncOp({
    name: 'flows/traces_by_session',
    silent: true,
    transport: 'ws',
    wsTimeoutMs: 15_000,
    commandType: 'flows/traces/by_session_requested',
    restMirror: { method: 'GET', path: '/flows/api/v1/traces/session/{session_id}' },
});

export const tracesByTaskOp = createAsyncOp({
    name: 'flows/traces_by_task',
    silent: true,
    transport: 'ws',
    wsTimeoutMs: 15_000,
    commandType: 'flows/traces/by_task_requested',
    restMirror: { method: 'GET', path: '/flows/api/v1/traces/task/{task_id}' },
});

export const tracesByTraceOp = createAsyncOp({
    name: 'flows/traces_by_trace',
    silent: true,
    transport: 'ws',
    wsTimeoutMs: 15_000,
    commandType: 'flows/traces/by_trace_requested',
    restMirror: { method: 'GET', path: '/flows/api/v1/traces/trace/{trace_id}' },
});

export const tracesByHandoffChainOp = createAsyncOp({
    name: 'flows/traces_by_handoff_chain',
    silent: true,
    transport: 'ws',
    wsTimeoutMs: 15_000,
    commandType: 'flows/traces/handoff_chain_requested',
    restMirror: { method: 'GET', path: '/flows/api/v1/traces/handoff-chain/{parent_session_id}' },
});

declare module '@platform/lib/events/factory-registry.js' {
    interface PlatformFactoryRegistry {
        'flows/traces_by_session': typeof tracesBySessionOp;
        'flows/traces_by_task': typeof tracesByTaskOp;
        'flows/traces_by_trace': typeof tracesByTraceOp;
        'flows/traces_by_handoff_chain': typeof tracesByHandoffChainOp;
    }
}
