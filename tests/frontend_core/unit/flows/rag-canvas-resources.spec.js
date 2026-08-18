/**
 * @vitest-environment node
 *
 * Reducers и extraEffect RAG-фабрик канвы. Без fetch, без подмены модулей:
 * события те же, что шина/push, состояние — канонический slice фабрики.
 */

import { beforeEach, describe, expect, it } from 'vitest';
import { resetFactories } from '../../helpers/factory-fixtures.js';
import {
    flowsRagDocumentsOp,
    flowsRagDocumentStatusOp,
} from '../../../../apps/flows/ui/events/resources/rag-documents.resource.js';
import {
    flowsRagSearchOp,
    flowsRagNodeTestSlice,
} from '../../../../apps/flows/ui/events/resources/rag-search.resource.js';

beforeEach(() => {
    resetFactories();
});

function recordingCtx(state, dispatched) {
    return {
        dispatch(type, payload, meta) {
            dispatched.push({ type, payload, meta: meta === undefined ? null : meta });
            return { id: `evt_${dispatched.length}`, type, payload, meta };
        },
        getState: () => state,
    };
}

function listedDocument(overrides) {
    return {
        document_id: 'doc_1',
        name: 'policy.pdf',
        status: 'processing',
        chunks_count: null,
        created_at: '2026-08-01T12:00:00Z',
        metadata: {},
        ...overrides,
    };
}

describe('flows/rag_documents extraReducer', () => {
    it('REQUESTED clears items and pins loadedNamespaceId', () => {
        const initial = {
            ...flowsRagDocumentsOp.slice.initial,
            items: [listedDocument()],
            loadedNamespaceId: 'kb-old',
        };
        const next = flowsRagDocumentsOp.reducer(initial, {
            type: flowsRagDocumentsOp.events.REQUESTED,
            id: 'req_1',
            payload: { namespaceId: 'kb-support', limit: 100, offset: 0 },
        });
        expect(next.busy).toBe(true);
        expect(next.items).toEqual([]);
        expect(next.loadedNamespaceId).toBe('kb-support');
    });

    it('REQUESTED without namespaceId throws', () => {
        expect(() => flowsRagDocumentsOp.reducer(flowsRagDocumentsOp.slice.initial, {
            type: flowsRagDocumentsOp.events.REQUESTED,
            id: 'req_1',
            payload: { limit: 100, offset: 0 },
        })).toThrow(/namespaceId required/);
    });

    it('SUCCEEDED replaces items from OffsetPage', () => {
        const afterRequest = flowsRagDocumentsOp.reducer(flowsRagDocumentsOp.slice.initial, {
            type: flowsRagDocumentsOp.events.REQUESTED,
            id: 'req_1',
            payload: { namespaceId: 'kb-support', limit: 100, offset: 0 },
        });
        const items = [listedDocument({ status: 'completed', chunks_count: 4 })];
        const next = flowsRagDocumentsOp.reducer(afterRequest, {
            type: flowsRagDocumentsOp.events.SUCCEEDED,
            id: 'ok_1',
            payload: { result: { items, total: 1, limit: 100, offset: 0 } },
        });
        expect(next.busy).toBe(false);
        expect(next.items).toEqual(items);
        expect(next.loadedNamespaceId).toBe('kb-support');
    });

    it('SUCCEEDED without items array throws', () => {
        expect(() => flowsRagDocumentsOp.reducer(flowsRagDocumentsOp.slice.initial, {
            type: flowsRagDocumentsOp.events.SUCCEEDED,
            id: 'ok_1',
            payload: { result: { total: 0 } },
        })).toThrow(/result.items required/);
    });

    it('push patches status, name and chunks on the matching document', () => {
        const listed = flowsRagDocumentsOp.reducer(flowsRagDocumentsOp.slice.initial, {
            type: flowsRagDocumentsOp.events.SUCCEEDED,
            id: 'ok_1',
            payload: { result: { items: [listedDocument()], total: 1, limit: 100, offset: 0 } },
        });
        const pinned = { ...listed, loadedNamespaceId: 'kb-support' };
        const next = flowsRagDocumentsOp.reducer(pinned, {
            type: 'rag/document/status_updated',
            id: 'push_1',
            payload: {
                document_id: 'doc_1',
                namespace_id: 'kb-support',
                status: 'completed',
                document_name: 'policy-v2.pdf',
                chunks_count: 7,
            },
        });
        expect(next.items).toHaveLength(1);
        expect(next.items[0]).toEqual({
            document_id: 'doc_1',
            name: 'policy-v2.pdf',
            status: 'completed',
            chunks_count: 7,
            created_at: '2026-08-01T12:00:00Z',
            metadata: { chunks_count: 7 },
        });
    });

    it('push ignores another namespace while a list is loaded', () => {
        const listed = flowsRagDocumentsOp.reducer(flowsRagDocumentsOp.slice.initial, {
            type: flowsRagDocumentsOp.events.SUCCEEDED,
            id: 'ok_1',
            payload: { result: { items: [listedDocument()], total: 1, limit: 100, offset: 0 } },
        });
        const pinned = { ...listed, loadedNamespaceId: 'kb-support' };
        const next = flowsRagDocumentsOp.reducer(pinned, {
            type: 'rag/document/status_updated',
            id: 'push_1',
            payload: {
                document_id: 'doc_1',
                namespace_id: 'kb-other',
                status: 'failed',
                error_message: 'split failed',
            },
        });
        expect(next.items[0].status).toBe('processing');
        expect(next.items[0].metadata).toEqual({});
    });

    it('push leaves unknown document_id untouched', () => {
        const listed = flowsRagDocumentsOp.reducer(flowsRagDocumentsOp.slice.initial, {
            type: flowsRagDocumentsOp.events.SUCCEEDED,
            id: 'ok_1',
            payload: { result: { items: [listedDocument()], total: 1, limit: 100, offset: 0 } },
        });
        const next = flowsRagDocumentsOp.reducer(listed, {
            type: 'rag/document/status_updated',
            id: 'push_1',
            payload: { document_id: 'doc_missing', namespace_id: 'kb-support', status: 'completed' },
        });
        expect(next.items[0].status).toBe('processing');
    });

    it('push with chunks_count throws when listed item has no metadata object', () => {
        const listed = flowsRagDocumentsOp.reducer(flowsRagDocumentsOp.slice.initial, {
            type: flowsRagDocumentsOp.events.SUCCEEDED,
            id: 'ok_1',
            payload: {
                result: {
                    items: [listedDocument({ metadata: null })],
                    total: 1,
                    limit: 100,
                    offset: 0,
                },
            },
        });
        expect(() => flowsRagDocumentsOp.reducer(listed, {
            type: 'rag/document/status_updated',
            id: 'push_1',
            payload: { document_id: 'doc_1', status: 'completed', chunks_count: 2 },
        })).toThrow(/item.metadata object required/);
    });
});

describe('flows/rag_documents extraEffect', () => {
    it('reloads the list on terminal push for the loaded namespace', async () => {
        const dispatched = [];
        const ctx = recordingCtx(
            { flowsRagDocuments: { loadedNamespaceId: 'kb-support', items: [listedDocument()] } },
            dispatched,
        );
        await flowsRagDocumentsOp.effect(
            {
                type: 'rag/document/status_updated',
                id: 'push_1',
                payload: { document_id: 'doc_1', namespace_id: 'kb-support', status: 'completed' },
            },
            ctx,
        );
        expect(dispatched).toEqual([
            {
                type: flowsRagDocumentsOp.events.REQUESTED,
                payload: { namespaceId: 'kb-support', limit: 100, offset: 0 },
                meta: { causation_id: 'push_1', source: 'ws' },
            },
        ]);
    });

    it('reloads on failed terminal status', async () => {
        const dispatched = [];
        const ctx = recordingCtx(
            { flowsRagDocuments: { loadedNamespaceId: 'kb-support', items: [] } },
            dispatched,
        );
        await flowsRagDocumentsOp.effect(
            {
                type: 'rag/document/status_updated',
                id: 'push_2',
                payload: { document_id: 'doc_1', namespace_id: 'kb-support', status: 'failed' },
            },
            ctx,
        );
        expect(dispatched).toHaveLength(1);
        expect(dispatched[0].payload.namespaceId).toBe('kb-support');
    });

    it('does not reload processing push', async () => {
        const dispatched = [];
        const ctx = recordingCtx(
            { flowsRagDocuments: { loadedNamespaceId: 'kb-support', items: [] } },
            dispatched,
        );
        await flowsRagDocumentsOp.effect(
            {
                type: 'rag/document/status_updated',
                id: 'push_3',
                payload: { document_id: 'doc_1', namespace_id: 'kb-support', status: 'processing' },
            },
            ctx,
        );
        expect(dispatched).toEqual([]);
    });

    it('does not reload a different loaded namespace', async () => {
        const dispatched = [];
        const ctx = recordingCtx(
            { flowsRagDocuments: { loadedNamespaceId: 'kb-other', items: [] } },
            dispatched,
        );
        await flowsRagDocumentsOp.effect(
            {
                type: 'rag/document/status_updated',
                id: 'push_4',
                payload: { document_id: 'doc_1', namespace_id: 'kb-support', status: 'completed' },
            },
            ctx,
        );
        expect(dispatched).toEqual([]);
    });

    it('throws when the documents slice is missing', async () => {
        const ctx = recordingCtx({}, []);
        await expect(flowsRagDocumentsOp.effect(
            {
                type: 'rag/document/status_updated',
                id: 'push_5',
                payload: { document_id: 'doc_1', namespace_id: 'kb-support', status: 'completed' },
            },
            ctx,
        )).rejects.toThrow(/slice flowsRagDocuments missing/);
    });
});

describe('flows/rag_document_status extraReducer', () => {
    it('writes lastResult from push', () => {
        const next = flowsRagDocumentStatusOp.reducer(flowsRagDocumentStatusOp.slice.initial, {
            type: 'rag/document/status_updated',
            id: 'push_1',
            payload: {
                document_id: 'doc_1',
                namespace_id: 'kb-support',
                status: 'failed',
                document_name: 'broken.pdf',
                error_message: 'embed failed',
                chunks_count: 0,
            },
        });
        expect(next.busy).toBe(false);
        expect(next.error).toBeNull();
        expect(next.lastResult).toEqual({
            document_id: 'doc_1',
            status: 'failed',
            document_name: 'broken.pdf',
            error_message: 'embed failed',
            chunks_count: 0,
            namespace_id: 'kb-support',
        });
    });
});

describe('flows/rag_search extraReducer', () => {
    it('keys result and error by nodeId from lastNodeId', () => {
        const requested = flowsRagSearchOp.reducer(flowsRagSearchOp.slice.initial, {
            type: flowsRagSearchOp.events.REQUESTED,
            id: 'req_1',
            payload: {
                nodeId: 'rag_node',
                namespaceId: 'kb-support',
                query: 'returns',
                limit: 5,
            },
        });
        expect(requested.lastNodeId).toBe('rag_node');
        expect(requested.errorByNodeId.rag_node).toBeNull();
        expect(requested.busy).toBe(true);

        const hits = {
            results: [
                {
                    document_name: 'policy.pdf',
                    content: 'return window is 14 days',
                    score: 0.91,
                    page_label: '3',
                },
            ],
        };
        const succeeded = flowsRagSearchOp.reducer(requested, {
            type: flowsRagSearchOp.events.SUCCEEDED,
            id: 'ok_1',
            payload: { result: hits },
        });
        expect(succeeded.busy).toBe(false);
        expect(succeeded.resultByNodeId.rag_node).toEqual(hits);
        expect(succeeded.errorByNodeId.rag_node).toBeNull();
    });

    it('FAILED stores the message for lastNodeId and keeps the previous hit list', () => {
        const withHits = {
            ...flowsRagSearchOp.slice.initial,
            lastNodeId: 'rag_node',
            resultByNodeId: { rag_node: { results: [{ document_name: 'a', content: 'x', score: 1 }] } },
            errorByNodeId: { rag_node: null },
        };
        const failed = flowsRagSearchOp.reducer(withHits, {
            type: flowsRagSearchOp.events.FAILED,
            id: 'fail_1',
            payload: { message: 'namespace missing' },
        });
        expect(failed.errorByNodeId.rag_node).toBe('namespace missing');
        expect(failed.resultByNodeId.rag_node.results).toHaveLength(1);
        expect(failed.busy).toBe(false);
    });

    it('REQUESTED without nodeId throws', () => {
        expect(() => flowsRagSearchOp.reducer(flowsRagSearchOp.slice.initial, {
            type: flowsRagSearchOp.events.REQUESTED,
            id: 'req_1',
            payload: { namespaceId: 'kb-support', query: 'q', limit: 5 },
        })).toThrow(/payload.nodeId required/);
    });

    it('SUCCEEDED without lastNodeId throws', () => {
        expect(() => flowsRagSearchOp.reducer(flowsRagSearchOp.slice.initial, {
            type: flowsRagSearchOp.events.SUCCEEDED,
            id: 'ok_1',
            payload: { result: { results: [] } },
        })).toThrow(/lastNodeId required on SUCCEEDED/);
    });

    it('FAILED without lastNodeId throws', () => {
        expect(() => flowsRagSearchOp.reducer(flowsRagSearchOp.slice.initial, {
            type: flowsRagSearchOp.events.FAILED,
            id: 'fail_1',
            payload: { message: 'boom' },
        })).toThrow(/lastNodeId required on FAILED/);
    });
});

describe('flows/rag_node_test slice', () => {
    it('rejects a missing nodeId', () => {
        expect(() => flowsRagNodeTestSlice.reducer(flowsRagNodeTestSlice.slice.initial, {
            type: 'flows/rag_node_test/query_set',
            payload: { query: 'hello' },
        })).toThrow(/payload.nodeId required/);
    });

    it('rejects a non-string query', () => {
        expect(() => flowsRagNodeTestSlice.reducer(flowsRagNodeTestSlice.slice.initial, {
            type: 'flows/rag_node_test/query_set',
            payload: { nodeId: 'n1', query: 12 },
        })).toThrow(/payload.query string required/);
    });

    it('overwrites query for the same node and isolates other nodes', () => {
        const first = flowsRagNodeTestSlice.reducer(flowsRagNodeTestSlice.slice.initial, {
            type: 'flows/rag_node_test/query_set',
            payload: { nodeId: 'n1', query: 'alpha' },
        });
        const second = flowsRagNodeTestSlice.reducer(first, {
            type: 'flows/rag_node_test/query_set',
            payload: { nodeId: 'n2', query: 'beta' },
        });
        const third = flowsRagNodeTestSlice.reducer(second, {
            type: 'flows/rag_node_test/query_set',
            payload: { nodeId: 'n1', query: 'gamma' },
        });
        expect(third.queryByNodeId).toEqual({ n1: 'gamma', n2: 'beta' });
    });
});
