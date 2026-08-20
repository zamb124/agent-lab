/**
 * @vitest-environment node
 */

import { beforeEach, describe, expect, it } from 'vitest';
import {
    clearNodeTestRunHandlersForTests,
    findNodeTestRunHandlers,
    registerNodeTestRunHandler,
    resolveNodeTestRunHandler,
} from '../../../../apps/flows/ui/_helpers/node-test-run-registry.js';
import { codeExecuteTestRunHandler } from '../../../../apps/flows/ui/_helpers/node-test-run-code-execute.js';
import {
    buildRagSearchPayload,
    ragSearchTestRunHandler,
} from '../../../../apps/flows/ui/_helpers/node-test-run-rag-search.js';
import { uniquePinnedResourceType } from '../../../../apps/flows/ui/_helpers/flows-branch-resource.js';
import {
    getTestRunRequestClientId,
    nextTestRunClientId,
    setTestRunRequestClientId,
} from '../../../../apps/flows/ui/_helpers/flows-test-run-gate.js';
import { flowsRagNodeTestSlice } from '../../../../apps/flows/ui/events/resources/rag-search.resource.js';

function ragBindCtx(overrides) {
    return {
        nodeId: 'n1',
        query: 'return policy',
        nodeConfig: { resources: { r1: { resource_id: 'r1' } } },
        editorState: {
            branchData: {
                resources: {
                    r1: {
                        type: 'rag',
                        name: 'RAG',
                        config: {
                            namespace: 'kb-support',
                            default_top_k: 5,
                        },
                    },
                },
            },
        },
        catalogItems: [],
        ...overrides,
    };
}

describe('node test-run registry', () => {
    beforeEach(() => {
        clearNodeTestRunHandlersForTests();
        registerNodeTestRunHandler(codeExecuteTestRunHandler);
        registerNodeTestRunHandler(ragSearchTestRunHandler);
    });

    it('resolves code_execute for non-resource nodes', () => {
        const handler = resolveNodeTestRunHandler({ nodeType: 'llm_node', resourceType: null });
        expect(handler.id).toBe('code_execute');
        expect(handler.opName).toBe('flows/code_execute');
    });

    it('resolves code_execute for datasource nodes', () => {
        const handler = resolveNodeTestRunHandler({ nodeType: 'datasource', resourceType: null });
        expect(handler.id).toBe('code_execute');
        expect(handler.opName).toBe('flows/code_execute');
    });

    it('resolves rag_search for resource + rag', () => {
        const handler = resolveNodeTestRunHandler({ nodeType: 'resource', resourceType: 'rag' });
        expect(handler.id).toBe('rag_search');
        expect(handler.opName).toBe('flows/rag_search');
    });

    it('throws when resource type has no handler', () => {
        expect(() => resolveNodeTestRunHandler({ nodeType: 'resource', resourceType: 'llm' })).toThrow(
            /expected exactly 1 handler, got 0/,
        );
        expect(findNodeTestRunHandlers({ nodeType: 'resource', resourceType: 'llm' })).toEqual([]);
    });

    it('throws on duplicate handler id', () => {
        expect(() => registerNodeTestRunHandler(codeExecuteTestRunHandler)).toThrow(/duplicate handler id/);
    });

    it('builds rag search payload from bind', () => {
        const payload = buildRagSearchPayload({
            nodeId: 'n1',
            query: '  return policy  ',
            nodeConfig: { resources: { r1: { resource_id: 'r1' } } },
            editorState: {
                branchData: {
                    resources: {
                        r1: {
                            type: 'rag',
                            name: 'RAG',
                            config: {
                                namespace: 'kb-support',
                                default_top_k: 7,
                                filters: { collection_id: 'faq' },
                                search_options: { rerank: true, rrf_k: 40 },
                            },
                        },
                    },
                },
            },
            catalogItems: [],
        });
        expect(payload).toEqual({
            nodeId: 'n1',
            namespaceId: 'kb-support',
            query: 'return policy',
            limit: 7,
            rerank: true,
            rrf_k: 40,
            filters: { collection_id: 'faq' },
        });
    });

    it('throws when rag query is empty', () => {
        expect(() => buildRagSearchPayload({
            nodeId: 'n1',
            query: '   ',
            nodeConfig: { resources: { r1: { resource_id: 'r1' } } },
            editorState: { branchData: { resources: {} } },
            catalogItems: [],
        })).toThrow(/query required/);
    });

    it('throws when nodeId is empty', () => {
        expect(() => buildRagSearchPayload(ragBindCtx({ nodeId: '' }))).toThrow(/nodeId required/);
    });

    it('throws when pinned resource count is not 1', () => {
        expect(() => buildRagSearchPayload(ragBindCtx({
            nodeConfig: { resources: {} },
        }))).toThrow(/expected 1 pinned resource, got 0/);
        expect(() => buildRagSearchPayload(ragBindCtx({
            nodeConfig: {
                resources: {
                    r1: { resource_id: 'r1' },
                    r2: { resource_id: 'r2' },
                },
            },
        }))).toThrow(/expected 1 pinned resource, got 2/);
    });

    it('throws when namespace is missing from bind', () => {
        expect(() => buildRagSearchPayload(ragBindCtx({
            editorState: {
                branchData: {
                    resources: {
                        r1: { type: 'rag', name: 'RAG', config: { default_top_k: 5 } },
                    },
                },
            },
        }))).toThrow(/namespace required/);
    });

    it('throws when default_top_k is missing', () => {
        expect(() => buildRagSearchPayload(ragBindCtx({
            editorState: {
                branchData: {
                    resources: {
                        r1: { type: 'rag', name: 'RAG', config: { namespace: 'kb-support' } },
                    },
                },
            },
        }))).toThrow(/default_top_k >= 1 required/);
    });

    it('throws when pinned type is not rag', () => {
        expect(() => buildRagSearchPayload(ragBindCtx({
            editorState: {
                branchData: {
                    resources: {
                        r1: { type: 'llm', name: 'LLM', config: { namespace: 'kb-support', default_top_k: 5 } },
                    },
                },
            },
        }))).toThrow(/pinned type is llm/);
    });

    it('omits filters when bind has none', () => {
        const payload = buildRagSearchPayload(ragBindCtx({}));
        expect(payload).toEqual({
            nodeId: 'n1',
            namespaceId: 'kb-support',
            query: 'return policy',
            limit: 5,
        });
        expect(Object.prototype.hasOwnProperty.call(payload, 'filters')).toBe(false);
    });

    it('throws when two handlers match the same node', () => {
        registerNodeTestRunHandler({
            id: 'rag_search_dup',
            opName: 'flows/rag_search',
            match: ({ nodeType, resourceType }) => nodeType === 'resource' && resourceType === 'rag',
            run: async () => {},
            formatViewModel: () => null,
            busyOf: () => false,
        });
        expect(() => resolveNodeTestRunHandler({ nodeType: 'resource', resourceType: 'rag' })).toThrow(
            /expected exactly 1 handler, got 2/,
        );
    });

    it('rejects a handler without required fields', () => {
        expect(() => registerNodeTestRunHandler({ id: 'broken' })).toThrow(/match required/);
    });
});

describe('ragSearchTestRunHandler view model and run', () => {
    beforeEach(() => {
        clearNodeTestRunHandlersForTests();
        registerNodeTestRunHandler(codeExecuteTestRunHandler);
        registerNodeTestRunHandler(ragSearchTestRunHandler);
    });

    it('formats hit count from resultByNodeId', () => {
        const view = ragSearchTestRunHandler.formatViewModel({
            nodeId: 'n1',
            t: (key, vars) => `${key}:${vars.count}`,
            op: {
                state: {
                    errorByNodeId: {},
                    resultByNodeId: { n1: { results: [{}, {}] } },
                },
            },
        });
        expect(view).toEqual({
            kind: 'ok',
            lines: ['rag_resource_editor.test_hits:2'],
            durationMs: null,
            fullPayload: { results: [{}, {}] },
            canOpenFull: true,
        });
    });

    it('formats a per-node error', () => {
        const view = ragSearchTestRunHandler.formatViewModel({
            nodeId: 'n1',
            t: () => {
                throw new Error('t must not run on error');
            },
            op: {
                state: {
                    errorByNodeId: { n1: 'namespace missing' },
                    resultByNodeId: {},
                },
            },
        });
        expect(view).toEqual({
            kind: 'error',
            lines: ['namespace missing'],
            durationMs: null,
            fullPayload: null,
            canOpenFull: false,
        });
    });

    it('returns null before the node has a result', () => {
        const view = ragSearchTestRunHandler.formatViewModel({
            nodeId: 'n1',
            t: () => 'unused',
            op: {
                state: {
                    errorByNodeId: {},
                    resultByNodeId: {},
                },
            },
        });
        expect(view).toBeNull();
    });

    it('throws when lastResult.results is not an array', () => {
        expect(() => ragSearchTestRunHandler.formatViewModel({
            nodeId: 'n1',
            t: () => 'unused',
            op: {
                state: {
                    errorByNodeId: {},
                    resultByNodeId: { n1: { hits: [] } },
                },
            },
        })).toThrow(/lastResult.results array required/);
    });

    it('toasts and does not search when query is empty', async () => {
        const toasts = [];
        const host = {
            nodeId: 'n1',
            toast(key, opts) {
                toasts.push({ key, opts });
            },
            _ragNodeTest: { value: { queryByNodeId: { n1: '   ' } } },
        };
        await ragSearchTestRunHandler.run({
            host,
            requestClientId: 'tr_1',
            matchCtx: {},
            op: {
                run() {
                    throw new Error('flows/rag_search must not run on empty query');
                },
            },
        });
        expect(toasts).toEqual([
            { key: 'rag_resource_editor.test_query_required', opts: { type: 'error' } },
        ]);
    });

    it('builds bind payload and runs the search op', async () => {
        const runs = [];
        const host = {
            nodeId: 'n1',
            nodeConfig: { resources: { r1: { resource_id: 'r1' } } },
            toast() {
                throw new Error('toast must not run when query is present');
            },
            _ragNodeTest: { value: { queryByNodeId: { n1: '  returns  ' } } },
        };
        await ragSearchTestRunHandler.run({
            host,
            requestClientId: 'tr_9',
            matchCtx: {
                editorState: {
                    branchData: {
                        resources: {
                            r1: {
                                type: 'rag',
                                name: 'RAG',
                                config: { namespace: 'kb-support', default_top_k: 8 },
                            },
                        },
                    },
                },
                catalogItems: [],
            },
            op: {
                async run(payload) {
                    runs.push(payload);
                    return { results: [] };
                },
            },
        });
        expect(getTestRunRequestClientId()).toBe('tr_9');
        expect(runs).toEqual([
            {
                nodeId: 'n1',
                namespaceId: 'kb-support',
                query: 'returns',
                limit: 8,
            },
        ]);
    });
});

describe('flows-test-run-gate', () => {
    it('issues unique client ids and stores the last request', () => {
        const first = nextTestRunClientId();
        const second = nextTestRunClientId();
        expect(first).toMatch(/^tr_\d+$/);
        expect(second).not.toBe(first);
        setTestRunRequestClientId(first);
        expect(getTestRunRequestClientId()).toBe(first);
        setTestRunRequestClientId(second);
        expect(getTestRunRequestClientId()).toBe(second);
    });

    it('throws on empty client id', () => {
        expect(() => setTestRunRequestClientId('')).toThrow(/non-empty string/);
    });
});

describe('uniquePinnedResourceType', () => {
    it('returns rag for a single inline branch resource', () => {
        const resourceType = uniquePinnedResourceType(
            { resources: { r1: { resource_id: 'r1' } } },
            { branchData: { resources: { r1: { type: 'rag', config: { namespace: 'kb-1' } } } } },
            [],
        );
        expect(resourceType).toBe('rag');
    });

    it('returns null when catalog is unresolved', () => {
        const resourceType = uniquePinnedResourceType(
            { resources: { r1: { resource_id: 'shared_1' } } },
            { branchData: { resources: { r1: { resource_id: 'shared_1' } } } },
            [],
        );
        expect(resourceType).toBeNull();
    });

    it('returns null when the node has no pinned resources', () => {
        expect(uniquePinnedResourceType({ resources: {} }, { branchData: { resources: {} } }, [])).toBeNull();
    });

    it('returns null when two pinned types differ', () => {
        const resourceType = uniquePinnedResourceType(
            { resources: { r1: { resource_id: 'r1' }, r2: { resource_id: 'r2' } } },
            {
                branchData: {
                    resources: {
                        r1: { type: 'rag', config: { namespace: 'kb-1' } },
                        r2: { type: 'llm', config: {} },
                    },
                },
            },
            [],
        );
        expect(resourceType).toBeNull();
    });

    it('returns rag when two pinned resources share the same type', () => {
        const resourceType = uniquePinnedResourceType(
            { resources: { r1: { resource_id: 'r1' }, r2: { resource_id: 'r2' } } },
            {
                branchData: {
                    resources: {
                        r1: { type: 'rag', config: { namespace: 'kb-1' } },
                        r2: { type: 'rag', config: { namespace: 'kb-2' } },
                    },
                },
            },
            [],
        );
        expect(resourceType).toBe('rag');
    });
});

describe('flows/rag_node_test slice', () => {
    it('stores query by nodeId', () => {
        const initial = flowsRagNodeTestSlice.slice.initial;
        const next = flowsRagNodeTestSlice.reducer(initial, {
            type: 'flows/rag_node_test/query_set',
            payload: { nodeId: 'n1', query: 'hello' },
        });
        expect(next.queryByNodeId).toEqual({ n1: 'hello' });
    });
});
