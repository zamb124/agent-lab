/**
 * Summaries — daily/period AI-сводки заметок CRM.
 *
 * Бэкенд:
 *   POST /crm/api/v1/entities/daily-summary  → { summary, entities, entity_links, generated_at, revalidating }
 *   POST /crm/api/v1/entities/period-summary → то же + period_truncated/period_summary_max_days
 *
 * Push `crm/daily_summary/updated` / `crm/period_summary/updated` мержится в
 * `lastResult` через extraReducer, если namespace/date совпадают с последним request.
 */

import { createAsyncOp } from '@platform/lib/events/index.js';
import { httpRequest } from '@platform/lib/events/http.js';

const CRM_DAILY_SUMMARY_UPDATED = 'crm/daily_summary/updated';
const CRM_PERIOD_SUMMARY_UPDATED = 'crm/period_summary/updated';

function _normalizeNamespace(value) {
    if (value === null || value === undefined) {
        return null;
    }
    if (typeof value !== 'string') {
        throw new Error('namespace must be string or null');
    }
    const trimmed = value.trim();
    return trimmed.length === 0 ? null : trimmed;
}

function _payloadNamespace(payload) {
    if (payload.namespace === null || payload.namespace === undefined) {
        return null;
    }
    if (typeof payload.namespace !== 'string') {
        return null;
    }
    return payload.namespace.length === 0 ? null : payload.namespace;
}

function _summaryStateFromPush(payload) {
    const st = payload.state;
    if (!st || typeof st !== 'object') {
        return null;
    }
    return {
        summary: typeof st.summary === 'string' ? st.summary : '',
        entities: Array.isArray(st.entities) ? st.entities : [],
        entity_links: Array.isArray(st.entity_links) ? st.entity_links : [],
        revalidating: false,
        generated_at: typeof st.generated_at === 'string' ? st.generated_at : new Date().toISOString(),
    };
}

export const dailySummaryOp = createAsyncOp({
    name: 'crm/daily_summary',
    silent: true,
    restMirror: { method: 'POST', path: '/crm/api/v1/entities/daily-summary' },
    extraInitial: {
        watchDate: null,
        watchNamespace: null,
    },
    request: async ({ payload }) => {
        if (!payload || typeof payload.date !== 'string' || payload.date.length === 0) {
            throw new Error('dailySummaryOp: payload.date required');
        }
        const body = {
            date: payload.date,
            namespace: _normalizeNamespace(payload.namespace),
            force_rebuild: payload.force_rebuild === true,
        };
        return await httpRequest({
            method: 'POST',
            url: '/crm/api/v1/entities/daily-summary',
            body,
        });
    },
    extraReducer: (state, event, events) => {
        if (event.type === events.REQUESTED) {
            const payload = event.payload && typeof event.payload === 'object' ? event.payload : {};
            return {
                ...state,
                watchDate: typeof payload.date === 'string' ? payload.date : null,
                watchNamespace: _normalizeNamespace(payload.namespace),
            };
        }
        if (event.type !== CRM_DAILY_SUMMARY_UPDATED) {
            return state;
        }
        const payload = event.payload;
        if (!payload || typeof payload !== 'object') {
            return state;
        }
        if (payload.date !== state.watchDate) {
            return state;
        }
        if (_payloadNamespace(payload) !== state.watchNamespace) {
            return state;
        }
        const next = _summaryStateFromPush(payload);
        if (next === null) {
            return state;
        }
        return { ...state, lastResult: next, busy: false, error: null };
    },
});

export const periodSummaryOp = createAsyncOp({
    name: 'crm/period_summary',
    silent: true,
    restMirror: { method: 'POST', path: '/crm/api/v1/entities/period-summary' },
    extraInitial: {
        watchDateFrom: null,
        watchDateTo: null,
        watchNamespace: null,
    },
    request: async ({ payload }) => {
        if (!payload || typeof payload.date_from !== 'string' || typeof payload.date_to !== 'string') {
            throw new Error('periodSummaryOp: { date_from, date_to } required');
        }
        const body = {
            date_from: payload.date_from,
            date_to: payload.date_to,
            namespace: _normalizeNamespace(payload.namespace),
            force_rebuild: payload.force_rebuild === true,
        };
        return await httpRequest({
            method: 'POST',
            url: '/crm/api/v1/entities/period-summary',
            body,
        });
    },
    extraReducer: (state, event, events) => {
        if (event.type === events.REQUESTED) {
            const payload = event.payload && typeof event.payload === 'object' ? event.payload : {};
            return {
                ...state,
                watchDateFrom: typeof payload.date_from === 'string' ? payload.date_from : null,
                watchDateTo: typeof payload.date_to === 'string' ? payload.date_to : null,
                watchNamespace: _normalizeNamespace(payload.namespace),
            };
        }
        if (event.type !== CRM_PERIOD_SUMMARY_UPDATED) {
            return state;
        }
        const payload = event.payload;
        if (!payload || typeof payload !== 'object') {
            return state;
        }
        if (payload.date_from !== state.watchDateFrom || payload.date_to !== state.watchDateTo) {
            return state;
        }
        if (_payloadNamespace(payload) !== state.watchNamespace) {
            return state;
        }
        const next = _summaryStateFromPush(payload);
        if (next === null) {
            return state;
        }
        return { ...state, lastResult: next, busy: false, error: null };
    },
});
