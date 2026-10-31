import { fixture, fixtureCleanup, html, expect, elementUpdated } from '../helpers/render.js';
import { resetPlatformState, bootstrapTestBus } from '../helpers/reset.js';
import { collectFactories, getPlatformBus } from '@platform/lib/events/index.js';
import { registerFactory } from '@platform/lib/events/factory-registry.js';
import { editorResource } from '../../../../apps/flows/ui/events/resources/editor.resource.js';
import {
    flowsResource,
    flowUpdateOp,
    flowReloadFromBundleOp,
    branchRemoveOp,
} from '../../../../apps/flows/ui/events/resources/flows.resource.js';
import {
    SAMPLE_DATAFLOW_NODES,
} from '../../helpers/flows-dataflow-fixtures.js';
import '../../../../apps/flows/ui/components/editor/flows-editor-header.js';

const FACTORIES = [editorResource, flowsResource, flowUpdateOp, flowReloadFromBundleOp, branchRemoveOp];

describe('flows-editor-header problems flyout', () => {
    beforeEach(() => resetPlatformState());
    afterEach(() => fixtureCleanup());

    function bootstrapHeader() {
        for (const factory of FACTORIES) registerFactory(factory);
        const collected = collectFactories(FACTORIES);
        bootstrapTestBus({ slices: collected.slices, effects: [] });
        return getPlatformBus();
    }

    it('shows problems badge when dataflow has issues', async () => {
        const bus = bootstrapHeader();
        bus.dispatch('flows/editor/flow_loaded', {
            branchId: 'default',
            flow: {
                flow_id: 'flow_test',
                name: 'Test Flow',
                entry: 'broken_1',
                nodes: { broken_1: { type: 'llm_node', name: 'Broken' } },
                edges: [],
            },
        });
        bus.dispatch('flows/editor/dataflow_set', { dataflow: { nodes: SAMPLE_DATAFLOW_NODES } });

        const el = await fixture(html`<flows-editor-header flow-id="flow_test"></flows-editor-header>`);
        await elementUpdated(el);

        const btn = el.shadowRoot.querySelector('.problems-btn');
        expect(btn).to.not.equal(null);
        expect(el.shadowRoot.querySelector('.problems-count').textContent).to.equal('2');
    });

    it('opens flyout and navigates to problem node', async () => {
        const bus = bootstrapHeader();
        bus.dispatch('flows/editor/flow_loaded', {
            branchId: 'default',
            flow: {
                flow_id: 'flow_test',
                name: 'Test Flow',
                entry: 'broken_1',
                nodes: { broken_1: { type: 'llm_node', name: 'Broken' } },
                edges: [],
            },
        });
        bus.dispatch('flows/editor/dataflow_set', { dataflow: { nodes: SAMPLE_DATAFLOW_NODES } });

        const el = await fixture(html`<flows-editor-header flow-id="flow_test"></flows-editor-header>`);
        await elementUpdated(el);

        el.shadowRoot.querySelector('.problems-btn').click();
        await elementUpdated(el);
        expect(el.shadowRoot.querySelector('.problems-flyout')).to.not.equal(null);

        const item = el.shadowRoot.querySelector('.problem-item');
        item.click();
        await elementUpdated(el);
        expect(el._problemsOpen).to.equal(false);
    });

    it('shows a single draft badge when interfaceDirty is set and merges UI problems into the flyout', async () => {
        const bus = bootstrapHeader();
        bus.dispatch('flows/editor/flow_loaded', {
            branchId: 'default',
            flow: {
                flow_id: 'flow_test',
                name: 'Test Flow',
                entry: 'broken_1',
                nodes: { broken_1: { type: 'llm_node', name: 'Broken' } },
                edges: [],
            },
        });
        bus.dispatch('flows/editor/dataflow_set', { dataflow: { nodes: SAMPLE_DATAFLOW_NODES } });

        const el = await fixture(html`<flows-editor-header
            flow-id="flow_test"
            .interfaceDirty=${true}
            .interfaceProblems=${[{ code: 'inputs_without_action', severity: 'error', pageId: 'main', blockId: null, params: {} }]}
        ></flows-editor-header>`);
        await elementUpdated(el);

        expect(el.shadowRoot.querySelectorAll('.status-badge').length).to.equal(1);
        expect(el.shadowRoot.querySelector('.status-badge').getAttribute('data-status')).to.equal('dirty');
        expect(el.shadowRoot.querySelector('.problems-count').textContent).to.equal('3');
    });
});
