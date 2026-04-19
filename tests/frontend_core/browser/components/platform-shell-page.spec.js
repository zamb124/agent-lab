/**
 * platform-shell-page: 404 / server-error.
 * + app-loader, platform-deployment-version, pwa-install-banner — простой
 * presentational smoke.
 */

import { fixture, html, expect } from '../helpers/render.js';
import { resetPlatformState, bootstrapTestBus } from '../helpers/reset.js';
import '@platform/lib/components/platform-shell-page.js';
import '@platform/lib/components/app-loader.js';
import '@platform/lib/components/platform-deployment-version.js';
import '@platform/lib/components/pwa-install-banner.js';
import '@platform/lib/components/platform-help-hint.js';

describe('platform-shell-page', () => {
    beforeEach(() => { resetPlatformState(); bootstrapTestBus(); });

    it('по умолчанию kind=not-found → 404', async () => {
        const el = await fixture(html`<platform-shell-page></platform-shell-page>`);
        expect(el.shadowRoot.querySelector('.code').textContent).to.equal('404');
    });

    it('kind=server-error → 500', async () => {
        const el = await fixture(html`<platform-shell-page kind="server-error"></platform-shell-page>`);
        expect(el.shadowRoot.querySelector('.code').textContent).to.equal('500');
    });
});

describe('app-loader / pwa-install-banner / platform-deployment-version / platform-help-hint smoke', () => {
    beforeEach(() => { resetPlatformState(); bootstrapTestBus(); });

    it('app-loader рендерится', async () => {
        const el = await fixture(html`<app-loader></app-loader>`);
        expect(el.shadowRoot).to.exist;
    });

    it('pwa-install-banner рендерится', async () => {
        const el = await fixture(html`<pwa-install-banner></pwa-install-banner>`);
        expect(el.shadowRoot).to.exist;
    });

    it('platform-deployment-version рендерится', async () => {
        const el = await fixture(html`<platform-deployment-version></platform-deployment-version>`);
        expect(el.shadowRoot).to.exist;
    });

    it('platform-help-hint рендерится', async () => {
        const el = await fixture(html`<platform-help-hint></platform-help-hint>`);
        expect(el.shadowRoot).to.exist;
    });
});
