/**
 * PlatformApp: static factories регистрация, монтирование platform-modal-stack,
 * defaultI18nNamespace.
 */

import { html as litHtml } from 'lit';
import { fixture, html, expect, elementUpdated } from '../helpers/render.js';
import { resetPlatformState } from '../helpers/reset.js';
import { PlatformApp } from '@platform/lib/base/PlatformApp.js';
import { createAsyncOp } from '@platform/lib/events/factories/async-op.js';
import { hasFactory } from '@platform/lib/events/factory-registry.js';
import { getPlatformBus, CoreEvents } from '@platform/lib/events/index.js';

describe('PlatformApp: factories', () => {
    beforeEach(() => resetPlatformState());

    it('static factories регистрируются в registry', async () => {
        const op = createAsyncOp({
            name: 'svc/test_app_op',
            silent: true,
            request: async () => ({ ok: true }),
        });
        class App extends PlatformApp {
            static defaultI18nNamespace = 'platform';
            static factories = [op];
            getBaseUrl() { return ''; }
            getRoutes() { return []; }
            rendersUnauthenticated() { return true; }
            renderRoute() { return litHtml`<div class="content">app</div>`; }
        }
        if (!customElements.get('frontend-core-test-app-1')) {
            customElements.define('frontend-core-test-app-1', App);
        }
        const el = await fixture(html`<frontend-core-test-app-1></frontend-core-test-app-1>`);
        expect(hasFactory('svc/test_app_op')).to.be.true;
        // bus поднят, slice op зарегистрирован
        const state = getPlatformBus().getState();
        expect(state[op.sliceKey]).to.exist;
        expect(el).to.exist;
    });

    it('требует уникальный sliceKey между factories и getServiceSlices()', async () => {
        const op = createAsyncOp({
            name: 'svc/test_collision_op',
            silent: true,
            request: async () => ({}),
        });
        class App extends PlatformApp {
            static defaultI18nNamespace = 'platform';
            static factories = [op];
            getBaseUrl() { return ''; }
            getRoutes() { return []; }
            rendersUnauthenticated() { return true; }
            getServiceSlices() {
                return { [op.sliceKey]: { reducer: (s) => s, initial: {} } };
            }
            renderRoute() { return litHtml`<div></div>`; }
        }
        if (!customElements.get('frontend-core-test-app-2')) {
            customElements.define('frontend-core-test-app-2', App);
        }
        // Конструктор PlatformApp бросает на коллизии sliceKey ДО монтирования.
        expect(() => new App()).to.throw(/sliceKey/);
    });
});

describe('PlatformApp: render', () => {
    beforeEach(() => resetPlatformState());

    it('рендерит loading-spinner до AUTH_VALIDATED', async () => {
        class App extends PlatformApp {
            static defaultI18nNamespace = 'platform';
            getBaseUrl() { return ''; }
            getRoutes() { return []; }
            renderRoute() { return litHtml`<div class="route-content">route</div>`; }
        }
        if (!customElements.get('frontend-core-test-app-3')) {
            customElements.define('frontend-core-test-app-3', App);
        }
        const el = await fixture(html`<frontend-core-test-app-3></frontend-core-test-app-3>`);
        expect(el.shadowRoot.querySelector('.loading-spinner')).to.exist;
    });

    it('после AUTH_USER_LOADED рендерит renderRoute() + platform-modal-stack', async () => {
        class App extends PlatformApp {
            static defaultI18nNamespace = 'platform';
            getBaseUrl() { return ''; }
            getRoutes() { return []; }
            renderRoute() { return litHtml`<div class="route-content">route</div>`; }
        }
        if (!customElements.get('frontend-core-test-app-4')) {
            customElements.define('frontend-core-test-app-4', App);
        }
        const el = await fixture(html`<frontend-core-test-app-4></frontend-core-test-app-4>`);
        getPlatformBus().dispatch(CoreEvents.AUTH_USER_LOADED, { user: { user_id: 'u1', name: 'A', company_id: 'c1' } });
        await elementUpdated(el);
        expect(el.shadowRoot.querySelector('.route-content')).to.exist;
        expect(el.shadowRoot.querySelector('platform-modal-stack')).to.exist;
    });
});
