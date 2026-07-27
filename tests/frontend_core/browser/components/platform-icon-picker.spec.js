/**
 * platform-icon-picker — выбор иконки, слой панели, клавиатура.
 */

import { fixture, html, expect, oneEvent, elementUpdated } from '../helpers/render.js';
import { resetPlatformState, bootstrapTestBus } from '../helpers/reset.js';
import '@platform/lib/components/platform-icon-picker.js';

const ICONS = ['user', 'folder', 'star'];

async function mountPicker(props = {}) {
    const el = await fixture(html`
        <platform-icon-picker
            .icons=${ICONS}
            .value=${props.value ?? ''}
            ?disabled=${props.disabled === true}
        ></platform-icon-picker>
    `);
    await elementUpdated(el);
    return el;
}

function triggerOf(el) {
    return el.shadowRoot.querySelector('.trigger');
}

function optionsOf(el) {
    return Array.from(el.shadowRoot.querySelectorAll('.option'));
}

describe('platform-icon-picker', () => {
    beforeEach(() => {
        resetPlatformState();
        bootstrapTestBus();
    });

    it('панель закрыта по умолчанию', async () => {
        const el = await mountPicker();

        expect(optionsOf(el).length).to.equal(0);
        expect(triggerOf(el).getAttribute('aria-expanded')).to.equal('false');
    });

    it('клик по триггеру открывает панель со всеми иконками', async () => {
        const el = await mountPicker();

        triggerOf(el).click();
        await elementUpdated(el);

        expect(optionsOf(el).length).to.equal(3);
        expect(triggerOf(el).getAttribute('aria-expanded')).to.equal('true');
    });

    it('повторный клик закрывает панель', async () => {
        const el = await mountPicker();

        triggerOf(el).click();
        await elementUpdated(el);
        triggerOf(el).click();
        await elementUpdated(el);

        expect(optionsOf(el).length).to.equal(0);
    });

    it('выбор иконки эмитит change и закрывает панель', async () => {
        const el = await mountPicker();
        triggerOf(el).click();
        await elementUpdated(el);

        const changed = oneEvent(el, 'change');
        optionsOf(el)[1].click();
        const event = await changed;
        await elementUpdated(el);

        expect(event.detail.value).to.equal('folder');
        expect(el.value).to.equal('folder');
        expect(optionsOf(el).length).to.equal(0);
    });

    it('выбранная иконка помечена активной', async () => {
        const el = await mountPicker({ value: 'star' });
        triggerOf(el).click();
        await elementUpdated(el);

        const active = optionsOf(el).filter((node) => node.classList.contains('active'));
        expect(active.length).to.equal(1);
        expect(active[0].textContent.trim()).to.equal('star');
    });

    it('Enter на триггере открывает панель', async () => {
        const el = await mountPicker();

        triggerOf(el).dispatchEvent(new KeyboardEvent('keydown', { key: 'Enter', bubbles: true }));
        await elementUpdated(el);

        expect(optionsOf(el).length).to.equal(3);
    });

    it('Escape закрывает панель', async () => {
        const el = await mountPicker();
        triggerOf(el).click();
        await elementUpdated(el);

        document.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape', bubbles: true }));
        await elementUpdated(el);

        expect(optionsOf(el).length).to.equal(0);
    });

    it('клик мимо закрывает панель', async () => {
        const el = await mountPicker();
        triggerOf(el).click();
        await elementUpdated(el);

        document.body.dispatchEvent(new PointerEvent('pointerdown', { bubbles: true, composed: true }));
        await elementUpdated(el);

        expect(optionsOf(el).length).to.equal(0);
    });

    it('отключённый пикер не открывается', async () => {
        const el = await mountPicker({ disabled: true });

        triggerOf(el).click();
        await elementUpdated(el);

        expect(optionsOf(el).length).to.equal(0);
    });

    it('панель показывается в top layer', async () => {
        const el = await mountPicker();
        triggerOf(el).click();
        await elementUpdated(el);

        const popover = el.shadowRoot.querySelector('platform-popover');
        expect(popover.matches(':popover-open')).to.be.true;
    });
});
