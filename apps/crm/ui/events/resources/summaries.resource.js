/**
 * Summaries — daily/period AI-сводки заметок CRM.
 *
 * Backend:
 *   POST /crm/api/v1/entities/daily-summary  → { summary, entities, generated_at, revalidating }
 *   POST /crm/api/v1/entities/period-summary → то же + period_truncated/period_summary_max_days
 *
 * Контроллер `useOp('crm/daily_summary')` хранит ответ в `result`. Слайс расширен
 * полем `summaryState` через `extraReducer`, чтобы WS-фрейм `crm/daily_summary/updated`
 * мог напрямую обновить хранимый payload без повторного fetch'а.
 */

import { createAsyncOp } from '@platform/lib/events/index.js';
import { httpRequest } from '@platform/lib/events/http.js';

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

export const dailySummaryOp = createAsyncOp({
    name: 'crm/daily_summary',
    silent: true,
    restMirror: { method: 'POST', path: '/crm/api/v1/entities/daily-summary' },
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
    extraEvents: { WS_PATCH: 'ws_patch' },
    extraReducer: (state, event, events) => {
        if (event.type === events.WS_PATCH) {
            return { ...state, result: event.payload };
        }
        return state;
    },
    actions: { applyWsPatch: 'ws_patch' },
});

export const periodSummaryOp = createAsyncOp({
    name: 'crm/period_summary',
    silent: true,
    restMirror: { method: 'POST', path: '/crm/api/v1/entities/period-summary' },
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
    extraEvents: { WS_PATCH: 'ws_patch' },
    extraReducer: (state, event, events) => {
        if (event.type === events.WS_PATCH) {
            return { ...state, result: event.payload };
        }
        return state;
    },
    actions: { applyWsPatch: 'ws_patch' },
});
