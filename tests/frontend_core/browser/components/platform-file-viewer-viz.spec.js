/**
 * Global FileRecord viewer for handler=viz: openFile → editor-config stub → platform-viz-host.
 * HTTP stub is the browser↔backend boundary only (no Python monkeypatch).
 */

import {
    fixture,
    fixtureCleanup,
    html,
    expect,
    elementUpdated,
    waitUntil,
    aTimeout,
} from '../helpers/render.js';
import { resetPlatformState, bootstrapTestBus } from '../helpers/reset.js';
import {
    getPlatformBus,
    FILES_EVENTS,
} from '@platform/lib/events/index.js';
import { PlatformElement } from '@platform/lib/platform-element/index.js';
import '@platform/lib/components/platform-modal-stack.js';
import '@platform/lib/components/platform-file-viewer-modal.js';
import '../../../../core/frontend/static/lib/chat/blocks/flows-chat-ui-viz.js';

const VIZ_MIME = 'application/vnd.platform.viz+json';
const MINIMAL_SVG = '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 16 16"><path d="M2 2h12v12H2z"/></svg>';

const VIZ_DOCUMENT = {
    schema_version: 1,
    kind: 'flowchart',
    engine: 'mermaid',
    title: 'Viewer Flow',
    spec: { source: 'flowchart TD\n  A-->B' },
};

class PlatformFileViewerOpenFixture extends PlatformElement {
    static properties = {
        file: { type: Object },
    };

    constructor() {
        super();
        this.file = null;
    }

    render() {
        return html`<button type="button" @click=${() => this.openFile(this.file, { source: 'spec' })}>Open</button>`;
    }
}

if (!customElements.get('platform-file-viewer-open-fixture')) {
    customElements.define('platform-file-viewer-open-fixture', PlatformFileViewerOpenFixture);
}

function vizEditorConfig(fileId, title = `${fileId}.viz`) {
    return {
        handler: 'viz',
        binding_id: `file:${fileId}`,
        file_id: fileId,
        title,
        original_name: title,
        content_type: VIZ_MIME,
        file_category: 'viz',
        onlyoffice_document_type: null,
        download_url: `/documents/api/v1/files/${encodeURIComponent(fileId)}/download`,
        capabilities: {
            view: true,
            edit: false,
            preview: true,
            sync_on_close: false,
            download: true,
            server_mutations: false,
        },
        viz: {
            stream_url: `/documents/api/v1/viewer-stream?file_id=${encodeURIComponent(fileId)}`,
            content_type: VIZ_MIME,
            kind: VIZ_DOCUMENT.kind,
            engine: VIZ_DOCUMENT.engine,
            title: VIZ_DOCUMENT.title,
            document: VIZ_DOCUMENT,
        },
    };
}

function queryDocumentViewerHost(modal) {
    return modal.shadowRoot?.querySelector('platform-document-viewer-host') || null;
}

function queryVizHost(modal) {
    const viewerHost = queryDocumentViewerHost(modal);
    return viewerHost?.shadowRoot?.querySelector('platform-viz-host') || null;
}

function jsonResponse(body, status = 200) {
    return new Response(JSON.stringify(body), {
        status,
        headers: { 'content-type': 'application/json; charset=utf-8' },
    });
}

function svgResponse() {
    return new Response(MINIMAL_SVG, {
        status: 200,
        headers: { 'content-type': 'image/svg+xml; charset=utf-8' },
    });
}

function installVizFetchMock() {
    const previousFetch = window.fetch;
    const calls = [];
    window.fetch = async (rawUrl, init = {}) => {
        const method = (init.method || 'GET').toUpperCase();
        const url = new URL(String(rawUrl), window.location.href);
        calls.push({ method, url: `${url.pathname}${url.search}`, init });

        if (method === 'GET' && url.pathname.startsWith('/static/core/assets/icons/')) {
            return svgResponse();
        }
        if (method === 'GET' && url.pathname.startsWith('/api/i18n/')) {
            return jsonResponse({
                platform: {
                    modal: { close: 'Close' },
                    file_viewer: {
                        loading: 'Loading',
                        syncing: 'Saving',
                        minimize: 'Minimize',
                        restore: 'Restore',
                        open_failed: 'Open failed: {message}',
                        close_failed: 'Close failed',
                    },
                },
            });
        }
        if (method === 'GET' && url.pathname === '/api/platform/file-types') {
            return jsonResponse({ categories: [], registry: [] });
        }

        const editorMatch = url.pathname.match(/^\/documents\/api\/v1\/files\/([^/]+)\/editor-config$/);
        if (method === 'GET' && editorMatch) {
            const fileId = decodeURIComponent(editorMatch[1]);
            return jsonResponse(vizEditorConfig(fileId, `${fileId}.viz`));
        }

        const syncMatch = url.pathname.match(/^\/documents\/api\/v1\/files\/([^/]+)\/sync$/);
        if (method === 'POST' && syncMatch) {
            const fileId = decodeURIComponent(syncMatch[1]);
            return jsonResponse({ file_id: fileId, checksum: `sha-${fileId}`, file_size: 42 });
        }

        return previousFetch(rawUrl, init);
    };
    return {
        calls,
        uninstall() {
            window.fetch = previousFetch;
        },
    };
}

async function mountStack() {
    const stack = await fixture(html`<platform-modal-stack></platform-modal-stack>`);
    await elementUpdated(stack);
    return stack;
}

async function waitForViewerCount(count) {
    await waitUntil(
        () => document.querySelectorAll('platform-file-viewer-modal[open]').length >= count,
        `${count} file viewer modal(s) mounted`,
    );
    const modals = Array.from(document.querySelectorAll('platform-file-viewer-modal[open]'));
    await Promise.all(modals.map((modal) => modal.updateComplete));
    return modals;
}

async function clickOpenButton(file) {
    const opener = await fixture(html`<platform-file-viewer-open-fixture .file=${file}></platform-file-viewer-open-fixture>`);
    opener.shadowRoot.querySelector('button').click();
    return opener;
}

describe('platform-file-viewer-modal viz handler', () => {
    let fetchMock;

    beforeEach(() => {
        resetPlatformState();
        bootstrapTestBus();
        fetchMock = installVizFetchMock();
    });

    afterEach(() => {
        fetchMock.uninstall();
        fixtureCleanup();
        document.querySelectorAll('platform-file-viewer-modal').forEach((node) => node.remove());
    });

    it('opens viz file without OnlyOffice iframe and closes without sync POST', async () => {
        await mountStack();
        await clickOpenButton({
            file_id: 'viz-diagram-1',
            original_name: 'diagram.viz',
            content_type: VIZ_MIME,
        });

        const [modal] = await waitForViewerCount(1);
        await waitUntil(
            () => queryVizHost(modal),
            'platform-viz-host mounted',
        );
        const vizHost = queryVizHost(modal);
        await elementUpdated(vizHost);

        expect(fetchMock.calls.some(
            (call) => call.method === 'GET' && call.url === '/documents/api/v1/files/viz-diagram-1/editor-config',
        )).to.equal(true);
        expect(queryDocumentViewerHost(modal)?.shadowRoot?.querySelector('platform-onlyoffice-host')).to.not.exist;
        expect(modal.shadowRoot?.querySelector('iframe[name="frameEditor"]')).to.not.exist;
        expect(vizHost.shadowRoot?.querySelector('platform-mermaid-host')).to.exist;

        const closeBtn = modal.shadowRoot.querySelector('.header-buttons .header-btn:last-child');
        closeBtn.click();
        await waitUntil(
            () => document.querySelector('platform-file-viewer-modal[open]') === null,
            'viewer removed after close',
        );
        expect(fetchMock.calls.some(
            (call) => call.method === 'POST' && call.url.includes('/sync'),
        )).to.equal(false);
    });

    it('flows-chat-ui-viz Open dispatches FILES_EVENTS.OPEN_REQUESTED', async () => {
        const bus = getPlatformBus();
        const openEvents = [];
        const unsub = bus.subscribeType(FILES_EVENTS.OPEN_REQUESTED, (event) => {
            openEvents.push(event);
        });
        try {
            const block = await fixture(html`
                <flows-chat-ui-viz
                    file_id="viz-chat-1"
                    kind="flowchart"
                    engine="mermaid"
                    title="Chat Flow"
                    .spec=${{ source: 'flowchart TD\n  A-->B' }}
                ></flows-chat-ui-viz>
            `);
            await elementUpdated(block);
            const openButton = block.shadowRoot?.querySelector('button');
            expect(openButton).to.exist;
            openButton.click();
            await aTimeout(0);
            expect(openEvents.length).to.be.greaterThan(0);
            const last = openEvents[openEvents.length - 1];
            expect(last.payload.file.file_id).to.equal('viz-chat-1');
            expect(last.payload.source).to.equal('flows_chat_viz');
        } finally {
            unsub();
        }
    });
});
