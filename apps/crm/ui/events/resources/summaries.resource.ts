/**
 * Summaries — daily/period AI-сводки заметок CRM.
 *
 * Бэкенд:
 *   POST /crm/api/v1/entities/daily-summary  → JsonObject
 *   POST /crm/api/v1/entities/period-summary → JsonObject
 *
 * Push `crm/daily_summary/updated` / `crm/period_summary/updated` мержится в
 * `lastResult` через extraReducer, если namespace/date совпадают с последним request.
 */

import { createAsyncOp } from '@platform/lib/events/index.js';

const CRM_DAILY_SUMMARY_UPDATED = 'crm/daily_summary/updated';
const CRM_PERIOD_SUMMARY_UPDATED = 'crm/period_summary/updated';

function _requireSummaryState(payload: Record<string, any>, owner: string) {
    const st = payload.state as Record<string, any> | null;
    if (!st || typeof st !== 'object' || Array.isArray(st)) {
        throw new Error(`${owner}: payload.state object required`);
    }
    if (typeof st.summary !== 'string') {
        throw new Error(`${owner}: payload.state.summary string required`);
    }
    if (!Array.isArray(st.entities)) {
        throw new Error(`${owner}: payload.state.entities array required`);
    }
    if (!Array.isArray(st.entity_links)) {
        throw new Error(`${owner}: payload.state.entity_links array required`);
    }
    if (typeof st.generated_at !== 'string' || st.generated_at.length === 0) {
        throw new Error(`${owner}: payload.state.generated_at string required`);
    }
    return {
        summary: st.summary,
        entities: st.entities,
        entity_links: st.entity_links,
        revalidating: false,
        generated_at: st.generated_at,
    };
}

function _namespaceOrNull(value: unknown, owner: string): string | null {
    if (value === null || value === undefined) {
        return null;
    }
    if (typeof value !== 'string') {
        throw new Error(`${owner}: namespace must be string or null`);
    }
    return value.length === 0 ? null : value;
}

export const dailySummaryOp = createAsyncOp({
    name: 'crm/daily_summary',
    silent: true,
    transport: 'ws',
    wsTimeoutMs: 15_000,
    commandType: 'crm/entities/daily_summary_requested',
    restMirror: { method: 'POST', path: '/crm/api/v1/entities/daily-summary' },
    extraInitial: {
        watchDate: null,
        watchNamespace: null,
    },
    extraReducer: (state, event, events) => {
        if (event.type === events.REQUESTED) {
            const payload = (event.payload as Record<string, any>);
            if (!payload || typeof payload !== 'object') {
                throw new Error('crm/daily_summary extraReducer: request payload required');
            }
            if (typeof payload.date !== 'string' || payload.date.length === 0) {
                throw new Error('crm/daily_summary extraReducer: payload.date required');
            }
            return {
                ...state,
                watchDate: payload.date,
                watchNamespace: _namespaceOrNull(payload.namespace, 'crm/daily_summary'),
            };
        }
        if (event.type !== CRM_DAILY_SUMMARY_UPDATED) {
            return state;
        }
        const payload = (event.payload as Record<string, any>);
        if (!payload || typeof payload !== 'object') {
            throw new Error('crm/daily_summary extraReducer: push payload required');
        }
        if (payload.date !== state.watchDate) {
            return state;
        }
        if (_namespaceOrNull(payload.namespace, 'crm/daily_summary') !== state.watchNamespace) {
            return state;
        }
        return {
            ...state,
            lastResult: _requireSummaryState(payload, 'crm/daily_summary'),
            busy: false,
            error: null,
        };
    },
});

export const periodSummaryOp = createAsyncOp({
    name: 'crm/period_summary',
    silent: true,
    transport: 'ws',
    wsTimeoutMs: 15_000,
    commandType: 'crm/entities/period_summary_requested',
    restMirror: { method: 'POST', path: '/crm/api/v1/entities/period-summary' },
    extraInitial: {
        watchDateFrom: null,
        watchDateTo: null,
        watchNamespace: null,
    },
    extraReducer: (state, event, events) => {
        if (event.type === events.REQUESTED) {
            const payload = (event.payload as Record<string, any>);
            if (!payload || typeof payload !== 'object') {
                throw new Error('crm/period_summary extraReducer: request payload required');
            }
            if (typeof payload.date_from !== 'string' || typeof payload.date_to !== 'string') {
                throw new Error('crm/period_summary extraReducer: date_from and date_to required');
            }
            return {
                ...state,
                watchDateFrom: payload.date_from,
                watchDateTo: payload.date_to,
                watchNamespace: _namespaceOrNull(payload.namespace, 'crm/period_summary'),
            };
        }
        if (event.type !== CRM_PERIOD_SUMMARY_UPDATED) {
            return state;
        }
        const payload = (event.payload as Record<string, any>);
        if (!payload || typeof payload !== 'object') {
            throw new Error('crm/period_summary extraReducer: push payload required');
        }
        if (payload.date_from !== state.watchDateFrom || payload.date_to !== state.watchDateTo) {
            return state;
        }
        if (_namespaceOrNull(payload.namespace, 'crm/period_summary') !== state.watchNamespace) {
            return state;
        }
        return {
            ...state,
            lastResult: _requireSummaryState(payload, 'crm/period_summary'),
            busy: false,
            error: null,
        };
    },
});
