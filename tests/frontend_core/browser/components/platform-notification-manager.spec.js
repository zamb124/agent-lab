/**
 * platform-notification-manager — колокольчик, счётчик, панель уведомлений.
 */

import { fixture, html, expect, elementUpdated, aTimeout } from '../helpers/render.js';
import { resetPlatformState, bootstrapTestBus } from '../helpers/reset.js';
import { getPlatformBus } from '@platform/lib/events/index.js';
import '@platform/lib/components/platform-notification-manager.js';

/** Inbox наполняется любым событием шины с префиксом `notify/`. */
function pushNotification(payload) {
    getPlatformBus().dispatch(
        `notify/${payload.scope ?? 'platform'}/${payload.kind ?? 'generic'}`,
        {
            title: payload.title ?? 'Заголовок',
            message: payload.message ?? 'Текст уведомления',
        },
        { source: 'system' },
    );
}

async function mountManager() {
    const el = await fixture(html`<platform-notification-manager></platform-notification-manager>`);
    await elementUpdated(el);
    return el;
}

function bellOf(el) {
    return el.shadowRoot.querySelector('.bell');
}

function panelOf(el) {
    return el.shadowRoot.querySelector('.platform-notif-portal');
}

describe('platform-notification-manager', () => {
    beforeEach(() => {
        resetPlatformState();
        bootstrapTestBus();
    });

    it('колокольчик виден, панель закрыта', async () => {
        const el = await mountManager();

        expect(bellOf(el)).to.exist;
        expect(panelOf(el)).to.be.null;
    });

    it('клик по колокольчику открывает панель', async () => {
        const el = await mountManager();

        bellOf(el).click();
        await elementUpdated(el);

        expect(panelOf(el)).to.exist;
    });

    it('панель показывается в top layer, а не обрезается сайдбаром', async () => {
        const el = await mountManager();

        bellOf(el).click();
        await elementUpdated(el);

        const popover = el.shadowRoot.querySelector('platform-popover');
        expect(popover.matches(':popover-open')).to.be.true;
    });

    it('повторный клик закрывает панель', async () => {
        const el = await mountManager();

        bellOf(el).click();
        await elementUpdated(el);
        bellOf(el).click();
        await elementUpdated(el);

        expect(panelOf(el)).to.be.null;
    });

    it('пустой список показывает заглушку', async () => {
        const el = await mountManager();

        bellOf(el).click();
        await elementUpdated(el);

        expect(el.shadowRoot.querySelector('.platform-notif-portal__empty')).to.exist;
    });

    it('полученное уведомление появляется в списке и в счётчике', async () => {
        const el = await mountManager();

        pushNotification({ title: 'Новая задача' });
        await elementUpdated(el);

        expect(el.shadowRoot.querySelector('.badge').textContent.trim()).to.equal('1');

        bellOf(el).click();
        await elementUpdated(el);

        const items = el.shadowRoot.querySelectorAll('.platform-notif-portal__item');
        expect(items.length).to.equal(1);
        expect(items[0].textContent).to.contain('Новая задача');
    });

    it('Escape закрывает панель', async () => {
        const el = await mountManager();
        bellOf(el).click();
        await elementUpdated(el);

        document.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape', bubbles: true }));
        await elementUpdated(el);

        expect(panelOf(el)).to.be.null;
    });

    it('клик мимо закрывает панель', async () => {
        const el = await mountManager();
        bellOf(el).click();
        await elementUpdated(el);
        // Outside-dismiss вешается после rAF и игнорирует жест открытия (~320ms).
        await aTimeout(400);

        document.body.dispatchEvent(new PointerEvent('pointerdown', { bubbles: true, composed: true }));
        await elementUpdated(el);

        expect(panelOf(el)).to.be.null;
    });
});
