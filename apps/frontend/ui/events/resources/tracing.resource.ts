/**
 * Ресурсы tracing — admin span list, фасеты и trace tree (команды `frontend/platform_tracing/*`,
 * REST-зеркало `apps/frontend/api/platform_tracing.py`). Доступно только активной компании system:
 * 403 → forbidden, 503 → unavailable.
 *
 * Состав:
 *   - tracingSpansList: createCursorList по `spans_requested`; buildQuery маппит filters в *_query поля.
 *   - tracingFacets: 6 фасет с дебаунсом и минимальной длиной запроса 2 (typeahead, HTTP).
 *   - tracingTraceLoadOp: `trace_tree_requested`, payload { trace_id }.
 */

import { createCursorList, createFacets, createAsyncOp } from '@platform/lib/events/index.js';
import { CoreEvents } from '@platform/lib/events/contract.js';

const BASE = '/frontend/api/platform-tracing';

function _buildSpansQuery(filters: Record<string, any>) {
    const q: Record<string, any> = {};
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
    baseUrl: '/frontend/api/platform-tracing/spans',
    transport: 'ws',
    wsTimeoutMs: 15_000,
    commandType: 'frontend/platform_tracing/spans_requested',
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
    transport: 'ws',
    wsTimeoutMs: 15_000,
    commandType: 'frontend/platform_tracing/trace_tree_requested',
    restMirror: { method: 'GET', path: '/frontend/api/platform-tracing/traces/:trace_id' },
    onFailure: (ctx) => {
        ctx.dispatch(
            CoreEvents.UI_TOAST_SHOW,
            { i18n_key: 'frontend:tracing_page.trace_load_error' },
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

declare module '@platform/lib/events/factory-registry.js' {
    interface PlatformFactoryRegistry {
        'frontend/tracing_spans': typeof tracingSpansList;
        'frontend/tracing_facets': typeof tracingFacets;
        'frontend/tracing_trace_load': typeof tracingTraceLoadOp;
    }
}
