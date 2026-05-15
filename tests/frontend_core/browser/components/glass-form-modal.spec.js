/**
 * PlatformFormModal: dirty-tracking + closeAfterSave().
 */

import { html as litHtml } from 'lit';
import { fixture, html, expect, elementUpdated, waitUntil } from '../helpers/render.js';
import { resetPlatformState, bootstrapTestBus } from '../helpers/reset.js';
import { PlatformFormModal } from '@platform/lib/components/glass-form-modal.js';
import { registerModalKind } from '@platform/lib/utils/modal-registry.js';
import '@platform/lib/components/platform-modal-stack.js';
import { getPlatformBus, CoreEvents } from '@platform/lib/events/index.js';

class TestFormModal extends PlatformFormModal {
    static modalKind = 'platform.form_test';
    static i18nNamespace = 'platform';
    render() { return super.render ? super.render() : litHtml`<form><input name="x"/></form>`; }
}
customElements.define('frontend-core-form-modal', TestFormModal);
registerModalKind('platform.form_test', 'frontend-core-form-modal');

describe('PlatformFormModal', () => {
    beforeEach(() => { resetPlatformState(); bootstrapTestBus(); });

    it('isDirty по умолчанию false; close() без isDirty закрывает', async () => {
        const stack = await fixture(html`<platform-modal-stack></platform-modal-stack>`);
        getPlatformBus().dispatch(CoreEvents.UI_MODAL_OPEN, { kind: 'platform.form_test', props: {} });
        await elementUpdated(stack);
        const modal = document.querySelector('frontend-core-form-modal');
        expect(modal, 'modal mounted').to.exist;
        const id = modal._modalId;
        modal.close();
        await elementUpdated(stack);
        await waitUntil(
            () => getPlatformBus().getState().modals.stack.find((m) => m.id === id) === undefined,
            'form modal removed after exit motion',
        );
    });

    it('closeAfterSave обнуляет isDirty и закрывает', async () => {
        const stack = await fixture(html`<platform-modal-stack></platform-modal-stack>`);
        getPlatformBus().dispatch(CoreEvents.UI_MODAL_OPEN, { kind: 'platform.form_test', props: { isDirty: true } });
        await elementUpdated(stack);
        const modal = document.querySelector('frontend-core-form-modal');
        expect(modal, 'modal mounted').to.exist;
        const id = modal._modalId;
        modal.closeAfterSave();
        await elementUpdated(stack);
        expect(modal.isDirty).to.be.false;
        await waitUntil(
            () => getPlatformBus().getState().modals.stack.find((m) => m.id === id) === undefined,
            'form modal removed after save close motion',
        );
    });

    it('close() при isDirty: platform-confirm, подтверждение снимает модалку со стека', async () => {
        const stack = await fixture(html`<platform-modal-stack></platform-modal-stack>`);
        getPlatformBus().dispatch(CoreEvents.UI_MODAL_OPEN, { kind: 'platform.form_test', props: {} });
        await elementUpdated(stack);
        const modal = document.querySelector('frontend-core-form-modal');
        expect(modal, 'modal mounted').to.exist;
        const id = modal._modalId;
        modal.isDirty = true;
        await elementUpdated(modal);
        const closePromise = modal.close();
        await elementUpdated(document.body);
        const confirmEl = document.querySelector('platform-confirm-modal');
        expect(confirmEl, 'platform-confirm mounted').to.exist;
        expect(confirmEl.open).to.be.true;
        await elementUpdated(confirmEl);
        const confirmBtn = confirmEl.shadowRoot.querySelector('.btn-danger');
        expect(confirmBtn, 'discard button').to.exist;
        confirmBtn.click();
        await closePromise;
        await elementUpdated(stack);
        await waitUntil(
            () => getPlatformBus().getState().modals.stack.find((m) => m.id === id) === undefined,
            'dirty form modal removed after discard motion',
        );
    });

    it('close() при isDirty: отмена в platform-confirm оставляет модалку на стеке', async () => {
        const stack = await fixture(html`<platform-modal-stack></platform-modal-stack>`);
        getPlatformBus().dispatch(CoreEvents.UI_MODAL_OPEN, { kind: 'platform.form_test', props: {} });
        await elementUpdated(stack);
        const modal = document.querySelector('frontend-core-form-modal');
        expect(modal, 'modal mounted').to.exist;
        const id = modal._modalId;
        modal.isDirty = true;
        await elementUpdated(modal);
        const closePromise = modal.close();
        await elementUpdated(document.body);
        const confirmEl = document.querySelector('platform-confirm-modal');
        expect(confirmEl, 'platform-confirm mounted').to.exist;
        await elementUpdated(confirmEl);
        const cancelBtn = confirmEl.shadowRoot.querySelector('.btn-secondary');
        expect(cancelBtn, 'keep editing button').to.exist;
        cancelBtn.click();
        await closePromise;
        await elementUpdated(stack);
        expect(getPlatformBus().getState().modals.stack.find((m) => m.id === id)).to.exist;
    });
});
