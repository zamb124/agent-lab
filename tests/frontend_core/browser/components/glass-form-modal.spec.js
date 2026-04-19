/**
 * PlatformFormModal: dirty-tracking + closeAfterSave().
 */

import { html as litHtml } from 'lit';
import { fixture, html, expect, elementUpdated } from '../helpers/render.js';
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
        expect(getPlatformBus().getState().modals.stack.find((m) => m.id === id)).to.be.undefined;
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
        expect(getPlatformBus().getState().modals.stack.find((m) => m.id === id)).to.be.undefined;
    });
});
