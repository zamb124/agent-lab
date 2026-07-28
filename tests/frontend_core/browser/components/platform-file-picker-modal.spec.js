/**
 * platform.file_picker — выбор из Documents или upload через uploadSpec.
 */

import { fixture, html, expect, elementUpdated, waitUntil } from '../helpers/render.js';
import { resetPlatformState, bootstrapTestBus } from '../helpers/reset.js';
import {
    createAsyncOp,
    getPlatformBus,
    CoreEvents,
} from '@platform/lib/events/index.js';
import '@platform/lib/components/platform-modal-stack.js';
import '@platform/lib/components/platform-file-picker-modal.js';
import { buildWikiPageFileCreateSpecJson } from '@platform/lib/utils/file-create-spec.js';

const catalogsOp = createAsyncOp({
    name: 'test/picker_catalogs',
    silent: true,
    restMirror: { method: 'GET', path: '/documents/api/v1/catalogs', service: 'office' },
    request: async () => ({
        items: [
            {
                catalog_id: 'cat-1',
                title: 'Wiki',
                file_count: 2,
            },
        ],
    }),
});

const documentsOp = createAsyncOp({
    name: 'test/picker_documents',
    silent: true,
    restMirror: { method: 'GET', path: '/documents/api/v1/documents', service: 'office' },
    request: async ({ payload }) => {
        if (!payload || typeof payload.catalog_id !== 'string') {
            throw new Error('test/picker_documents: catalog_id required');
        }
        return {
            items: [
                {
                    file_id: 'doc-image-1',
                    title: 'cover.png',
                    file_category: 'image',
                    file_size: 2048,
                    updated_at: '2026-07-28T12:00:00Z',
                },
                {
                    file_id: 'doc-pdf-1',
                    title: 'report.pdf',
                    file_category: 'file',
                    file_size: 4096,
                    updated_at: '2026-07-28T12:00:00Z',
                },
            ],
        };
    },
});

const searchOp = createAsyncOp({
    name: 'test/picker_search',
    silent: true,
    restMirror: { method: 'GET', path: '/documents/api/v1/documents/search', service: 'office' },
    request: async () => ({ items: [] }),
});

const uploadOp = createAsyncOp({
    name: 'test/picker_upload',
    silent: true,
    restMirror: { method: 'POST', path: '/frontend/api/v1/files/' },
    request: async ({ payload }) => {
        if (!payload || !(payload.file instanceof File)) {
            throw new Error('test/picker_upload: file required');
        }
        if (typeof payload.spec !== 'string' || payload.spec.length === 0) {
            throw new Error('test/picker_upload: spec required');
        }
        return {
            file_id: 'uploaded-1',
            original_name: payload.file.name,
            content_type: payload.file.type || 'application/octet-stream',
            file_size: payload.file.size,
        };
    },
});

function jsonResponse(body, status = 200) {
    return new Response(JSON.stringify(body), {
        status,
        headers: { 'content-type': 'application/json; charset=utf-8' },
    });
}

function installFetchMock() {
    const previousFetch = window.fetch;
    window.fetch = async (rawUrl, init = {}) => {
        const method = (init.method || 'GET').toUpperCase();
        const url = new URL(String(rawUrl), window.location.href);

        if (method === 'GET' && url.pathname.startsWith('/api/i18n/')) {
            return jsonResponse({
                platform: {
                    modal: { close: 'Close' },
                    file_picker: {
                        title: 'Choose a file',
                        catalogs: 'Folders',
                        no_catalogs: 'No folders yet',
                        search_label: 'Search',
                        search_placeholder: 'Search files…',
                        upload: 'Upload',
                        drop_title: 'Drop a file here or click to upload',
                        drop_hint: 'The file will appear in Documents',
                        uploading: 'Uploading…',
                        loading: 'Loading files…',
                        empty: 'No files in this folder',
                        cancel: 'Cancel',
                        error_not_image: 'Only images can be used here',
                        error_type_mismatch: 'This file type is not allowed',
                    },
                },
            });
        }
        if (method === 'GET' && url.pathname.startsWith('/static/core/assets/icons/')) {
            return new Response('<svg xmlns="http://www.w3.org/2000/svg"></svg>', {
                status: 200,
                headers: { 'content-type': 'image/svg+xml' },
            });
        }
        return previousFetch(rawUrl, init);
    };
    return {
        uninstall() {
            window.fetch = previousFetch;
        },
    };
}

function openPicker(props) {
    getPlatformBus().dispatch(CoreEvents.UI_MODAL_OPEN, {
        kind: 'platform.file_picker',
        props: {
            uploadOpName: 'test/picker_upload',
            uploadSpec: buildWikiPageFileCreateSpecJson({
                wikiPageId: 'page-1',
                namespaceId: 'knowledge',
            }),
            catalogsOpName: 'test/picker_catalogs',
            documentsOpName: 'test/picker_documents',
            searchOpName: 'test/picker_search',
            ...props,
        },
    });
}

describe('platform-file-picker-modal', () => {
    let fetchMock;

    beforeEach(() => {
        resetPlatformState();
        bootstrapTestBus({
            factories: [catalogsOp, documentsOp, searchOp, uploadOp],
        });
        fetchMock = installFetchMock();
    });

    afterEach(() => {
        fetchMock.uninstall();
        document.querySelectorAll('platform-file-picker-modal').forEach((node) => node.remove());
    });

    it('buildWikiPageFileCreateSpecJson задаёт wiki_page source', () => {
        const spec = JSON.parse(buildWikiPageFileCreateSpecJson({
            wikiPageId: 'page-1',
            namespaceId: 'knowledge',
            metadata: { purpose: 'wiki_cover' },
        }));
        expect(spec.source_kind).to.equal('wiki_page');
        expect(spec.source_ref.wiki_page_id).to.equal('page-1');
        expect(spec.source_ref.namespace_id).to.equal('knowledge');
        expect(spec.metadata.purpose).to.equal('wiki_cover');
    });

    it('выбор карточки вызывает onSelect и закрывает модалку', async () => {
        const stack = await fixture(html`<platform-modal-stack></platform-modal-stack>`);
        let selected = null;
        openPicker({
            acceptMimePrefix: 'image/',
            onSelect: (file) => {
                selected = file;
            },
        });
        await elementUpdated(stack);

        await waitUntil(
            () => document.querySelector('platform-file-picker-modal') !== null,
            'file picker mounted',
        );
        const modal = document.querySelector('platform-file-picker-modal');
        expect(modal).to.exist;

        await waitUntil(
            () => modal.shadowRoot.querySelectorAll('platform-file-card').length > 0,
            'document cards rendered',
        );
        await elementUpdated(modal);

        const cards = modal.shadowRoot.querySelectorAll('platform-file-card');
        expect(cards.length).to.equal(1);
        expect(cards[0].fileName).to.equal('cover.png');

        cards[0].shadowRoot.querySelector('.card').click();
        await waitUntil(() => selected !== null, 'onSelect called');
        expect(selected.file_id).to.equal('doc-image-1');
        expect(selected.original_name).to.equal('cover.png');

        await waitUntil(
            () => document.querySelector('platform-file-picker-modal[open]') === null,
            'picker closed after select',
        );
    });

    it('upload нового файла отдаёт результат в onSelect', async () => {
        const stack = await fixture(html`<platform-modal-stack></platform-modal-stack>`);
        let selected = null;
        openPicker({
            acceptMimePrefix: '',
            onSelect: (file) => {
                selected = file;
            },
        });
        await elementUpdated(stack);

        await waitUntil(
            () => document.querySelector('platform-file-picker-modal') !== null,
            'file picker mounted',
        );
        const modal = document.querySelector('platform-file-picker-modal');
        expect(modal).to.exist;
        await elementUpdated(modal);

        const input = modal.shadowRoot.querySelector('input[type="file"]');
        expect(input).to.exist;
        const file = new File(['hello'], 'notes.txt', { type: 'text/plain' });
        const transfer = new DataTransfer();
        transfer.items.add(file);
        input.files = transfer.files;
        input.dispatchEvent(new Event('change', { bubbles: true }));

        await waitUntil(() => selected !== null, 'upload onSelect called');
        expect(selected.file_id).to.equal('uploaded-1');
        expect(selected.original_name).to.equal('notes.txt');
        expect(selected.content_type).to.equal('text/plain');
    });
});
