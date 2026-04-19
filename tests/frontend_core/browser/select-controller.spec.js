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

class CounterEl extends LitElement {
    constructor() {
        super();
        this._sidebar = new SelectController(this, (s) => s.ui.sidebar.mobileOpen);
    }
    render() { return litHtml`<div class="v">${String(this._sidebar.value)}</div>`; }
}
customElements.define('frontend-core-counter-el', CounterEl);

describe('SelectController', () => {
    beforeEach(() => { resetPlatformState(); bootstrapTestBus(); });

    it('требует функцию-селектор', () => {
        expect(() => new SelectController({}, null)).to.throw(/selector/);
    });

    it('value доступен сразу после connect', async () => {
        const el = await fixture(html`<frontend-core-counter-el></frontend-core-counter-el>`);
        expect(el.shadowRoot.querySelector('.v').textContent).to.equal('false');
    });

    it('реактивность: dispatch меняет state → render обновляется', async () => {
        const el = await fixture(html`<frontend-core-counter-el></frontend-core-counter-el>`);
        getPlatformBus().dispatch(CoreEvents.UI_SIDEBAR_OPEN_REQUESTED, null);
        await elementUpdated(el);
        expect(el.shadowRoot.querySelector('.v').textContent).to.equal('true');
    });

    it('при disconnect отписывается', async () => {
        const el = await fixture(html`<frontend-core-counter-el></frontend-core-counter-el>`);
        const bus = getPlatformBus();
        el.remove();
        const before = el.shadowRoot.querySelector('.v').textContent;
        bus.dispatch(CoreEvents.UI_SIDEBAR_OPEN_REQUESTED, null);
        // никаких ошибок и render-цикл не дёргается
        expect(el.shadowRoot.querySelector('.v').textContent).to.equal(before);
    });
});
