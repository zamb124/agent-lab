/**
 * @vitest-environment node
 *
 * Reducers RAG-фабрик канвы: owner rag/* + slice flows/rag_node_test.
 * События те же, что шина/push.
 */

import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { CoreEvents } from '@platform/lib/events/contract.js';
import { platformWs } from '@platform/lib/events/effects/ws.effect.js';
import { resetFactories } from '../../helpers/factory-fixtures.js';
import { documentsResource } from '../../../../core/frontend/static/lib/events/resources/rag-documents.resource.js';
import { documentStatusResource } from '../../../../core/frontend/static/lib/events/resources/rag-document-status.resource.js';
import { searchOp } from '../../../../core/frontend/static/lib/events/resources/rag-search.resource.js';
import { flowsRagNodeTestSlice } from '../../../../apps/flows/ui/events/resources/rag-node-test.resource.js';
import { buildCtx } from '../../helpers/bus-fixtures.js';

beforeEach(() => {
    resetFactories();
});
afterEach(() => {
    vi.restoreAllMocks();
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

describe('rag/documents extraReducer', () => {
    it('REQUESTED clears items and pins loadedNamespaceId', () => {
        const initial = {
            ...documentsResource.slice.initial,
            items: [listedDocument()],
            loadedNamespaceId: 'kb-old',
        };
        const next = documentsResource.reducer(initial, {
            type: documentsResource.events.REQUESTED,
            id: 'req_1',
            payload: { namespace_id: 'kb-support' },
        });
        expect(next.busy).toBe(true);
        expect(next.items).toEqual([]);
        expect(next.loadedNamespaceId).toBe('kb-support');
    });

    it('REQUESTED without namespace_id throws', () => {
        expect(() => documentsResource.reducer(documentsResource.slice.initial, {
            type: documentsResource.events.REQUESTED,
            id: 'req_1',
            payload: {},
        })).toThrow(/namespace_id required/);
    });

    it('SUCCEEDED replaces items from OffsetPage', () => {
        const afterRequest = documentsResource.reducer(documentsResource.slice.initial, {
            type: documentsResource.events.REQUESTED,
            id: 'req_1',
            payload: { namespace_id: 'kb-support' },
        });
        const items = [listedDocument({ status: 'completed', chunks_count: 4 })];
        const next = documentsResource.reducer(afterRequest, {
            type: documentsResource.events.SUCCEEDED,
            id: 'ok_1',
            payload: { result: { items, total: 1, limit: 100, offset: 0 } },
        });
        expect(next.busy).toBe(false);
        expect(next.items).toEqual(items);
        expect(next.loadedNamespaceId).toBe('kb-support');
    });

    it('SUCCEEDED without items array throws', () => {
        expect(() => documentsResource.reducer(documentsResource.slice.initial, {
            type: documentsResource.events.SUCCEEDED,
            id: 'ok_1',
            payload: { result: { total: 0 } },
        })).toThrow(/result.items required/);
    });

    it('push patches status, name and chunks on the matching document', () => {
        const listed = documentsResource.reducer(documentsResource.slice.initial, {
            type: documentsResource.events.SUCCEEDED,
            id: 'ok_1',
            payload: { result: { items: [listedDocument()], total: 1, limit: 100, offset: 0 } },
        });
        const pinned = { ...listed, loadedNamespaceId: 'kb-support' };
        const next = documentsResource.reducer(pinned, {
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
            chunks_count: null,
            created_at: '2026-08-01T12:00:00Z',
            metadata: { chunks_count: 7, error_message: null },
        });
    });

    it('push ignores another namespace while a list is loaded', () => {
        const listed = documentsResource.reducer(documentsResource.slice.initial, {
            type: documentsResource.events.SUCCEEDED,
            id: 'ok_1',
            payload: { result: { items: [listedDocument()], total: 1, limit: 100, offset: 0 } },
        });
        const pinned = { ...listed, loadedNamespaceId: 'kb-support' };
        const next = documentsResource.reducer(pinned, {
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
        const listed = documentsResource.reducer(documentsResource.slice.initial, {
            type: documentsResource.events.SUCCEEDED,
            id: 'ok_1',
            payload: { result: { items: [listedDocument()], total: 1, limit: 100, offset: 0 } },
        });
        const next = documentsResource.reducer(listed, {
            type: 'rag/document/status_updated',
            id: 'push_1',
            payload: { document_id: 'doc_missing', namespace_id: 'kb-support', status: 'completed' },
        });
        expect(next.items[0].status).toBe('processing');
    });
});

describe('rag/documents extraEffect', () => {
    it('reloads the list on terminal push for the loaded namespace', async () => {
        const dispatched = [];
        const ctx = recordingCtx(
            { ragDocuments: { loadedNamespaceId: 'kb-support', items: [listedDocument()] } },
            dispatched,
        );
        await documentsResource.effect(
            {
                type: 'rag/document/status_updated',
                id: 'push_1',
                payload: { document_id: 'doc_1', namespace_id: 'kb-support', status: 'completed' },
            },
            ctx,
        );
        expect(dispatched).toEqual([
            {
                type: documentsResource.events.REQUESTED,
                payload: { namespace_id: 'kb-support' },
                meta: { causation_id: 'push_1', source: 'ws' },
            },
        ]);
    });

    it('reloads on failed terminal status', async () => {
        const dispatched = [];
        const ctx = recordingCtx(
            { ragDocuments: { loadedNamespaceId: 'kb-support', items: [] } },
            dispatched,
        );
        await documentsResource.effect(
            {
                type: 'rag/document/status_updated',
                id: 'push_2',
                payload: { document_id: 'doc_1', namespace_id: 'kb-support', status: 'failed' },
            },
            ctx,
        );
        expect(dispatched).toHaveLength(1);
        expect(dispatched[0].payload.namespace_id).toBe('kb-support');
    });

    it('does not reload processing push', async () => {
        const dispatched = [];
        const ctx = recordingCtx(
            { ragDocuments: { loadedNamespaceId: 'kb-support', items: [] } },
            dispatched,
        );
        await documentsResource.effect(
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
            { ragDocuments: { loadedNamespaceId: 'kb-other', items: [] } },
            dispatched,
        );
        await documentsResource.effect(
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
        await expect(documentsResource.effect(
            {
                type: 'rag/document/status_updated',
                id: 'push_5',
                payload: { document_id: 'doc_1', namespace_id: 'kb-support', status: 'completed' },
            },
            ctx,
        )).rejects.toThrow(/slice ragDocuments missing/);
    });
});

describe('rag/document_status extraReducer', () => {
    it('ignores non-push events and invalid payload', () => {
        const initial = documentStatusResource.slice.initial;
        expect(documentStatusResource.reducer(initial, {
            type: documentStatusResource.events.REQUESTED,
            payload: { document_id: 'doc_1' },
        })).toMatchObject({ busy: true });
        expect(documentStatusResource.reducer(initial, {
            type: 'rag/document/status_updated',
            payload: null,
        })).toBe(initial);
        expect(documentStatusResource.reducer(initial, {
            type: 'rag/document/status_updated',
            payload: { document_id: '', status: 'completed' },
        })).toBe(initial);
    });

    it('writes lastResult from push', () => {
        const next = documentStatusResource.reducer(documentStatusResource.slice.initial, {
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

    it('onSuccess toast for completed and failed status RPC', async () => {
        const spy = vi.spyOn(platformWs, 'request').mockResolvedValueOnce({
            status: 'completed',
            document_name: 'ok.pdf',
        });
        const dispatched = [];
        await documentStatusResource.effect(
            {
                type: documentStatusResource.events.REQUESTED,
                payload: { document_id: 'doc_1' },
                id: 'st1',
                meta: {},
            },
            buildCtx(() => ({}), dispatched),
        );
        expect(dispatched.some((event) => (
            event.type === CoreEvents.UI_TOAST_SHOW
            && event.payload.i18n_key === 'rag:toast.document_processed'
        ))).toBe(true);

        spy.mockResolvedValueOnce({ status: 'failed', document_name: 'bad.pdf' });
        const failedDispatch = [];
        await documentStatusResource.effect(
            {
                type: documentStatusResource.events.REQUESTED,
                payload: { document_id: 'doc_2' },
                id: 'st2',
                meta: {},
            },
            buildCtx(() => ({}), failedDispatch),
        );
        expect(failedDispatch.some((event) => (
            event.type === CoreEvents.UI_TOAST_SHOW
            && event.payload.i18n_key === 'rag:toast.document_process_failed'
        ))).toBe(true);
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

    it('keys search result and error by bindSearch nodeId', () => {
        const bound = flowsRagNodeTestSlice.reducer(flowsRagNodeTestSlice.slice.initial, {
            type: 'flows/rag_node_test/search_bind',
            payload: { nodeId: 'rag_node' },
        });
        expect(bound.lastNodeId).toBe('rag_node');
        expect(bound.errorByNodeId.rag_node).toBeNull();

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
        const succeeded = flowsRagNodeTestSlice.reducer(bound, {
            type: searchOp.events.SUCCEEDED,
            id: 'ok_1',
            payload: { result: hits },
        });
        expect(succeeded.resultByNodeId.rag_node).toEqual(hits);
        expect(succeeded.errorByNodeId.rag_node).toBeNull();
    });

    it('FAILED stores the message for lastNodeId and keeps the previous hit list', () => {
        const withHits = {
            ...flowsRagNodeTestSlice.slice.initial,
            lastNodeId: 'rag_node',
            resultByNodeId: { rag_node: { results: [{ document_name: 'a', content: 'x', score: 1 }] } },
            errorByNodeId: { rag_node: null },
        };
        const failed = flowsRagNodeTestSlice.reducer(withHits, {
            type: searchOp.events.FAILED,
            id: 'fail_1',
            payload: { message: 'namespace missing' },
        });
        expect(failed.errorByNodeId.rag_node).toBe('namespace missing');
        expect(failed.resultByNodeId.rag_node.results).toHaveLength(1);
    });

    it('ignores search events before bindSearch', () => {
        const next = flowsRagNodeTestSlice.reducer(flowsRagNodeTestSlice.slice.initial, {
            type: searchOp.events.SUCCEEDED,
            id: 'ok_1',
            payload: { result: { results: [] } },
        });
        expect(next.resultByNodeId).toEqual({});
        expect(next.lastNodeId).toBeNull();
    });
});
