import { fixture, fixtureCleanup, html, expect, elementUpdated } from '../helpers/render.js';
import { resetPlatformState } from '../helpers/reset.js';
import { collectFactories, getPlatformBus } from '@platform/lib/events/index.js';
import { registerFactory } from '@platform/lib/events/factory-registry.js';
import {
    bootstrapFlowsEditor,
    FLOW_CANVAS_FACTORIES,
    seedEditorDataflow,
    SAMPLE_DATAFLOW_NODES,
    SAMPLE_BRANCH_NODES,
} from '../../helpers/flows-dataflow-fixtures.js';
import '../../../../apps/flows/ui/components/flow-canvas/flows-flow-canvas.js';

describe('flows-flow-canvas dataflow smoke', () => {
    beforeEach(() => {
        resetPlatformState();
        for (const factory of FLOW_CANVAS_FACTORIES) registerFactory(factory);
        const collected = collectFactories(FLOW_CANVAS_FACTORIES);
        bootstrapFlowsEditor({ slices: collected.slices });
    });
    afterEach(() => fixtureCleanup());

    it('renders data wires layer when showDataWires is enabled', async () => {
        const bus = getPlatformBus();
        bus.dispatch('flows/editor/flow_loaded', {
            branchId: 'default',
            flow: {
                flow_id: 'flow_test',
                name: 'Test',
                entry: 'code_1',
                nodes: {
                    code_1: { ...SAMPLE_BRANCH_NODES.code_1, pos_x: 0, pos_y: 0 },
                    llm_1: { ...SAMPLE_BRANCH_NODES.llm_1, pos_x: 300, pos_y: 0 },
                },
                edges: [{ from_node: 'code_1', to_node: 'llm_1' }],
            },
        });
        seedEditorDataflow(bus);
        bus.dispatch('flows/editor/data_wires_toggled', {});

        const el = await fixture(html`<flows-flow-canvas flow-id="flow_test" branch-id="default"></flows-flow-canvas>`);
        await elementUpdated(el);

        const wiresLayer = el.shadowRoot.querySelector('.data-wires-layer');
        expect(wiresLayer).to.not.equal(null);
        expect(wiresLayer.children.length).to.be.greaterThan(0);
    });

    it('renders output chip hit targets for pointer wire drag', async () => {
        const bus = getPlatformBus();
        bus.dispatch('flows/editor/flow_loaded', {
            branchId: 'default',
            flow: {
                flow_id: 'flow_test',
                name: 'Test',
                entry: 'code_1',
                nodes: {
                    code_1: { ...SAMPLE_BRANCH_NODES.code_1, pos_x: 0, pos_y: 0 },
                    llm_1: { ...SAMPLE_BRANCH_NODES.llm_1, pos_x: 300, pos_y: 0 },
                },
                edges: [{ from_node: 'code_1', to_node: 'llm_1' }],
            },
        });
        seedEditorDataflow(bus);

        const el = await fixture(html`<flows-flow-canvas flow-id="flow_test" branch-id="default"></flows-flow-canvas>`);
        await elementUpdated(el);

        const hits = el.shadowRoot.querySelectorAll('.node-dataflow-chip-hit');
        expect(hits.length).to.be.greaterThan(0);
        const inputHits = el.shadowRoot.querySelectorAll('.node-dataflow-chip-hit[data-chip-side="in"]');
        expect(inputHits.length).to.be.greaterThan(0);
    });

    it('highlights connected data wires when hovering a chip', async () => {
        const bus = getPlatformBus();
        bus.dispatch('flows/editor/flow_loaded', {
            branchId: 'default',
            flow: {
                flow_id: 'flow_test',
                name: 'Test',
                entry: 'code_1',
                nodes: {
                    code_1: { ...SAMPLE_BRANCH_NODES.code_1, pos_x: 0, pos_y: 0 },
                    llm_1: { ...SAMPLE_BRANCH_NODES.llm_1, pos_x: 300, pos_y: 0 },
                },
                edges: [{ from_node: 'code_1', to_node: 'llm_1' }],
            },
        });
        seedEditorDataflow(bus);
        bus.dispatch('flows/editor/data_wires_toggled', {});

        const el = await fixture(html`<flows-flow-canvas flow-id="flow_test" branch-id="default"></flows-flow-canvas>`);
        await elementUpdated(el);

        const outputHit = el.shadowRoot.querySelector(
            'rect.node-dataflow-chip-hit[data-chip-node-id="code_1"][data-chip-side="out"]',
        );
        expect(outputHit).to.not.equal(null);
        outputHit.dispatchEvent(new PointerEvent('pointerenter', { bubbles: true }));
        await elementUpdated(el);

        const highlighted = el.shadowRoot.querySelector('.data-wire-path[data-highlighted]');
        expect(highlighted).to.not.equal(null);
        const dimmed = el.shadowRoot.querySelectorAll('.data-wire-path[data-dimmed]');
        expect(dimmed.length).to.equal(0);
    });

    it('highlights all variable wires when hovering input chip on downstream consumer (fan-out)', async () => {
        const bus = getPlatformBus();
        bus.dispatch('flows/editor/flow_loaded', {
            branchId: 'default',
            flow: {
                flow_id: 'flow_test',
                name: 'Test',
                entry: 'code_1',
                nodes: {
                    code_1: { ...SAMPLE_BRANCH_NODES.code_1, pos_x: 0, pos_y: 0 },
                    llm_1: { ...SAMPLE_BRANCH_NODES.llm_1, pos_x: 300, pos_y: 0 },
                    llm_2: { ...SAMPLE_BRANCH_NODES.llm_1, name: 'LLM 2', pos_x: 300, pos_y: 200 },
                },
                edges: [
                    { from_node: 'code_1', to_node: 'llm_1' },
                    { from_node: 'code_1', to_node: 'llm_2' },
                ],
            },
        });
        bus.dispatch('flows/editor/dataflow_set', {
            dataflow: {
                nodes: {
                    ...SAMPLE_DATAFLOW_NODES,
                    llm_2: {
                        incoming_state: [{ path: 'topic', type: 'string', source: 'previous' }],
                        input_mapping: [{
                            target: 'topic',
                            source: '@state:topic',
                            source_kind: 'state',
                            source_path: 'topic',
                            status: 'ok',
                            producers: ['code_1'],
                        }],
                        writes: [],
                        issues: [],
                        canvas: {
                            inputs: [{
                                label: 'topic',
                                type: 'string',
                                status: 'ok',
                                required: true,
                                producer_node: 'code_1',
                            }],
                            outputs: [],
                            has_issues: false,
                            error_count: 0,
                            warning_count: 0,
                        },
                        required_inputs: [],
                    },
                },
            },
        });
        bus.dispatch('flows/editor/data_wires_toggled', {});

        const el = await fixture(html`<flows-flow-canvas flow-id="flow_test" branch-id="default"></flows-flow-canvas>`);
        await elementUpdated(el);

        const inputHit = el.shadowRoot.querySelector(
            'rect.node-dataflow-chip-hit[data-chip-node-id="llm_2"][data-chip-side="in"]',
        );
        expect(inputHit).to.not.equal(null);
        inputHit.dispatchEvent(new PointerEvent('pointerenter', { bubbles: true }));
        await elementUpdated(el);

        const highlighted = el.shadowRoot.querySelectorAll('.data-wire-path[data-highlighted]');
        expect(highlighted.length).to.equal(2);
        const dimmed = el.shadowRoot.querySelectorAll('.data-wire-path[data-dimmed]');
        expect(dimmed.length).to.equal(0);
    });

    it('renders problems badge on node with canvas issues', async () => {
        const bus = getPlatformBus();
        bus.dispatch('flows/editor/flow_loaded', {
            branchId: 'default',
            flow: {
                flow_id: 'flow_test',
                name: 'Test',
                entry: 'broken_1',
                nodes: {
                    broken_1: { ...SAMPLE_BRANCH_NODES.broken_1, pos_x: 0, pos_y: 0 },
                },
                edges: [],
            },
        });
        seedEditorDataflow(bus);

        const el = await fixture(html`<flows-flow-canvas flow-id="flow_test" branch-id="default"></flows-flow-canvas>`);
        await elementUpdated(el);

        const badge = el.shadowRoot.querySelector('.badge-problems');
        expect(badge).to.not.equal(null);
    });
});
