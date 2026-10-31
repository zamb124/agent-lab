/**
 * Canvas-only query/result карты Play для resource type=rag.
 * Транспорт поиска — rag/search; этот slice только привязывает ответ к nodeId.
 */

import { createSlice } from '@platform/lib/events/index.js';
import { searchOp } from '@platform/lib/events/resources/rag-search.resource.js';
import type { RagNodeTestSlice } from '../editor.types.js';

function _isPlainObject(value: unknown): value is Record<string, unknown> {
    return value !== null && typeof value === 'object' && !Array.isArray(value);
}

function emptyStringMap(): Record<string, string> {
    return {};
}

function emptyResultMap(): Record<string, unknown> {
    return {};
}

function emptyErrorMap(): Record<string, string | null> {
    return {};
}

const NO_NODE_ID: string | null = null;

export const flowsRagNodeTestSlice = createSlice({
    name: 'flows/rag_node_test',
    extraInitial: {
        queryByNodeId: emptyStringMap(),
        resultByNodeId: emptyResultMap(),
        errorByNodeId: emptyErrorMap(),
        lastNodeId: NO_NODE_ID,
    },
    actions: {
        setQuery: 'query_set',
        bindSearch: 'search_bind',
    },
    extraReducer: (state: RagNodeTestSlice, event, events) => {
        if (event.type === events.QUERY_SET) {
            const payload = event.payload;
            if (!_isPlainObject(payload)) {
                throw new Error('flows/rag_node_test: payload.nodeId required');
            }
            const nodeId = payload.nodeId;
            const query = payload.query;
            if (typeof nodeId !== 'string' || nodeId.length === 0) {
                throw new Error('flows/rag_node_test: payload.nodeId required');
            }
            if (typeof query !== 'string') {
                throw new Error('flows/rag_node_test: payload.query string required');
            }
            return {
                ...state,
                queryByNodeId: { ...state.queryByNodeId, [nodeId]: query },
            };
        }
        if (event.type === events.SEARCH_BIND) {
            const payload = event.payload;
            if (!_isPlainObject(payload)) {
                throw new Error('flows/rag_node_test: bindSearch nodeId required');
            }
            const nodeId = payload.nodeId;
            if (typeof nodeId !== 'string' || nodeId.length === 0) {
                throw new Error('flows/rag_node_test: bindSearch nodeId required');
            }
            return {
                ...state,
                lastNodeId: nodeId,
                errorByNodeId: { ...state.errorByNodeId, [nodeId]: null },
            };
        }
        const nodeId = state.lastNodeId;
        if (typeof nodeId !== 'string' || nodeId.length === 0) {
            return state;
        }
        if (event.type === searchOp.events.SUCCEEDED) {
            if (!_isPlainObject(event.payload) || !('result' in event.payload)) {
                throw new Error('flows/rag_node_test: search SUCCEEDED result required');
            }
            return {
                ...state,
                resultByNodeId: { ...state.resultByNodeId, [nodeId]: event.payload.result },
                errorByNodeId: { ...state.errorByNodeId, [nodeId]: null },
            };
        }
        if (event.type === searchOp.events.FAILED) {
            if (!_isPlainObject(event.payload)) {
                throw new Error('flows/rag_node_test: search FAILED message required');
            }
            const message = event.payload.message;
            if (typeof message !== 'string') {
                throw new Error('flows/rag_node_test: search FAILED message required');
            }
            return {
                ...state,
                errorByNodeId: { ...state.errorByNodeId, [nodeId]: message },
            };
        }
        return state;
    },
});

declare module '@platform/lib/events/factory-registry.js' {
    interface PlatformFactoryRegistry {
        'flows/rag_node_test': typeof flowsRagNodeTestSlice;
    }
}
