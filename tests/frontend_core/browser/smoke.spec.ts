/**
 * Smoke: убеждаемся, что Web Test Runner поднимается и Lit с PlatformElement
 * рендерятся в реальном Chromium.
 */

import { LitElement, html as litHtml } from 'lit';
import { PlatformElement } from '@platform/lib/platform-element/index.js';
import { fixture, html, expect } from './helpers/render.js';
import { resetPlatformState, bootstrapTestBus } from './helpers/reset.js';
import { qs, shadow, type TestEl } from './helpers/dom.js';

class SmokeMarker extends LitElement {
    override render() { return litHtml`<span class="marker">ok</span>`; }
}
customElements.define('frontend-core-smoke-marker', SmokeMarker);

class PlatformSmoke extends PlatformElement {
    override render() { return litHtml`<span class="ps-marker">ps-ok</span>`; }
}
customElements.define('frontend-core-platform-smoke', PlatformSmoke);

describe('frontend_core: smoke', () => {
    beforeEach(() => { resetPlatformState(); bootstrapTestBus(); });

    it('Lit рендерится в shadow DOM', async () => {
        const el = await fixture<TestEl>(html`<frontend-core-smoke-marker></frontend-core-smoke-marker>`);
        expect(qs(shadow(el), '.marker').textContent.trim()).to.equal('ok');
    });

    it('PlatformElement потомок рендерится с активным bus', async () => {
        const el = await fixture<TestEl>(html`<frontend-core-platform-smoke></frontend-core-platform-smoke>`);
        expect(qs(shadow(el), '.ps-marker').textContent.trim()).to.equal('ps-ok');
        expect(el.bus).to.exist;
    });
});
