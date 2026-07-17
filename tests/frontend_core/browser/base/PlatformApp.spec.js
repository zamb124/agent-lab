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
import { CRMApp } from '../../../../apps/crm/ui/app/crm-app.js';
import { FlowsApp } from '../../../../apps/flows/ui/app/flows-app.js';
import { FrontendApp } from '../../../../apps/frontend/ui/app/frontend-app.js';
import { OfficeApp } from '../../../../apps/office/ui/app/office-app.js';
import { HumanitecModelsApp } from '../../../../apps/provider_litserve/ui/app/litserve-app.js';
import { RagApp } from '../../../../apps/rag/ui/app/rag-app.js';
import { SyncApp } from '../../../../apps/sync/ui/app/sync-app.js';
import { WorktrackerApp } from '../../../../apps/worktracker/ui/app/worktracker-app.js';

const PLATFORM_ASSISTANT_BRANCH_MATRIX = Object.freeze([
    { serviceId: 'frontend', branchId: 'console', app: FrontendApp },
    { serviceId: 'crm', branchId: 'crm', app: CRMApp },
    { serviceId: 'flows', branchId: 'flows', app: FlowsApp },
    { serviceId: 'sync', branchId: 'sync', app: SyncApp },
    { serviceId: 'rag', branchId: 'documents', app: RagApp },
    { serviceId: 'office', branchId: 'documents', app: OfficeApp },
    { serviceId: 'worktracker', branchId: 'worktracker', app: WorktrackerApp },
    { serviceId: 'litserve', branchId: 'litserve', app: HumanitecModelsApp },
]);

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

    it('service app roots declare Lara branch for all eight SPA', () => {
        for (const entry of PLATFORM_ASSISTANT_BRANCH_MATRIX) {
            expect(entry.app.platformAssistant).to.deep.include({
                serviceId: entry.serviceId,
                branchId: entry.branchId,
                showLauncher: true,
            });
        }
    });

    it('рендерит platform-spinner до AUTH_VALIDATED', async () => {
        class App extends PlatformApp {
            static defaultI18nNamespace = 'platform';
            static platformAssistant = {
                serviceId: 'frontend',
                branchId: 'console',
                showLauncher: false,
            };
            getBaseUrl() { return ''; }
            getRoutes() { return []; }
            renderRoute() { return litHtml`<div class="route-content">route</div>`; }
        }
        if (!customElements.get('frontend-core-test-app-3')) {
            customElements.define('frontend-core-test-app-3', App);
        }
        const el = await fixture(html`<frontend-core-test-app-3></frontend-core-test-app-3>`);
        expect(el.shadowRoot.querySelector('.loading-container')).to.exist;
        expect(el.shadowRoot.querySelector('platform-spinner')).to.exist;
        expect(el.shadowRoot.querySelector('.loading-text')).to.not.exist;
    });

    it('после AUTH_USER_LOADED рендерит renderRoute() + platform-modal-stack', async () => {
        class App extends PlatformApp {
            static defaultI18nNamespace = 'platform';
            static platformAssistant = {
                serviceId: 'frontend',
                branchId: 'console',
                showLauncher: false,
            };
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
        const lara = el.shadowRoot.querySelector('platform-chat[flow-id="lara"]');
        expect(lara).to.exist;
        expect(lara.branchId).to.equal('console');
        expect(lara.companyId).to.equal('c1');
    });

    it('не монтирует Lara на маршруте, исключённом route policy', async () => {
        class App extends PlatformApp {
            static defaultI18nNamespace = 'platform';
            static platformAssistant = {
                serviceId: 'frontend',
                branchId: 'console',
                showLauncher: true,
            };
            getBaseUrl() { return ''; }
            getRoutes() { return []; }
            shouldRenderPlatformAssistant() { return false; }
            renderRoute() { return litHtml`<div class="public-route">public</div>`; }
        }
        if (!customElements.get('frontend-core-test-app-5')) {
            customElements.define('frontend-core-test-app-5', App);
        }
        const el = await fixture(html`<frontend-core-test-app-5></frontend-core-test-app-5>`);
        getPlatformBus().dispatch(CoreEvents.AUTH_USER_LOADED, {
            user: { user_id: 'u2', name: 'B', company_id: 'c2' },
        });
        await elementUpdated(el);
        expect(el.shadowRoot.querySelector('.public-route')).to.exist;
        expect(el.shadowRoot.querySelector('platform-chat[flow-id="lara"]')).to.equal(null);
    });

    it('service apps hide Lara on public guest routes', () => {
        expect(FrontendApp.prototype.shouldRenderPlatformAssistant.call({}, 'landing')).to.equal(false);
        expect(FrontendApp.prototype.shouldRenderPlatformAssistant.call({}, 'login')).to.equal(false);
        expect(FrontendApp.prototype.shouldRenderPlatformAssistant.call({}, 'dashboard')).to.equal(true);
        expect(SyncApp.prototype.shouldRenderPlatformAssistant.call({}, 'call_join')).to.equal(false);
        expect(SyncApp.prototype.shouldRenderPlatformAssistant.call({}, 'channel')).to.equal(true);
        expect(OfficeApp.prototype.shouldRenderPlatformAssistant.call({}, 'documents_public_preview')).to.equal(false);
        expect(OfficeApp.prototype.shouldRenderPlatformAssistant.call({}, 'documents')).to.equal(true);
    });
});

for (const entry of PLATFORM_ASSISTANT_BRANCH_MATRIX) {
    describe(`PlatformApp Lara mount: ${entry.serviceId}`, () => {
        beforeEach(() => resetPlatformState());

        it(`монтирует branch ${entry.branchId}`, async () => {
            class App extends PlatformApp {
                static defaultI18nNamespace = 'platform';
                static platformAssistant = {
                    serviceId: entry.serviceId,
                    branchId: entry.branchId,
                    showLauncher: true,
                };
                getBaseUrl() { return ''; }
                getRoutes() { return []; }
                renderRoute() { return litHtml`<div class="route-content">${entry.serviceId}</div>`; }
            }
            const tagName = `frontend-core-test-lara-${entry.serviceId}`;
            if (!customElements.get(tagName)) {
                customElements.define(tagName, App);
            }
            const el = await fixture(document.createElement(tagName));
            getPlatformBus().dispatch(CoreEvents.AUTH_USER_LOADED, {
                user: { user_id: 'u1', name: 'A', company_id: 'c1' },
            });
            await elementUpdated(el);
            const lara = el.shadowRoot.querySelector('platform-chat[flow-id="lara"]');
            expect(lara).to.exist;
            expect(lara.branchId).to.equal(entry.branchId);
            expect(lara.launcherStorageScope).to.equal(entry.serviceId);
            expect(lara.showLauncher).to.equal(true);
        });
    });
}
