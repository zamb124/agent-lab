/**
 * platform-button + platform-switch + tag-input + glass-toast — простые
 * presentational компоненты UI Kit. Smoke + основные атрибуты.
 */

import { fixture, html, expect, oneEvent } from '../helpers/render.js';
import { resetPlatformState, bootstrapTestBus } from '../helpers/reset.js';
import '@platform/lib/components/platform-button.js';
import '@platform/lib/components/platform-switch.js';
import '@platform/lib/components/tag-input.js';
import '@platform/lib/components/glass-toast.js';

describe('platform-button', () => {
    beforeEach(() => { resetPlatformState(); bootstrapTestBus(); });

    it('default variant=primary', async () => {
        const el = await fixture(html`<platform-button>x</platform-button>`);
        expect(el.shadowRoot.querySelector('button.primary')).to.exist;
    });

    it('disabled / loading блокируют button', async () => {
        const el = await fixture(html`<platform-button disabled>x</platform-button>`);
        expect(el.shadowRoot.querySelector('button').disabled).to.be.true;
        const el2 = await fixture(html`<platform-button loading>x</platform-button>`);
        expect(el2.shadowRoot.querySelector('button').disabled).to.be.true;
    });

    it('variant=danger проставляет класс', async () => {
        const el = await fixture(html`<platform-button variant="danger">x</platform-button>`);
        expect(el.shadowRoot.querySelector('button.danger')).to.exist;
    });
});

describe('platform-switch', () => {
    beforeEach(() => { resetPlatformState(); bootstrapTestBus(); });

    it('рендерится без ошибок', async () => {
        const el = await fixture(html`<platform-switch></platform-switch>`);
        expect(el.shadowRoot).to.exist;
    });
});

describe('tag-input', () => {
    beforeEach(() => { resetPlatformState(); bootstrapTestBus(); });

    it('рендерится без ошибок', async () => {
        const el = await fixture(html`<tag-input .tags=${['a', 'b']}></tag-input>`);
        expect(el.shadowRoot).to.exist;
    });
});

describe('glass-toast', () => {
    beforeEach(() => { resetPlatformState(); bootstrapTestBus(); });

    it('рендерится с message', async () => {
        const el = await fixture(html`<glass-toast type="success" .message=${'Hello'} .duration=${0}></glass-toast>`);
        expect(el.shadowRoot).to.exist;
    });

    it('type=error: одна кнопка close, индикатор в span.icon (не вторая кнопка)', async () => {
        const el = await fixture(html`<glass-toast type="error" .message=${'Failed to switch provider'} .duration=${0}></glass-toast>`);
        const root = el.shadowRoot;
        const closeButtons = root.querySelectorAll('button.close');
        expect(closeButtons).to.have.length(1);
        const icon = root.querySelector('.icon');
        expect(icon).to.exist;
        expect(icon.textContent).to.equal('!');
    });
});
