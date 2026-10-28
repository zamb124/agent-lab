/**
 * Canvas-only query/result карты Play для resource type=rag.
 * Транспорт поиска — rag/search; этот slice только привязывает ответ к nodeId.
 */

import { createSlice } from '@platform/lib/events/index.js';
import { searchOp } from '@platform/lib/events/resources/rag-search.resource.js';
import type { RagNodeTestSlice } from '../editor.types.js';

function _isPlainObject(value: unknown): value is Record<string, any> {
    return value !== null && typeof value === 'object' && !Array.isArray(value);
}

export const flowsRagNodeTestSlice = createSlice({
    name: 'flows/rag_node_test',
    extraInitial: {
        queryByNodeId: {} as Record<string, any>,
        resultByNodeId: {} as Record<string, any>,
        errorByNodeId: {} as Record<string, any>,
        lastNodeId: null as string | null,
    },
    actions: {
        setQuery: 'query_set',
        bindSearch: 'search_bind',
    },
    extraReducer: (state: RagNodeTestSlice, event, events) => {
        const s = state as Record<string, any>;
        if (event.type === events.QUERY_SET) {
            const payload = event.payload;
            if (!_isPlainObject(payload) || typeof (payload as any).nodeId !== 'string' || (payload as any).nodeId.length === 0) {
                throw new Error('flows/rag_node_test: payload.nodeId required');
            }
            if (typeof (payload as any).query !== 'string') {
                throw new Error('flows/rag_node_test: payload.query string required');
            }
            return {
                ...state,
                queryByNodeId: { ...s.queryByNodeId, [(payload as any).nodeId]: (payload as any).query },
            };
        }
        if (event.type === events.SEARCH_BIND) {
            const payload = event.payload;
            if (!_isPlainObject(payload) || typeof (payload as any).nodeId !== 'string' || (payload as any).nodeId.length === 0) {
                throw new Error('flows/rag_node_test: bindSearch nodeId required');
            }
            return {
                ...state,
                lastNodeId: (payload as any).nodeId,
                errorByNodeId: { ...s.errorByNodeId, [(payload as any).nodeId]: null },
            };
        }
        const nodeId = s.lastNodeId;
        if (typeof nodeId !== 'string' || nodeId.length === 0) {
            return state;
        }
        if (event.type === searchOp.events.SUCCEEDED) {
            if (!_isPlainObject(event.payload) || !('result' in event.payload)) {
                throw new Error('flows/rag_node_test: search SUCCEEDED result required');
            }
            return {
                ...state,
                resultByNodeId: { ...s.resultByNodeId, [nodeId]: event.payload.result },
                errorByNodeId: { ...s.errorByNodeId, [nodeId]: null },
            };
        }
        if (event.type === searchOp.events.FAILED) {
            if (!event.payload || typeof (event.payload as Record<string, any>).message !== 'string') {
                throw new Error('flows/rag_node_test: search FAILED message required');
            }
            return {
                ...state,
                errorByNodeId: { ...s.errorByNodeId, [nodeId]: (event.payload as Record<string, any>).message },
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
