/**
 * Canvas-only query/result карты Play для resource type=rag.
 * Транспорт поиска — rag/search; этот slice только привязывает ответ к nodeId.
 */

import { createSlice } from '@platform/lib/events/index.js';
import { searchOp } from '@platform/lib/events/resources/rag-search.resource.js';

function _isPlainObject(value) {
    return value !== null && typeof value === 'object' && !Array.isArray(value);
}

export const flowsRagNodeTestSlice = createSlice({
    name: 'flows/rag_node_test',
    extraInitial: {
        queryByNodeId: {},
        resultByNodeId: {},
        errorByNodeId: {},
        lastNodeId: null,
    },
    actions: {
        setQuery: 'query_set',
        bindSearch: 'search_bind',
    },
    extraReducer: (state, event, events) => {
        if (event.type === events.QUERY_SET) {
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
        }
        if (event.type === events.SEARCH_BIND) {
            const payload = event.payload;
            if (!_isPlainObject(payload) || typeof payload.nodeId !== 'string' || payload.nodeId.length === 0) {
                throw new Error('flows/rag_node_test: bindSearch nodeId required');
            }
            return {
                ...state,
                lastNodeId: payload.nodeId,
                errorByNodeId: { ...state.errorByNodeId, [payload.nodeId]: null },
            };
        }
        const nodeId = state.lastNodeId;
        if (typeof nodeId !== 'string' || nodeId.length === 0) {
            return state;
        }
        if (event.type === searchOp.events.SUCCEEDED) {
            if (!event.payload || !('result' in event.payload)) {
                throw new Error('flows/rag_node_test: search SUCCEEDED result required');
            }
            return {
                ...state,
                resultByNodeId: { ...state.resultByNodeId, [nodeId]: event.payload.result },
                errorByNodeId: { ...state.errorByNodeId, [nodeId]: null },
            };
        }
        if (event.type === searchOp.events.FAILED) {
            if (!event.payload || typeof event.payload.message !== 'string') {
                throw new Error('flows/rag_node_test: search FAILED message required');
            }
            return {
                ...state,
                errorByNodeId: { ...state.errorByNodeId, [nodeId]: event.payload.message },
            };
        }
        return state;
    },
});
