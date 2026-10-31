/**
 * Runtime typography: Inter на body и в Shadow DOM (кнопки не должны падать в UA Arial).
 * Без поднятия сервисов — web-test-runner + Playwright + tokens/reset из static middleware.
 */

import { fixture, fixtureCleanup, html, expect, elementUpdated } from '../helpers/render.js';
import { resetPlatformState, bootstrapTestBus } from '../helpers/reset.js';
import { PlatformElement } from '@platform/lib/platform-element/index.js';
import '@platform/lib/components/platform-button.js';

const TOKENS_HREF = '/core/frontend/static/assets/css/tokens.css';
const RESET_HREF = '/core/frontend/static/assets/css/reset.css';

const FORBIDDEN_PRIMARY_FONTS = new Set([
    'Arial',
    'Times New Roman',
    'Times',
    'Courier New',
    'Courier',
]);

class ShadowButtonTypographyProbe extends PlatformElement {
    render() {
        return html`
            <button class="probe-button">
                <span class="probe-label">Alice</span>
            </button>
        `;
    }
}

if (!customElements.get('shadow-button-typography-probe')) {
    customElements.define('shadow-button-typography-probe', ShadowButtonTypographyProbe);
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
 * @param {string} fontFamily
 */
function primaryFontName(fontFamily) {
    const first = fontFamily.split(',')[0].trim();
    return first.replace(/^['"]|['"]$/g, '');
}

/**
 * @param {Element} element
 * @param {string} [label]
 */
function expectPlatformSans(element, label = 'element') {
    const primary = primaryFontName(getComputedStyle(element).fontFamily);
    expect(FORBIDDEN_PRIMARY_FONTS.has(primary), `${label}: forbidden UA font "${primary}"`).to.be.false;
    expect(primary, `${label}: expected Inter, got "${primary}"`).to.equal('Inter');
}

describe('platform typography runtime', () => {
    beforeEach(async () => {
        resetPlatformState();
        bootstrapTestBus();
        await loadStylesheet(TOKENS_HREF);
        await loadStylesheet(RESET_HREF);
        await document.fonts.ready;
    });

    afterEach(() => {
        fixtureCleanup();
    });

    it('reset.css задаёт Inter на body', () => {
        expectPlatformSans(document.body, 'body');
    });

    it('PlatformElement shadow reset: span внутри button не рисуется Arial (как platform-user)', async () => {
        const el = await fixture(html`<shadow-button-typography-probe></shadow-button-typography-probe>`);
        await elementUpdated(el);

        const probeButton = el.shadowRoot.querySelector('.probe-button');
        const probeLabel = el.shadowRoot.querySelector('.probe-label');
        expect(probeButton, 'probe .probe-button').to.exist;
        expect(probeLabel, 'probe .probe-label').to.exist;

        expectPlatformSans(probeButton, 'probe .probe-button');
        expectPlatformSans(probeLabel, 'probe .probe-label');
    });

    it('platform-button: inner button наследует Inter из PlatformElement shadow reset', async () => {
        const el = await fixture(html`<platform-button>Save</platform-button>`);
        await elementUpdated(el);

        const button = el.shadowRoot.querySelector('button');
        expect(button, 'platform-button inner button').to.exist;
        expectPlatformSans(button, 'platform-button inner button');
    });
});
