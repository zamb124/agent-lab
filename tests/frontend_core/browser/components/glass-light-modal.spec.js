/**
 * PlatformLightModal: light DOM модалка, close() диспатчит UI_MODAL_CLOSED
 * (а не CLOSE — потому что light-модалки могут быть mounted напрямую в DOM
 * библиотеками типа Drawflow).
 */

import { fixture, html, expect } from '../helpers/render.js';
import { resetPlatformState, bootstrapTestBus } from '../helpers/reset.js';
import { PlatformLightModal } from '@platform/lib/components/glass-light-modal.js';
import { getPlatformBus, CoreEvents } from '@platform/lib/events/index.js';

class TestLightModal extends PlatformLightModal {}
customElements.define('frontend-core-light-modal', TestLightModal);

describe('PlatformLightModal', () => {
    beforeEach(() => { resetPlatformState(); bootstrapTestBus(); });

    it('по умолчанию open=false', async () => {
        const el = await fixture(html`<frontend-core-light-modal></frontend-core-light-modal>`);
        expect(el.open).to.be.false;
    });

    it('close() диспатчит UI_MODAL_CLOSED с kind=tagName', async () => {
        const el = await fixture(html`<frontend-core-light-modal></frontend-core-light-modal>`);
        const events = [];
        getPlatformBus().subscribeAny((e) => events.push(e));
        el.close();
        const closed = events.find((e) => e.type === CoreEvents.UI_MODAL_CLOSED);
        expect(closed).to.exist;
        expect(closed.payload.kind).to.equal('frontend-core-light-modal');
    });
});
