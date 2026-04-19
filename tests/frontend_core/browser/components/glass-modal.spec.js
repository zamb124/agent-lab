/**
 * GlassModal / PlatformModal: контракт открытия/закрытия через bus.
 * Прямой this.open = true / new + appendChild — запрещены.
 */

import { html as litHtml } from 'lit';
import { fixture, html, expect, elementUpdated } from '../helpers/render.js';
import { resetPlatformState, bootstrapTestBus } from '../helpers/reset.js';
import { GlassModal, PlatformModal } from '@platform/lib/components/glass-modal.js';
import { registerModalKind } from '@platform/lib/utils/modal-registry.js';
import '@platform/lib/components/platform-modal-stack.js';
import { getPlatformBus, CoreEvents } from '@platform/lib/events/index.js';

class TestGlassModal extends PlatformModal {
    static modalKind = 'platform.glass_test';
    static i18nNamespace = 'platform';
    render() { return litHtml`${super.render()}`; }
}
customElements.define('frontend-core-glass-modal', TestGlassModal);
registerModalKind('platform.glass_test', 'frontend-core-glass-modal');

describe('GlassModal/PlatformModal', () => {
    beforeEach(() => { resetPlatformState(); bootstrapTestBus(); });

    it('PlatformModal — алиас GlassModal', () => {
        expect(PlatformModal).to.equal(GlassModal);
    });

    it('close() без _modalId — throw (защита от прямого монтирования)', async () => {
        const el = await fixture(html`<frontend-core-glass-modal></frontend-core-glass-modal>`);
        expect(() => el.close()).to.throw(/_modalId/);
    });

    it('открытие через UI_MODAL_OPEN → автомонтаж + open=true + _modalId', async () => {
        const stack = await fixture(html`<platform-modal-stack></platform-modal-stack>`);
        getPlatformBus().dispatch(CoreEvents.UI_MODAL_OPEN, { kind: 'platform.glass_test', props: { heading: 'Hi' } });
        await elementUpdated(stack);
        // GlassModal портирует себя в document.body на open, поэтому ищем глобально.
        const modal = document.querySelector('frontend-core-glass-modal');
        expect(modal).to.exist;
        expect(modal.open).to.be.true;
        expect(modal.heading).to.equal('Hi');
        expect(modal._modalId).to.match(/^modal_/);
    });

    it('close() диспатчит UI_MODAL_CLOSE с правильным id и убирает из стека', async () => {
        const stack = await fixture(html`<platform-modal-stack></platform-modal-stack>`);
        getPlatformBus().dispatch(CoreEvents.UI_MODAL_OPEN, { kind: 'platform.glass_test', props: {} });
        await elementUpdated(stack);
        const modal = document.querySelector('frontend-core-glass-modal');
        expect(modal, 'modal mounted after dispatch').to.exist;
        const id = modal._modalId;
        modal.close();
        await elementUpdated(stack);
        expect(getPlatformBus().getState().modals.stack.find((m) => m.id === id)).to.be.undefined;
    });
});
