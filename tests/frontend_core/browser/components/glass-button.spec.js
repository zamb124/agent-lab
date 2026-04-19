/**
 * GlassButton: рендер с variant/size/disabled/loading.
 */

import { fixture, html, expect, elementUpdated } from '../helpers/render.js';
import { resetPlatformState, bootstrapTestBus } from '../helpers/reset.js';
import '@platform/lib/components/glass-button.js';

describe('glass-button', () => {
    beforeEach(() => { resetPlatformState(); bootstrapTestBus(); });

    it('рендерит <button> по умолчанию', async () => {
        const el = await fixture(html`<glass-button>Hi</glass-button>`);
        const btn = el.shadowRoot.querySelector('button');
        expect(btn).to.exist;
        expect(btn.classList.contains('primary')).to.be.true;
    });

    it('применяет variant и size как классы', async () => {
        const el = await fixture(html`<glass-button variant="ghost" size="lg">x</glass-button>`);
        const btn = el.shadowRoot.querySelector('button');
        expect(btn.classList.contains('ghost')).to.be.true;
        expect(btn.classList.contains('lg')).to.be.true;
    });

    it('disabled — атрибут на нативном button', async () => {
        const el = await fixture(html`<glass-button disabled>x</glass-button>`);
        expect(el.shadowRoot.querySelector('button').disabled).to.be.true;
    });

    it('loading тоже disable native button', async () => {
        const el = await fixture(html`<glass-button loading>x</glass-button>`);
        expect(el.shadowRoot.querySelector('button').disabled).to.be.true;
    });

    it('реактивно меняет variant', async () => {
        const el = await fixture(html`<glass-button>x</glass-button>`);
        el.variant = 'danger';
        await elementUpdated(el);
        expect(el.shadowRoot.querySelector('button').classList.contains('danger')).to.be.true;
    });
});
