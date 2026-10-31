/**
 * platform-markdown-editor — strict document / API / modes / preview / fail-closed.
 */

import {
    fixture,
    fixtureCleanup,
    html,
    expect,
    elementUpdated,
    waitUntil,
    oneEvent,
    aTimeout,
} from '../helpers/render.js';
import { resetPlatformState, bootstrapTestBus } from '../helpers/reset.js';
import { setDefaultI18nNamespace } from '@platform/lib/utils/i18n-namespace.js';
import { seedPlatformMarkdownEditorI18n, platformEn } from '../helpers/seed-platform-i18n.js';
import '@platform/lib/components/platform-markdown-editor.js';
import {q, qs, qsa, shadow, type TestEl} from '../helpers/dom.js';

async function prepare() {
    resetPlatformState();
    bootstrapTestBus();
    setDefaultI18nNamespace('platform');
    await seedPlatformMarkdownEditorI18n();
}

function assertUnifiedChangeDetail(detail: any) {
    expect(detail).to.be.an('object');
    expect(detail).to.have.all.keys(['value', 'htmlValue', 'textValue']);
    expect((detail as TestEl).value).to.be.a('string');
    expect(detail.htmlValue).to.be.a('string');
    expect(detail.textValue).to.be.a('string');
}

async function mountDocument(props: any = {}) {
    const editor = await fixture<TestEl>(html`
        <platform-markdown-editor
            .value=${(props as TestEl).value ?? ''}
            .label=${props.label ?? ''}
            .hint=${props.hint ?? ''}
            .placeholder=${props.placeholder ?? ''}
            .readonly=${props.readonly === true}
            .showHeader=${props.showHeader !== false}
            .showPreview=${props.showPreview !== false}
            .showHint=${props.showHint !== false}
            .enableVariables=${props.enableVariables === true}
            .enableMentions=${props.enableMentions === true}
            .acceptFileDrop=${props.acceptFileDrop === true}
            .variant=${props.variant ?? 'default'}
            .viewMode=${props.viewMode ?? 'source'}
            .minHeight=${props.minHeight ?? 150}
        ></platform-markdown-editor>
    `);
    if (props.viewMode !== 'preview' || props.readonly !== true) {
        await waitUntil(() => editor._editorView !== null, 'CodeMirror ready', { timeout: 15_000 });
    } else {
        await elementUpdated(editor);
    }
    return editor;
}

describe('platform-markdown-editor registration & defaults', () => {
    beforeEach(async function prepareHook() {
        this.timeout(20_000);
        await prepare();
    });

    afterEach(() => {
        fixtureCleanup();
    });

    it('registers custom element once', () => {
        expect(customElements.get('platform-markdown-editor')).to.exist;
    });

    it('defaults: source document surface with empty value', async () => {
        const editor = await mountDocument();
        expect(editor.variant).to.equal('default');
        expect(editor.viewMode).to.equal('source');
        expect((editor as TestEl).value).to.equal('');
        expect(editor.getValue()).to.equal('');
        expect(editor.readonly).to.equal(false);
        expect(editor.enableVariables).to.equal(false);
        expect(editor.enableMentions).to.equal(false);
        expect(editor.acceptFileDrop).to.equal(false);
        expect(q(shadow(editor), '#codemirror-container')).to.exist;
        expect(q(shadow(editor), '.compose-shell')).to.equal(null);
    });
});

describe('platform-markdown-editor document API', () => {
    beforeEach(async function prepareHook() {
        this.timeout(20_000);
        await prepare();
    });

    afterEach(() => {
        fixtureCleanup();
    });

    it('getValue / setValue / prop value stay in sync', async () => {
        const editor = await mountDocument({ value: 'alpha' });
        expect(editor.getValue()).to.equal('alpha');

        editor.setValue('beta');
        await elementUpdated(editor);
        expect(editor.getValue()).to.equal('beta');
        expect((editor as TestEl).value).to.equal('beta');

        (editor as TestEl).value = 'gamma';
        await elementUpdated(editor);
        expect(editor.getValue()).to.equal('gamma');
    });

    it('insertTextAtCursor emits unified change detail', async () => {
        const editor = await mountDocument({ value: '' });
        const changePromise = oneEvent(editor, 'change');
        editor.insertTextAtCursor('hello **world**');
        const event = await changePromise;
        assertUnifiedChangeDetail((event as CustomEvent).detail);
        expect((event as CustomEvent).detail.value).to.equal('hello **world**');
        expect((event as CustomEvent).detail.textValue).to.include('hello');
        expect((event as CustomEvent).detail.htmlValue.length).to.be.greaterThan(0);
        expect(editor.getValue()).to.equal('hello **world**');
    });

    it('insertTextAtCursor with empty string throws', async () => {
        const editor = await mountDocument({ value: 'keep' });
        expect(() => editor.insertTextAtCursor('')).to.throw(
            'platform-markdown-editor: insertTextAtCursor text required',
        );
        expect(editor.getValue()).to.equal('keep');
    });

    it('focus() focuses CodeMirror without throw', async () => {
        const editor = await mountDocument({ value: 'x' });
        expect(() => editor.focus()).to.not.throw();
        expect(editor._editorView.hasFocus).to.equal(true);
    });

    it('blur emits when CodeMirror loses focus', async function blurEmits() {
        this.timeout(10_000);
        const editor = await mountDocument({ value: 'x' });
        editor._editorView.contentDOM.focus();
        await aTimeout(20);
        expect(editor._editorView.hasFocus).to.equal(true);
        const blurPromise = new Promise((resolve, reject) => {
            const timeoutId = window.setTimeout(() => {
                reject(new Error('custom blur event timeout'));
            }, 8000);
            const onBlur = (event: any) => {
                if (!(event instanceof CustomEvent) || (event as CustomEvent).detail !== null) {
                    return;
                }
                window.clearTimeout(timeoutId);
                editor.removeEventListener('blur', onBlur);
                resolve(event);
            };
            editor.addEventListener('blur', onBlur);
            editor._editorView.contentDOM.blur();
        });
        const event = await blurPromise;
        expect((event as CustomEvent).detail).to.equal(null);
    });

    it('toolbar wrapSelection and prefixSelectedLines mutate markdown', async () => {
        const editor = await mountDocument({ value: 'word' });
        editor._editorView.dispatch({
            selection: { anchor: 0, head: 4 },
        });
        editor._wrapSelection('**', '**', 'text');
        expect(editor.getValue()).to.equal('**word**');

        editor.setValue('line');
        editor._editorView.dispatch({
            selection: { anchor: 0, head: 4 },
        });
        editor._prefixSelectedLines('- ');
        expect(editor.getValue()).to.equal('- line');
    });

    it('format toolbar buttons apply bold and heading', async () => {
        const editor = await mountDocument({ value: 'word' });
        editor._editorView.dispatch({ selection: { anchor: 0, head: 4 } });
        const bold = [...qsa(shadow(editor), '.tool-btn')]
            .find((btn) => btn.title === platformEn.markdown_editor.format_bold);
        expect(bold).to.exist;
        (bold as TestEl).click();
        await waitUntil(() => editor.getValue() === '**word**', 'bold applied');

        editor.setValue('Title');
        editor._editorView.dispatch({ selection: { anchor: 0, head: 5 } });
        const h2 = [...qsa(shadow(editor), '.tool-btn')]
            .find((btn) => btn.title === platformEn.markdown_editor.format_heading);
        (h2 as TestEl).click();
        await waitUntil(() => editor.getValue() === '## Title', 'heading applied');
    });

    it('accept-file-drop inserts dropped text/plain at cursor', async () => {
        const editor = await mountDocument({ value: '', acceptFileDrop: true });
        const changePromise = oneEvent(editor, 'change');
        const drop = new Event('drop', { bubbles: true, cancelable: true });
        Object.defineProperty(drop, 'dataTransfer', {
            value: {
                getData: (type: any) => (type === 'text/plain' ? 'dropped-token' : ''),
            },
        });
        editor._editorView.dom.dispatchEvent(drop);
        const event = await changePromise;
        expect((event as CustomEvent).detail.value).to.equal('dropped-token');
    });

    it('disconnectedCallback destroys CodeMirror and removes escape listener', async () => {
        const editor = await mountDocument({ value: 'x' });
        expect(editor._editorView).to.not.equal(null);
        editor._toggleFullscreen();
        expect(editor.fullscreenMode).to.equal(true);
        editor.remove();
        expect(editor._editorView).to.equal(null);
        expect(document.body.style.overflow).to.equal('');
    });
});

describe('platform-markdown-editor modes & chrome', () => {
    beforeEach(async function prepareHook() {
        this.timeout(20_000);
        await prepare();
    });

    afterEach(() => {
        fixtureCleanup();
    });

    it('_setMode edit/preview/split and rejects unknown mode', async () => {
        const editor = await mountDocument({ value: '# Hi' });
        editor._setMode('preview');
        await elementUpdated(editor);
        expect(editor.previewMode).to.equal(true);
        expect(editor.splitMode).to.equal(false);
        expect(qs(shadow(editor), '.preview-container')).to.exist;

        editor._setMode('split');
        await elementUpdated(editor);
        await waitUntil(() => editor._editorView !== null, 'split CM ready', { timeout: 15_000 });
        expect(editor.splitMode).to.equal(true);
        expect(editor.previewMode).to.equal(false);
        expect(qs(shadow(editor), '.split-container')).to.exist;

        editor._setMode('edit');
        await elementUpdated(editor);
        expect(editor.previewMode).to.equal(false);
        expect(editor.splitMode).to.equal(false);

        expect(() => editor._setMode('wysiwyg')).to.throw(/unsupported mode/);
        expect(() => editor._setMode('')).to.throw(/unsupported mode/);
    });

    it('mode tabs switch via UI', async () => {
        const editor = await mountDocument({ value: 'body' });
        const tabs = qsa(shadow(editor), '.mode-tab');
        expect(tabs.length).to.equal(3);
        tabs[1]!.click();
        await elementUpdated(editor);
        expect(editor.previewMode).to.equal(true);
        tabs[2]!.click();
        await elementUpdated(editor);
        await waitUntil(() => editor._editorView !== null, 'split ready', { timeout: 15_000 });
        expect(editor.splitMode).to.equal(true);
        tabs[0]!.click();
        await elementUpdated(editor);
        expect(editor.previewMode).to.equal(false);
        expect(editor.splitMode).to.equal(false);
    });

    it('Escape exits fullscreen', async () => {
        const editor = await mountDocument({ value: 'x' });
        editor._toggleFullscreen();
        expect(editor.hasAttribute('fullscreen')).to.equal(true);
        expect(document.body.style.overflow).to.equal('hidden');
        document.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape', bubbles: true }));
        await elementUpdated(editor);
        expect(editor.fullscreenMode).to.equal(false);
        expect(editor.hasAttribute('fullscreen')).to.equal(false);
        expect(document.body.style.overflow).to.equal('');
    });

    it('showHeader=false hides header; format toolbar is independent', async () => {
        const bare = await mountDocument({ showHeader: false, value: 'a' });
        expect(q(shadow(bare), '.editor-header')).to.equal(null);
        expect(qs(shadow(bare), '.format-toolbar')).to.exist;
        expect(qs(shadow(bare), 'platform-voice-dictation')).to.exist;

        bare.showFormatToolbar = false;
        await elementUpdated(bare);
        expect(qs(shadow(bare), '.format-toolbar')).to.exist;
        expect(q(shadow(bare), 'platform-voice-dictation')).to.exist;

        bare.enableVoiceDictation = false;
        await elementUpdated(bare);
        expect(q(shadow(bare), '.format-toolbar')).to.equal(null);
        expect(q(shadow(bare), 'platform-voice-dictation')).to.equal(null);

        const labeled = await mountDocument({
            value: 'a',
            label: 'Prompt',
            hint: 'Helpful hint',
        });
        expect(qs(shadow(labeled), '.editor-label').textContent).to.equal('Prompt');
        expect(qs(shadow(labeled), 'platform-help-hint')).to.exist;
        expect(qs(shadow(labeled), '.format-toolbar')).to.exist;
    });

    it('enableVoiceDictation inserts transcribed text at cursor', async () => {
        const editor = await mountDocument({ value: 'prefix' });
        expect(editor.enableVoiceDictation).to.equal(true);
        const mic = qs(shadow(editor), 'platform-voice-dictation');
        expect(mic).to.exist;
        mic.dispatchEvent(new CustomEvent('transcribed', {
            detail: { text: 'spoken', provider: 'mock' },
            bubbles: true,
            composed: true,
        }));
        await elementUpdated(editor);
        expect(editor.getValue()).to.equal('prefix\n\nspoken');
    });

    it('hides voice dictation when readonly or previewMode', async () => {
        const editor = await mountDocument({ value: 'x', readonly: true });
        expect(q(shadow(editor), 'platform-voice-dictation')).to.equal(null);

        const preview = await mountDocument({ value: 'x' });
        preview.previewMode = true;
        await elementUpdated(preview);
        expect(q(shadow(preview), 'platform-voice-dictation')).to.equal(null);
    });

    it('boolean attribute ?show-header=false does NOT clear constructor default true', async () => {
        const editor = await fixture<TestEl>(html`
            <platform-markdown-editor
                .value=${'x'}
                ?show-header=${false}
            ></platform-markdown-editor>
        `);
        await waitUntil(() => editor._editorView !== null, 'CodeMirror ready', { timeout: 15_000 });
        expect(editor.showHeader).to.equal(true);
        expect(qs(shadow(editor), '.editor-header')).to.exist;
    });

    it('fills available height by default; compact opts out', async () => {
        const host = await fixture<TestEl>(html`
            <div style="display:flex;flex-direction:column;height:480px;">
                <platform-markdown-editor .value=${'fill-me'}></platform-markdown-editor>
            </div>
        `);
        const editor = qs(host!, 'platform-markdown-editor');
        await waitUntil(() => editor._editorView !== null, 'CodeMirror ready', { timeout: 15_000 });
        expect(editor.compact).to.equal(false);
        const editorHeight = editor.getBoundingClientRect().height;
        expect(editorHeight).to.be.at.least(400);

        const compactHost = await fixture<TestEl>(html`
            <div style="display:flex;flex-direction:column;height:480px;">
                <platform-markdown-editor compact .value=${'x'} .minHeight=${120}></platform-markdown-editor>
            </div>
        `);
        const compactEditor = qs(compactHost!, 'platform-markdown-editor');
        await waitUntil(() => compactEditor._editorView !== null, 'compact CM ready', { timeout: 15_000 });
        expect(compactEditor.compact).to.equal(true);
        expect(compactEditor.getBoundingClientRect().height).to.be.below(280);
    });

    it('embed + showHeader=false keeps format palette without mode chrome', async () => {
        const editor = await fixture<TestEl>(html`
            <platform-markdown-editor
                variant="embed"
                .value=${'# note'}
                .showHeader=${false}
                .showPreview=${false}
                .showHint=${false}
                .showFormatToolbar=${true}
            ></platform-markdown-editor>
        `);
        await waitUntil(() => editor._editorView !== null, 'CodeMirror ready', { timeout: 15_000 });
        expect(q(shadow(editor), '.editor-header')).to.equal(null);
        expect(q(shadow(editor), '.mode-switch')).to.equal(null);
        expect(qs(shadow(editor), '.format-toolbar')).to.exist;
        expect(qs(shadow(editor), '#codemirror-container')).to.exist;
    });

    it('empty preview shows i18n empty_preview copy', async () => {
        const editor = await mountDocument({ value: '' });
        editor._setMode('preview');
        await elementUpdated(editor);
        const preview = qs(shadow(editor), '.preview-container');
        expect(preview.textContent).to.equal(platformEn.markdown_editor.empty_preview);
    });

    it('readonly preview-only path skips CodeMirror', async () => {
        const editor = await fixture<TestEl>(html`
            <platform-markdown-editor
                readonly
                view-mode="preview"
                .value=${'## Office preview'}
            ></platform-markdown-editor>
        `);
        await elementUpdated(editor);
        expect(editor._editorView).to.equal(null);
        expect(q(shadow(editor), '#codemirror-container')).to.equal(null);
        expect(qs(shadow(editor), '.preview-container').textContent)
            .to.include('Office preview');
    });

    it('document stats reflect words and characters', async () => {
        const editor = await mountDocument({ value: 'one two' });
        const status = qs(shadow(editor), '.editor-status');
        expect(status.textContent).to.include('2');
        expect(status.textContent).to.include('7');
    });
});

describe('platform-markdown-editor mentions', () => {
    beforeEach(async function prepareHook() {
        this.timeout(20_000);
        await prepare();
    });

    afterEach(() => {
        fixtureCleanup();
    });

    it('emits mention-query when typing @query', async () => {
        const editor = await mountDocument({ value: '', enableMentions: true });
        const mentionPromise = oneEvent(editor, 'mention-query');
        editor.insertTextAtCursor('@vik');
        const event = await mentionPromise;
        expect((event as CustomEvent).detail.query).to.equal('vik');
        expect((event as CustomEvent).detail.from).to.be.a('number');
        expect((event as CustomEvent).detail.to).to.be.a('number');
        expect((event as CustomEvent).detail.to).to.be.greaterThan((event as CustomEvent).detail.from);
    });

    it('insertMention inserts CRM token and validates args', async () => {
        const editor = await mountDocument({ value: '', enableMentions: true });
        expect(() => editor.insertMention({ name: '', entityId: 'e1' }))
            .to.throw(/mention name required/);
        expect(() => editor.insertMention({ name: 'Ada', entityId: '' }))
            .to.throw(/mention entityId required/);

        const changePromise = oneEvent(editor, 'change');
        editor.insertMention({ name: 'Ada Lovelace', entityId: 'ent_42' });
        const event = await changePromise;
        expect((event as CustomEvent).detail.value).to.equal('[@Ada Lovelace](entity:ent_42)');
    });
});

describe('platform-markdown-editor fail-closed', () => {
    beforeEach(async function prepareHook() {
        this.timeout(20_000);
        await prepare();
    });

    afterEach(() => {
        fixtureCleanup();
    });

    it('link insert rejects empty and non-allowlisted schemes', async () => {
        const editor = await mountDocument({ value: '' });

        const drivePrompt = async (value: any) => {
            const p = editor._insertLink();
            const modal = qs(document!, 'platform-confirm-modal');
            expect(modal, 'platformPrompt открывает модалку').to.exist;
            await modal.updateComplete;
            if (value === null) {
                modal._onCancel();
            } else {
                modal.inputValue = value;
                modal._onConfirm();
            }
            return p;
        };
        const rejects = async (p: any, re: any) => {
            let err = null;
            try {
                await p;
            } catch (e) {
                err = e;
            }
            expect(err, 'ожидалась ошибка').to.exist;
            expect(String((err as Error).message)).to.match(re);
        };

        await rejects(drivePrompt('   '), /link href required/);
        await rejects(drivePrompt('javascript:alert(1)'), /http\(s\) or mailto/);
        await rejects(drivePrompt('/relative'), /http\(s\) or mailto/);

        await drivePrompt('https://safe.example/path');
        expect(editor.getValue()).to.equal('[link](https://safe.example/path)');

        const before = editor.getValue();
        await drivePrompt(null);
        expect(editor.getValue()).to.equal(before);
    });

    it('invalid attachment index throws', async () => {
        const editor = await mountDocument({ value: '' });
        editor.attachments = [{
            filename: 'a.txt',
            content_type: 'text/plain',
            file_id: 'file_md_test_1',
            url: '/frontend/api/v1/files/download/file_md_test_1',
            size: 1,
        }];
        expect(() => editor._removeAttachment(-1)).to.throw(/invalid attachment index/);
        expect(() => editor._removeAttachment(3)).to.throw(/invalid attachment index/);
    });
});
