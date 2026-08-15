import { fixture, fixtureCleanup, html, expect, elementUpdated } from '../helpers/render.js';
import { resetPlatformState } from '../helpers/reset.js';
import { collectFactories, getPlatformBus } from '@platform/lib/events/index.js';
import { registerFactory } from '@platform/lib/events/factory-registry.js';
import {
    bootstrapFlowsEditor,
    FLOW_CANVAS_FACTORIES,
    SAMPLE_BRANCH_NODES,
} from '../../helpers/flows-dataflow-fixtures.js';
import '../../../../apps/flows/ui/components/flow-canvas/flows-flow-canvas.js';

describe('flows-flow-canvas running node orbit', () => {
    beforeEach(() => {
        resetPlatformState();
        for (const factory of FLOW_CANVAS_FACTORIES) registerFactory(factory);
        const collected = collectFactories(FLOW_CANVAS_FACTORIES);
        bootstrapFlowsEditor({ slices: collected.slices });
    });
    afterEach(() => fixtureCleanup());

    it('renders firefly orbit when node is running', async () => {
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

        const runningNode = el.shadowRoot.querySelector('g.node[data-node-id="code_1"][data-state="running"]');
        expect(runningNode).to.not.equal(null);

        const orbit = runningNode.querySelector('.node-run-orbit[data-run-tone="info"]');
        expect(orbit).to.not.equal(null);

        const head = orbit.querySelector('.node-run-firefly-head animateMotion');
        expect(head).to.not.equal(null);
        expect(head.getAttribute('repeatCount')).to.equal('indefinite');

        const arc = orbit.querySelector('.node-run-arc');
        expect(arc).to.not.equal(null);
        expect(arc.getAttribute('pathLength')).to.equal('100');
    });

    it('renders warning-toned orbit on breakpoint hit', async () => {
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

        bus.dispatch('flows/breakpoint/hit', { node_id: 'code_1' });
        await elementUpdated(el);

        const hitNode = el.shadowRoot.querySelector('g.node[data-node-id="code_1"][data-state="breakpoint-hit"]');
        expect(hitNode).to.not.equal(null);

        const orbit = hitNode.querySelector('.node-run-orbit[data-run-tone="warning"]');
        expect(orbit).to.not.equal(null);
        expect(orbit.querySelector('.node-run-firefly-head')).to.not.equal(null);
    });
});
