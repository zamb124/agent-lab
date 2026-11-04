/**
 * GlassModal / PlatformModal: контракт открытия/закрытия через bus.
 * Прямой this.open = true / new + appendChild — запрещены.
 */

import { html as litHtml } from 'lit';
import { fixture, html, expect, elementUpdated, nextFrame, waitUntil } from '../helpers/render.js';
import { resetPlatformState, bootstrapTestBus } from '../helpers/reset.js';
import { GlassModal, PlatformModal } from '@platform/lib/components/glass-modal.js';
import { registerModalKind } from '@platform/lib/utils/modal-registry.js';
import '@platform/lib/components/platform-modal-stack.js';
import { getPlatformBus, CoreEvents } from '@platform/lib/events/index.js';
import { qs, shadow, type TestEl } from '../helpers/dom.js';

class TestGlassModal extends PlatformModal {
    static modalKind = 'platform.glass_test';
    static i18nNamespace = 'platform';
    override render() { return litHtml`${super.render()}`; }
}
customElements.define('frontend-core-glass-modal', TestGlassModal);
registerModalKind('platform.glass_test', 'frontend-core-glass-modal');

describe('GlassModal/PlatformModal', () => {
    beforeEach(() => { resetPlatformState(); bootstrapTestBus(); });

    it('PlatformModal — алиас GlassModal', () => {
        expect(PlatformModal).to.equal(GlassModal);
    });

    it('close() без _modalId — throw (защита от прямого монтирования)', async () => {
        const el = await fixture<TestEl>(html`<frontend-core-glass-modal></frontend-core-glass-modal>`);
        expect(() => el.close()).to.throw(/_modalId/);
    });

    it('открытие через UI_MODAL_OPEN → автомонтаж + open=true + _modalId', async () => {
        const stack = await fixture<TestEl>(html`<platform-modal-stack></platform-modal-stack>`);
        getPlatformBus().dispatch(CoreEvents.UI_MODAL_OPEN, { kind: 'platform.glass_test', props: { heading: 'Hi' } });
        await elementUpdated(stack);
        // GlassModal портирует себя в document.body на open, поэтому ищем глобально.
        const modal = qs(document!, 'frontend-core-glass-modal');
        expect(modal).to.exist;
        expect(modal.open).to.be.true;
        expect(modal.heading).to.equal('Hi');
        expect(modal._modalId).to.match(/^modal_/);
    });

    it('close() диспатчит UI_MODAL_CLOSE, затем stack убирает модалку после exit-motion', async () => {
        const stack = await fixture<TestEl>(html`<platform-modal-stack></platform-modal-stack>`);
        getPlatformBus().dispatch(CoreEvents.UI_MODAL_OPEN, { kind: 'platform.glass_test', props: {} });
        await elementUpdated(stack);
        const modal = qs(document!, 'frontend-core-glass-modal');
        expect(modal, 'modal mounted after dispatch').to.exist;
        const id = modal._modalId;
        modal.close();
        await waitUntil(
            () => (getPlatformBus().getState() as Record<string, any>).modals.stack.find((m: any) => m.id === id) === undefined,
            'modal removed after exit motion',
        );
    });

    it('драг шапки само-завершается при потерянном mouseup (buttons=0) — кнопка close остаётся кликабельной', async () => {
        const stack = await fixture<TestEl>(html`<platform-modal-stack></platform-modal-stack>`);
        getPlatformBus().dispatch(CoreEvents.UI_MODAL_OPEN, { kind: 'platform.glass_test', props: {} });
        await elementUpdated(stack);
        const modal = qs(document!, 'frontend-core-glass-modal');
        expect(modal, 'modal mounted').to.exist;

        const header = qs(shadow(modal), '.modal-header');
        header.dispatchEvent(new MouseEvent('mousedown', { button: 0, buttons: 1, clientX: 400, clientY: 100, bubbles: true, composed: true }));
        await elementUpdated(modal);
        expect(modal._isDragging).to.be.true;

        document.dispatchEvent(new MouseEvent('mousemove', { buttons: 1, clientX: 450, clientY: 140, bubbles: true, composed: true }));
        await elementUpdated(modal);
        const moved = modal._position;
        expect(moved.x, 'position moved while dragging').to.not.equal(null);

        // Потерянный mouseup: кнопка отпущена (buttons=0), но mouseup до document не дошёл.
        document.dispatchEvent(new MouseEvent('mousemove', { buttons: 0, clientX: 500, clientY: 200, bubbles: true, composed: true }));
        await elementUpdated(modal);
        expect(modal._isDragging, 'drag must self-heal on released button').to.be.false;

        const before = modal._position;
        document.dispatchEvent(new MouseEvent('mousemove', { buttons: 0, clientX: 600, clientY: 260, bubbles: true, composed: true }));
        await elementUpdated(modal);
        expect(modal._position.x, 'modal must not chase cursor after lost mouseup').to.equal(before.x);

        const id = modal._modalId;
        modal.close();
        await waitUntil(
            () => (getPlatformBus().getState() as Record<string, any>).modals.stack.find((m: any) => m.id === id) === undefined,
            'modal closes after stuck drag healed',
        );
    });

    it('blur окна во время драга шапки завершает жест', async () => {
        const stack = await fixture<TestEl>(html`<platform-modal-stack></platform-modal-stack>`);
        getPlatformBus().dispatch(CoreEvents.UI_MODAL_OPEN, { kind: 'platform.glass_test', props: {} });
        await elementUpdated(stack);
        const modal = qs(document!, 'frontend-core-glass-modal');
        expect(modal, 'modal mounted').to.exist;

        const header = qs(shadow(modal), '.modal-header');
        header.dispatchEvent(new MouseEvent('mousedown', { button: 0, buttons: 1, clientX: 400, clientY: 100, bubbles: true, composed: true }));
        await elementUpdated(modal);
        expect(modal._isDragging).to.be.true;

        window.dispatchEvent(new Event('blur'));
        await elementUpdated(modal);
        expect(modal._isDragging, 'window blur must end the drag').to.be.false;
    });

    it('toggleFullscreen делает compositor FLIP motion и оставляет fullscreen state', async () => {
        const stack = await fixture<TestEl>(html`<platform-modal-stack></platform-modal-stack>`);
        getPlatformBus().dispatch(CoreEvents.UI_MODAL_OPEN, { kind: 'platform.glass_test', props: {} });
        await elementUpdated(stack);
        const modal = qs(document!, 'frontend-core-glass-modal');
        expect(modal, 'modal mounted after dispatch').to.exist;
        modal.style.setProperty('--modal-fullscreen-motion-duration', '1ms');

        const promise = modal.toggleFullscreen();
        await elementUpdated(modal);
        await nextFrame();
        expect(modal._fullscreenMotionActive).to.be.true;
        await promise;
        await elementUpdated(modal);

        expect(modal._isFullscreen).to.be.true;
        expect(modal._fullscreenMotionActive).to.be.false;
        expect(qs(shadow(modal), '.modal').classList.contains('fullscreen')).to.be.true;
    });
});
