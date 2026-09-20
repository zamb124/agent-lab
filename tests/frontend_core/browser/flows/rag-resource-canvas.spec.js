/**
 * RAG resource-нода на канве: инспектор, документы, test-run, скрытые node.files.
 * Состояние — реальные фабрики и события шины. HTTP-effects не регистрируются:
 * list/search приходят как SUCCEEDED/push, как после живого RAG.
 */

import { fixture, fixtureCleanup, html, expect, elementUpdated, waitUntil } from '../helpers/render.js';
import { resetPlatformState, bootstrapTestBus } from '../helpers/reset.js';
import { collectFactories, getPlatformBus, CoreEvents } from '@platform/lib/events/index.js';
import { registerFactory } from '@platform/lib/events/factory-registry.js';
import { platformFileCreateOp } from '@platform/lib/events/factories/platform-file-create.js';
import { codeExecuteOp } from '../../../../apps/flows/ui/events/resources/code.resource.js';
import { editorResource } from '../../../../apps/flows/ui/events/resources/editor.resource.js';
import { resourcesBundleResource } from '../../../../apps/flows/ui/events/resources/resources-bundle.resource.js';
import {
    exceptionAbsorbAllowNamesOp,
    executionLimitsOp,
} from '../../../../apps/flows/ui/events/resources/metadata.resource.js';
import { namespacesResource } from '../../../../core/frontend/static/lib/events/resources/rag-namespaces.resource.js';
import {
    documentsResource,
    documentUploadOp,
    documentRemoveOp,
} from '../../../../core/frontend/static/lib/events/resources/rag-documents.resource.js';
import { documentStatusResource } from '../../../../core/frontend/static/lib/events/resources/rag-document-status.resource.js';
import { searchOp, searchDefaultsOp } from '../../../../core/frontend/static/lib/events/resources/rag-search.resource.js';
import { flowsRagNodeTestSlice } from '../../../../apps/flows/ui/events/resources/rag-node-test.resource.js';
import {
    clearNodeTestRunHandlersForTests,
    registerNodeTestRunHandler,
} from '../../../../apps/flows/ui/_helpers/node-test-run-registry.js';
import { codeExecuteTestRunHandler } from '../../../../apps/flows/ui/_helpers/node-test-run-code-execute.js';
import { ragSearchTestRunHandler } from '../../../../apps/flows/ui/_helpers/node-test-run-rag-search.js';
import flowsEn from '../../../../core/i18n/translations/en/flows.json' with { type: 'json' };
import platformEn from '../../../../core/i18n/translations/en/platform.json' with { type: 'json' };
import '../../../../apps/flows/ui/components/resources/flows-rag-resource-editor.js';
import '../../../../apps/flows/ui/components/nodes/flows-resource-node-editor.js';

const RAG_FACTORIES = [
    namespacesResource,
    searchDefaultsOp,
    documentsResource,
    documentUploadOp,
    documentStatusResource,
    documentRemoveOp,
    searchOp,
    flowsRagNodeTestSlice,
];

const NODE_FACTORIES = [
    ...RAG_FACTORIES,
    editorResource,
    resourcesBundleResource,
    platformFileCreateOp,
    codeExecuteOp,
    exceptionAbsorbAllowNamesOp,
    executionLimitsOp,
];

function bootstrapFactories(factories) {
    for (const factory of factories) {
        registerFactory(factory);
    }
    const collected = collectFactories(factories);
    bootstrapTestBus({ slices: collected.slices, effects: [] });
}

function seedTranslations() {
    const bus = getPlatformBus();
    const previous = bus.getState().i18n.translations.en || {};
    bus.dispatch(
        CoreEvents.I18N_LOCALE_LOADED,
        {
            locale: 'en',
            bundle: {
                ...previous,
                ...platformEn,
                platform: platformEn,
                flows: flowsEn,
            },
        },
        { source: 'system' },
    );
    bus.dispatch(
        CoreEvents.I18N_LOCALE_CHANGED,
        { locale: 'en', default_namespace: 'flows' },
        { source: 'system' },
    );
}

function ragResource(config) {
    return {
        resource_id: 'r1',
        type: 'rag',
        name: 'Knowledge',
        config,
    };
}

async function settleDocuments(el, items) {
    const bus = getPlatformBus();
    bus.dispatch(documentsResource.events.SUCCEEDED, {
        result: { items, total: items.length, limit: 100, offset: 0 },
    });
    await elementUpdated(el);
    await waitUntil(
        () => el.shadowRoot.querySelector('.docs-list, .drop-zone, .hint'),
        'documents section settled',
    );
}

describe('flows-rag-resource-editor on canvas', () => {
    beforeEach(() => {
        resetPlatformState();
        clearNodeTestRunHandlersForTests();
        registerNodeTestRunHandler(codeExecuteTestRunHandler);
        registerNodeTestRunHandler(ragSearchTestRunHandler);
        bootstrapFactories(RAG_FACTORIES);
        seedTranslations();
    });

    afterEach(() => {
        clearNodeTestRunHandlersForTests();
        fixtureCleanup();
    });

    it('disables documents and hides test query without namespace or nodeId', async () => {
        const el = await fixture(html`
            <flows-rag-resource-editor
                .resourceId=${'r1'}
                .resource=${ragResource({})}
            ></flows-rag-resource-editor>
        `);
        await elementUpdated(el);

        const titles = [...el.shadowRoot.querySelectorAll('.section-title')].map((node) => node.textContent);
        expect(titles).to.include(flowsEn.rag_resource_editor.section_documents);
        expect(titles).to.not.include(flowsEn.rag_resource_editor.section_test);
        expect(el.shadowRoot.textContent).to.include(flowsEn.rag_resource_editor.documents_disabled);
        const upload = [...el.shadowRoot.querySelectorAll('platform-button')]
            .find((btn) => btn.getAttribute('aria-label') === flowsEn.rag_resource_editor.documents_upload);
        expect(upload).to.not.equal(undefined);
        expect(upload.disabled).to.equal(true);
    });

    it('throws on upload when namespace is empty', async () => {
        const el = await fixture(html`
            <flows-rag-resource-editor
                .resourceId=${'r1'}
                .resource=${ragResource({})}
            ></flows-rag-resource-editor>
        `);
        await elementUpdated(el);
        expect(() => el._uploadFile(new File(['x'], 'note.txt', { type: 'text/plain' }))).to.throw(
            /namespace required for upload/,
        );
    });

    it('shows document status, chunks and error from the list slice', async () => {
        const el = await fixture(html`
            <flows-rag-resource-editor
                .resourceId=${'r1'}
                .nodeId=${'rag_node'}
                .resource=${ragResource({ namespace: 'kb-support', default_top_k: 5 })}
            ></flows-rag-resource-editor>
        `);
        await elementUpdated(el);
        await settleDocuments(el, [
            {
                document_id: 'doc_ok',
                name: 'policy.pdf',
                status: 'completed',
                chunks_count: 4,
                created_at: '2026-08-01T00:00:00Z',
                metadata: {},
            },
            {
                document_id: 'doc_fail',
                name: 'broken.pdf',
                status: 'failed',
                chunks_count: 0,
                created_at: '2026-08-02T00:00:00Z',
                metadata: { error_message: 'embed failed' },
            },
        ]);

        const rows = [...el.shadowRoot.querySelectorAll('.doc-row')];
        expect(rows).to.have.length(2);
        expect(rows[0].textContent).to.include('policy.pdf');
        expect(rows[0].textContent).to.include(flowsEn.rag_resource_editor.status_completed);
        expect(rows[0].textContent).to.include('4');
        expect(rows[1].textContent).to.include(flowsEn.rag_resource_editor.status_failed);
        expect(rows[1].textContent).to.include('embed failed');
        expect(() => el._renderDocumentRow({ document_id: 'doc_x', status: 'completed' })).to.throw(
            /document name required/,
        );
    });

    it('patches a listed document from rag/document/status_updated', async () => {
        const el = await fixture(html`
            <flows-rag-resource-editor
                .resourceId=${'r1'}
                .nodeId=${'rag_node'}
                .resource=${ragResource({ namespace: 'kb-support', default_top_k: 5 })}
            ></flows-rag-resource-editor>
        `);
        await elementUpdated(el);
        await settleDocuments(el, [
            {
                document_id: 'doc_1',
                name: 'draft.pdf',
                status: 'processing',
                created_at: '2026-08-01T00:00:00Z',
                metadata: {},
            },
        ]);

        getPlatformBus().dispatch('rag/document/status_updated', {
            document_id: 'doc_1',
            namespace_id: 'kb-support',
            status: 'completed',
            document_name: 'draft.pdf',
            chunks_count: 6,
        });
        await elementUpdated(el);

        const row = el.shadowRoot.querySelector('.doc-row');
        expect(row.textContent).to.include(flowsEn.rag_resource_editor.status_completed);
        expect(row.textContent).to.include('6');
    });

    it('writes test query into the slice and renders search hits', async () => {
        const el = await fixture(html`
            <flows-rag-resource-editor
                .resourceId=${'r1'}
                .nodeId=${'rag_node'}
                .resource=${ragResource({ namespace: 'kb-support', default_top_k: 5 })}
            ></flows-rag-resource-editor>
        `);
        await elementUpdated(el);
        await settleDocuments(el, []);

        const queryField = [...el.shadowRoot.querySelectorAll('platform-field')]
            .find((field) => field.label === flowsEn.rag_resource_editor.field_test_query);
        expect(queryField).to.not.equal(undefined);
        queryField.dispatchEvent(new CustomEvent('change', {
            detail: { value: 'return window' },
            bubbles: true,
            composed: true,
        }));
        expect(getPlatformBus().getState().flowsRagNodeTest.queryByNodeId.rag_node).to.equal('return window');

        const bus = getPlatformBus();
        bus.dispatch('flows/rag_node_test/search_bind', { nodeId: 'rag_node' });
        bus.dispatch(searchOp.events.SUCCEEDED, {
            result: {
                results: [
                    {
                        document_name: 'policy.pdf',
                        content: 'Customers may return goods within 14 days.',
                        score: 0.875,
                        page_label: '2',
                    },
                ],
            },
        });
        await elementUpdated(el);

        const card = el.shadowRoot.querySelector('.result-card');
        expect(card).to.not.equal(null);
        expect(card.textContent).to.include('policy.pdf');
        expect(card.textContent).to.include('Customers may return goods within 14 days.');
        expect(card.textContent).to.include('87.5%');
        expect(card.textContent).to.include('2');
    });

    it('shows empty hits copy when search returned no results', async () => {
        const el = await fixture(html`
            <flows-rag-resource-editor
                .resourceId=${'r1'}
                .nodeId=${'rag_node'}
                .resource=${ragResource({ namespace: 'kb-support', default_top_k: 5 })}
            ></flows-rag-resource-editor>
        `);
        await elementUpdated(el);
        const bus = getPlatformBus();
        bus.dispatch('flows/rag_node_test/search_bind', { nodeId: 'rag_node' });
        bus.dispatch(searchOp.events.SUCCEEDED, { result: { results: [] } });
        await elementUpdated(el);
        expect(el.shadowRoot.textContent).to.include(flowsEn.rag_resource_editor.test_results_empty);
    });

    it('throws when a search hit is missing document_name', async () => {
        const el = await fixture(html`
            <flows-rag-resource-editor
                .resourceId=${'r1'}
                .nodeId=${'rag_node'}
                .resource=${ragResource({ namespace: 'kb-support', default_top_k: 5 })}
            ></flows-rag-resource-editor>
        `);
        await elementUpdated(el);
        expect(() => el._renderSearchHit({ content: 'x', score: 0.1 })).to.throw(
            /hit.document_name required/,
        );
    });

    it('throws when a search hit is missing a finite score', async () => {
        const el = await fixture(html`
            <flows-rag-resource-editor
                .resourceId=${'r1'}
                .nodeId=${'rag_node'}
                .resource=${ragResource({ namespace: 'kb-support', default_top_k: 5 })}
            ></flows-rag-resource-editor>
        `);
        await elementUpdated(el);
        expect(() => el._renderSearchHit({
            document_name: 'policy.pdf',
            content: 'x',
        })).to.throw(/hit.score number required/);
    });

    it('shows search and index bind fields and emits default_top_k', async () => {
        const el = await fixture(html`
            <flows-rag-resource-editor
                .resourceId=${'r1'}
                .nodeId=${'rag_node'}
                .resource=${ragResource({ namespace: 'kb-support', default_top_k: 5 })}
            ></flows-rag-resource-editor>
        `);
        await elementUpdated(el);
        const titles = [...el.shadowRoot.querySelectorAll('.section-title')].map((node) => node.textContent);
        expect(titles).to.include(flowsEn.rag_resource_editor.section_search);
        expect(titles).to.include(flowsEn.rag_resource_editor.section_index);
        const topK = [...el.shadowRoot.querySelectorAll('platform-field')]
            .find((field) => field.label === flowsEn.rag_resource_editor.field_default_top_k);
        expect(topK).to.not.equal(undefined);
        expect(topK.value).to.equal(5);
        const patches = [];
        el.addEventListener('change', (event) => {
            if (event.detail && event.detail.resourceId === 'r1') {
                patches.push(event.detail);
            }
        });
        el._onTopK({ detail: { value: 8 } });
        expect(patches).to.deep.equal([{
            resourceId: 'r1',
            patch: { config: { namespace: 'kb-support', default_top_k: 8 } },
        }]);
        expect(() => el._onTopK({ detail: { value: 0 } })).to.throw(/default_top_k >= 1/);
    });
});

describe('flows-resource-node-editor RAG on canvas', () => {
    beforeEach(() => {
        resetPlatformState();
        clearNodeTestRunHandlersForTests();
        registerNodeTestRunHandler(codeExecuteTestRunHandler);
        registerNodeTestRunHandler(ragSearchTestRunHandler);
        bootstrapFactories(NODE_FACTORIES);
        seedTranslations();
        getPlatformBus().dispatch('flows/editor/flow_loaded', {
            branchId: 'base',
            flow: {
                flow_id: 'flow_rag',
                name: 'RAG canvas',
                entry: 'rag_node',
                nodes: {
                    rag_node: {
                        type: 'resource',
                        name: 'Knowledge',
                        resources: { r1: { resource_id: 'r1' } },
                    },
                },
                edges: [],
                resources: {
                    r1: {
                        type: 'rag',
                        name: 'Knowledge',
                        config: { namespace: 'kb-support', default_top_k: 5 },
                    },
                },
            },
        });
    });

    afterEach(() => {
        clearNodeTestRunHandlersForTests();
        fixtureCleanup();
    });

    it('hides node.files and keeps the RAG test query on the resource node', async () => {
        const el = await fixture(html`
            <flows-resource-node-editor
                .nodeId=${'rag_node'}
                .flowId=${'flow_rag'}
                .branchId=${'base'}
                .nodeType=${'resource'}
                .nodeConfig=${{
                    type: 'resource',
                    name: 'Knowledge',
                    resources: { r1: { resource_id: 'r1' } },
                    files: [{ file_id: 'file_1', original_name: 'secret.txt' }],
                }}
                .flowVariables=${{}}
                .graphNodes=${[]}
            ></flows-resource-node-editor>
        `);
        await elementUpdated(el);

        const base = el.shadowRoot.querySelector('flows-base-node-editor');
        expect(base).to.not.equal(null);
        expect(base.shadowRoot.querySelector('.field-pill-file-refs-shell')).to.equal(null);
        expect(base.shadowRoot.textContent).to.not.include(flowsEn.base_node_editor.files_section);

        const rag = el.shadowRoot.querySelector('flows-rag-resource-editor');
        expect(rag).to.not.equal(null);
        expect(rag.nodeId).to.equal('rag_node');
        const titles = [...rag.shadowRoot.querySelectorAll('.section-title')].map((node) => node.textContent);
        expect(titles).to.include(flowsEn.rag_resource_editor.section_documents);
        expect(titles).to.include(flowsEn.rag_resource_editor.section_test);
    });

    it('Play with empty query toasts and does not start search', async () => {
        const el = await fixture(html`
            <flows-resource-node-editor
                .nodeId=${'rag_node'}
                .flowId=${'flow_rag'}
                .branchId=${'base'}
                .nodeType=${'resource'}
                .nodeConfig=${{
                    type: 'resource',
                    name: 'Knowledge',
                    resources: { r1: { resource_id: 'r1' } },
                }}
                .flowVariables=${{}}
                .graphNodes=${[]}
            ></flows-resource-node-editor>
        `);
        await elementUpdated(el);
        const base = el.shadowRoot.querySelector('flows-base-node-editor');
        const toasts = [];
        const stop = getPlatformBus().subscribeType(CoreEvents.UI_TOAST_SHOW, (event) => {
            toasts.push(event.payload);
        });
        await base._runNodeTest();
        stop();
        expect(toasts).to.deep.equal([
            {
                type: 'error',
                i18n_key: 'flows:rag_resource_editor.test_query_required',
                i18n_vars: null,
                duration: null,
            },
        ]);
        expect(getPlatformBus().getState().flowsRagNodeTest.lastNodeId).to.equal(null);
        expect(getPlatformBus().getState().ragSearch.busy).to.equal(false);
    });
});
