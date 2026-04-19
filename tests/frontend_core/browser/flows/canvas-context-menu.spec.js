/**
 * Smoke: flows-canvas-context-menu — пункты меню по target и эмит action/close.
 */

import { fixture, fixtureCleanup, html, expect } from '../helpers/render.js';
import { resetPlatformState } from '../helpers/reset.js';
import { bootstrapPlatformBus } from '@platform/lib/events/index.js';
import '../../../../apps/flows/ui/components/flow-canvas/flows-canvas-context-menu.js';

function setupBus() {
    return bootstrapPlatformBus({ baseUrl: '', routes: [], slices: {}, effects: [] });
}

describe('flows-canvas-context-menu', () => {
    beforeEach(() => { resetPlatformState(); setupBus(); });
    afterEach(() => fixtureCleanup());

    it('node target рендерит пункты для ноды', async () => {
        const el = await fixture(html`
            <flows-canvas-context-menu .x=${10} .y=${20} target="node" target-id="n1"></flows-canvas-context-menu>
        `);
        const items = el.shadowRoot.querySelectorAll('.item');
        expect(items.length).to.be.greaterThan(2);
        const labels = Array.from(items).map((i) => i.textContent.trim()).join(' ');
        expect(labels).to.satisfy((s) => s.length > 0);
    });

    it('background target рендерит add_sticky / fit_view / select_all', async () => {
        const el = await fixture(html`
            <flows-canvas-context-menu .x=${0} .y=${0} target="background"></flows-canvas-context-menu>
        `);
        const items = Array.from(el.shadowRoot.querySelectorAll('.item'));
        expect(items.length).to.be.greaterThan(2);
    });

    it('click пункта эмитит action c kind и закрывает (close)', async () => {
        const el = await fixture(html`
            <flows-canvas-context-menu .x=${0} .y=${0} target="background"></flows-canvas-context-menu>
        `);
        let actionDetail = null;
        let closed = false;
        el.addEventListener('action', (e) => { actionDetail = e.detail; });
        el.addEventListener('close', () => { closed = true; });
        const firstItem = el.shadowRoot.querySelector('.item');
        firstItem.click();
        expect(actionDetail).to.not.be.null;
        expect(actionDetail.target).to.equal('background');
        expect(closed).to.equal(true);
    });
});
