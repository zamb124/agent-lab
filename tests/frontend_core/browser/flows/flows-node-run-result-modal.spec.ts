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
import '../../../../apps/flows/ui/modals/flows-node-run-result-modal.js';
import {q, qs, qsa, shadow, type TestEl} from '../helpers/dom.js';

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

function loadCodeNode() {
    getPlatformBus().dispatch('flows/editor/flow_loaded', {
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
}

describe('flows-node-run-result-modal', () => {
    beforeEach(() => {
        resetPlatformState();
        for (const factory of FLOW_CANVAS_FACTORIES) registerFactory(factory);
        const collected = collectFactories(FLOW_CANVAS_FACTORIES);
        bootstrapFlowsEditor({ slices: collected.slices });
        seedFlowsTranslations();
    });
    afterEach(() => {
        for (const el of qsa(document!, 'flows-node-run-result-modal')) {
            el.remove();
        }
        fixtureCleanup();
    });

    function captureBusEvents() {
        const events: any[] = [];
        getPlatformBus().subscribeAny((e: any) => events.push(e));
        return events;
    }

    async function typeSearch(modal: any, text: any) {
        const search = qs(shadow(modal), 'platform-modal-search-field');
        expect(search).to.not.equal(null);
        const field = qs(shadow(search)!, 'platform-field');
        const inner = qs(shadow(field)!, 'platform-field-string');
        const input = qs(shadow(inner)!, 'input.field-pill-input');
        (input as TestEl).value = text;
        input!.dispatchEvent(new Event('input', { bubbles: true, composed: true }));
        await elementUpdated(modal);
    }

    it('selects path, switches runs, toggles tree/json, shows markdown and copy', async () => {
        const bus = getPlatformBus();
        loadCodeNode();
        bus.dispatch('flows/run/node_completed', {
            node_id: 'code_1',
            node_type: 'code',
            run_index: 0,
            duration_ms: 10,
            result_preview: 'first',
            diff: [
                {
                    path: 'result',
                    old_value: { a: 1 },
                    new_value: { a: 1, nested: { b: 2 } },
                    change_type: 'changed',
                },
            ],
        });
        bus.dispatch('flows/run/node_completed', {
            node_id: 'code_1',
            node_type: 'code',
            run_index: 1,
            duration_ms: 20,
            result_preview: 'second',
            diff: [
                {
                    path: 'markdown',
                    old_value: null,
                    new_value: '# Title\n\nSee [docs](https://example.com)',
                    change_type: 'added',
                },
            ],
        });

        const modal = await fixture<TestEl>(html`
            <flows-node-run-result-modal
                .nodeId=${'code_1'}
                .runIndex=${1}
                .selectedPath=${'markdown'}
                .open=${true}
            ></flows-node-run-result-modal>
        `);
        await elementUpdated(modal);

        expect(q(shadow(modal), '.field-row[data-path="markdown"][data-active="true"]')).to.not.equal(null);
        const markdownView = qs(shadow(modal), 'flows-node-run-value-view');
        expect(markdownView).to.not.equal(null);
        expect(q(shadow(markdownView)!, 'platform-markdown-editor')).to.not.equal(null);

        const firstRun = q(shadow(modal), '.run-row[data-run-index="0"]');
        expect(firstRun).to.not.equal(null);
        (firstRun as TestEl).click();
        await elementUpdated(modal);

        expect(q(shadow(modal), '.field-row[data-path="result"]')).to.not.equal(null);
        const valueView = qs(shadow(modal), 'flows-node-run-value-view');
        expect(q(shadow(valueView)!, 'flows-json-tree')).to.not.equal(null);

        const treeRow = qs(shadow(qs(shadow(valueView)!, 'flows-json-tree')), '.row[data-path="result.nested"]');
        expect(treeRow).to.not.equal(null);
        (treeRow as TestEl).click();
        await elementUpdated(modal);
        await elementUpdated(valueView)!;
        const nestedChildren = qs(shadow(qs(shadow(valueView)!, 'flows-json-tree')), '.row[data-path="result.nested.b"]');
        expect(nestedChildren).to.not.equal(null);

        const jsonToggle = qs(shadow(valueView)!, 'platform-segmented-control');
        const jsonSegment = qs(shadow(jsonToggle)!, 'button.segment[aria-label="JSON"]');
        expect(jsonSegment).to.not.equal(null);
        (jsonSegment as TestEl).click();
        await elementUpdated(valueView)!;
        expect(q(shadow(valueView)!, 'platform-json-editor')).to.not.equal(null);

        const events = captureBusEvents();
        const copyBtn = q(shadow(modal), 'platform-button[aria-label="Copy selected value"]');
        expect(copyBtn).to.not.equal(null);
        (copyBtn as TestEl).click();
        await elementUpdated(modal);
        const copied = events.find((event) => event.type === CoreEvents.UI_CLIPBOARD_COPY_REQUESTED);
        expect(copied).to.not.equal(undefined);
        expect(copied.payload.text).to.include('"nested"');
        expect(copied.payload.success_i18n_key).to.equal('flows:node_run_result_modal.toast_copied');
    });

    it('shows every field of a long diff and filters by search', async () => {
        const bus = getPlatformBus();
        loadCodeNode();
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
        const modal = await fixture<TestEl>(html`
            <flows-node-run-result-modal .nodeId=${'code_1'} .runIndex=${0} .open=${true}></flows-node-run-result-modal>
        `);
        await elementUpdated(modal);
        expect(qsa(shadow(modal), '.field-row').length).to.equal(12);
        await typeSearch(modal, 'field_11');
        const visible = qsa(shadow(modal), '.field-row');
        expect(visible.length).to.equal(1);
        expect(visible[0]!.getAttribute('data-path')).to.equal('field_11');
    });

    it('changed field switches old/new through segmented control', async () => {
        const bus = getPlatformBus();
        loadCodeNode();
        bus.dispatch('flows/run/node_completed', {
            node_id: 'code_1',
            node_type: 'code',
            run_index: 0,
            result_preview: 'changed',
            diff: [{
                path: 'result',
                old_value: { a: 1 },
                new_value: { a: 1, nested: { b: 2 } },
                change_type: 'changed',
            }],
        });
        const modal = await fixture<TestEl>(html`
            <flows-node-run-result-modal
                .nodeId=${'code_1'}
                .runIndex=${0}
                .selectedPath=${'result'}
                .open=${true}
            ></flows-node-run-result-modal>
        `);
        await elementUpdated(modal);
        const valueView = qs(shadow(modal), 'flows-node-run-value-view');
        expect(q(shadow(qs(shadow(valueView)!, 'flows-json-tree')), '.row[data-path="result.nested"]')).to.not.equal(null);
        const sideControl = qs(shadow(modal), '.viewer-toolbar platform-segmented-control');
        const oldSegment = q(shadow(sideControl), 'button.segment[aria-label="Before"]');
        (oldSegment as TestEl).click();
        await elementUpdated(modal);
        await elementUpdated(valueView)!;
        expect(q(shadow(qs(shadow(valueView)!, 'flows-json-tree')), '.row[data-path="result.nested"]')).to.equal(null);
        expect(q(shadow(qs(shadow(valueView)!, 'flows-json-tree')), '.row[data-path="result.a"]')).to.not.equal(null);
    });

    it('follows latest run only when the cursor was on previous latest', async () => {
        const bus = getPlatformBus();
        loadCodeNode();
        bus.dispatch('flows/run/node_completed', {
            node_id: 'code_1',
            node_type: 'code',
            run_index: 0,
            result_preview: 'first',
            diff: [{ path: 'one', old_value: null, new_value: 1, change_type: 'added' }],
        });
        bus.dispatch('flows/run/node_completed', {
            node_id: 'code_1',
            node_type: 'code',
            run_index: 1,
            result_preview: 'second',
            diff: [{ path: 'two', old_value: null, new_value: 2, change_type: 'added' }],
        });
        const following = await fixture<TestEl>(html`
            <flows-node-run-result-modal .nodeId=${'code_1'} .runIndex=${1} .open=${true}></flows-node-run-result-modal>
        `);
        await elementUpdated(following);
        expect(q(shadow(following), '.run-row[data-run-index="1"][data-active="true"]')).to.not.equal(null);
        bus.dispatch('flows/run/node_completed', {
            node_id: 'code_1',
            node_type: 'code',
            run_index: 2,
            result_preview: 'third',
            diff: [{ path: 'three', old_value: null, new_value: 3, change_type: 'added' }],
        });
        await elementUpdated(following);
        expect(q(shadow(following), '.run-row[data-run-index="2"][data-active="true"]')).to.not.equal(null);
        expect(q(shadow(following), '.field-row[data-path="three"]')).to.not.equal(null);

        const pinned = await fixture<TestEl>(html`
            <flows-node-run-result-modal .nodeId=${'code_1'} .runIndex=${0} .open=${true}></flows-node-run-result-modal>
        `);
        await elementUpdated(pinned);
        expect(q(shadow(pinned), '.run-row[data-run-index="0"][data-active="true"]')).to.not.equal(null);
        bus.dispatch('flows/run/node_completed', {
            node_id: 'code_1',
            node_type: 'code',
            run_index: 3,
            result_preview: 'fourth',
            diff: [{ path: 'four', old_value: null, new_value: 4, change_type: 'added' }],
        });
        await elementUpdated(pinned);
        expect(q(shadow(pinned), '.run-row[data-run-index="0"][data-active="true"]')).to.not.equal(null);
        expect(q(shadow(pinned), '.field-row[data-path="one"]')).to.not.equal(null);
        expect(q(shadow(pinned), '.field-row[data-path="four"]')).to.equal(null);
    });

    it('rejects unknown nodeId without opening an empty inspector', async () => {
        loadCodeNode();
        const modal = (document.createElement('flows-node-run-result-modal') as TestEl);
        modal.nodeId = 'missing_node';
        modal.open = true;
        document.body.append(modal);
        const failure = modal.updateComplete.then(
            () => {
                throw new Error('flows-node-run-result-modal: expected throw for missing node');
            },
            (error: any) => error,
        );
        const error = await failure;
        modal.remove();
        expect(String(error.message)).to.include('no runs for node missing_node');
    });

    it('error kind shows error panel without field list', async () => {
        const bus = getPlatformBus();
        loadCodeNode();
        bus.dispatch('flows/run/node_failed', {
            node_id: 'code_1',
            node_type: 'code',
            run_index: 0,
            error: 'ValueError: boom',
            duration_ms: 8,
        });

        const modal = await fixture<TestEl>(html`
            <flows-node-run-result-modal
                .nodeId=${'code_1'}
                .runIndex=${0}
                .open=${true}
            ></flows-node-run-result-modal>
        `);
        await elementUpdated(modal);

        expect(qs(shadow(modal), '.error-text').textContent).to.include('ValueError: boom');
        expect(q(shadow(modal), '.fields-pane')).to.equal(null);
        expect(q(shadow(modal), '.viewer-toolbar')).to.equal(null);
    });
});
