/**
 * Logs — записи логов flows из Loki по whitelist-ключам observability.
 * REST: `apps/flows/src/api/v1/observability_logs.py`.
 */

import { createAsyncOp } from '@platform/lib/events/index.js';
import { httpRequest } from '@platform/lib/events/http.js';

function logsQueryString(payload) {
    const params = new URLSearchParams();
    if (payload.limit) params.set('limit', String(payload.limit));
    if (payload.time_from) params.set('time_from', payload.time_from);
    if (payload.time_to) params.set('time_to', payload.time_to);
    const qs = params.toString();
    return qs ? `?${qs}` : '';
}

export const logsByTraceOp = createAsyncOp({
    name: 'flows/logs_by_trace',
    silent: true,
    restMirror: { method: 'GET', path: '/flows/api/v1/observability/logs/by-trace/{trace_id}' },
    request: async ({ payload }) => {
        if (!payload || typeof payload.trace_id !== 'string' || payload.trace_id.length === 0) {
            throw new Error('logsByTraceOp: { trace_id } required');
        }
        return httpRequest({
            method: 'GET',
            url: `/flows/api/v1/observability/logs/by-trace/${encodeURIComponent(payload.trace_id)}${logsQueryString(payload)}`,
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
        return httpRequest({
            method: 'GET',
            url: `/flows/api/v1/observability/logs/by-session/${encodeURIComponent(payload.session_id)}${logsQueryString(payload)}`,
        });
    },
});

export const logsByRequestOp = createAsyncOp({
    name: 'flows/logs_by_request',
    silent: true,
    restMirror: { method: 'GET', path: '/flows/api/v1/observability/logs/by-request/{request_id}' },
    request: async ({ payload }) => {
        if (!payload || typeof payload.request_id !== 'string' || payload.request_id.length === 0) {
            throw new Error('logsByRequestOp: { request_id } required');
        }
        return httpRequest({
            method: 'GET',
            url: `/flows/api/v1/observability/logs/by-request/${encodeURIComponent(payload.request_id)}${logsQueryString(payload)}`,
        });
    },
});

export const logsBySpanOp = createAsyncOp({
    name: 'flows/logs_by_span',
    silent: true,
    restMirror: { method: 'GET', path: '/flows/api/v1/observability/logs/by-span/{span_id}' },
    request: async ({ payload }) => {
        if (!payload || typeof payload.span_id !== 'string' || payload.span_id.length === 0) {
            throw new Error('logsBySpanOp: { span_id } required');
        }
        return httpRequest({
            method: 'GET',
            url: `/flows/api/v1/observability/logs/by-span/${encodeURIComponent(payload.span_id)}${logsQueryString(payload)}`,
        });
    },
});

export const logsByUserOp = createAsyncOp({
    name: 'flows/logs_by_user',
    silent: true,
    restMirror: { method: 'GET', path: '/flows/api/v1/observability/logs/by-user/{user_id}' },
    request: async ({ payload }) => {
        if (!payload || typeof payload.user_id !== 'string' || payload.user_id.length === 0) {
            throw new Error('logsByUserOp: { user_id } required');
        }
        return httpRequest({
            method: 'GET',
            url: `/flows/api/v1/observability/logs/by-user/${encodeURIComponent(payload.user_id)}${logsQueryString(payload)}`,
        });
    },
});
