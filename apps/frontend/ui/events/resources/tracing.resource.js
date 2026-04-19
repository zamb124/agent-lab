/**
 * Tracing resources — admin span list, фасеты и trace tree.
 *
 * API:
 *   GET /frontend/api/platform-tracing/spans          (cursor pagination)
 *   GET /frontend/api/platform-tracing/traces/{id}    (tree)
 *   GET /frontend/api/platform-tracing/facets/companies|users|services|namespaces|operations|event-types
 *
 * Доступно только активной компании system. 403 → forbidden, 503 → unavailable.
 *
 * Состав:
 *   - tracingSpansList: createCursorList по spans, statusMap 403→forbidden,
 *     503→unavailable. Свой buildQuery маппит filters в *_query поля.
 *   - tracingFacets: 6 фасет с дебаунсом и минимальной длиной запроса 2.
 *   - tracingTraceLoadOp: GET /traces/{id}, payload { trace_id }.
 */

import { createCursorList, createFacets, createAsyncOp } from '@platform/lib/events/index.js';
import { httpRequest } from '@platform/lib/events/http.js';
import { CoreEvents } from '@platform/lib/events/contract.js';

const BASE = '/frontend/api/platform-tracing';

function _buildSpansQuery(filters) {
    const q = {};
    if (filters.company_id)     q.company_id_query = filters.company_id;
    if (filters.user_id)        q.user_id_query = filters.user_id;
    if (filters.service_name)   q.service_name_query = filters.service_name;
    if (filters.namespace)      q.namespace_query = filters.namespace;
    if (filters.operation_name) q.operation_name_query = filters.operation_name;
    if (filters.event_type)     q.event_type_query = filters.event_type;
    if (filters.from_time)      q.from_time = filters.from_time;
    if (filters.to_time)        q.to_time = filters.to_time;
    return q;
}

export const tracingSpansList = createCursorList({
    name: 'frontend/tracing_spans',
    baseUrl: `${BASE}/spans`,
    pageSize: 50,
    buildQuery: _buildSpansQuery,
    statusMap: { 403: 'forbidden', 503: 'unavailable' },
    errorToastKey: 'frontend:tracing_page.load_error',
});

export const tracingFacets = createFacets({
    name: 'frontend/tracing_facets',
    baseUrl: `${BASE}/facets`,
    facets: {
        companies:   'companies',
        users:       'users',
        services:    'services',
        namespaces:  'namespaces',
        operations:  'operations',
        event_types: 'event-types',
    },
    debounceMs: 200,
    minQueryLength: 2,
    pageSize: 20,
});

export const tracingTraceLoadOp = createAsyncOp({
    name: 'frontend/tracing_trace_load',
    silent: true,
    request: async ({ payload }) => {
        const id = payload && payload.trace_id;
        if (!id) throw new Error('tracing_trace_load: trace_id required');
        return await httpRequest({
            method: 'GET',
            url: `${BASE}/traces/${encodeURIComponent(id)}`,
        });
    },
    onFailure: (ctx) => {
        ctx.dispatch(
            CoreEvents.UI_TOAST_SHOW,
            { type: 'error', i18n_key: 'frontend:tracing_page.trace_load_error' },
            { source: 'local' },
        );
    },
    actions: {
        closeTrace: 'closed',
    },
    extraReducer: (state, event, events) => {
        if (event.type === events.CLOSED) {
            return { ...state, lastResult: null, error: null, busy: false };
        }
        return state;
    },
});
