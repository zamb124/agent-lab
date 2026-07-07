import { fixture, fixtureCleanup, html, expect, elementUpdated } from '../helpers/render.js';
import { resetPlatformState, bootstrapTestBus } from '../helpers/reset.js';
import '../../../../core/frontend/static/lib/chat/platform-chat.js';

const TOKENS_HREF = '/core/frontend/static/assets/css/tokens.css';

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
 * @param {string} varName
 * @param {ParentNode} [scope]
 */
function readBackgroundForVar(varName, scope = document.documentElement) {
    const probe = document.createElement('div');
    probe.style.cssText = `position:absolute;visibility:hidden;background:var(${varName})`;
    scope.appendChild(probe);
    const backgroundColor = getComputedStyle(probe).backgroundColor;
    probe.remove();
    return backgroundColor;
}

describe('platform-chat theme tokens', () => {
    /** @type {ReturnType<typeof bootstrapTestBus>} */
    let bus;
    /** @type {(() => void) | null} */
    let restoreFetch;

    beforeEach(async () => {
        resetPlatformState();
        bus = bootstrapTestBus();
        await loadStylesheet(TOKENS_HREF);

        const previousFetch = window.fetch;
        restoreFetch = () => {
            window.fetch = previousFetch;
        };
        window.fetch = async (rawUrl, init = {}) => {
            const method = (init.method || 'GET').toUpperCase();
            const url = new URL(String(rawUrl), window.location.href);
            if (method === 'GET' && /\/flows\/api\/v1\/[^/]+\/chat-profile$/.test(url.pathname)) {
                return new Response(JSON.stringify({ chat: {}, viewer: {}, look: null }), {
                    status: 200,
                    headers: { 'content-type': 'application/json; charset=utf-8' },
                });
            }
            return previousFetch(rawUrl, init);
        };
    });

    afterEach(() => {
        if (restoreFetch) {
            restoreFetch();
            restoreFetch = null;
        }
        fixtureCleanup();
    });

    it('maps --platform-chat-panel-bg to platform glass-solid-strong', () => {
        const glassStrong = readBackgroundForVar('--glass-solid-strong');
        const chatPanelBg = readBackgroundForVar('--platform-chat-panel-bg');
        expect(chatPanelBg).to.equal(glassStrong);
    });

    it('drawer panel shell uses platform-chat panel tokens, not inline host palette', async () => {
        const el = await fixture(html`
            <platform-chat
                display="drawer"
                profile="spa"
                flow-id="theme-test-flow"
                flows-base-url="/flows"
                initial-open
            ></platform-chat>
        `);
        await elementUpdated(el);

        const panel = el.renderRoot.querySelector('.panel');
        expect(panel).to.not.equal(null);

        const expectedPanelBg = readBackgroundForVar('--platform-chat-panel-bg');
        const panelBg = getComputedStyle(panel).backgroundColor;
        expect(panelBg).to.equal(expectedPanelBg);

        expect(el.style.getPropertyValue('--platform-chat-accent').trim()).to.equal('');
        expect(el.style.getPropertyValue('--embed-chat-accent').trim()).to.equal('');
    });
});
