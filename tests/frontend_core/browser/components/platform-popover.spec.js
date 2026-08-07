/**
 * platform-popover — top layer, позиционирование, закрытие, режимы открытия.
 *
 * Тесты написаны до перевода существующих dropdown на примитив: они фиксируют
 * контракт, на который эти компоненты будут опираться.
 */

import { fixture, html, expect, oneEvent, elementUpdated, aTimeout } from '../helpers/render.js';
import { resetPlatformState, bootstrapTestBus } from '../helpers/reset.js';
import '@platform/lib/components/platform-popover.js';

/** Обёртка «якорь + попап» — как в реальном использовании. */
async function mountPopover(attrs = {}) {
    const host = await fixture(html`
        <div style="padding: 200px;">
            <button id="anchor" style="width: 120px; height: 32px;">Открыть</button>
            <platform-popover
                trigger=${attrs.trigger ?? 'manual'}
                placement=${attrs.placement ?? 'bottom-start'}
                role=${attrs.role ?? 'dialog'}
                ?match-width=${attrs.matchWidth === true}
                ?close-on-scroll=${attrs.closeOnScroll === true}
            >
                <div style="width: 160px; height: 100px;">содержимое</div>
            </platform-popover>
        </div>
    `);
    const anchor = host.querySelector('#anchor');
    const popover = host.querySelector('platform-popover');
    popover.anchor = anchor;
    await elementUpdated(popover);
    return { host, anchor, popover };
}

describe('platform-popover', () => {
    beforeEach(() => {
        resetPlatformState();
        bootstrapTestBus();
    });

    it('закрыт по умолчанию и не отображается', async () => {
        const { popover } = await mountPopover();

        expect(popover.open).to.be.false;
        expect(getComputedStyle(popover).display).to.equal('none');
    });

    it('открывается в top layer, оставаясь в дереве владельца', async () => {
        const { popover, host } = await mountPopover();

        popover.open = true;
        await elementUpdated(popover);

        // Top layer вместо переноса в body: aria-связи и поиск по поддереву
        // владельца продолжают работать.
        expect(popover.matches(':popover-open')).to.be.true;
        expect(host.contains(popover)).to.be.true;
    });

    it('при закрытии покидает top layer и остаётся на месте', async () => {
        const { popover, host } = await mountPopover();

        popover.open = true;
        await elementUpdated(popover);
        popover.open = false;
        await elementUpdated(popover);

        expect(popover.matches(':popover-open')).to.be.false;
        expect(host.contains(popover)).to.be.true;
    });

    it('позиционируется под якорем и проставляет data-placement', async () => {
        const { popover, anchor } = await mountPopover({ placement: 'bottom-start' });

        popover.open = true;
        await elementUpdated(popover);

        const anchorRect = anchor.getBoundingClientRect();
        const popoverRect = popover.getBoundingClientRect();
        expect(popover.getAttribute('data-placement')).to.equal('bottom-start');
        expect(popoverRect.top).to.be.greaterThan(anchorRect.bottom - 1);
        expect(Math.abs(popoverRect.left - anchorRect.left)).to.be.below(2);
    });

    it('match-width растягивает слой по ширине якоря', async () => {
        const { popover, anchor } = await mountPopover({ matchWidth: true });

        popover.open = true;
        await elementUpdated(popover);

        const surface = popover.shadowRoot.querySelector('.surface');
        expect(Math.round(surface.getBoundingClientRect().width)).to.equal(
            Math.round(anchor.getBoundingClientRect().width),
        );
    });

    it('эмитит popover-open и popover-close', async () => {
        const { popover } = await mountPopover();

        const opened = oneEvent(popover, 'popover-open');
        popover.open = true;
        await opened;

        const closed = oneEvent(popover, 'popover-close');
        popover.open = false;
        await closed;
    });

    it('Escape закрывает и сообщает причину', async () => {
        const { popover } = await mountPopover();
        popover.open = true;
        await elementUpdated(popover);

        const dismissed = oneEvent(popover, 'popover-dismiss');
        document.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape', bubbles: true }));
        const event = await dismissed;

        expect(event.detail.reason).to.equal('escape');
        expect(popover.open).to.be.false;
    });

    it('клик мимо закрывает слой', async () => {
        const { popover } = await mountPopover();
        popover.open = true;
        await elementUpdated(popover);
        // Outside-dismiss вешается после rAF и игнорирует жест открытия (~320ms).
        await aTimeout(400);

        const dismissed = oneEvent(popover, 'popover-dismiss');
        document.body.dispatchEvent(new PointerEvent('pointerdown', { bubbles: true, composed: true }));
        const event = await dismissed;

        expect(event.detail.reason).to.equal('outside');
        expect(popover.open).to.be.false;
    });

    it('pointerdown сразу после open не гасит слой (жест открытия)', async () => {
        const { popover } = await mountPopover();
        popover.open = true;
        await elementUpdated(popover);

        document.body.dispatchEvent(new PointerEvent('pointerdown', { bubbles: true, composed: true }));
        await elementUpdated(popover);
        await aTimeout(50);

        expect(popover.open).to.be.true;
        expect(popover.matches(':popover-open')).to.be.true;
    });

    it('клик внутри слоя не закрывает его', async () => {
        const { popover } = await mountPopover();
        popover.open = true;
        await elementUpdated(popover);

        const inner = popover.querySelector('div');
        inner.dispatchEvent(new PointerEvent('pointerdown', { bubbles: true, composed: true }));
        await elementUpdated(popover);

        expect(popover.open).to.be.true;
    });

    it('клик по якорю не закрывает слой через outside-обработчик', async () => {
        const { popover, anchor } = await mountPopover();
        popover.open = true;
        await elementUpdated(popover);

        anchor.dispatchEvent(new PointerEvent('pointerdown', { bubbles: true, composed: true }));
        await elementUpdated(popover);

        expect(popover.open).to.be.true;
    });

    it('trigger="click" открывает и закрывает по клику на якорь', async () => {
        const { popover, anchor } = await mountPopover({ trigger: 'click' });

        anchor.click();
        await elementUpdated(popover);
        expect(popover.open).to.be.true;

        anchor.click();
        await elementUpdated(popover);
        expect(popover.open).to.be.false;
    });

    it('trigger="contextmenu" открывает у точки курсора', async () => {
        const { popover, anchor } = await mountPopover({ trigger: 'contextmenu' });

        anchor.dispatchEvent(
            new MouseEvent('contextmenu', { bubbles: true, cancelable: true, clientX: 300, clientY: 250 }),
        );
        await elementUpdated(popover);

        expect(popover.open).to.be.true;
        const rect = popover.getBoundingClientRect();
        expect(Math.abs(rect.left - 300)).to.be.below(2);
    });

    it('show(anchor) принимает точку как якорь', async () => {
        const { popover } = await mountPopover();

        popover.show({ x: 120, y: 140 });
        await elementUpdated(popover);

        const rect = popover.getBoundingClientRect();
        expect(Math.abs(rect.left - 120)).to.be.below(2);
        expect(popover.open).to.be.true;
    });

    it('role отражается в атрибуте для доступности', async () => {
        const { popover } = await mountPopover({ role: 'menu' });

        expect(popover.getAttribute('role')).to.equal('menu');
    });

    it('reposition пересчитывает координаты после сдвига якоря', async () => {
        const { popover, anchor } = await mountPopover();
        popover.open = true;
        await elementUpdated(popover);
        const before = popover.getBoundingClientRect().top;

        anchor.style.marginTop = '80px';
        popover.reposition();
        await elementUpdated(popover);

        expect(popover.getBoundingClientRect().top).to.be.greaterThan(before);
    });

    it('close-on-scroll закрывает слой при прокрутке', async () => {
        const { popover } = await mountPopover({ closeOnScroll: true });
        popover.open = true;
        await elementUpdated(popover);

        const dismissed = oneEvent(popover, 'popover-dismiss');
        window.dispatchEvent(new Event('scroll'));
        const event = await dismissed;

        expect(event.detail.reason).to.equal('scroll');
    });

    it('снятие с DOM убирает узел вместе со слоем', async () => {
        const { popover, host } = await mountPopover();
        popover.open = true;
        await elementUpdated(popover);

        popover.remove();
        await elementUpdated(popover);

        expect(popover.matches(':popover-open')).to.be.false;
        expect(host.contains(popover)).to.be.false;
    });
});
