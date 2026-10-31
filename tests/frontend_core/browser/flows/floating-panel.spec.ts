/**
 * Smoke: flows-floating-panel — рендер chrome, collapse, backdrop close, close emit,
 * assistant column resize.
 */

import { fixture, fixtureCleanup, html, expect, elementUpdated } from '../helpers/render.js';
import { resetPlatformState } from '../helpers/reset.js';
import { bootstrapPlatformBus } from '@platform/lib/events/index.js';
import {
    ASSISTANT_COL_WIDTH_DEFAULT,
    FLOWS_EDITOR_PROPERTY_PANEL_PREFS_KEY,
} from '../../../../apps/flows/ui/_helpers/flows-editor-property-panel-prefs.js';
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

function readPrefsRoot() {
    const raw = window.localStorage.getItem(FLOWS_EDITOR_PROPERTY_PANEL_PREFS_KEY);
    if (raw === null) {
        return {};
    }
    return JSON.parse(raw);
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

    it('без ai-active handle ассистента не рендерится', async () => {
        const el = await fixture(html`
            <flows-floating-panel
                panel-id="assistant-closed"
                header-icon="code"
                header-title="X"
                ai-enabled
            ></flows-floating-panel>
        `);
        await elementUpdated(el);
        expect(el.shadowRoot.querySelector('.assistant-resize-handle')).to.be.null;
    });

    it('при ai-active показывает handle и drag меняет ширину + localStorage', async () => {
        const el = await fixture(html`
            <flows-floating-panel
                panel-id="assistant-resize"
                header-icon="code"
                header-title="X"
                ai-enabled
                ai-active
            >
                <div slot="editor">Editor</div>
                <div slot="assistant">Chat</div>
            </flows-floating-panel>
        `);
        await elementUpdated(el);

        const handle = el.shadowRoot.querySelector('.assistant-resize-handle');
        expect(handle).to.not.be.null;
        expect(el.style.getPropertyValue('--panel-assistant-width')).to.equal(
            `${ASSISTANT_COL_WIDTH_DEFAULT}px`,
        );

        handle.setPointerCapture = () => {};
        handle.releasePointerCapture = () => {};
        handle.hasPointerCapture = () => false;

        el._panelViewport = () => ({ width: 1800, height: 1000 });
        el._applyFloatingPanelRect({
            left: 24,
            top: 24,
            width: 1400,
            height: 800,
        });
        const widthBefore = el._panelRect?.width;

        const startX = 900;
        handle.dispatchEvent(new PointerEvent('pointerdown', {
            pointerId: 21,
            button: 0,
            clientX: startX,
            clientY: 200,
            bubbles: true,
            cancelable: true,
        }));
        // Влево — шире чат за счёт editor; outer panel width не меняется
        window.dispatchEvent(new PointerEvent('pointermove', {
            pointerId: 21,
            clientX: startX - 70,
            clientY: 200,
        }));
        window.dispatchEvent(new PointerEvent('pointerup', {
            pointerId: 21,
            clientX: startX - 70,
            clientY: 200,
        }));
        await elementUpdated(el);

        const cssWidth = el.style.getPropertyValue('--panel-assistant-width');
        expect(cssWidth).to.equal('450px');
        expect(el._panelRect?.width).to.equal(widthBefore);
        const prefs = readPrefsRoot();
        expect(prefs.assistant_width).to.equal(450);
    });

    it('assistant slot ограничивает высоту slotted-контента под panel height', async () => {
        const el = await fixture(html`
            <flows-floating-panel
                panel-id="assistant-scroll-height"
                header-icon="code"
                header-title="X"
                ai-enabled
                ai-active
            >
                <div slot="editor">Editor</div>
                <div slot="assistant" id="assistant-fill" style="box-sizing:border-box">
                    <div style="height:2400px;flex-shrink:0">tall</div>
                </div>
            </flows-floating-panel>
        `);
        await elementUpdated(el);
        el._panelViewport = () => ({ width: 1800, height: 1000 });
        el._applyFloatingPanelRect({
            left: 24,
            top: 24,
            width: 1200,
            height: 640,
        });
        await elementUpdated(el);

        const sheetText = [...el.shadowRoot.adoptedStyleSheets]
            .map((sheet) => [...sheet.cssRules].map((rule) => rule.cssText).join('\n'))
            .join('\n');
        expect(sheetText).to.match(/grid-template-rows:\s*minmax\(0(?:px)?, 1fr\)/);

        const assistantSlot = el.shadowRoot.querySelector('.panel-assistant slot');
        const assigned = assistantSlot.assignedElements({ flatten: true });
        expect(assigned.length).to.equal(1);
        const slotted = assigned[0];
        expect(slotted.clientHeight).to.be.lessThan(640);
        expect(slotted.clientHeight).to.be.greaterThan(0);
        expect(slotted.scrollHeight).to.be.greaterThan(slotted.clientHeight);
    });
});
