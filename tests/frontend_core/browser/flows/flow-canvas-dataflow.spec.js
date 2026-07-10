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
    seedEditorDataflow,
    SAMPLE_BRANCH_NODES,
} from '../../helpers/flows-dataflow-fixtures.js';
import '../../../../apps/flows/ui/components/flow-canvas/flows-flow-canvas.js';

const CANVAS_FACTORIES = [editorResource, editorBulkDeleteOp, stickyNoteUpsertOp];

describe('flows-flow-canvas dataflow smoke', () => {
    beforeEach(() => {
        resetPlatformState();
        for (const factory of CANVAS_FACTORIES) registerFactory(factory);
        const collected = collectFactories(CANVAS_FACTORIES);
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
