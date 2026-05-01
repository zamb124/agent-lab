/**
 * Logs — записи логов flows из Loki по trace_id или session_id.
 * REST: `apps/flows/src/api/v1/observability_logs.py`.
 */

import { createAsyncOp } from '@platform/lib/events/index.js';
import { httpRequest } from '@platform/lib/events/http.js';

export const logsByTraceOp = createAsyncOp({
    name: 'flows/logs_by_trace',
    silent: true,
    restMirror: { method: 'GET', path: '/flows/api/v1/observability/logs/by-trace/{trace_id}' },
    request: async ({ payload }) => {
        if (!payload || typeof payload.trace_id !== 'string' || payload.trace_id.length === 0) {
            throw new Error('logsByTraceOp: { trace_id } required');
        }
        const params = new URLSearchParams();
        if (payload.limit) params.set('limit', String(payload.limit));
        if (payload.time_from) params.set('time_from', payload.time_from);
        if (payload.time_to) params.set('time_to', payload.time_to);
        const qs = params.toString();
        return httpRequest({
            method: 'GET',
            url: `/flows/api/v1/observability/logs/by-trace/${encodeURIComponent(payload.trace_id)}${qs ? '?' + qs : ''}`,
        });
    },
});

export const logsBySessionOp = createAsyncOp({
    name: 'flows/logs_by_session',
    silent: true,
    restMirror: { method: 'GET', path: '/flows/api/v1/observability/logs/by-session/{session_id}' },
    request: async ({ payload }) => {
        if (!payload || typeof payload.session_id !== 'string' || payload.session_id.length === 0) {
            throw new Error('logsBySessionOp: { session_id } required');
        }
        const params = new URLSearchParams();
        if (payload.limit) params.set('limit', String(payload.limit));
        if (payload.time_from) params.set('time_from', payload.time_from);
        if (payload.time_to) params.set('time_to', payload.time_to);
        const qs = params.toString();
        return httpRequest({
            method: 'GET',
            url: `/flows/api/v1/observability/logs/by-session/${encodeURIComponent(payload.session_id)}${qs ? '?' + qs : ''}`,
        });
    },
});
