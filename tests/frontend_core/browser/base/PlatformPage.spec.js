/**
 * PlatformPage: routeKey/routeParams getters, navigate helper.
 */

import { html as litHtml } from 'lit';
import { fixture, html, expect, elementUpdated } from '../helpers/render.js';
import { resetPlatformState, bootstrapTestBus } from '../helpers/reset.js';
import { PlatformPage } from '@platform/lib/base/PlatformPage.js';
import { getPlatformBus, CoreEvents } from '@platform/lib/events/index.js';

class TestPage extends PlatformPage {
    static i18nNamespace = 'platform';
    render() { return litHtml`<span class="route">${this.routeKey || 'none'}</span>`; }
}
customElements.define('frontend-core-test-page', TestPage);

describe('PlatformPage', () => {
    beforeEach(() => { resetPlatformState(); bootstrapTestBus(); });

    it('routeKey изначально null', async () => {
        const el = await fixture(html`<frontend-core-test-page></frontend-core-test-page>`);
        expect(el.routeKey).to.be.null;
        expect(el.routeParams).to.deep.equal({});
    });

    it('реагирует на ROUTER_ROUTE_CHANGED', async () => {
        const el = await fixture(html`<frontend-core-test-page></frontend-core-test-page>`);
        getPlatformBus().dispatch(CoreEvents.ROUTER_ROUTE_CHANGED, { routeKey: 'home', params: { id: 'x' }, pathname: '/home' });
        await elementUpdated(el);
        expect(el.routeKey).to.equal('home');
        expect(el.routeParams).to.deep.equal({ id: 'x' });
        expect(el.shadowRoot.querySelector('.route').textContent).to.equal('home');
    });

    it('navigate без routeKey — throw', async () => {
        const el = await fixture(html`<frontend-core-test-page></frontend-core-test-page>`);
        expect(() => el.navigate('')).to.throw(/routeKey/);
    });
});
