import { fixture, fixtureCleanup, html, expect, elementUpdated, waitUntil } from '../helpers/render.js';
import { resetPlatformState } from '../helpers/reset.js';
import { collectFactories, getPlatformBus, CoreEvents } from '@platform/lib/events/index.js';
import { registerFactory } from '@platform/lib/events/factory-registry.js';
import {
    bootstrapFlowsEditor,
    FLOW_CANVAS_FACTORIES,
    SAMPLE_BRANCH_NODES,
} from '../../helpers/flows-dataflow-fixtures.js';
import flowsEn from '../../../../core/i18n/translations/en/flows.json' with { type: 'json' };
import '@platform/lib/components/platform-modal-stack.js';
import '../../../../apps/flows/ui/components/flow-canvas/flows-flow-canvas.js';
import '../../../../apps/flows/ui/modals/flows-node-run-result-modal.js';

function seedFlowsTranslations() {
    const bus = getPlatformBus();
    const previous = bus.getState().i18n.translations.en || {};
    bus.dispatch(
        CoreEvents.I18N_LOCALE_LOADED,
        { locale: 'en', bundle: { ...previous, flows: flowsEn } },
        { source: 'system' },
    );
    bus.dispatch(
        CoreEvents.I18N_LOCALE_CHANGED,
        { locale: 'en', default_namespace: 'flows' },
        { source: 'system' },
    );
}

describe('flows-flow-canvas node run result pill', () => {
    beforeEach(() => {
        resetPlatformState();
        for (const factory of FLOW_CANVAS_FACTORIES) registerFactory(factory);
        const collected = collectFactories(FLOW_CANVAS_FACTORIES);
        bootstrapFlowsEditor({ slices: collected.slices });
        seedFlowsTranslations();
    });
    afterEach(() => {
        for (const el of document.querySelectorAll('flows-node-run-result-modal')) {
            el.remove();
        }
        fixtureCleanup();
    });

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

        const typeChip = node.querySelector('.node-run-result-type-chip');
        expect(typeChip).to.not.equal(null);

        const changeRows = node.querySelectorAll('.node-run-result-change');
        expect(changeRows.length).to.equal(5);
        expect(expandedHeight).to.be.greaterThan(180);
        expect(pillExpanded.textContent).not.to.include('{');
        expect(pillExpanded.textContent).not.to.include('[');
    });

    it('maximize opens flows.node_run_result modal', async () => {
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

        bus.dispatch('flows/run/node_completed', {
            node_id: 'code_1',
            node_type: 'code',
            run_index: 0,
            duration_ms: 12,
            result_preview: 'ok',
            diff: [
                { path: 'result', old_value: null, new_value: { title: 'x' }, change_type: 'added' },
            ],
        });
        await elementUpdated(el);

        const maximize = el.shadowRoot.querySelector('.node-run-result-maximize');
        expect(maximize).to.not.equal(null);
        maximize.click();
        await elementUpdated(el);

        const stack = bus.getState().modals.stack;
        expect(stack.length).to.be.greaterThan(0);
        expect(stack[stack.length - 1].kind).to.equal('flows.node_run_result');
        expect(stack[stack.length - 1].props.nodeId).to.equal('code_1');
        expect(stack[stack.length - 1].props.runIndex).to.equal(0);
    });

    it('row click opens inspector with selectedPath', async () => {
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

        bus.dispatch('flows/run/node_completed', {
            node_id: 'code_1',
            node_type: 'code',
            run_index: 0,
            diff: [
                { path: 'result', old_value: null, new_value: 'hello', change_type: 'added' },
            ],
        });
        await elementUpdated(el);

        const pill = el.shadowRoot.querySelector('.node-run-result-pill');
        pill.click();
        await elementUpdated(el);

        const row = el.shadowRoot.querySelector('.node-run-result-change[data-path="result"]');
        expect(row).to.not.equal(null);
        row.click();
        await elementUpdated(el);

        const stack = bus.getState().modals.stack;
        expect(stack[stack.length - 1].kind).to.equal('flows.node_run_result');
        expect(stack[stack.length - 1].props.selectedPath).to.equal('result');
    });

    it('two node_completed show latest pill and run count badge', async () => {
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

        bus.dispatch('flows/run/node_completed', {
            node_id: 'code_1',
            node_type: 'code',
            run_index: 0,
            result_preview: 'first run',
            diff: [],
        });
        bus.dispatch('flows/run/node_completed', {
            node_id: 'code_1',
            node_type: 'code',
            run_index: 1,
            result_preview: 'second run',
            diff: [],
        });
        await elementUpdated(el);

        const pills = el.shadowRoot.querySelectorAll('.node-run-result-pill[data-tone="ok"]');
        expect(pills.length).to.equal(1);
        expect(pills[0].textContent).to.include('second run');
        expect(pills[0].textContent).not.to.include('first run');
        const badge = el.shadowRoot.querySelector('.node-run-result-run-badge');
        expect(badge).to.not.equal(null);
        expect(badge.getAttribute('data-run-count')).to.equal('2');
        expect(badge.textContent).to.include('2');
    });

    it('expanded index shows 8 rows and more line, more click opens inspector', async () => {
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
        bus.dispatch('flows/run/node_completed', {
            node_id: 'code_1',
            node_type: 'code',
            run_index: 0,
            result_preview: 'many',
            diff: Array.from({ length: 12 }, (_, index) => ({
                path: `field_${index}`,
                old_value: null,
                new_value: index,
                change_type: 'added',
            })),
        });
        await elementUpdated(el);
        const pill = el.shadowRoot.querySelector('.node-run-result-pill');
        pill.click();
        await elementUpdated(el);
        expect(el.shadowRoot.querySelectorAll('.node-run-result-change').length).to.equal(8);
        const more = el.shadowRoot.querySelector('.node-run-result-more');
        expect(more).to.not.equal(null);
        expect(more.textContent).to.include('4');
        more.click();
        await elementUpdated(el);
        const stack = bus.getState().modals.stack;
        expect(stack[stack.length - 1].kind).to.equal('flows.node_run_result');
        expect(stack[stack.length - 1].props.nodeId).to.equal('code_1');
    });

    it('maximize does not expand pill and run badge opens inspector', async () => {
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
        bus.dispatch('flows/run/node_completed', {
            node_id: 'code_1',
            node_type: 'code',
            run_index: 0,
            result_preview: 'first',
            diff: [],
        });
        bus.dispatch('flows/run/node_completed', {
            node_id: 'code_1',
            node_type: 'code',
            run_index: 1,
            result_preview: 'second',
            diff: [],
        });
        await elementUpdated(el);
        const pill = el.shadowRoot.querySelector('.node-run-result-pill');
        const maximize = el.shadowRoot.querySelector('.node-run-result-maximize');
        maximize.click();
        await elementUpdated(el);
        expect(pill.hasAttribute('data-expanded')).to.equal(false);
        expect(bus.getState().modals.stack[bus.getState().modals.stack.length - 1].kind).to.equal('flows.node_run_result');
        const badge = el.shadowRoot.querySelector('.node-run-result-run-badge');
        badge.click();
        await elementUpdated(el);
        const opened = bus.getState().modals.stack[bus.getState().modals.stack.length - 1];
        expect(opened.props.nodeId).to.equal('code_1');
        expect(opened.props.runIndex).to.equal(1);
    });

    it('expanded height stays compact for huge JSON payload', async () => {
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
        bus.dispatch('flows/run/node_completed', {
            node_id: 'code_1',
            node_type: 'code',
            run_index: 0,
            result_preview: 'huge',
            diff: [{
                path: 'result',
                old_value: null,
                new_value: Array.from({ length: 80 }, (_, index) => ({
                    title: `hit-${index}-${'x'.repeat(200)}`,
                })),
                change_type: 'added',
            }],
        });
        await elementUpdated(el);
        const pill = el.shadowRoot.querySelector('.node-run-result-pill');
        pill.click();
        await elementUpdated(el);
        const height = Number.parseFloat(
            el.shadowRoot.querySelector('foreignObject.node-run-result').getAttribute('height'),
        );
        expect(el.shadowRoot.querySelectorAll('.node-run-result-change').length).to.equal(1);
        expect(pill.textContent).to.include('80');
        expect(pill.textContent).not.to.include('{');
        expect(height).to.be.lessThan(160);
    });

    it('maximize mounts real inspector through platform-modal-stack', async () => {
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
        const host = await fixture(html`
            <div>
                <flows-flow-canvas flow-id="flow_test" branch-id="default"></flows-flow-canvas>
                <platform-modal-stack></platform-modal-stack>
            </div>
        `);
        const canvas = host.querySelector('flows-flow-canvas');
        await elementUpdated(canvas);
        bus.dispatch('flows/run/node_completed', {
            node_id: 'code_1',
            node_type: 'code',
            run_index: 0,
            result_preview: 'ok',
            primary_field: 'result',
            diff: [
                { path: 'result', old_value: null, new_value: { title: 'live' }, change_type: 'added' },
                { path: 'field_extra', old_value: null, new_value: 1, change_type: 'added' },
            ],
        });
        await elementUpdated(canvas);
        canvas.shadowRoot.querySelector('.node-run-result-maximize').click();
        await waitUntil(
            () => document.querySelector('flows-node-run-result-modal'),
            'node run inspector mounted',
        );
        const modal = document.querySelector('flows-node-run-result-modal');
        await elementUpdated(modal);
        expect(modal.shadowRoot.querySelector('.field-row[data-path="result"]')).to.not.equal(null);
        expect(modal.shadowRoot.querySelector('.field-row[data-path="field_extra"]')).to.not.equal(null);
        const valueView = modal.shadowRoot.querySelector('flows-node-run-value-view');
        expect(valueView).to.not.equal(null);
        expect(valueView.shadowRoot.querySelector('flows-json-tree')).to.not.equal(null);
    });
});
