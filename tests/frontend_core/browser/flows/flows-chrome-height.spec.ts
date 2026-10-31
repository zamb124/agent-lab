/**
 * Flows chrome density contract — shared control heights on editor/evaluation surfaces.
 */

import { fixture, fixtureCleanup, html, expect, elementUpdated, nextFrame } from '../helpers/render.js';
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
import '../../../../apps/flows/ui/components/editor/flows-editor-header.js';
import '../../../../apps/flows/ui/components/interface-editor/flows-interface-toolbar.js';
import { interfaceEditorSlice } from '../../../../apps/flows/ui/events/resources/interface-editor.resource.js';
import '../../../../apps/flows/ui/components/evaluation/flows-evaluation-run-toolbar.js';

const FACTORIES = [editorResource, flowsResource, flowUpdateOp, flowReloadFromBundleOp, branchRemoveOp, interfaceEditorSlice];

function buttonHeight(platformButton) {
    return platformButton.shadowRoot.querySelector('button').getBoundingClientRect().height;
}

describe('flows chrome height canon', () => {
    beforeEach(() => {
        resetPlatformState();
    });

    afterEach(() => {
        fixtureCleanup();
    });

    it('editor header icon-only buttons stay within chrome tier (28–32px)', async () => {
        for (const factory of FACTORIES) {
            registerFactory(factory);
        }
        const collected = collectFactories(FACTORIES);
        bootstrapTestBus({ slices: collected.slices, effects: [] });

        const el = await fixture(html`
            <flows-editor-header flow-id="flow-demo" branch-id="base"></flows-editor-header>
        `);
        await elementUpdated(el);

        const iconButtons = [...el.shadowRoot.querySelectorAll('platform-button[icon-only]')];
        expect(iconButtons.length).to.be.greaterThan(0);

        for (const btn of iconButtons) {
            const height = buttonHeight(btn);
            expect(height).to.be.at.least(27);
            expect(height).to.be.at.most(33);
        }

        const heights = iconButtons.map((btn) => buttonHeight(btn));
        const delta = Math.max(...heights) - Math.min(...heights);
        expect(delta).to.be.at.most(4);
    });

    it('editor header stack height stays within desktop chrome rhythm (≤64px)', async () => {
        for (const factory of FACTORIES) {
            registerFactory(factory);
        }
        const collected = collectFactories(FACTORIES);
        bootstrapTestBus({ slices: collected.slices, effects: [] });

        const wrap = await fixture(html`
            <div style="width: 1440px;">
                <flows-editor-header flow-id="flow-demo" branch-id="base"></flows-editor-header>
            </div>
        `);
        await elementUpdated(wrap);

        const el = wrap.querySelector('flows-editor-header');
        const height = el.getBoundingClientRect().height;
        expect(height).to.be.at.most(64);

        const branches = el.shadowRoot.querySelector('.branches-slot platform-segmented-control');
        expect(branches).to.not.equal(null);
        expect(el.shadowRoot.querySelectorAll('.status-badge').length).to.equal(1);
        expect(el.shadowRoot.querySelectorAll('[data-action="publish"]').length).to.equal(1);
    });

    it('unified chrome with interface tools stays one bar (≤64px) without a second publish', async () => {
        for (const factory of FACTORIES) {
            registerFactory(factory);
        }
        const collected = collectFactories(FACTORIES);
        bootstrapTestBus({ slices: collected.slices, effects: [] });
        getPlatformBus().dispatch('flows/editor/workspace_set', { workspace: 'interface' });

        const wrap = await fixture(html`
            <div style="width: 1440px;">
                <flows-editor-header flow-id="flow-demo" branch-id="base">
                    <flows-interface-toolbar slot="workspace-tools"></flows-interface-toolbar>
                </flows-editor-header>
            </div>
        `);
        await elementUpdated(wrap);
        await nextFrame();

        const el = wrap.querySelector('flows-editor-header');
        expect(el.getBoundingClientRect().height).to.be.at.most(64);
        expect(el.shadowRoot.querySelectorAll('.status-badge').length).to.equal(1);
        expect(el.shadowRoot.querySelectorAll('[data-action="publish"]').length).to.equal(1);
        const toolbar = el.querySelector('flows-interface-toolbar');
        expect(toolbar).to.not.equal(null);
        expect(toolbar.renderRoot.querySelector('.status')).to.equal(null);
        expect(el.querySelectorAll('[data-action="publish"]').length + el.shadowRoot.querySelectorAll('[data-action="publish"]').length).to.equal(1);
    });

    it('evaluation run toolbar shell uses flows toolbar min-height token', async () => {
        bootstrapTestBus();

        const el = await fixture(html`
            <div style="--flows-toolbar-shell-min-height: 48px;">
                <flows-evaluation-run-toolbar
                    branch-id="base"
                    .selectedSuite=${{ suite_id: 's1', name: 'Suite' }}
                    .selectedCase=${{ case_id: 'c1', name: 'Case' }}
                    .caseTemplates=${[]}
                    run-scope="suite"
                    trials="1"
                    max-concurrency="1"
                ></flows-evaluation-run-toolbar>
            </div>
        `);
        await nextFrame();

        const toolbar = el.querySelector('flows-evaluation-run-toolbar').shadowRoot.querySelector('.toolbar-shell');
        expect(toolbar).to.not.equal(null);

        const styles = getComputedStyle(toolbar);
        expect(parseFloat(styles.minHeight)).to.be.closeTo(48, 2);
    });

    it('flow editor page registers the interface editor custom element', async () => {
        const { FlowEditorPage } = await import('../../../../apps/flows/ui/pages/flow-editor-page.js');
        expect(FlowEditorPage).to.be.a('function');
        expect(customElements.get('flows-interface-editor')).to.not.equal(undefined);
        expect(customElements.get('flow-editor-page')).to.not.equal(undefined);
    });
});
