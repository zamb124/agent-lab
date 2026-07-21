/**
 * RAG Namespace API для редактора flows-ресурса (cross-service → rag).
 */

import { createAsyncOp } from '@platform/lib/events/index.js';
import { httpRequest } from '@platform/lib/events/http.js';

export const flowsRagNamespacesListOp = createAsyncOp({
    name: 'flows/rag_namespaces_list',
    silent: true,
    transport: 'http',
    restMirror: { method: 'GET', path: '/rag/api/v1/namespaces', service: 'rag' },
    request: async () => httpRequest({
        method: 'GET',
        url: '/rag/api/v1/namespaces?limit=200&offset=0',
    }),
});

export const flowsRagNamespacesCreateOp = createAsyncOp({
    name: 'flows/rag_namespaces_create',
    transport: 'http',
    restMirror: { method: 'POST', path: '/rag/api/v1/namespaces', service: 'rag' },
    successToastKey: 'flows:rag_resource_editor.toast_namespace_created',
    errorToastKey: 'flows:rag_resource_editor.toast_namespace_create_failed',
    request: async ({ payload }) => {
        if (!payload || typeof payload !== 'object') {
            throw new Error('flowsRagNamespacesCreateOp: payload required');
        }
        return httpRequest({
            method: 'POST',
            url: '/rag/api/v1/namespaces',
            body: payload,
        });
    },
});

export const flowsRagSearchDefaultsOp = createAsyncOp({
    name: 'flows/rag_search_defaults',
    silent: true,
    transport: 'http',
    restMirror: { method: 'GET', path: '/rag/api/v1/search-defaults', service: 'rag' },
    request: async () => httpRequest({
        method: 'GET',
        url: '/rag/api/v1/search-defaults',
    }),
});
