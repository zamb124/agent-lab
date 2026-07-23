/**
 * Smoke: flows-editor-header tiered actions + overflow menu.
 */

import { fixture, fixtureCleanup, html, expect, elementUpdated } from '../helpers/render.js';
import { resetPlatformState, bootstrapTestBus } from '../helpers/reset.js';
import { CoreEvents } from '@platform/lib/events/contract.js';
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
        document.querySelectorAll('.flows-editor-header-menu-portal').forEach((node) => node.remove());
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

        const branchesScroll = el.shadowRoot.querySelector('.branches-slot .branches-scroll');
        const branchesAdd = el.shadowRoot.querySelector('.branches-slot .branches-add');
        expect(branchesScroll).to.not.equal(null);
        expect(branchesAdd).to.not.equal(null);
        expect(branchesScroll.contains(branchesSlot)).to.equal(true);
    });

    it('overflow anchor не поднимает глобальный z-index без открытого меню', async () => {
        for (const factory of FACTORIES) {
            registerFactory(factory);
        }
        const collected = collectFactories(FACTORIES);
        bootstrapTestBus({ slices: collected.slices, effects: [] });

        const el = await fixture(html`
            <flows-editor-header flow-id="flow-demo" branch-id="base"></flows-editor-header>
        `);
        await elementUpdated(el);

        const overflowAnchor = el.shadowRoot.querySelector('.overflow-anchor');
        expect(overflowAnchor).to.not.equal(null);
        expect(overflowAnchor.hasAttribute('data-open')).to.equal(false);
        expect(window.getComputedStyle(overflowAnchor).zIndex).to.equal('auto');
    });

    it('overflow menu закрывается при UI_MODAL_OPEN', async () => {
        for (const factory of FACTORIES) {
            registerFactory(factory);
        }
        const collected = collectFactories(FACTORIES);
        const bus = bootstrapTestBus({ slices: collected.slices, effects: [] });

        const el = await fixture(html`
            <flows-editor-header flow-id="flow-demo" branch-id="base"></flows-editor-header>
        `);
        el._overflowOpen = true;
        await elementUpdated(el);

        bus.dispatch(CoreEvents.UI_MODAL_OPEN, { kind: 'flows.flow_edit', props: { flowId: 'flow-demo' } });
        await elementUpdated(el);

        expect(el._overflowOpen).to.equal(false);
        expect(document.body.querySelector('.flows-editor-header-menu-portal')).to.equal(null);
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

        const flyout = document.body.querySelector('.flows-editor-header-menu-portal');
        expect(flyout).to.not.equal(null);

        const menuButtons = flyout.querySelectorAll('platform-button[block]');
        expect(menuButtons.length).to.be.greaterThan(1);

        const employeeBtn = menuButtons[0];
        const settingsBtn = menuButtons[1];
        expect(settingsBtn.shadowRoot.querySelector('button.ghost')).to.not.equal(null);

        let opened = null;
        el.openModal = (kind, props) => {
            opened = { kind, props };
        };

        employeeBtn.click();
        await elementUpdated(el);
        expect(opened).to.deep.equal({ kind: 'flows.employee_settings', props: { flowId: 'flow-demo' } });
        expect(el._overflowOpen).to.equal(false);

        el._overflowOpen = true;
        await elementUpdated(el);
        const flyoutAgain = document.body.querySelector('.flows-editor-header-menu-portal');
        expect(flyoutAgain).to.not.equal(null);
        const settingsBtnAgain = flyoutAgain.querySelectorAll('platform-button[block]')[1];
        opened = null;
        settingsBtnAgain.click();
        await elementUpdated(el);

        expect(opened).to.deep.equal({ kind: 'flows.flow_edit', props: { flowId: 'flow-demo' } });
        expect(el._overflowOpen).to.equal(false);
    });

    it('overflow menu exposes guest preview share action', async () => {
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

        const flyout = document.body.querySelector('.flows-editor-header-menu-portal');
        expect(flyout).to.not.equal(null);

        let opened = null;
        el.openModal = (kind, props) => {
            opened = { kind, props };
        };

        const menuButtons = [...flyout.querySelectorAll('platform-button')];
        expect(menuButtons.length).to.be.greaterThan(0);

        menuButtons[0].click();
        await elementUpdated(el);

        expect(opened).to.deep.equal({
            kind: 'flows.preview_share',
            props: { flowId: 'flow-demo', branchId: 'default' },
        });
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

        const flyout = document.body.querySelector('.flows-editor-header-menu-portal');
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
