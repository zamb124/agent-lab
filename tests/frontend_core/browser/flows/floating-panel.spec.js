/**
 * Smoke: flows-floating-panel — рендер chrome, collapse, backdrop close, close emit.
 */

import { fixture, fixtureCleanup, html, expect, elementUpdated } from '../helpers/render.js';
import { resetPlatformState } from '../helpers/reset.js';
import { bootstrapPlatformBus } from '@platform/lib/events/index.js';
import { FLOWS_EDITOR_PROPERTY_PANEL_PREFS_KEY } from '../../../../apps/flows/ui/_helpers/flows-editor-property-panel-prefs.js';
import '@platform/lib/components/platform-button.js';
import '../../../../apps/flows/ui/components/editor/flows-floating-panel.js';

function panelButtonByIcon(el, iconName) {
    const buttons = el.shadowRoot.querySelectorAll('.panel-actions platform-button');
    for (const btn of buttons) {
        if (btn.querySelector(`platform-icon[name="${iconName}"]`) !== null) {
            return btn;
        }
    }
    return null;
}

function clickPanelButton(btn) {
    const inner = btn.shadowRoot?.querySelector('button');
    if (inner instanceof HTMLButtonElement) {
        inner.click();
        return;
    }
    btn.click();
}

describe('flows-floating-panel', () => {
    beforeEach(() => {
        resetPlatformState();
        bootstrapPlatformBus({ baseUrl: '', routes: [], slices: {}, effects: [] });
        window.localStorage.removeItem(FLOWS_EDITOR_PROPERTY_PANEL_PREFS_KEY);
    });
    afterEach(() => fixtureCleanup());

    it('рендерит header с title и icon', async () => {
        const el = await fixture(html`
            <flows-floating-panel header-icon="code" header-title="My Node" color-token="var(--accent)">
                <span>Body</span>
            </flows-floating-panel>
        `);
        const name = el.shadowRoot.querySelector('.panel-name');
        expect(name.textContent).to.contain('My Node');
        const slot = el.shadowRoot.querySelector('slot');
        expect(slot).to.not.be.null;
    });

    it('collapse toggle сворачивает body', async () => {
        const el = await fixture(html`
            <flows-floating-panel header-icon="code" header-title="X">
                <span>Body</span>
            </flows-floating-panel>
        `);
        await elementUpdated(el);
        const collapseBtn = panelButtonByIcon(el, 'minimize');
        expect(collapseBtn).to.not.equal(null);
        clickPanelButton(collapseBtn);
        await elementUpdated(el);
        expect(el.hasAttribute('data-collapsed')).to.equal(true);
    });

    it('backdrop click эмитит close только при show-backdrop', async () => {
        const el = await fixture(html`
            <flows-floating-panel
                panel-id="test-backdrop-panel"
                header-icon="code"
                header-title="X"
                show-backdrop
            ></flows-floating-panel>
        `);
        await elementUpdated(el);
        let closed = false;
        el.addEventListener('close', () => { closed = true; });
        const backdrop = el.shadowRoot.querySelector('.panel-backdrop');
        expect(backdrop).to.not.be.null;
        backdrop.click();
        expect(closed).to.equal(true);
    });

    it('без show-backdrop backdrop не рендерится', async () => {
        const el = await fixture(html`
            <flows-floating-panel header-icon="code" header-title="X"></flows-floating-panel>
        `);
        expect(el.shadowRoot.querySelector('.panel-backdrop')).to.be.null;
    });

    it('close-кнопка эмитит close', async () => {
        const el = await fixture(html`
            <flows-floating-panel header-icon="code" header-title="X"></flows-floating-panel>
        `);
        await elementUpdated(el);
        let closed = false;
        el.addEventListener('close', () => { closed = true; });
        const closeBtn = panelButtonByIcon(el, 'close');
        expect(closeBtn).to.not.equal(null);
        clickPanelButton(closeBtn);
        expect(closed).to.equal(true);
    });
});
