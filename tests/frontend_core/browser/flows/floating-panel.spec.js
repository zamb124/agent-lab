/**
 * Smoke: flows-floating-panel — рендер chrome, expand toggle, close emit.
 */

import { fixture, fixtureCleanup, html, expect, elementUpdated } from '../helpers/render.js';
import { resetPlatformState } from '../helpers/reset.js';
import { bootstrapPlatformBus } from '@platform/lib/events/index.js';
import '../../../../apps/flows/ui/components/editor/flows-floating-panel.js';

describe('flows-floating-panel', () => {
    beforeEach(() => {
        resetPlatformState();
        bootstrapPlatformBus({ baseUrl: '', routes: [], slices: {}, effects: [] });
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

    it('expand toggle эмитит expand-change; parent выставляет expanded', async () => {
        // flows-floating-panel — controlled-компонент: state.panelExpanded
        // живёт у parent (см. flow-editor-page), который слушает expand-change
        // и снова кладёт ?expanded=... обратно в проп. Тест эмулирует это.
        const el = await fixture(html`
            <flows-floating-panel header-icon="code" header-title="X"></flows-floating-panel>
        `);
        let lastDetail = null;
        el.addEventListener('expand-change', (e) => {
            lastDetail = e.detail;
            el.expanded = e.detail.expanded;
        });
        const expandBtn = el.shadowRoot.querySelector('.panel-btn.expand');
        expandBtn.click();
        await elementUpdated(el);
        expect(lastDetail).to.deep.equal({ expanded: true });
        expect(el.expanded).to.equal(true);
        expect(el.hasAttribute('expanded')).to.equal(true);
    });

    it('close-кнопка эмитит close', async () => {
        const el = await fixture(html`
            <flows-floating-panel header-icon="code" header-title="X"></flows-floating-panel>
        `);
        let closed = false;
        el.addEventListener('close', () => { closed = true; });
        const closeBtn = Array.from(el.shadowRoot.querySelectorAll('.panel-btn')).pop();
        closeBtn.click();
        expect(closed).to.equal(true);
    });
});
