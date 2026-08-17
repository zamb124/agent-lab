/**
 * flow-ui-drawer cluster: реальные pointer-жесты Chromium, viewport и localStorage.
 */

import { resetMouse, sendMouse, setViewport } from '@web/test-runner-commands';
import { fixture, fixtureCleanup, html, expect, elementUpdated, waitUntil } from '../helpers/render.js';
import { buildDefaultChatDocument } from '@platform/lib/flow-ui/templates/chat-template.js';
import {
    drawerGeometryStorageKey,
    readEmbedDrawerGeometry,
    readLaraDrawerGeometry,
    writeEmbedDrawerGeometry,
    writeLaraDrawerGeometry,
} from '@platform/lib/flow-ui/shell/preferences.js';
import { FLOW_UI_DRAWER_MOVE_START } from '@platform/lib/flow-ui/shell/drawer-move.js';
import '@platform/lib/flow-ui/shell/drawer.js';
import '@platform/lib/flow-ui/components/platform-flow-ui.js';

const DESKTOP_VIEWPORT = Object.freeze({ width: 1280, height: 800 });
const MOBILE_VIEWPORT = Object.freeze({ width: 400, height: 720 });
const EMBED_PREFS_PREFIX = 'linnex.flow-ui.preferences.v1:drawer:';

/** @type {string[]} */
const trackedStorageKeys = [];

function uniqueSnakeId(prefix) {
    return `${prefix}_${crypto.randomUUID().replace(/-/g, '')}`;
}

function trackStorageKey(key) {
    trackedStorageKeys.push(key);
    return key;
}

function toPagePoint(clientX, clientY) {
    let x = clientX;
    let y = clientY;
    let view = window;
    while (view.frameElement instanceof Element) {
        const frameRect = view.frameElement.getBoundingClientRect();
        x += frameRect.left;
        y += frameRect.top;
        view = view.parent;
    }
    return { x: Math.round(x), y: Math.round(y) };
}

function isInteractiveHit(node) {
    let current = node;
    while (current instanceof Element) {
        if (['BUTTON', 'A', 'INPUT', 'TEXTAREA', 'SELECT', 'SUMMARY'].includes(current.tagName)) {
            return true;
        }
        if (current.getAttribute('role') === 'button') {
            return true;
        }
        const root = current.getRootNode();
        current = current.parentElement ?? (root instanceof ShadowRoot ? root.host : null);
    }
    return false;
}

function pointInside(el) {
    const rect = el.getBoundingClientRect();
    if (rect.width <= 0 || rect.height <= 0) {
        throw new Error(`drawer-geometry test: ${el.className || el.tagName} has no box`);
    }
    const samples = [
        { x: rect.left + rect.width / 2, y: rect.top + Math.min(8, rect.height / 2) },
        { x: rect.left + 10, y: rect.top + 6 },
        { x: rect.right - 10, y: rect.top + 6 },
        { x: rect.left + rect.width / 2, y: rect.top + rect.height / 2 },
    ];
    for (const sample of samples) {
        const hit = el.ownerDocument.elementFromPoint(sample.x, sample.y);
        if (hit === null || isInteractiveHit(hit)) {
            continue;
        }
        return toPagePoint(sample.x, sample.y);
    }
    return toPagePoint(rect.left + rect.width / 2, rect.top + rect.height / 2);
}

async function mouseClick(el) {
    const point = pointInside(el);
    await sendMouse({ type: 'click', position: [point.x, point.y] });
}

async function mouseDrag(el, dx, dy) {
    const point = pointInside(el);
    await sendMouse({ type: 'move', position: [point.x, point.y] });
    await sendMouse({ type: 'down' });
    await sendMouse({ type: 'move', position: [point.x + dx, point.y + dy] });
    await sendMouse({ type: 'up' });
}

function launcherOf(el) {
    const launcher = el.shadowRoot.querySelector('.launcher');
    if (launcher === null) {
        throw new Error('drawer-geometry test: launcher is required');
    }
    return launcher;
}

function panelOf(el) {
    const panel = el.shadowRoot.querySelector('.panel');
    if (panel === null) {
        throw new Error('drawer-geometry test: panel is required');
    }
    return panel;
}

async function mountDrawer(config = {}) {
    const branchId = typeof config.branchId === 'string' ? config.branchId : uniqueSnakeId('geo');
    const embedId = typeof config.embedId === 'string' ? config.embedId : '';
    if (embedId !== '') {
        trackStorageKey(`${EMBED_PREFS_PREFIX}${embedId}`);
    } else {
        trackStorageKey(drawerGeometryStorageKey(branchId));
    }
    const el = await fixture(html`
        <flow-ui-drawer .config=${{
            baseUrl: '/flows',
            branchId,
            flowId: 'lara',
            showLauncher: true,
            locale: 'en',
            profile: 'spa',
            ...config,
        }}></flow-ui-drawer>
    `);
    await elementUpdated(el);
    return el;
}

async function waitOpen(el) {
    await waitUntil(() => el.hasAttribute('open'), 'drawer opened', { timeout: 5_000 });
}

async function hydrateDrawerDocument(el) {
    const flowUi = el.shadowRoot.querySelector('platform-flow-ui');
    if (flowUi === null) {
        throw new Error('drawer-geometry test: platform-flow-ui is required');
    }
    flowUi.initialDocument = buildDefaultChatDocument({ greetingMessage: '' });
    await elementUpdated(flowUi);
    await waitUntil(
        () => flowUi.shadowRoot.querySelector('flow-ui-surface') !== null,
        'flow-ui-surface after local document',
        { timeout: 5_000 },
    );
    const surface = flowUi.shadowRoot.querySelector('flow-ui-surface');
    await elementUpdated(surface);
    await waitUntil(
        () => surface.shadowRoot.querySelector('.section--chat-header') !== null,
        'chat header after local document',
        { timeout: 5_000 },
    );
    return surface.shadowRoot.querySelector('.section--chat-header');
}

describe('flow-ui-drawer geometry', function () {
    this.timeout(15_000);

    beforeEach(async () => {
        await setViewport(DESKTOP_VIEWPORT);
    });

    afterEach(async () => {
        await resetMouse();
        await setViewport(DESKTOP_VIEWPORT);
        fixtureCleanup();
        while (trackedStorageKeys.length > 0) {
            window.localStorage.removeItem(trackedStorageKeys.pop());
        }
    });

    it('toggles on launcher click and does not toggle on drag', async () => {
        const el = await mountDrawer();
        expect(el.getAttribute('data-drawer-gestures')).to.equal('on');
        const launcher = launcherOf(el);

        await mouseClick(launcher);
        await waitOpen(el);
        expect(el.hasAttribute('open')).to.equal(true);

        const leftBefore = launcher.getBoundingClientRect().left;
        await mouseDrag(launcher, -80, 0);
        await waitUntil(
            () => launcher.getBoundingClientRect().left < leftBefore - 20,
            'launcher moved left',
            { timeout: 5_000 },
        );
        expect(el.hasAttribute('open')).to.equal(true);
    });

    it('moves the launcher when the chat header is dragged', async () => {
        const el = await mountDrawer();
        await mouseClick(launcherOf(el));
        await waitOpen(el);
        const header = await hydrateDrawerDocument(el);
        const launcher = launcherOf(el);
        const leftBefore = launcher.getBoundingClientRect().left;

        await mouseDrag(header, -90, 0);
        await waitUntil(
            () => launcher.getBoundingClientRect().left < leftBefore - 20,
            'header drag moved launcher',
            { timeout: 5_000 },
        );
        expect(el.hasAttribute('open')).to.equal(true);
    });

    it('chat header emits flow-ui-drawer-move-start when drawer-move is on', async () => {
        const document = buildDefaultChatDocument({ greetingMessage: '' });
        const wrap = await fixture(html`
            <div style="width:480px;height:640px;display:flex;flex-direction:column">
                <platform-flow-ui
                    style="flex:1 1 0;min-height:0;height:100%"
                    display="drawer"
                    profile="embed_public"
                    locale="en"
                    .initialDocument=${document}
                ></platform-flow-ui>
            </div>
        `);
        const host = wrap.querySelector('platform-flow-ui');
        await elementUpdated(host);
        await waitUntil(
            () => host.shadowRoot.querySelector('flow-ui-surface') !== null,
            'surface after local document',
            { timeout: 5_000 },
        );
        const surface = host.shadowRoot.querySelector('flow-ui-surface');
        await elementUpdated(surface);
        expect(surface.hasAttribute('drawer-move')).to.equal(true);
        await waitUntil(
            () => surface.shadowRoot.querySelector('.section--chat-header') !== null,
            'chat header visible',
            { timeout: 5_000 },
        );
        const header = surface.shadowRoot.querySelector('.section--chat-header');
        const moved = new Promise((resolve) => {
            host.addEventListener(FLOW_UI_DRAWER_MOVE_START, resolve, { once: true });
        });
        const point = pointInside(header);
        await sendMouse({ type: 'move', position: [point.x, point.y] });
        await sendMouse({ type: 'down' });
        const event = await moved;
        expect(event.detail.clientX).to.be.a('number');
        expect(event.detail.clientY).to.be.a('number');
        expect(event.detail.pointerId).to.be.a('number');
        await sendMouse({ type: 'up' });
    });

    it('SE handle changes width and height', async () => {
        const branchId = uniqueSnakeId('geo');
        writeLaraDrawerGeometry(branchId, {
            launcherLeft: 180,
            launcherTop: 480,
            panelWidth: 300,
            panelHeight: 320,
        });
        const el = await mountDrawer({ branchId });
        await mouseClick(launcherOf(el));
        await waitOpen(el);
        await waitUntil(
            () => el.shadowRoot.querySelector('.resize-handle') !== null,
            'resize handle visible',
            { timeout: 5_000 },
        );
        const handle = el.shadowRoot.querySelector('.resize-handle');
        const panel = panelOf(el);
        const start = panel.getBoundingClientRect();
        await mouseDrag(handle, 70, 50);
        await waitUntil(
            () => {
                const next = panel.getBoundingClientRect();
                return next.width > start.width + 20 && next.height > start.height + 20;
            },
            'panel grew from SE',
            { timeout: 5_000 },
        );
    });

    it('persists cluster geometry and restores it after remount', async () => {
        const branchId = uniqueSnakeId('geo');
        const storageKey = drawerGeometryStorageKey(branchId);
        const el = await mountDrawer({ branchId });
        const launcher = launcherOf(el);
        await mouseDrag(launcher, -80, -30);
        await waitUntil(
            () => window.localStorage.getItem(storageKey) !== null,
            'geometry written',
            { timeout: 5_000 },
        );
        const savedLeft = Math.round(launcher.getBoundingClientRect().left);
        const raw = window.localStorage.getItem(storageKey);
        expect(JSON.parse(raw).launcherLeft).to.be.closeTo(savedLeft, 1);

        fixtureCleanup();
        const restored = await mountDrawer({ branchId });
        expect(Math.round(launcherOf(restored).getBoundingClientRect().left)).to.be.closeTo(
            savedLeft,
            1,
        );
    });

    it('round-trips Lara and embed geometry through real localStorage', async () => {
        const branchId = uniqueSnakeId('geo');
        const embedId = uniqueSnakeId('emb');
        trackStorageKey(drawerGeometryStorageKey(branchId));
        trackStorageKey(`${EMBED_PREFS_PREFIX}${embedId}`);
        const geometry = {
            launcherLeft: 80,
            launcherTop: 90,
            panelWidth: 320,
            panelHeight: 400,
        };
        writeLaraDrawerGeometry(branchId, geometry);
        expect(readLaraDrawerGeometry(branchId)).to.deep.equal(geometry);
        expect(readLaraDrawerGeometry(uniqueSnakeId('geo'))).to.equal(null);

        writeEmbedDrawerGeometry(embedId, geometry);
        expect(readEmbedDrawerGeometry(embedId)).to.deep.equal(geometry);
        expect(readEmbedDrawerGeometry(uniqueSnakeId('emb'))).to.equal(null);
    });

    it('throws on a present but invalid Lara record', async () => {
        const branchId = uniqueSnakeId('geo');
        const storageKey = trackStorageKey(drawerGeometryStorageKey(branchId));
        window.localStorage.setItem(storageKey, '{not-json');
        expect(() => readLaraDrawerGeometry(branchId)).to.throw();
        window.localStorage.setItem(storageKey, JSON.stringify({ launcherLeft: 1 }));
        expect(() => readLaraDrawerGeometry(branchId)).to.throw(/expected/);
    });

    it('hides the resize handle while expanded', async () => {
        const el = await mountDrawer();
        await mouseClick(launcherOf(el));
        await waitOpen(el);
        await waitUntil(
            () => el.shadowRoot.querySelector('.resize-handle') !== null,
            'resize handle before expand',
            { timeout: 5_000 },
        );
        el.dispatchEvent(new CustomEvent('flow-ui-drawer-expand-toggle', {
            bubbles: true,
            composed: true,
            detail: { expanded: true },
        }));
        await elementUpdated(el);
        expect(el.hasAttribute('expanded')).to.equal(true);
        expect(el.getAttribute('data-drawer-gestures')).to.equal('off');
        expect(el.shadowRoot.querySelector('.resize-handle')).to.equal(null);
        const panel = panelOf(el).getBoundingClientRect();
        expect(panel.width).to.be.greaterThan(1000);
        expect(panel.height).to.be.greaterThan(600);
    });

    it('turns gestures off on a mobile-width viewport', async () => {
        const el = await mountDrawer();
        expect(el.getAttribute('data-drawer-gestures')).to.equal('on');
        await setViewport(MOBILE_VIEWPORT);
        await waitUntil(
            () => el.getAttribute('data-drawer-gestures') === 'off',
            'gestures off after mobile viewport',
            { timeout: 5_000 },
        );
        expect(el.shadowRoot.querySelector('.resize-handle')).to.equal(null);
        expect(window.innerWidth).to.equal(MOBILE_VIEWPORT.width);
    });

    it('ignores a broken persist record and uses the default corner', async () => {
        const branchId = uniqueSnakeId('geo');
        window.localStorage.setItem(drawerGeometryStorageKey(branchId), '{not-json');
        const el = await mountDrawer({ branchId });
        expect(el.getAttribute('data-embed-position')).to.equal('bottom-right');
        const rect = launcherOf(el).getBoundingClientRect();
        expect(rect.right).to.be.closeTo(window.innerWidth - 22, 2);
        expect(rect.bottom).to.be.closeTo(window.innerHeight - 22, 2);
    });
});
