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
import {q, qs, qsa, shadow, type TestEl} from '../helpers/dom.js';

describe('platform-button', () => {
    beforeEach(() => { resetPlatformState(); bootstrapTestBus(); });

    it('default variant=primary', async () => {
        const el = await fixture<TestEl>(html`<platform-button>x</platform-button>`);
        expect(qs(shadow(el), 'button.primary')).to.exist;
    });

    it('disabled / loading блокируют button', async () => {
        const el = await fixture<TestEl>(html`<platform-button disabled>x</platform-button>`);
        expect(qs(shadow(el), 'button').disabled).to.be.true;
        const el2 = await fixture<TestEl>(html`<platform-button loading>x</platform-button>`);
        expect(qs(shadow(el2), 'button').disabled).to.be.true;
    });

    it('variant=danger проставляет класс', async () => {
        const el = await fixture<TestEl>(html`<platform-button variant="danger">x</platform-button>`);
        expect(qs(shadow(el), 'button.danger')).to.exist;
    });

    it('boolean danger тоже выбирает danger-вариант', async () => {
        const el = await fixture<TestEl>(html`<platform-button danger>x</platform-button>`);
        expect(qs(shadow(el), 'button.danger')).to.exist;
    });

    it('ghost + danger выбирает ghost-danger (menu/toolbar destructive)', async () => {
        const el = await fixture<TestEl>(html`<platform-button variant="ghost" danger>x</platform-button>`);
        expect(q(shadow(el), 'button.ghost-danger')).to.exist;
        expect(q(shadow(el), 'button.danger')).to.equal(null);
    });

    it('block растягивает кнопку на ширину контейнера', async () => {
        const el = await fixture<TestEl>(html`<platform-button block variant="ghost">Menu item</platform-button>`);
        expect(el.hasAttribute('block')).to.equal(true);
        const button = qs(shadow(el), 'button');
        expect(button.classList.contains('ghost')).to.equal(true);
    });

    it('icon-only прокидывает accessible label во внутреннюю кнопку', async () => {
        const el = await fixture<TestEl>(html`
            <platform-button icon-only aria-label="Apply">
                <span>ok</span>
            </platform-button>
        `);
        const button = qs(shadow(el), 'button');
        expect(button.getAttribute('aria-label')).to.equal('Apply');
        expect(button.getAttribute('title')).to.equal('Apply');
    });

    it('icon-only compact uses 32px chrome control size', async () => {
        const el = await fixture<TestEl>(html`
            <platform-button icon-only density="compact" aria-label="Action">
                <span>x</span>
            </platform-button>
        `);
        const height = qs(shadow(el), 'button').getBoundingClientRect().height;
        expect(height).to.be.closeTo(32, 1);
    });
});

describe('platform-switch', () => {
    beforeEach(() => { resetPlatformState(); bootstrapTestBus(); });

    it('рендерится без ошибок', async () => {
        const el = await fixture<TestEl>(html`<platform-switch></platform-switch>`);
        expect(shadow(el)).to.exist;
    });
});

describe('tag-input', () => {
    beforeEach(() => { resetPlatformState(); bootstrapTestBus(); });

    it('рендерится без ошибок', async () => {
        const el = await fixture<TestEl>(html`<tag-input .tags=${['a', 'b']}></tag-input>`);
        expect(shadow(el)).to.exist;
    });
});

describe('glass-toast', () => {
    beforeEach(() => { resetPlatformState(); bootstrapTestBus(); });

    it('рендерится с message', async () => {
        const el = await fixture<TestEl>(html`<glass-toast type="success" .message=${'Hello'} .duration=${0}></glass-toast>`);
        expect(shadow(el)).to.exist;
    });

    it('type=error: одна кнопка close, индикатор в span.icon (не вторая кнопка)', async () => {
        const el = await fixture<TestEl>(html`<glass-toast type="error" .message=${'Failed to switch provider'} .duration=${0}></glass-toast>`);
        const root = shadow(el);
        const closeButtons = qsa(root!, 'button.close');
        expect(closeButtons).to.have.length(1);
        const icon = qs(root!, '.icon');
        expect(icon).to.exist;
        expect(icon.textContent).to.equal('!');
    });
});
