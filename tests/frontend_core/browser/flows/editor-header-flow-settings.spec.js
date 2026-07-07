/**
 * Smoke: flows-editor-header tiered actions + overflow menu.
 */

import { fixture, fixtureCleanup, html, expect, elementUpdated } from '../helpers/render.js';
import { resetPlatformState, bootstrapTestBus } from '../helpers/reset.js';
import { collectFactories } from '@platform/lib/events/factories/register.js';
import { registerFactory } from '@platform/lib/events/factory-registry.js';
import { editorResource } from '../../../../apps/flows/ui/events/resources/editor.resource.js';
import {
    flowsResource,
    flowUpdateOp,
    flowReloadFromBundleOp,
    branchRemoveOp,
} from '../../../../apps/flows/ui/events/resources/flows.resource.js';
import '../../../../apps/flows/ui/components/editor/flows-editor-header.js';

const FACTORIES = [editorResource, flowsResource, flowUpdateOp, flowReloadFromBundleOp, branchRemoveOp];

describe('flows-editor-header flow settings entry', () => {
    beforeEach(() => {
        resetPlatformState();
    });

    afterEach(() => {
        fixtureCleanup();
    });

    it('кнопка flow-settings вызывает openModal(flows.flow_edit)', async () => {
        for (const factory of FACTORIES) {
            registerFactory(factory);
        }
        const collected = collectFactories(FACTORIES);
        bootstrapTestBus({ slices: collected.slices, effects: [] });

        const el = await fixture(html`
            <flows-editor-header flow-id="flow-demo"></flows-editor-header>
        `);
        await elementUpdated(el);

        const btn = el.shadowRoot.querySelector('[data-action="flow-settings"]');
        expect(btn).to.not.equal(null);

        let opened = null;
        el.openModal = (kind, props) => {
            opened = { kind, props };
        };

        btn.click();
        await elementUpdated(el);

        expect(opened).to.deep.equal({ kind: 'flows.flow_edit', props: { flowId: 'flow-demo' } });
    });

    it('desktop header renders overflow anchor and inline branches slot', async () => {
        for (const factory of FACTORIES) {
            registerFactory(factory);
        }
        const collected = collectFactories(FACTORIES);
        bootstrapTestBus({ slices: collected.slices, effects: [] });

        const el = await fixture(html`
            <flows-editor-header flow-id="flow-demo" branch-id="base"></flows-editor-header>
        `);
        await elementUpdated(el);

        const actions = el.shadowRoot.querySelector('.header-actions');
        expect(actions).to.not.equal(null);

        const overflowAnchor = el.shadowRoot.querySelector('.overflow-anchor');
        expect(overflowAnchor).to.not.equal(null);

        const branchesSlot = el.shadowRoot.querySelector('.branches-slot platform-segmented-control');
        expect(branchesSlot).to.not.equal(null);
    });

    it('mobile overflow menu uses block ghost buttons at 390px', async () => {
        for (const factory of FACTORIES) {
            registerFactory(factory);
        }
        const collected = collectFactories(FACTORIES);
        bootstrapTestBus({ slices: collected.slices, effects: [] });

        const el = await fixture(html`
            <flows-editor-header flow-id="flow-demo" branch-id="base"></flows-editor-header>
        `);
        el._isMobile = true;
        el._overflowOpen = true;
        await elementUpdated(el);

        const flyout = el.shadowRoot.querySelector('.menu-flyout');
        expect(flyout).to.not.equal(null);

        const menuButtons = flyout.querySelectorAll('platform-button[block]');
        expect(menuButtons.length).to.be.greaterThan(0);

        const settingsBtn = menuButtons[0];
        expect(settingsBtn.shadowRoot.querySelector('button.ghost')).to.not.equal(null);

        let opened = null;
        el.openModal = (kind, props) => {
            opened = { kind, props };
        };

        settingsBtn.click();
        await elementUpdated(el);

        expect(opened).to.deep.equal({ kind: 'flows.flow_edit', props: { flowId: 'flow-demo' } });
        expect(el._overflowOpen).to.equal(false);
    });

    it('overflow menu exposes API console action', async () => {
        for (const factory of FACTORIES) {
            registerFactory(factory);
        }
        const collected = collectFactories(FACTORIES);
        bootstrapTestBus({ slices: collected.slices, effects: [] });

        const el = await fixture(html`
            <flows-editor-header flow-id="flow-demo" branch-id="base"></flows-editor-header>
        `);
        el._overflowOpen = true;
        await elementUpdated(el);

        const flyout = el.shadowRoot.querySelector('.menu-flyout');
        expect(flyout).to.not.equal(null);

        let opened = null;
        el.openModal = (kind, props) => {
            opened = { kind, props };
        };

        const menuButtons = [...flyout.querySelectorAll('platform-button')];
        expect(menuButtons.length).to.be.greaterThan(2);

        menuButtons[2].click();
        await elementUpdated(el);

        expect(opened).to.deep.equal({
            kind: 'flows.api_console',
            props: { flowId: 'flow-demo', branchId: 'base' },
        });
    });
});
