/**
 * platform-emoji-picker — категории, поиск, выбор, сброс.
 */

import { fixture, html, expect, oneEvent, elementUpdated } from '../helpers/render.js';
import { resetPlatformState, bootstrapTestBus } from '../helpers/reset.js';
import '@platform/lib/components/platform-emoji-picker.js';
import {q, qs, qsa, shadow, type TestEl} from '../helpers/dom.js';

async function mountPicker(value = '') {
    const el = await fixture<TestEl>(html`<platform-emoji-picker value=${value}></platform-emoji-picker>`);
    await elementUpdated(el);
    return el;
}

function cells(el: any) {
    return Array.from(qsa(shadow(el), '.cell'));
}

describe('platform-emoji-picker', () => {
    beforeEach(() => {
        resetPlatformState();
        bootstrapTestBus();
    });

    it('показывает категории и эмодзи', async () => {
        const el = await mountPicker();

        expect(qsa(shadow(el), '.group-title').length).to.be.greaterThan(1);
        expect(cells(el).length).to.be.greaterThan(10);
    });

    it('выбор эмодзи эмитит emoji-select', async () => {
        const el = await mountPicker();

        const selected = oneEvent(el, 'emoji-select');
        qs(shadow(el), '[data-emoji="🚀"]').click();
        const event = await selected;

        expect((event as CustomEvent).detail.emoji).to.equal('🚀');
        expect((el as TestEl).value).to.equal('🚀');
    });

    it('текущее значение помечено выбранным', async () => {
        const el = await mountPicker('📄');

        const selected = cells(el).filter((cell) => cell.classList.contains('is-selected'));
        expect(selected.length).to.equal(1);
        expect(selected[0]!.dataset.emoji).to.equal('📄');
        expect(selected[0]!.getAttribute('aria-selected')).to.equal('true');
    });

    it('поиск по русскому ключевому слову', async () => {
        const el = await mountPicker();

        const input = qs(shadow(el), 'input');
        (input as TestEl).value = 'задача';
        input.dispatchEvent(new Event('input', { bubbles: true }));
        await elementUpdated(el);

        const found = cells(el).map((cell) => (cell as TestEl).dataset.emoji);
        expect(found).to.include('🎯');
        expect(found.length).to.be.below(5);
    });

    it('поиск по английскому ключевому слову', async () => {
        const el = await mountPicker();

        const input = qs(shadow(el), 'input');
        (input as TestEl).value = 'bug';
        input.dispatchEvent(new Event('input', { bubbles: true }));
        await elementUpdated(el);

        expect(cells(el).map((cell) => (cell as TestEl).dataset.emoji)).to.include('🐞');
    });

    it('поиск без совпадений показывает заглушку', async () => {
        const el = await mountPicker();

        const input = qs(shadow(el), 'input');
        (input as TestEl).value = 'абракадабра';
        input.dispatchEvent(new Event('input', { bubbles: true }));
        await elementUpdated(el);

        expect(qs(shadow(el), '.empty')).to.exist;
        expect(cells(el).length).to.equal(0);
    });

    it('кнопка сброса появляется только при выбранном значении', async () => {
        const empty = await mountPicker();
        expect(q(shadow(empty), '[data-emoji-clear]')).to.be.null;

        const filled = await mountPicker('⭐️');
        expect(qs(shadow(filled), '[data-emoji-clear]')).to.exist;
    });

    it('сброс эмитит emoji-clear и очищает значение', async () => {
        const el = await mountPicker('⭐️');

        const cleared = oneEvent(el, 'emoji-clear');
        qs(shadow(el), '[data-emoji-clear]').click();
        await cleared;
        await elementUpdated(el);

        expect((el as TestEl).value).to.equal('');
    });
});
