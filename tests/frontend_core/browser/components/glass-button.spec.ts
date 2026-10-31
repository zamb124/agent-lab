/**
 * GlassButton: рендер с variant/size/disabled/loading.
 */

import { fixture, html, expect, elementUpdated } from '../helpers/render.js';
import { resetPlatformState, bootstrapTestBus } from '../helpers/reset.js';
import '@platform/lib/components/glass-button.js';
import { qs, shadow, type TestEl } from '../helpers/dom.js';

describe('glass-button', () => {
    beforeEach(() => { resetPlatformState(); bootstrapTestBus(); });

    it('рендерит <button> по умолчанию', async () => {
        const el = await fixture<TestEl>(html`<glass-button>Hi</glass-button>`);
        const btn = qs(shadow(el), 'button');
        expect(btn).to.exist;
        expect(btn.classList.contains('primary')).to.be.true;
    });

    it('применяет variant и size как классы', async () => {
        const el = await fixture<TestEl>(html`<glass-button variant="ghost" size="lg">x</glass-button>`);
        const btn = qs(shadow(el), 'button');
        expect(btn.classList.contains('ghost')).to.be.true;
        expect(btn.classList.contains('lg')).to.be.true;
    });

    it('disabled — атрибут на нативном button', async () => {
        const el = await fixture<TestEl>(html`<glass-button disabled>x</glass-button>`);
        expect(qs(shadow(el), 'button').disabled).to.be.true;
    });

    it('loading тоже disable native button', async () => {
        const el = await fixture<TestEl>(html`<glass-button loading>x</glass-button>`);
        expect(qs(shadow(el), 'button').disabled).to.be.true;
    });

    it('реактивно меняет variant', async () => {
        const el = await fixture<TestEl>(html`<glass-button>x</glass-button>`);
        el.variant = 'danger';
        await elementUpdated(el);
        expect(qs(shadow(el), 'button').classList.contains('danger')).to.be.true;
    });
});
