/**
 * Primary CTA text on violet fill must stay white in light theme.
 * Guards against :host button { color: inherit } overpowering .cta-btn / .btn-primary.
 */

import { css } from 'lit';
import { fixture, fixtureCleanup, html, expect, elementUpdated } from '../helpers/render.js';
import { resetPlatformState, bootstrapTestBus } from '../helpers/reset.js';
import { PlatformElement } from '@platform/lib/platform-element/index.js';

const TOKENS_HREF = '/core/frontend/static/assets/css/tokens.css';

class PrimaryCtaColorProbe extends PlatformElement {
    static styles = [
        PlatformElement.styles,
        css`
            .cta-btn {
                background: var(--platform-btn-primary-bg);
                color: var(--platform-btn-primary-text);
                border: none;
                border-radius: var(--btn-radius, 22px);
                padding: var(--btn-padding, 8px 24px);
            }
        `,
    ];

    render() {
        return html`
            <button class="cta-btn" type="button">Add note</button>
            <button class="btn btn-primary" type="button">Primary</button>
        `;
    }
}

if (!customElements.get('primary-cta-color-probe')) {
    customElements.define('primary-cta-color-probe', PrimaryCtaColorProbe);
}

/**
 * @param {string} href
 */
function loadStylesheet(href) {
    return new Promise((resolve, reject) => {
        const existing = document.querySelector(`link[rel="stylesheet"][href="${href}"]`);
        if (existing) {
            resolve();
            return;
        }
        const link = document.createElement('link');
        link.rel = 'stylesheet';
        link.href = href;
        link.onload = () => resolve();
        link.onerror = () => reject(new Error(`Failed to load stylesheet: ${href}`));
        document.head.appendChild(link);
    });
}

/**
 * @param {string} color
 */
function isWhiteRgb(color) {
    const match = color.match(/^rgba?\(\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)/);
    if (!match) {
        return false;
    }
    return Number(match[1]) === 255 && Number(match[2]) === 255 && Number(match[3]) === 255;
}

describe('platform button primary text color', () => {
    /** @type {string | null} */
    let previousTheme;

    beforeEach(async () => {
        resetPlatformState();
        bootstrapTestBus();
        await loadStylesheet(TOKENS_HREF);
        previousTheme = document.documentElement.getAttribute('data-theme');
        document.documentElement.setAttribute('data-theme', 'light');
    });

    afterEach(() => {
        if (previousTheme === null) {
            document.documentElement.removeAttribute('data-theme');
        } else {
            document.documentElement.setAttribute('data-theme', previousTheme);
        }
        fixtureCleanup();
    });

    it('light theme: .cta-btn and .btn-primary keep white text over platform primary bg', async () => {
        const el = await fixture(html`<primary-cta-color-probe></primary-cta-color-probe>`);
        await elementUpdated(el);

        const cta = el.shadowRoot.querySelector('.cta-btn');
        const primary = el.shadowRoot.querySelector('.btn-primary');
        expect(cta, '.cta-btn').to.exist;
        expect(primary, '.btn-primary').to.exist;

        const ctaColor = getComputedStyle(cta).color;
        const primaryColor = getComputedStyle(primary).color;
        expect(isWhiteRgb(ctaColor), `.cta-btn color should be white, got "${ctaColor}"`).to.equal(true);
        expect(isWhiteRgb(primaryColor), `.btn-primary color should be white, got "${primaryColor}"`).to.equal(true);
    });
});
