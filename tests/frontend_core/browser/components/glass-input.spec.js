/**
 * GlassInput, GlassTextarea, GlassCard, GlassSpinner — простые presentational
 * компоненты UI Kit. Проверяем рендер базовых атрибутов и события input/change.
 */

import { fixture, html, expect, oneEvent } from '../helpers/render.js';
import { resetPlatformState, bootstrapTestBus } from '../helpers/reset.js';
import '@platform/lib/components/glass-input.js';
import '@platform/lib/components/glass-textarea.js';
import '@platform/lib/components/glass-card.js';
import '@platform/lib/components/glass-spinner.js';

describe('glass-input', () => {
    beforeEach(() => { resetPlatformState(); bootstrapTestBus(); });

    it('рендерит <input> с placeholder и value', async () => {
        const el = await fixture(html`<glass-input value="hi" placeholder="ph"></glass-input>`);
        const inp = el.shadowRoot.querySelector('input');
        expect(inp.value).to.equal('hi');
        expect(inp.placeholder).to.equal('ph');
    });

    it('disabled / required прокидывает', async () => {
        const el = await fixture(html`<glass-input disabled required></glass-input>`);
        const inp = el.shadowRoot.querySelector('input');
        expect(inp.disabled).to.be.true;
        expect(inp.required).to.be.true;
    });

    it('input-event эмитится с detail.value', async () => {
        const el = await fixture(html`<glass-input></glass-input>`);
        const inp = el.shadowRoot.querySelector('input');
        const promise = oneEvent(el, 'input');
        inp.value = 'typed';
        inp.dispatchEvent(new Event('input', { bubbles: true }));
        const ev = await promise;
        expect(ev.detail.value).to.equal('typed');
        expect(el.value).to.equal('typed');
    });

    it('error атрибут добавляет класс error', async () => {
        const el = await fixture(html`<glass-input error></glass-input>`);
        expect(el.shadowRoot.querySelector('.input-wrapper').classList.contains('error')).to.be.true;
    });
});

describe('glass-textarea', () => {
    beforeEach(() => { resetPlatformState(); bootstrapTestBus(); });

    it('рендерит <textarea>', async () => {
        const el = await fixture(html`<glass-textarea value="lines"></glass-textarea>`);
        expect(el.shadowRoot.querySelector('textarea')).to.exist;
    });
});

describe('glass-card', () => {
    beforeEach(() => { resetPlatformState(); bootstrapTestBus(); });

    it('содержит slot для контента', async () => {
        const el = await fixture(html`<glass-card>inner</glass-card>`);
        expect(el.shadowRoot.querySelector('slot')).to.exist;
    });
});

describe('glass-spinner', () => {
    beforeEach(() => { resetPlatformState(); bootstrapTestBus(); });

    it('рендерится без ошибок', async () => {
        const el = await fixture(html`<glass-spinner></glass-spinner>`);
        expect(el.shadowRoot).to.exist;
    });
});
