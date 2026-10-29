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
import { isPlainRecord } from '@platform/lib/events/payload.js';

const CRM_DAILY_SUMMARY_UPDATED = 'crm/daily_summary/updated';
const CRM_PERIOD_SUMMARY_UPDATED = 'crm/period_summary/updated';

function requirePayload(payload: unknown, message: string): Record<string, unknown> {
    if (!isPlainRecord(payload)) {
        throw new Error(message);
    }
    return payload;
}

function _requireSummaryState(payload: Record<string, unknown>, owner: string) {
    const st = payload.state;
    if (!isPlainRecord(st)) {
        throw new Error(`${owner}: payload.state object required`);
    }
    const summary = st.summary;
    if (typeof summary !== 'string') {
        throw new Error(`${owner}: payload.state.summary string required`);
    }
    const entities = st.entities;
    if (!Array.isArray(entities)) {
        throw new Error(`${owner}: payload.state.entities array required`);
    }
    const entityLinks = st.entity_links;
    if (!Array.isArray(entityLinks)) {
        throw new Error(`${owner}: payload.state.entity_links array required`);
    }
    const generatedAt = st.generated_at;
    if (typeof generatedAt !== 'string' || generatedAt.length === 0) {
        throw new Error(`${owner}: payload.state.generated_at string required`);
    }
    return {
        summary,
        entities,
        entity_links: entityLinks,
        revalidating: false,
        generated_at: generatedAt,
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
            const payload = requirePayload(event.payload, 'crm/daily_summary extraReducer: request payload required');
            const date = payload.date;
            if (typeof date !== 'string' || date.length === 0) {
                throw new Error('crm/daily_summary extraReducer: payload.date required');
            }
            return {
                ...state,
                watchDate: date,
                watchNamespace: _namespaceOrNull(payload.namespace, 'crm/daily_summary'),
            };
        }
        if (event.type !== CRM_DAILY_SUMMARY_UPDATED) {
            return state;
        }
        const payload = requirePayload(event.payload, 'crm/daily_summary extraReducer: push payload required');
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
            const payload = requirePayload(event.payload, 'crm/period_summary extraReducer: request payload required');
            const dateFrom = payload.date_from;
            const dateTo = payload.date_to;
            if (typeof dateFrom !== 'string' || typeof dateTo !== 'string') {
                throw new Error('crm/period_summary extraReducer: date_from and date_to required');
            }
            return {
                ...state,
                watchDateFrom: dateFrom,
                watchDateTo: dateTo,
                watchNamespace: _namespaceOrNull(payload.namespace, 'crm/period_summary'),
            };
        }
        if (event.type !== CRM_PERIOD_SUMMARY_UPDATED) {
            return state;
        }
        const payload = requirePayload(event.payload, 'crm/period_summary extraReducer: push payload required');
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

declare module '@platform/lib/events/factory-registry.js' {
    interface PlatformFactoryRegistry {
        'crm/daily_summary': typeof dailySummaryOp;
        'crm/period_summary': typeof periodSummaryOp;
    }
}
