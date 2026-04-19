/**
 * platform-modal-stack: единственное место рендера модалок. Слушает state.modals.stack,
 * монтирует/убирает компоненты по kind, прокидывает props и _modalId.
 */

import { html as litHtml } from 'lit';
import { fixture, html, expect, elementUpdated } from '../helpers/render.js';
import { resetPlatformState, bootstrapTestBus } from '../helpers/reset.js';
import '@platform/lib/components/platform-modal-stack.js';
import { PlatformElement } from '@platform/lib/platform-element/index.js';
import { registerModalKind } from '@platform/lib/utils/modal-registry.js';
import { getPlatformBus, CoreEvents } from '@platform/lib/events/index.js';

class TestStackModal extends PlatformElement {
    static properties = { open: { type: Boolean, reflect: true }, _modalId: { state: true }, title: { type: String } };
    constructor() { super(); this.open = false; this.title = ''; }
    render() { return litHtml`<div class="m">${this.title}</div>`; }
}
customElements.define('frontend-core-stack-modal', TestStackModal);
registerModalKind('platform.stack_test', 'frontend-core-stack-modal');

describe('platform-modal-stack', () => {
    beforeEach(() => { resetPlatformState(); bootstrapTestBus(); });

    it('создаёт компонент по kind при UI_MODAL_OPEN', async () => {
        const stack = await fixture(html`<platform-modal-stack></platform-modal-stack>`);
        getPlatformBus().dispatch(CoreEvents.UI_MODAL_OPEN, { kind: 'platform.stack_test', props: { title: 'Hello' } });
        await elementUpdated(stack);
        const modal = stack.querySelector('frontend-core-stack-modal');
        expect(modal).to.exist;
        expect(modal.title).to.equal('Hello');
        expect(modal.open).to.be.true;
        expect(modal._modalId).to.match(/^modal_/);
    });

    it('убирает компонент при UI_MODAL_CLOSE', async () => {
        const stack = await fixture(html`<platform-modal-stack></platform-modal-stack>`);
        getPlatformBus().dispatch(CoreEvents.UI_MODAL_OPEN, { kind: 'platform.stack_test', props: {} });
        await elementUpdated(stack);
        const modalId = stack.querySelector('frontend-core-stack-modal')._modalId;
        getPlatformBus().dispatch(CoreEvents.UI_MODAL_CLOSE, { id: modalId });
        await elementUpdated(stack);
        expect(stack.querySelector('frontend-core-stack-modal')).to.be.null;
    });

    it('несколько модалок в стеке', async () => {
        const stack = await fixture(html`<platform-modal-stack></platform-modal-stack>`);
        getPlatformBus().dispatch(CoreEvents.UI_MODAL_OPEN, { kind: 'platform.stack_test', props: { title: 'a' } });
        getPlatformBus().dispatch(CoreEvents.UI_MODAL_OPEN, { kind: 'platform.stack_test', props: { title: 'b' } });
        await elementUpdated(stack);
        const modals = stack.querySelectorAll('frontend-core-stack-modal');
        expect(modals.length).to.equal(2);
        expect(modals[0].title).to.equal('a');
        expect(modals[1].title).to.equal('b');
    });
});
