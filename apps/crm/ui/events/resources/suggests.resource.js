/**
 * Suggests — фоновые предложения CRM по выбранному namespace.
 *
 * Backend (`/crm/api/v1/namespaces/{namespace}/suggests`):
 *   GET  /                    → OffsetPage[SuggestResponse]
 *   POST /{suggest_id}/resolve → SuggestResponse
 *   POST /{suggest_id}/dismiss → SuggestResponse
 */

import { createAsyncOp } from '@platform/lib/events/index.js';
import { httpRequest } from '@platform/lib/events/http.js';

const VALID_STATUSES = new Set(['', 'pending', 'resolved', 'dismissed', 'auto_resolved']);

function _requireNamespace(payload, owner) {
    if (!payload || typeof payload.namespace !== 'string' || payload.namespace.length === 0) {
        throw new Error(`${owner}: payload.namespace required`);
    }
    return payload.namespace;
}

function _requireSuggestId(payload, owner) {
    if (!payload || typeof payload.suggest_id !== 'string' || payload.suggest_id.length === 0) {
        throw new Error(`${owner}: payload.suggest_id required`);
    }
    return payload.suggest_id;
}

function _requireStatus(payload, owner) {
    if (!payload || typeof payload.status !== 'string') {
        throw new Error(`${owner}: payload.status required`);
    }
    if (!VALID_STATUSES.has(payload.status)) {
        throw new Error(`${owner}: unsupported status "${payload.status}"`);
    }
    return payload.status;
}

function _requirePageNumber(payload, field, owner) {
    if (!payload || typeof payload[field] !== 'number') {
        throw new Error(`${owner}: payload.${field} required`);
    }
    return payload[field];
}

export const suggestsListOp = createAsyncOp({
    name: 'crm/suggests_list',
    silent: true,
    restMirror: { method: 'GET', path: '/crm/api/v1/namespaces/:namespace/suggests' },
    request: async ({ payload }) => {
        const namespace = _requireNamespace(payload, 'suggestsListOp');
        const status = _requireStatus(payload, 'suggestsListOp');
        const limit = _requirePageNumber(payload, 'limit', 'suggestsListOp');
        const offset = _requirePageNumber(payload, 'offset', 'suggestsListOp');
        return await httpRequest({
            method: 'GET',
            url: `/crm/api/v1/namespaces/${encodeURIComponent(namespace)}/suggests`,
            query: { status, limit, offset },
        });
    },
});

export const suggestResolveOp = createAsyncOp({
    name: 'crm/suggest_resolve',
    successToastKey: 'crm:toast.suggest.resolved',
    errorToastKey: 'crm:toast.suggest.resolve_failed',
    restMirror: {
        method: 'POST',
        path: '/crm/api/v1/namespaces/:namespace/suggests/:suggest_id/resolve',
    },
    request: async ({ payload }) => {
        const namespace = _requireNamespace(payload, 'suggestResolveOp');
        const suggestId = _requireSuggestId(payload, 'suggestResolveOp');
        return await httpRequest({
            method: 'POST',
            url: `/crm/api/v1/namespaces/${encodeURIComponent(namespace)}/suggests/${encodeURIComponent(suggestId)}/resolve`,
        });
    },
});

export const suggestDismissOp = createAsyncOp({
    name: 'crm/suggest_dismiss',
    successToastKey: 'crm:toast.suggest.dismissed',
    errorToastKey: 'crm:toast.suggest.dismiss_failed',
    restMirror: {
        method: 'POST',
        path: '/crm/api/v1/namespaces/:namespace/suggests/:suggest_id/dismiss',
    },
    request: async ({ payload }) => {
        const namespace = _requireNamespace(payload, 'suggestDismissOp');
        const suggestId = _requireSuggestId(payload, 'suggestDismissOp');
        return await httpRequest({
            method: 'POST',
            url: `/crm/api/v1/namespaces/${encodeURIComponent(namespace)}/suggests/${encodeURIComponent(suggestId)}/dismiss`,
        });
    },
});
