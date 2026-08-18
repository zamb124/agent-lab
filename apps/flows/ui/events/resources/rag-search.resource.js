/**
 * Test-run поиск RAG с канвы + query slice (query не в bind).
 */

import { createAsyncOp, createSlice } from '@platform/lib/events/index.js';
import { httpRequest } from '@platform/lib/events/http.js';
import { packSearchRequestOptions } from '@platform/lib/rag/pack_search_request_options.js';

function _isPlainObject(value) {
    return value !== null && typeof value === 'object' && !Array.isArray(value);
}

export const flowsRagSearchOp = createAsyncOp({
    name: 'flows/rag_search',
    silent: true,
    transport: 'http',
    restMirror: { method: 'POST', path: '/rag/api/v1/namespaces/:namespace_id/search', service: 'rag' },
    request: ({ payload }) => {
        if (!payload || typeof payload.nodeId !== 'string' || payload.nodeId.length === 0) {
            throw new Error('flows/rag_search: payload.nodeId required');
        }
        if (typeof payload.namespaceId !== 'string' || payload.namespaceId.length === 0) {
            throw new Error('flows/rag_search: payload.namespaceId required');
        }
        if (typeof payload.query !== 'string' || payload.query.length === 0) {
            throw new Error('flows/rag_search: payload.query required');
        }
        if (typeof payload.limit !== 'number' || !Number.isFinite(payload.limit) || payload.limit < 1) {
            throw new Error('flows/rag_search: payload.limit >= 1 required');
        }
        const body = {
            query: payload.query,
            limit: payload.limit,
            ...packSearchRequestOptions(payload),
        };
        if (payload.filters !== undefined && payload.filters !== null) {
            if (!_isPlainObject(payload.filters)) {
                throw new Error('flows/rag_search: payload.filters must be object');
            }
            body.filters = payload.filters;
        }
        return httpRequest({
            method: 'POST',
            url: `/rag/api/v1/namespaces/${encodeURIComponent(payload.namespaceId)}/search`,
            body,
        });
    },
    extraInitial: {
        resultByNodeId: {},
        errorByNodeId: {},
        lastNodeId: null,
    },
    extraReducer: (state, event, events) => {
        if (event.type === events.REQUESTED) {
            const nodeId = event.payload && event.payload.nodeId;
            if (typeof nodeId !== 'string' || nodeId.length === 0) {
                throw new Error('flows/rag_search: REQUESTED payload.nodeId required');
            }
            return {
                ...state,
                lastNodeId: nodeId,
                errorByNodeId: { ...state.errorByNodeId, [nodeId]: null },
            };
        }
        if (event.type === events.SUCCEEDED) {
            const nodeId = state.lastNodeId;
            if (typeof nodeId !== 'string' || nodeId.length === 0) {
                throw new Error('flows/rag_search: lastNodeId required on SUCCEEDED');
            }
            return {
                ...state,
                resultByNodeId: { ...state.resultByNodeId, [nodeId]: event.payload.result },
                errorByNodeId: { ...state.errorByNodeId, [nodeId]: null },
            };
        }
        if (event.type === events.FAILED) {
            const nodeId = state.lastNodeId;
            if (typeof nodeId !== 'string' || nodeId.length === 0) {
                throw new Error('flows/rag_search: lastNodeId required on FAILED');
            }
            return {
                ...state,
                errorByNodeId: { ...state.errorByNodeId, [nodeId]: event.payload.message },
            };
        }
        return state;
    },
});

export const flowsRagNodeTestSlice = createSlice({
    name: 'flows/rag_node_test',
    extraInitial: {
        queryByNodeId: {},
    },
    actions: {
        setQuery: 'query_set',
    },
    extraReducer: (state, event, events) => {
        if (event.type !== events.QUERY_SET) {
            return state;
        }
        const payload = event.payload;
        if (!_isPlainObject(payload) || typeof payload.nodeId !== 'string' || payload.nodeId.length === 0) {
            throw new Error('flows/rag_node_test: payload.nodeId required');
        }
        if (typeof payload.query !== 'string') {
            throw new Error('flows/rag_node_test: payload.query string required');
        }
        return {
            ...state,
            queryByNodeId: { ...state.queryByNodeId, [payload.nodeId]: payload.query },
        };
    },
});
