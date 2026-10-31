/**
 * platform-shell-page: 404 / server-error.
 * + platform-spinner, platform-deployment-version, pwa-install-banner — простой
 * presentational smoke.
 */

import { fixture, html, expect } from '../helpers/render.js';
import { resetPlatformState, bootstrapTestBus } from '../helpers/reset.js';
import '@platform/lib/components/platform-shell-page.js';
import '@platform/lib/components/platform-spinner.js';
import '@platform/lib/components/platform-deployment-version.js';
import '@platform/lib/components/pwa-install-banner.js';
import '@platform/lib/components/platform-help-hint.js';
import { qs, shadow, type TestEl } from '../helpers/dom.js';

describe('platform-shell-page', () => {
    beforeEach(() => { resetPlatformState(); bootstrapTestBus(); });

    it('по умолчанию kind=not-found → 404', async () => {
        const el = await fixture<TestEl>(html`<platform-shell-page></platform-shell-page>`);
        expect(qs(shadow(el), '.code').textContent).to.equal('404');
    });

    it('kind=server-error → 500', async () => {
        const el = await fixture<TestEl>(html`<platform-shell-page kind="server-error"></platform-shell-page>`);
        expect(qs(shadow(el), '.code').textContent).to.equal('500');
    });
});

describe('platform-spinner / pwa-install-banner / platform-deployment-version / platform-help-hint smoke', () => {
    beforeEach(() => { resetPlatformState(); bootstrapTestBus(); });

    it('platform-spinner рендерится', async () => {
        const el = await fixture<TestEl>(html`<platform-spinner size="xl"></platform-spinner>`);
        expect(shadow(el)).to.exist;
    });

    it('pwa-install-banner рендерится', async () => {
        const el = await fixture<TestEl>(html`<pwa-install-banner></pwa-install-banner>`);
        expect(shadow(el)).to.exist;
    });

    it('platform-deployment-version рендерится', async () => {
        const el = await fixture<TestEl>(html`<platform-deployment-version></platform-deployment-version>`);
        expect(shadow(el)).to.exist;
    });

    it('platform-help-hint рендерится', async () => {
        const el = await fixture<TestEl>(html`<platform-help-hint></platform-help-hint>`);
        expect(shadow(el)).to.exist;
    });
});
