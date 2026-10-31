/**
 * Global FileRecord viewer: любое UI-место открывает файл через
 * PlatformElement.openFile -> files.effect -> platform.file_viewer.
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
    registerFactory,
    collectFactories,
} from '@platform/lib/events/index.js';
import type { PlatformFactory } from '@platform/lib/events/factory-registry.js';
import type { CollectableFactory } from '@platform/lib/events/factories/register.js';
import { PlatformElement } from '@platform/lib/platform-element/index.js';
import '@platform/lib/components/platform-modal-stack.js';
import '@platform/lib/components/platform-file-viewer-modal.js';
import '../../../../apps/sync/ui/components/sync-message-bubble.js';
import '../../../../apps/crm/ui/components/entity-card.js';
import '../../../../apps/crm/ui/components/note-card-view.js';

import {
    messagesStoreSlice,
    messagesReactOp,
    messagesTranscribeAudioOp,
    messagesTranscribeVideoOp,
    messagesTranscribeCallOp,
} from '../../../../apps/sync/ui/events/resources/messages.resource.js';
import { chatUiResource } from '../../../../apps/sync/ui/events/resources/chat-ui.resource.js';
import { callAcceptOp } from '../../../../apps/sync/ui/events/resources/calls.resource.js';

import {
    entitiesResource,
    entityCardOp,
    entityUpdateOp,
    entityCreateForm,
    entityEditForm,
    entitySearchOp,
} from '../../../../apps/crm/ui/events/resources/entities.resource.js';
import { entityTypesResource } from '../../../../apps/crm/ui/events/resources/entity-types.resource.js';
import { relationshipsResource } from '../../../../apps/crm/ui/events/resources/relationships.resource.js';
import { relationshipTypesResource } from '../../../../apps/crm/ui/events/resources/relationship-types.resource.js';
import {
    attachmentsListOp,
    attachmentUploadOp,
    attachmentDeleteOp,
} from '../../../../apps/crm/ui/events/resources/attachments.resource.js';
import { grantsListOp } from '../../../../apps/crm/ui/events/resources/grants.resource.js';
import { relatedEntitiesOp } from '../../../../apps/crm/ui/events/resources/graph.resource.js';
import { platformFileCreateOp } from '@platform/lib/events/factories/platform-file-create.js';
import { namespacesResource } from '../../../../apps/crm/ui/events/resources/namespaces.resource.js';
import { graphViewSlice } from '../../../../apps/crm/ui/events/resources/graph-view.resource.js';
import { noteComposeSlice } from '../../../../apps/crm/ui/events/resources/note-compose.resource.js';
import {q, qs, qsa, shadow, type TestEl} from '../helpers/dom.js';

declare global {
    interface Window {
        __platformFileViewerSpecEditors?: Array<{ destroyed: boolean; destroyEditor(): void }>;
    }
}

const DOC_SERVER_URL = 'https://docs.example.test';
const DOCX_MIME = 'application/vnd.openxmlformats-officedocument.wordprocessingml.document';
const PDF_MIME = 'application/pdf';
const MINIMAL_SVG = '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 16 16"><path d="M2 2h12v12H2z"/></svg>';

class PlatformFileViewerOpenFixture extends PlatformElement {
    static override properties = {
        file: { type: Object },
    };

    constructor() {
        super();
        (this as TestEl).file = null;
    }

    override render() {
        return html`<button type="button" @click=${() => (this as TestEl).openFile((this as TestEl).file, { source: 'spec' })}>Open</button>`;
    }
}

if (!customElements.get('platform-file-viewer-open-fixture')) {
    customElements.define('platform-file-viewer-open-fixture', PlatformFileViewerOpenFixture);
}

function base64urlJson(value: any) {
    const encoded = btoa(String.fromCharCode(...new TextEncoder().encode(JSON.stringify(value))));
    return encoded.replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/g, '');
}

function editorConfigFor(fileId: any, title = `${fileId}.docx`) {
    if (title.toLowerCase().endsWith('.html') || title.toLowerCase().endsWith('.htm')) {
        return {
            handler: 'text',
            file_id: fileId,
            title,
            original_name: title,
            content_type: 'text/html',
            file_category: 'text',
            onlyoffice_document_type: null,
            download_url: `/documents/api/v1/office-download?file_id=${encodeURIComponent(fileId)}`,
            capabilities: {
                view: true,
                edit: true,
                preview: true,
                sync_on_close: true,
                download: true,
                server_mutations: false,
            },
            text: {
                stream_url: `/documents/api/v1/viewer-stream?file_id=${encodeURIComponent(fileId)}`,
                save_url: `/documents/api/v1/viewer-save?file_id=${encodeURIComponent(fileId)}`,
                content_type: 'text/html',
                edit_mode: true,
                max_edit_bytes: 512000,
                presentation: 'html',
                default_view_mode: 'preview',
            },
        };
    }
    const claims = {
        type: 'desktop',
        documentType: 'word',
        document: {
            fileType: 'docx',
            key: `file-${fileId}`,
            title,
            url: `/documents/api/v1/files/${encodeURIComponent(fileId)}/download`,
        },
        editorConfig: {
            mode: 'edit',
            callbackUrl: `/documents/api/v1/files/${encodeURIComponent(fileId)}/callback`,
            lang: 'en',
            user: { id: 'u1', name: 'Spec User' },
        },
    };
    return {
        handler: 'onlyoffice',
        file_id: fileId,
        title,
        original_name: title,
        content_type: DOCX_MIME,
        file_category: 'office_doc',
        onlyoffice_document_type: 'word',
        download_url: null,
        capabilities: {
            view: true,
            edit: true,
            preview: true,
            sync_on_close: true,
            download: true,
            server_mutations: true,
        },
        onlyoffice: {
            document_server_url: DOC_SERVER_URL,
            token: `e30.${base64urlJson(claims)}.sig`,
        },
    };
}

function queryDocumentViewerHost(modal: any) {
    return qs(shadow(modal), 'platform-document-viewer-host') || null;
}

function queryOnlyOfficeHost(modal: any) {
    const viewerHost = queryDocumentViewerHost(modal);
    return viewerHost?.shadowRoot?.querySelector('platform-onlyoffice-host') || null;
}

function jsonResponse(body: any, status = 200) {
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

function installOfficeFetchMock() {
    const previousFetch = window.fetch;
    const calls: any[] = [];
    window.fetch = async (rawUrl, init: any = {}) => {
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
                        download: 'Download',
                        view_preview: 'Preview',
                        view_raw: 'Raw',
                        view_mode_group: 'View mode',
                    },
                    document_viewer: {
                        loading: 'Loading file',
                        missing_stream_url: 'Missing stream',
                        load_failed: 'Load failed {status}',
                        html_preview: 'HTML preview',
                        save_hint: 'Save hint',
                    },
                },
                sync: {
                    bubble: {
                        file_fallback: 'File',
                        download_title: 'Download',
                    },
                },
            });
        }
        if (method === 'GET' && url.pathname === '/api/platform/file-types') {
            return jsonResponse({ categories: [], registry: [] });
        }

        const editorMatch = url.pathname.match(/^\/documents\/api\/v1\/files\/([^/]+)\/editor-config$/);
        if (method === 'GET' && editorMatch) {
            const fileId = decodeURIComponent(editorMatch[1]!);
            const titleHint = url.searchParams.get('title');
            const title = typeof titleHint === 'string' && titleHint.length > 0
                ? titleHint
                : (fileId.includes('html') ? `${fileId}.html` : `${fileId}.docx`);
            return jsonResponse(editorConfigFor(fileId, title));
        }

        if (method === 'GET' && url.pathname === '/documents/api/v1/viewer-stream') {
            return new Response('<!DOCTYPE html><html><body><h1>Preview Deck</h1></body></html>', {
                status: 200,
                headers: { 'content-type': 'text/html; charset=utf-8' },
            });
        }

        const syncMatch = url.pathname.match(/^\/documents\/api\/v1\/files\/([^/]+)\/sync$/);
        if (method === 'POST' && syncMatch) {
            const fileId = decodeURIComponent(syncMatch[1]!);
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

function installDocsApiFake() {
    const prevDocsApi = window.DocsAPI;
    const prevOrigin = window.__ooDocsApiOrigin;
    const prevSpecEditors = window.__platformFileViewerSpecEditors;
    const editors: any[] = [];
    window.__platformFileViewerSpecEditors = editors;
    window.__ooDocsApiOrigin = DOC_SERVER_URL;
    window.DocsAPI = {
        DocEditor: (function DocEditor(id: string, config: Record<string, unknown>) {
            const iframe = document.createElement('iframe');
            iframe.name = 'frameEditor';
            iframe.src = `about:blank?frameEditorId=${encodeURIComponent(id)}`;
            const placeholder = document.getElementById(id);
            if (placeholder) {
                placeholder.appendChild(iframe);
            }
            const editor = {
                id,
                config,
                iframe,
                destroyed: false,
                destroyEditor() {
                    editor.destroyed = true;
                    iframe.remove();
                },
            };
            editors.push(editor);
            const events = (config as { events?: Record<string, ((arg?: unknown) => void) | undefined> }).events;
            setTimeout(() => {
                events?.onAppReady?.();
                events?.onDocumentReady?.();
                events?.onDocumentStateChange?.({ data: true });
            }, 0);
            return editor;
        }) as unknown as new (placeholderId: string, init: Record<string, unknown>) => { destroyEditor(): void },
    };

    return {
        editors,
        uninstall() {
            if (prevDocsApi === undefined) {
                delete window.DocsAPI;
            } else {
                window.DocsAPI = prevDocsApi;
            }
            if (prevOrigin === undefined) {
                delete window.__ooDocsApiOrigin;
            } else {
                window.__ooDocsApiOrigin = prevOrigin;
            }
            if (prevSpecEditors === undefined) {
                delete window.__platformFileViewerSpecEditors;
            } else {
                window.__platformFileViewerSpecEditors = prevSpecEditors;
            }
        },
    };
}

function mouse(target: any, type: any, x: any, y: any) {
    target.dispatchEvent(new MouseEvent(type, {
        bubbles: true,
        composed: true,
        cancelable: true,
        button: 0,
        buttons: type === 'mouseup' ? 0 : 1,
        clientX: Math.round(x),
        clientY: Math.round(y),
    }));
}

function registerFactoriesForTest(factories: any) {
    const unique = [...new Set(factories)];
    for (const factory of unique) {
        registerFactory(factory as PlatformFactory);
    }
    return collectFactories(unique as CollectableFactory[]);
}

function setupBusWithFactories(factories: any[] = []) {
    const collected = registerFactoriesForTest(factories);
    return bootstrapTestBus({ slices: collected.slices, effects: [] });
}

function syncFactories() {
    return [
        messagesStoreSlice,
        messagesReactOp,
        messagesTranscribeAudioOp,
        messagesTranscribeVideoOp,
        messagesTranscribeCallOp,
        chatUiResource,
        callAcceptOp,
    ];
}

function crmFactories() {
    return [
        entitiesResource,
        entityCardOp,
        entityUpdateOp,
        entityCreateForm,
        entityEditForm,
        entitySearchOp,
        entityTypesResource,
        relationshipsResource,
        relationshipTypesResource,
        attachmentsListOp,
        attachmentUploadOp,
        attachmentDeleteOp,
        grantsListOp,
        relatedEntitiesOp,
        platformFileCreateOp,
        namespacesResource,
        graphViewSlice,
        noteComposeSlice,
    ];
}

async function mountStack() {
    const stack = await fixture<TestEl>(html`<platform-modal-stack></platform-modal-stack>`);
    await elementUpdated(stack);
    return stack;
}

async function waitForViewerCount(count: any) {
    await waitUntil(
        () => qsa(document!, 'platform-file-viewer-modal[open]').length >= count,
        `${count} file viewer modal(s) mounted`,
    );
    const modals = Array.from(qsa(document!, 'platform-file-viewer-modal[open]'));
    await Promise.all(modals.map((modal) => modal.updateComplete));
    return modals;
}

async function waitForOnlyOfficeIframe(modal: any) {
    await waitUntil(
        () => queryOnlyOfficeHost(modal),
        'onlyoffice host mounted',
    );
    const host = queryOnlyOfficeHost(modal);
    await elementUpdated(host!);
    await waitUntil(
        () => Boolean((host as TestEl).config.token),
        'onlyoffice config assigned',
    );
    await waitUntil(
        () => Boolean((host as TestEl)._configKey),
        'onlyoffice boot key computed',
    );
    expect(window.DocsAPI?.DocEditor, 'fake DocsAPI is installed before editor boot').to.be.a('function');
    expect(window.__ooDocsApiOrigin).to.equal(DOC_SERVER_URL);
    await aTimeout(100);
    if (modal._error) {
        throw new Error(`OnlyOffice host emitted error: ${modal._error}`);
    }
    await waitUntil(
        () => window.__platformFileViewerSpecEditors!.length > 0,
        'fake OnlyOffice DocEditor constructed',
    );
    await waitUntil(
        () => Boolean(q(shadow(host!), 'iframe[name="frameEditor"]')),
        'fake OnlyOffice iframe reparented into the host',
    );
    return qs(shadow(host!), 'iframe[name="frameEditor"]');
}

async function clickOpenButton(file: any) {
    const opener = await fixture<TestEl>(html`<platform-file-viewer-open-fixture .file=${file}></platform-file-viewer-open-fixture>`);
    qs(shadow(opener), 'button').click();
    return opener;
}

function lastFileOpenEvent(events: any) {
    const items = events.filter((event: any) => event.type === FILES_EVENTS.OPEN_REQUESTED);
    return items[items.length - 1] || null;
}

describe('platform-file-viewer-modal global viewer', () => {
    let fetchMock: any;
    let docsApi: any;

    beforeEach(() => {
        resetPlatformState();
        setupBusWithFactories();
        fetchMock = installOfficeFetchMock();
        docsApi = installDocsApiFake();
    });

    afterEach(() => {
        docsApi.uninstall();
        fetchMock.uninstall();
        fixtureCleanup();
        qsa(document!, 'platform-file-viewer-modal, iframe[name="frameEditor"]').forEach((node) => node.remove());
        qsa(document!, '[data-file-viewer-underlay]').forEach((node) => node.remove());
    });

    it('opens through openFile, fetches editor config from FileRecord endpoint, renders invisible shell and syncs on close', async () => {
        await mountStack();
        await clickOpenButton({
            file_id: 'contract-docx',
            original_name: 'Contract.docx',
            content_type: DOCX_MIME,
        });

        const [modal] = await waitForViewerCount(1);
        const iframe = await waitForOnlyOfficeIframe(modal);

        expect(iframe.getAttribute('allow')).to.include('clipboard-read');
        expect(fetchMock.calls.some((call: any) => call.method === 'GET' && call.url === '/documents/api/v1/files/contract-docx/editor-config')).to.equal(true);
        expect(docsApi.editors[0].config.document.title).to.equal('contract-docx.docx');

        const scrimStyle = getComputedStyle(qs(shadow(modal!), '.modal-scrim'));
        const headerStyle = getComputedStyle(qs(shadow(modal!), '.modal-header'));
        const shellRect = qs(shadow(modal!), '.viewer-shell').getBoundingClientRect();
        expect(scrimStyle.backgroundColor).to.equal('rgba(0, 0, 0, 0)');
        expect(headerStyle.position).to.equal('fixed');
        expect(shellRect.width).to.be.greaterThan(window.innerWidth * 0.9);
        expect(shellRect.height).to.be.greaterThan(window.innerHeight * 0.9);

        qs(shadow(modal!), '.header-buttons .header-btn:last-child').click();
        await waitUntil(
            () => fetchMock.calls.some((call: any) => call.method === 'POST' && call.url === '/documents/api/v1/files/contract-docx/sync'),
            'editor sync requested before close',
        );
        const syncCall = fetchMock.calls.find((call: any) => call.method === 'POST' && call.url === '/documents/api/v1/files/contract-docx/sync');
        expect(JSON.parse(syncCall.init.body)).to.include({ close: true, dirty: true });
        await waitUntil(
            () => q(document!, 'platform-file-viewer-modal[open]') === null,
            'viewer removed after synced close',
        );
    });

    it('minimizes to a compact draggable file chip, restores, drags full controls, and supports multiple viewers', async () => {
        await mountStack();
        const underlay = (document.createElement('button') as TestEl);
        (underlay as TestEl).dataset.fileViewerUnderlay = 'true';
        underlay.textContent = 'Underlying action';
        underlay.style.cssText = 'position:fixed;left:24px;top:24px;width:180px;height:44px;z-index:10;';
        let underlayClicks = 0;
        underlay.addEventListener('click', () => {
            underlayClicks += 1;
        });
        document.body.appendChild(underlay);

        await clickOpenButton({ file_id: 'first-docx', original_name: 'First.docx', content_type: DOCX_MIME });
        let [first] = await waitForViewerCount(1);
        const firstIframe = await waitForOnlyOfficeIframe(first);

        const minimizeButton = qs(shadow(first!), '.header-buttons .header-btn:first-child');
        (minimizeButton as TestEl).click();
        await elementUpdated(first!);
        await aTimeout(0);
        expect(first!.minimized).to.equal(true);
        expect(qs(shadow(first!), '.drag-dots')).to.exist;
        expect(qs(shadow(first!), 'platform-icon[file-icon]')).to.exist;
        expect(qs(shadow(first!), '.header-buttons .header-btn:first-child platform-icon').name).to.equal('fullscreen');
        expect(getComputedStyle(qs(shadow(first!), '.modal-scrim')).display).to.equal('none');
        expect(qs(shadow(first!), 'platform-document-viewer-host').suspended).to.equal(true);
        expect(firstIframe.style.pointerEvents).to.equal('none');
        const hit = document.elementFromPoint(48, 40);
        expect(hit === underlay || underlay.contains(hit)).to.equal(true);
        (hit as TestEl).click();
        expect(underlayClicks).to.equal(1);
        const chip = qs(shadow(first!), '.modal');
        const chipRect = chip.getBoundingClientRect();
        expect(chipRect.width).to.be.lessThan(340);
        expect(chipRect.height).to.be.lessThan(70);

        const chipHeader = qs(shadow(first!), '.modal-header');
        mouse(chipHeader, 'mousedown', chipRect.left + 24, chipRect.top + 24);
        document.dispatchEvent(new MouseEvent('mousemove', {
            bubbles: true,
            clientX: chipRect.left - 70,
            clientY: chipRect.top - 60,
            buttons: 1,
        }));
        document.dispatchEvent(new MouseEvent('mouseup', { bubbles: true, clientX: chipRect.left - 70, clientY: chipRect.top - 60 }));
        await elementUpdated(first!);
        const draggedChipRect = chip.getBoundingClientRect();
        expect(draggedChipRect.left).to.be.lessThan(chipRect.left - 30);
        expect(draggedChipRect.top).to.be.lessThan(chipRect.top - 20);

        mouse(chipHeader, 'mousedown', draggedChipRect.left + 24, draggedChipRect.top + 24);
        document.dispatchEvent(new MouseEvent('mousemove', {
            bubbles: true,
            clientX: -2000,
            clientY: -2000,
            buttons: 1,
        }));
        document.dispatchEvent(new MouseEvent('mouseup', { bubbles: true, clientX: -2000, clientY: -2000 }));
        await elementUpdated(first!);
        const clampedChipRect = chip.getBoundingClientRect();
        expect(clampedChipRect.left).to.be.at.least(0);
        expect(clampedChipRect.top).to.be.at.least(0);
        expect(clampedChipRect.right).to.be.at.most(window.innerWidth);
        expect(clampedChipRect.bottom).to.be.at.most(window.innerHeight);

        qs(shadow(first!), '.header-buttons .header-btn:first-child').click();
        await elementUpdated(first!);
        expect(first!.minimized).to.equal(false);

        const fullHeader = qs(shadow(first!), '.modal-header');
        const fullHeaderRect = fullHeader.getBoundingClientRect();
        mouse(fullHeader, 'mousedown', fullHeaderRect.left + 28, fullHeaderRect.top + 20);
        document.dispatchEvent(new MouseEvent('mousemove', {
            bubbles: true,
            clientX: fullHeaderRect.left - 90,
            clientY: fullHeaderRect.top + 80,
            buttons: 1,
        }));
        document.dispatchEvent(new MouseEvent('mouseup', { bubbles: true, clientX: fullHeaderRect.left - 90, clientY: fullHeaderRect.top + 80 }));
        await aTimeout(0);
        const movedHeaderRect = fullHeader.getBoundingClientRect();
        expect(movedHeaderRect.top).to.be.greaterThan(fullHeaderRect.top + 30);
        expect(movedHeaderRect.left).to.be.lessThan(fullHeaderRect.left - 30);

        await clickOpenButton({ file_id: 'second-docx', original_name: 'Second.docx', content_type: DOCX_MIME });
        const modals = await waitForViewerCount(2);
        await Promise.all(modals.map((modal) => waitForOnlyOfficeIframe(modal)));
        expect(modals.map((modal) => modal.fileId).sort()).to.deep.equal(['first-docx', 'second-docx']);
        expect(qsa(document!, 'platform-file-viewer-modal[open]').length).to.equal(2);
    });

    it('HTML text presentation defaults to preview iframe and switches to raw code via header actions', async () => {
        await mountStack();
        await clickOpenButton({
            file_id: 'deck-html',
            original_name: 'BACKEND-STATUS-REQUEST.html',
            content_type: 'text/html',
        });

        const [modal] = await waitForViewerCount(1);
        await waitUntil(
            () => Boolean(modal!.config.text?.presentation === 'html'),
            'html open config assigned',
        );

        const typeActions = qs(shadow(modal!), '.header-type-actions');
        expect(typeActions).to.exist;
        const modeButtons = [...qsa(typeActions!, '.header-btn-label')];
        expect(modeButtons).to.have.length(2);
        expect(modeButtons[0]!.getAttribute('aria-pressed')).to.equal('true');
        expect(modeButtons[1]!.getAttribute('aria-pressed')).to.equal('false');

        const viewerHost = queryDocumentViewerHost(modal);
        await waitUntil(
            () => Boolean(viewerHost?.shadowRoot?.querySelector('platform-document-text-viewer')),
            'text viewer mounted',
        );
        const textViewer = qs(shadow(viewerHost), 'platform-document-text-viewer');
        await waitUntil(
            () => Boolean(q(shadow(textViewer), 'iframe.html-preview-frame')),
            'html preview iframe rendered',
        );
        expect(q(shadow(textViewer), 'platform-code-editor')).to.equal(null);

        modeButtons[1]!.click();
        await elementUpdated(modal!);
        await waitUntil(
            () => Boolean(q(shadow(textViewer), 'platform-code-editor')),
            'raw code editor rendered after Raw click',
        );
        expect(q(shadow(textViewer), 'iframe.html-preview-frame')).to.equal(null);
        expect(modeButtons[0]!.getAttribute('aria-pressed')).to.equal('false');
        expect(modeButtons[1]!.getAttribute('aria-pressed')).to.equal('true');
    });
});

describe('global file entrypoints dispatch the shared viewer event', () => {
    let fetchMock: any;
    let docsApi: any;
    let events: any;

    beforeEach(() => {
        resetPlatformState();
        fetchMock = installOfficeFetchMock();
        docsApi = installDocsApiFake();
        events = [];
    });

    afterEach(() => {
        docsApi.uninstall();
        fetchMock.uninstall();
        fixtureCleanup();
        qsa(document!, 'platform-file-viewer-modal, iframe[name="frameEditor"]').forEach((node) => node.remove());
    });

    it('sync message file attachment opens through the same global viewer event', async () => {
        setupBusWithFactories(syncFactories());
        getPlatformBus().subscribeAny((event: any) => events.push(event));
        await mountStack();

        const bubble = await fixture<TestEl>(html`
            <sync-message-bubble
                .message=${{
                    message_id: 'm1',
                    channel_id: 'c1',
                    sender: { user_id: 'u2', display_name: 'User' },
                    contents: [{
                        type: 'file/document',
                        data: {
                            file_id: 'sync-docx',
                            original_name: 'Sync.docx',
                            content_type: DOCX_MIME,
                            file_size: 128,
                        },
                    }, {
                        type: 'file/document',
                        data: {
                            file_id: 'sync-pdf',
                            original_name: 'Coverage.pdf',
                            content_type: PDF_MIME,
                            file_size: 256,
                        },
                    }],
                }}
                my-user-id="u1"
            ></sync-message-bubble>
        `);
        await elementUpdated(bubble);
        const syncRows = [...qsa(shadow(bubble), '.file')];
        const syncIcons = [...qsa(shadow(bubble), '.file platform-icon[file-icon]')].map((icon) => icon.name);
        expect(syncRows).to.have.length(2);
        expect(syncIcons).to.deep.equal(['word', 'pdf']);
        const firstRect = syncRows[0]!.getBoundingClientRect();
        const secondRect = syncRows[1]!.getBoundingClientRect();
        expect(secondRect.top - firstRect.bottom).to.be.greaterThan(6);
        syncRows[0]!.click();
        await waitUntil(() => lastFileOpenEvent(events)?.payload?.file?.file_id === 'sync-docx', 'sync attachment opened file');
        expect(lastFileOpenEvent(events).payload.file.original_name).to.equal('Sync.docx');
    });

    it('CRM entity and note attachment rows/actions open through the same global viewer event', async () => {
        setupBusWithFactories(crmFactories());
        getPlatformBus().subscribeAny((event: any) => events.push(event));
        await mountStack();

        const entityCard = (document.createElement('crm-entity-card') as TestEl);
        entityCard._openEntityAttachmentItem({
            id: 'crm-entity-docx',
            filename: 'Entity.docx',
            contentType: DOCX_MIME,
            sizeBytes: 256,
            downloadUrl: '/api/v1/files/download/crm-entity-docx',
        });
        await waitUntil(() => lastFileOpenEvent(events)?.payload?.file?.file_id === 'crm-entity-docx', 'CRM entity attachment opened file');

        events.length = 0;
        entityCard._attachmentsData = [{
            document_id: 'crm-entity-row-docx',
            filename: 'Entity Row.docx',
            metadata: { content_type: DOCX_MIME, file_size: 300 },
            download_url: '/api/v1/files/download/crm-entity-row-docx',
            status: 'ready',
        }];
        const entityPopover = await fixture<TestEl>(html`${entityCard._renderEntityAttachmentsPopover('view')}`);
        expect(qs(entityPopover!, '.attachments-popover-row platform-icon[file-icon]').name).to.equal('word');
        qs(entityPopover!, '.attachments-popover-row').click();
        await waitUntil(() => lastFileOpenEvent(events)?.payload?.file?.file_id === 'crm-entity-row-docx', 'CRM entity attachment row opened file');

        events.length = 0;
        const noteCard = (document.createElement('crm-note-card-view') as TestEl);
        noteCard._openAttachmentItem({
            id: 'crm-note-docx',
            filename: 'Note.docx',
            contentType: DOCX_MIME,
            sizeBytes: 512,
            downloadUrl: '/api/v1/files/download/crm-note-docx',
        });
        await waitUntil(() => lastFileOpenEvent(events)?.payload?.file?.file_id === 'crm-note-docx', 'CRM note attachment opened file');
        expect(lastFileOpenEvent(events).payload.file.original_name).to.equal('Note.docx');

        events.length = 0;
        const noteRow = await fixture<TestEl>(html`${noteCard._renderAttachmentRow({
            id: 'crm-note-row-docx',
            filename: 'Note Row.docx',
            contentType: DOCX_MIME,
            sizeBytes: 512,
            status: 'ready',
            downloadUrl: '/api/v1/files/download/crm-note-row-docx',
            canDelete: true,
        }, 'view')}`);
        expect(qs(noteRow!, 'platform-icon[file-icon]').name).to.equal('word');
        (noteRow as TestEl).click();
        await waitUntil(() => lastFileOpenEvent(events)?.payload?.file?.file_id === 'crm-note-row-docx', 'CRM note attachment row opened file');
        expect(lastFileOpenEvent(events).payload.file.original_name).to.equal('Note Row.docx');
    });
});
