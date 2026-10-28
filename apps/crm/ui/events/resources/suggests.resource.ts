/**
 * Suggests — фоновые предложения CRM по выбранному namespace.
 *
 * Backend (`/crm/api/v1/namespaces/{namespace}/suggests`):
 *   GET  /                    → OffsetPage[CRMSuggest]
 *   POST /{suggest_id}/resolve → CRMSuggest
 *   POST /{suggest_id}/dismiss → CRMSuggest
 */

import { createAsyncOp } from '@platform/lib/events/index.js';

export const suggestsListOp = createAsyncOp({
    name: 'crm/suggests_list',
    silent: true,
    transport: 'ws',
    wsTimeoutMs: 8_000,
    commandType: 'crm/suggests/list_requested',
    restMirror: { method: 'GET', path: '/crm/api/v1/namespaces/:namespace/suggests' },
    extraReducer: (state, event) => {
        if (
            event.type !== 'crm/suggest_resolve/succeeded'
            && event.type !== 'crm/suggest_dismiss/succeeded'
        ) {
            return state;
        }
        const result = (event.payload as Record<string, any>) && (event.payload as Record<string, any>).result;
        if (!result || typeof result !== 'object' || typeof result.suggest_id !== 'string') {
            return state;
        }
        const page = state.lastResult as { items?: unknown; total?: unknown } | null | undefined;
        if (!page || typeof page !== 'object' || !Array.isArray(page.items)) {
            return state;
        }
        const nextItems = page.items.filter(
            (row) => row && (row as Record<string, any>).suggest_id !== (result as Record<string, any>).suggest_id,
        );
        if (nextItems.length === page.items.length) {
            return state;
        }
        if (typeof page.total !== 'number') {
            throw new Error('crm/suggests_list extraReducer: page.total number required');
        }
        const nextTotal = page.total - 1;
        if (nextTotal < 0) {
            throw new Error('crm/suggests_list extraReducer: page.total underflow');
        }
        return {
            ...state,
            lastResult: {
                ...page,
                items: nextItems,
                total: nextTotal,
            },
        };
    },
});

export const suggestResolveOp = createAsyncOp({
    name: 'crm/suggest_resolve',
    successToastKey: 'crm:toast.suggest.resolved',
    errorToastKey: 'crm:toast.suggest.resolve_failed',
    transport: 'ws',
    wsTimeoutMs: 8_000,
    commandType: 'crm/suggests/resolve_requested',
    restMirror: {
        method: 'POST',
        path: '/crm/api/v1/namespaces/:namespace/suggests/:suggest_id/resolve',
    },
});

export const suggestDismissOp = createAsyncOp({
    name: 'crm/suggest_dismiss',
    successToastKey: 'crm:toast.suggest.dismissed',
    errorToastKey: 'crm:toast.suggest.dismiss_failed',
    transport: 'ws',
    wsTimeoutMs: 8_000,
    commandType: 'crm/suggests/dismiss_requested',
    restMirror: {
        method: 'POST',
        path: '/crm/api/v1/namespaces/:namespace/suggests/:suggest_id/dismiss',
    },
});

declare module '@platform/lib/events/factory-registry.js' {
    interface PlatformFactoryRegistry {
        'crm/suggests_list': typeof suggestsListOp;
        'crm/suggest_resolve': typeof suggestResolveOp;
        'crm/suggest_dismiss': typeof suggestDismissOp;
    }
}
