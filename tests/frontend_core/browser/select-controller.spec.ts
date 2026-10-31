/**
 * SelectController: Lit ReactiveController, подписка на срез state, requestUpdate
 * при изменении.
 */

import { LitElement, html as litHtml } from 'lit';
import { fixture, html, expect, elementUpdated } from './helpers/render.js';
import { resetPlatformState, bootstrapTestBus } from './helpers/reset.js';
import { SelectController } from '@platform/lib/events/select-controller.js';
import { getPlatformBus } from '@platform/lib/events/index.js';
import { CoreEvents } from '@platform/lib/events/contract.js';
import { qs, shadow, type TestEl } from './helpers/dom.js';

class CounterEl extends LitElement {
    constructor() {
        super();
        (this as TestEl)._sidebar = new SelectController(this, (s) => s.ui.sidebar.mobileOpen);
    }
    override render() { return litHtml`<div class="v">${String((this as TestEl)._sidebar.value)}</div>`; }
}
customElements.define('frontend-core-counter-el', CounterEl);

describe('SelectController', () => {
    beforeEach(() => { resetPlatformState(); bootstrapTestBus(); });

    it('требует функцию-селектор', () => {
        expect(() => new SelectController({ addController() {}, requestUpdate() {} }, null!)).to.throw(/selector/);
    });

    it('value доступен сразу после connect', async () => {
        const el = await fixture<TestEl>(html`<frontend-core-counter-el></frontend-core-counter-el>`);
        expect(qs(shadow(el), '.v').textContent).to.equal('false');
    });

    it('реактивность: dispatch меняет state → render обновляется', async () => {
        const el = await fixture<TestEl>(html`<frontend-core-counter-el></frontend-core-counter-el>`);
        getPlatformBus().dispatch(CoreEvents.UI_SIDEBAR_OPEN_REQUESTED, null);
        await elementUpdated(el);
        expect(qs(shadow(el), '.v').textContent).to.equal('true');
    });

    it('при disconnect отписывается', async () => {
        const el = await fixture<TestEl>(html`<frontend-core-counter-el></frontend-core-counter-el>`);
        const bus = getPlatformBus();
        el.remove();
        const before = qs(shadow(el), '.v').textContent;
        bus.dispatch(CoreEvents.UI_SIDEBAR_OPEN_REQUESTED, null);
        // никаких ошибок и render-цикл не дёргается
        expect(qs(shadow(el), '.v').textContent).to.equal(before);
    });
});
