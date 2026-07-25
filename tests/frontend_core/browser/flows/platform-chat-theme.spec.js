import { fixture, fixtureCleanup, html, expect, elementUpdated } from '../helpers/render.js';
import { resetPlatformState, bootstrapTestBus } from '../helpers/reset.js';
import '../../../../core/frontend/static/lib/chat/platform-chat.js';
import { platformStorageKey } from '../../../../core/frontend/static/lib/utils/storage-keys.js';

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
        window.localStorage.removeItem(platformStorageKey('crm', 'lara_launcher_position.crm'));
        window.localStorage.removeItem(platformStorageKey('crm', 'lara_panel_width.crm'));
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

    it('uses Linnex mark and persists dragged launcher position without opening', async () => {
        const el = await fixture(html`
            <platform-chat
                display="drawer"
                profile="spa"
                flow-id="lara"
                branch-id="crm"
                launcher-storage-scope="crm"
                flows-base-url="/flows"
                show-launcher
            ></platform-chat>
        `);
        await elementUpdated(el);

        const fab = el.renderRoot.querySelector('.fab');
        const logo = el.renderRoot.querySelector('.fab-logo');
        expect(fab).to.exist;
        expect(logo.getAttribute('src')).to.equal(
            `${window.location.origin}/static/core/assets/service_logos/linnex_spinner_logo.png`,
        );

        const rect = fab.getBoundingClientRect();
        fab.dispatchEvent(new PointerEvent('pointerdown', {
            pointerId: 11,
            button: 0,
            clientX: rect.left + 10,
            clientY: rect.top + 10,
            bubbles: true,
        }));
        window.dispatchEvent(new PointerEvent('pointermove', {
            pointerId: 11,
            clientX: 120,
            clientY: 140,
        }));
        window.dispatchEvent(new PointerEvent('pointerup', {
            pointerId: 11,
            clientX: 120,
            clientY: 140,
        }));
        fab.click();
        await elementUpdated(el);

        expect(el.open).to.equal(false);
        const serialized = window.localStorage.getItem(
            platformStorageKey('crm', 'lara_launcher_position.crm'),
        );
        expect(serialized).to.be.a('string');
        const saved = JSON.parse(serialized);
        expect(saved.left).to.be.at.least(8);
        expect(saved.top).to.be.at.least(8);

        fixtureCleanup();
        const restored = await fixture(html`
            <platform-chat
                display="drawer"
                profile="spa"
                flow-id="lara"
                branch-id="crm"
                launcher-storage-scope="crm"
                flows-base-url="/flows"
                show-launcher
            ></platform-chat>
        `);
        await elementUpdated(restored);
        const restoredFab = restored.renderRoot.querySelector('.fab');
        expect(restoredFab.style.left).to.equal(`${saved.left}px`);
        expect(restoredFab.style.top).to.equal(`${saved.top}px`);
    });

    it('opens the Lara drawer on launcher click', async () => {
        const el = await fixture(html`
            <platform-chat
                display="drawer"
                profile="spa"
                flow-id="lara"
                branch-id="crm"
                launcher-storage-scope="crm"
                flows-base-url="/flows"
                show-launcher
            ></platform-chat>
        `);
        await elementUpdated(el);
        el.renderRoot.querySelector('.fab').click();
        await elementUpdated(el);
        expect(el.open).to.equal(true);
    });

    it('persists dragged panel width and restores on remount', async () => {
        const previousMatchMedia = window.matchMedia;
        window.matchMedia = (query) => {
            if (String(query).includes('max-width: 767px')) {
                return {
                    matches: false,
                    media: String(query),
                    onchange: null,
                    addListener() {},
                    removeListener() {},
                    addEventListener() {},
                    removeEventListener() {},
                    dispatchEvent() {
                        return false;
                    },
                };
            }
            return previousMatchMedia.call(window, query);
        };

        try {
            const el = await fixture(html`
                <platform-chat
                    display="drawer"
                    profile="spa"
                    flow-id="lara"
                    branch-id="crm"
                    launcher-storage-scope="crm"
                    flows-base-url="/flows"
                    initial-open
                ></platform-chat>
            `);
            await elementUpdated(el);
            expect(el.open).to.equal(true);

            const handle = el.renderRoot.querySelector('.panel-resize-handle');
            expect(handle).to.exist;
            expect(handle.getAttribute('data-edge')).to.equal('left');

            const panel = el.renderRoot.querySelector('.panel');
            const startWidth = panel.getBoundingClientRect().width;
            expect(startWidth).to.be.above(0);

            handle.dispatchEvent(new PointerEvent('pointerdown', {
                pointerId: 21,
                button: 0,
                clientX: 40,
                clientY: 120,
                bubbles: true,
            }));
            window.dispatchEvent(new PointerEvent('pointermove', {
                pointerId: 21,
                clientX: 40 - 120,
                clientY: 120,
            }));
            window.dispatchEvent(new PointerEvent('pointerup', {
                pointerId: 21,
                clientX: 40 - 120,
                clientY: 120,
            }));
            await elementUpdated(el);

            const serialized = window.localStorage.getItem(
                platformStorageKey('crm', 'lara_panel_width.crm'),
            );
            expect(serialized).to.be.a('string');
            const savedWidth = JSON.parse(serialized);
            expect(savedWidth).to.be.a('number');
            expect(savedWidth).to.be.at.least(320);
            expect(savedWidth).to.be.above(startWidth);

            fixtureCleanup();
            const restored = await fixture(html`
                <platform-chat
                    display="drawer"
                    profile="spa"
                    flow-id="lara"
                    branch-id="crm"
                    launcher-storage-scope="crm"
                    flows-base-url="/flows"
                    initial-open
                ></platform-chat>
            `);
            await elementUpdated(restored);
            const restoredPanel = restored.renderRoot.querySelector('.panel');
            expect(restoredPanel.style.getPropertyValue('--embed-panel-width').trim()).to.equal(
                `${savedWidth}px`,
            );
        } finally {
            window.matchMedia = previousMatchMedia;
        }
    });
});
