/**
 * platform-markdown-editor compose / wysiwyg — mail surface, attachments, primary/discard.
 */

import {
    fixture,
    fixtureCleanup,
    html,
    expect,
    elementUpdated,
    waitUntil,
    oneEvent,
} from '../helpers/render.js';
import { resetPlatformState, bootstrapTestBus } from '../helpers/reset.js';
import { setDefaultI18nNamespace } from '@platform/lib/utils/i18n-namespace.js';
import { getPlatformBus, CoreEvents } from '@platform/lib/events/index.js';
import {
    MARKDOWN_EDITOR_MAX_ATTACHMENT_BYTES,
} from '@platform/lib/utils/markdown-html.js';
import { seedPlatformMarkdownEditorI18n, platformEn } from '../helpers/seed-platform-i18n.js';
import '@platform/lib/components/platform-markdown-editor.js';

async function prepare() {
    resetPlatformState();
    bootstrapTestBus();
    setDefaultI18nNamespace('platform');
    await seedPlatformMarkdownEditorI18n();
}

function captureBusEvents() {
    /** @type {Array<{type: string, payload: Record<string, unknown>}>} */
    const events = [];
    getPlatformBus().subscribeAny((event) => {
        events.push({ type: event.type, payload: event.payload });
    });
    return events;
}

async function mountCompose(props = {}) {
    const editor = await fixture(html`
        <platform-markdown-editor
            variant="compose"
            view-mode="wysiwyg"
            .value=${props.value ?? ''}
            .htmlValue=${props.htmlValue ?? ''}
            .placeholder=${props.placeholder ?? ''}
            .primaryLabel=${props.primaryLabel ?? ''}
            .readonly=${props.readonly === true}
            .showPrimary=${props.showPrimary !== false}
            .showAttach=${props.showAttach === true}
            .showDiscard=${props.showDiscard === true}
            .showFormatToggle=${props.showFormatToggle === true}
            .primaryDisabled=${props.primaryDisabled === true}
            .attachments=${props.attachments ?? []}
        ></platform-markdown-editor>
    `);
    await elementUpdated(editor);
    await waitUntil(
        () => editor.shadowRoot.querySelector('.editor-body') !== null,
        'compose body ready',
    );
    return editor;
}

function body(editor) {
    const el = editor.shadowRoot.querySelector('.editor-body');
    if (!(el instanceof HTMLElement)) {
        throw new Error('compose editor-body missing');
    }
    return el;
}

describe('platform-markdown-editor compose / wysiwyg', () => {
    beforeEach(async function prepareHook() {
        this.timeout(20_000);
        await prepare();
    });

    afterEach(() => {
        fixtureCleanup();
    });

    it('renders compose-shell contenteditable, not CodeMirror', async () => {
        const editor = await mountCompose();
        expect(editor.shadowRoot.querySelector('.compose-shell')).to.exist;
        expect(body(editor).getAttribute('contenteditable')).to.equal('true');
        expect(editor.shadowRoot.querySelector('#codemirror-container')).to.equal(null);
        expect(editor._editorView).to.equal(null);
    });

    it('view-mode=wysiwyg alone is compose surface', async () => {
        const editor = await fixture(html`
            <platform-markdown-editor view-mode="wysiwyg" .value=${''}></platform-markdown-editor>
        `);
        await elementUpdated(editor);
        expect(editor.shadowRoot.querySelector('.compose-shell')).to.exist;
    });

    it('typing emits unified change with markdown/html/text', async () => {
        const editor = await mountCompose();
        const changePromise = oneEvent(editor, 'change');
        const el = body(editor);
        el.innerHTML = '<p>Hello <strong>mail</strong></p>';
        el.dispatchEvent(new Event('input', { bubbles: true }));
        const event = await changePromise;
        expect(event.detail).to.have.all.keys(['value', 'htmlValue', 'textValue']);
        expect(event.detail.textValue).to.include('Hello');
        expect(event.detail.textValue).to.include('mail');
        expect(event.detail.value).to.include('Hello');
        expect(event.detail.htmlValue).to.include('<strong>mail</strong>');
        expect(editor.value).to.equal(event.detail.value);
        expect(editor.htmlValue).to.equal(event.detail.htmlValue);
    });

    it('syncs from htmlValue / markdown value when not focused', async () => {
        const editor = await mountCompose({ htmlValue: '<p>from-html</p>' });
        expect(body(editor).textContent).to.include('from-html');

        const editor2 = await mountCompose({ value: '**md**' });
        expect(body(editor2).innerHTML.toLowerCase()).to.include('strong');
    });

    it('insertTextAtCursor in compose emits change', async () => {
        const editor = await mountCompose();
        const changePromise = oneEvent(editor, 'change');
        editor.insertTextAtCursor('compose-insert');
        const event = await changePromise;
        expect(event.detail.textValue).to.include('compose-insert');
    });

    it('primary emits detail + attachments; discard emits null', async () => {
        const editor = await mountCompose({
            showPrimary: true,
            showDiscard: true,
            attachments: [{
                filename: 'a.txt',
                content_type: 'text/plain',
                file_id: 'file_compose_test_1',
                url: '/frontend/api/v1/files/download/file_compose_test_1',
                size: 1,
            }],
        });
        body(editor).innerHTML = '<p>body</p>';
        body(editor).dispatchEvent(new Event('input', { bubbles: true }));

        const primaryPromise = oneEvent(editor, 'primary');
        const primaryBtn = editor.shadowRoot.querySelector('.action-bar > platform-button');
        expect(primaryBtn).to.exist;
        editor._onPrimary();
        const primary = await primaryPromise;
        expect(primary.detail.value).to.be.a('string');
        expect(primary.detail.htmlValue).to.be.a('string');
        expect(primary.detail.textValue).to.be.a('string');
        expect(primary.detail.attachments).to.have.length(1);
        expect(primary.detail.attachments[0].filename).to.equal('a.txt');

        const discardPromise = oneEvent(editor, 'discard');
        editor._onDiscard();
        const discard = await discardPromise;
        expect(discard.detail).to.equal(null);
    });

    it('readonly compose blocks format/primary/discard/toggle', async () => {
        const editor = await mountCompose({
            readonly: true,
            showPrimary: true,
            showDiscard: true,
            showFormatToggle: true,
        });
        expect(body(editor).getAttribute('contenteditable')).to.equal('false');
        expect(() => editor._wysiwygFormat('bold')).to.throw(/readonly/);
        expect(() => editor._onPrimary()).to.throw(/readonly/);
        expect(() => editor._onDiscard()).to.throw(/readonly/);
        expect(() => editor._toggleFormat()).to.throw(/readonly/);
        expect(() => editor._insertLink()).to.throw(/readonly/);
    });

    it('format toggle opens toolbar; bold command updates html', async () => {
        const editor = await mountCompose({ showFormatToggle: true });
        expect(editor.shadowRoot.querySelector('.compose-fmt')).to.equal(null);
        editor._toggleFormat();
        await elementUpdated(editor);
        expect(editor.shadowRoot.querySelector('.compose-fmt')).to.exist;

        const el = body(editor);
        el.focus();
        document.execCommand('selectAll');
        editor.insertTextAtCursor('fmt');
        await elementUpdated(editor);
        // Select all text then bold via private format path
        const selection = window.getSelection();
        selection.removeAllRanges();
        const range = document.createRange();
        range.selectNodeContents(el);
        selection.addRange(range);
        editor._wysiwygFormat('bold');
        expect(el.innerHTML.toLowerCase()).to.match(/<(strong|b)>/);
    });

    it('attach adds file, remove emits attachments-change, oversized toasts', async () => {
        const editor = await mountCompose({ showAttach: true });
        const input = editor.shadowRoot.querySelector('.file-input');
        expect(input).to.exist;

        const originalFetch = window.fetch;
        window.fetch = async (inputUrl, init = {}) => {
            const url = typeof inputUrl === 'string' ? inputUrl : String(inputUrl);
            const method = (init.method || 'GET').toUpperCase();
            if (method === 'POST' && url.endsWith('/frontend/api/v1/files/uploads')) {
                return new Response(JSON.stringify({
                    upload_id: 'up_md_1',
                    file_id: 'file_md_note',
                    chunk_size_bytes: 5 * 1024 * 1024,
                }), { status: 200, headers: { 'Content-Type': 'application/json' } });
            }
            if (method === 'PUT' && url.includes('/frontend/api/v1/files/uploads/up_md_1/parts/')) {
                return new Response(JSON.stringify({ part_number: 1, etag: 'etag-1' }), {
                    status: 200,
                    headers: { 'Content-Type': 'application/json' },
                });
            }
            if (method === 'POST' && url.endsWith('/frontend/api/v1/files/uploads/up_md_1/complete')) {
                return new Response(JSON.stringify({
                    file_id: 'file_md_note',
                    original_name: 'note.txt',
                    content_type: 'text/plain',
                    file_size: 5,
                    url: '/frontend/api/v1/files/download/file_md_note',
                    checksum: 'sha256:test',
                    is_public: false,
                    metadata: {},
                    created_at: '2026-01-01T00:00:00Z',
                }), { status: 200, headers: { 'Content-Type': 'application/json' } });
            }
            throw new Error(`unexpected fetch ${method} ${url}`);
        };

        try {
            const okFile = new File(['hello'], 'note.txt', { type: 'text/plain' });
            const dt = new DataTransfer();
            dt.items.add(okFile);
            Object.defineProperty(input, 'files', { configurable: true, value: dt.files });

            const attachPromise = oneEvent(editor, 'attachments-change');
            input.dispatchEvent(new Event('change', { bubbles: true }));
            const attached = await attachPromise;
            expect(attached.detail.attachments).to.have.length(1);
            expect(attached.detail.attachments[0].filename).to.equal('note.txt');
            expect(attached.detail.attachments[0].file_id).to.equal('file_md_note');
            expect(attached.detail.attachments[0].url).to.equal(
                '/frontend/api/v1/files/download/file_md_note',
            );
            expect(attached.detail.attachments[0].content_type).to.equal('text/plain');
            expect(Object.prototype.hasOwnProperty.call(attached.detail.attachments[0], 'content_base64'))
                .to.equal(false);
            await elementUpdated(editor);
            expect(editor.shadowRoot.querySelector('.att-chip-name').textContent).to.equal('note.txt');

            const removePromise = oneEvent(editor, 'attachments-change');
            editor.shadowRoot.querySelector('.att-chip-remove').click();
            const removed = await removePromise;
            expect(removed.detail.attachments).to.have.length(0);

            const events = captureBusEvents();
            const big = new File(
                [new Uint8Array(MARKDOWN_EDITOR_MAX_ATTACHMENT_BYTES + 1)],
                'huge.bin',
                { type: 'application/octet-stream' },
            );
            const dt2 = new DataTransfer();
            dt2.items.add(big);
            Object.defineProperty(input, 'files', { configurable: true, value: dt2.files });
            await editor._onFilesSelected({ target: input });
            const toast = events.find((e) => e.type === CoreEvents.UI_TOAST_SHOW);
            expect(toast).to.exist;
            expect(String(toast.payload.i18n_key)).to.include('attach_too_large');
            expect(editor.attachments).to.have.length(0);
        } finally {
            window.fetch = originalFetch;
        }
    });

    it('compose link insert uses createLink with allowlisted href', async () => {
        const editor = await mountCompose();
        const originalPrompt = window.prompt;
        window.prompt = () => 'https://mail.example/x';
        body(editor).focus();
        editor.insertTextAtCursor('linkme');
        const selection = window.getSelection();
        selection.removeAllRanges();
        const range = document.createRange();
        range.selectNodeContents(body(editor));
        selection.addRange(range);
        editor._insertLink();
        expect(body(editor).innerHTML.toLowerCase()).to.include('href="https://mail.example/x"');
        window.prompt = originalPrompt;
    });

    it('primaryDisabled disables primary button', async () => {
        const editor = await mountCompose({ showPrimary: true, primaryDisabled: true });
        const btn = editor.shadowRoot.querySelector('.action-bar platform-button');
        expect(btn.hasAttribute('disabled') || btn.disabled === true).to.equal(true);
    });
});
