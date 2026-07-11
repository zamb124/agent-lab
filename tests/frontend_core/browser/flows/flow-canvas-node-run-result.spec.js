import { fixture, fixtureCleanup, html, expect, elementUpdated } from '../helpers/render.js';
import { resetPlatformState } from '../helpers/reset.js';
import { collectFactories, getPlatformBus } from '@platform/lib/events/index.js';
import { registerFactory } from '@platform/lib/events/factory-registry.js';
import {
    editorResource,
    editorBulkDeleteOp,
    stickyNoteUpsertOp,
} from '../../../../apps/flows/ui/events/resources/editor.resource.js';
import {
    bootstrapFlowsEditor,
    SAMPLE_BRANCH_NODES,
} from '../../helpers/flows-dataflow-fixtures.js';
import '../../../../apps/flows/ui/components/flow-canvas/flows-flow-canvas.js';

const CANVAS_FACTORIES = [editorResource, editorBulkDeleteOp, stickyNoteUpsertOp];

describe('flows-flow-canvas node run result pill', () => {
    beforeEach(() => {
        resetPlatformState();
        for (const factory of CANVAS_FACTORIES) registerFactory(factory);
        const collected = collectFactories(CANVAS_FACTORIES);
        bootstrapFlowsEditor({ slices: collected.slices });
    });
    afterEach(() => fixtureCleanup());

    it('renders result pill under completed node', async () => {
        const bus = getPlatformBus();
        bus.dispatch('flows/editor/flow_loaded', {
            branchId: 'default',
            flow: {
                flow_id: 'flow_test',
                name: 'Test',
                entry: 'code_1',
                nodes: {
                    code_1: { ...SAMPLE_BRANCH_NODES.code_1, pos_x: 0, pos_y: 0 },
                },
                edges: [],
            },
        });

        const el = await fixture(html`<flows-flow-canvas flow-id="flow_test" branch-id="default"></flows-flow-canvas>`);
        await elementUpdated(el);

        bus.dispatch('flows/run/flow_started', { task_id: 't1' });
        bus.dispatch('flows/run/node_started', { node_id: 'code_1', task_id: 't1' });
        bus.dispatch('flows/run/node_completed', {
            node_id: 'code_1',
            node_type: 'code',
            run_index: 0,
            duration_ms: 120,
            result_preview: 'Mock result',
            diff: [],
        });
        await elementUpdated(el);

        const node = el.shadowRoot.querySelector('g.node[data-node-id="code_1"][data-state="completed"]');
        expect(node).to.not.equal(null);

        const pill = node.querySelector('.node-run-result-pill[data-tone="ok"]');
        expect(pill).to.not.equal(null);
        expect(pill.textContent).to.include('Mock result');
    });

    it('renders running pill while node executes', async () => {
        const bus = getPlatformBus();
        bus.dispatch('flows/editor/flow_loaded', {
            branchId: 'default',
            flow: {
                flow_id: 'flow_test',
                name: 'Test',
                entry: 'code_1',
                nodes: {
                    code_1: { ...SAMPLE_BRANCH_NODES.code_1, pos_x: 0, pos_y: 0 },
                },
                edges: [],
            },
        });

        const el = await fixture(html`<flows-flow-canvas flow-id="flow_test" branch-id="default"></flows-flow-canvas>`);
        await elementUpdated(el);

        bus.dispatch('flows/run/node_started', { node_id: 'code_1', task_id: 't1' });
        await elementUpdated(el);

        const pill = el.shadowRoot.querySelector('.node-run-result-pill[data-tone="running"]');
        expect(pill).to.not.equal(null);
    });

    it('hides pill when showCanvasRunResults is false', async () => {
        const bus = getPlatformBus();
        bus.dispatch('flows/editor/flow_loaded', {
            branchId: 'default',
            flow: {
                flow_id: 'flow_test',
                name: 'Test',
                entry: 'code_1',
                nodes: {
                    code_1: { ...SAMPLE_BRANCH_NODES.code_1, pos_x: 0, pos_y: 0 },
                },
                edges: [],
            },
        });
        bus.dispatch('flows/editor/canvas_run_results_toggled', { value: false });

        const el = await fixture(html`<flows-flow-canvas flow-id="flow_test" branch-id="default"></flows-flow-canvas>`);
        await elementUpdated(el);

        bus.dispatch('flows/run/node_completed', {
            node_id: 'code_1',
            result_preview: 'hidden',
            diff: [],
        });
        await elementUpdated(el);

        expect(el.shadowRoot.querySelector('.node-run-result-pill')).to.equal(null);
    });

    it('renders expanded change badges with dynamic pill height', async () => {
        const bus = getPlatformBus();
        bus.dispatch('flows/editor/flow_loaded', {
            branchId: 'default',
            flow: {
                flow_id: 'flow_test',
                name: 'Test',
                entry: 'mcp_1',
                nodes: {
                    mcp_1: {
                        ...SAMPLE_BRANCH_NODES.code_1,
                        node_id: 'mcp_1',
                        node_type: 'mcp',
                        pos_x: 0,
                        pos_y: 0,
                    },
                },
                edges: [],
            },
        });

        const el = await fixture(html`<flows-flow-canvas flow-id="flow_test" branch-id="default"></flows-flow-canvas>`);
        await elementUpdated(el);

        bus.dispatch('flows/run/node_completed', {
            node_id: 'mcp_1',
            node_type: 'mcp',
            run_index: 0,
            duration_ms: 14770,
            result_preview: 'index: ok · 14770 ms',
            primary_field: 'mcp_result',
            diff: [
                {
                    path: 'variables.search_providers_status',
                    old_value: null,
                    new_value: { index: { ok: true, latency_ms: 14770 } },
                    change_type: 'added',
                },
                {
                    path: 'variables.query',
                    old_value: 'old',
                    new_value: 'new',
                    change_type: 'changed',
                },
                {
                    path: 'variables.search_user_query',
                    old_value: null,
                    new_value: 'hello',
                    change_type: 'added',
                },
                {
                    path: 'variables.search_effective_query',
                    old_value: null,
                    new_value: 'hello',
                    change_type: 'added',
                },
                {
                    path: 'variables.search_file_names',
                    old_value: null,
                    new_value: [],
                    change_type: 'added',
                },
            ],
        });
        await elementUpdated(el);

        const node = el.shadowRoot.querySelector('g.node[data-node-id="mcp_1"]');
        expect(node).to.not.equal(null);

        const foreignObject = node.querySelector('foreignObject.node-run-result');
        expect(foreignObject).to.not.equal(null);
        const collapsedHeight = Number.parseFloat(foreignObject.getAttribute('height'));
        expect(collapsedHeight).to.be.greaterThan(44);

        const pill = node.querySelector('.node-run-result-pill[data-tone="ok"]');
        expect(pill).to.not.equal(null);
        expect(pill.textContent).to.include('index: ok');
        expect(pill.textContent).not.to.include('{');
        expect(pill.hasAttribute('data-expanded')).to.equal(false);

        pill.click();
        await elementUpdated(el);

        const pillExpanded = node.querySelector('.node-run-result-pill[data-tone="ok"]');
        expect(pillExpanded.hasAttribute('data-expanded')).to.equal(true);

        const expandedForeignObject = node.querySelector('foreignObject.node-run-result');
        const expandedHeight = Number.parseFloat(expandedForeignObject.getAttribute('height'));
        expect(expandedHeight).to.be.greaterThan(collapsedHeight);

        const addedBadge = node.querySelector('.node-run-result-change[data-change-type="added"] .node-run-result-change-badge');
        expect(addedBadge).to.not.equal(null);
        expect(addedBadge.textContent).to.include('+');

        const changeRows = node.querySelectorAll('.node-run-result-change');
        expect(changeRows.length).to.equal(5);
        expect(expandedHeight).to.be.greaterThan(180);
    });
});
