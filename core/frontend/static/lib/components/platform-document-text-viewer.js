/**
 * platform-document-text-viewer — Lit viewer для text handler (CodeMirror / HTML preview / Markdown preview).
 */
import { html, css, nothing } from 'lit';
import { PlatformElement } from '../platform-element/index.js';
import './platform-json-editor.js';
import './platform-code-editor.js';
import './platform-markdown-editor.js';

function languageFromFileName(originalName, contentType) {
    const normalizedType = typeof contentType === 'string' ? contentType.split(';', 1)[0].trim() : '';
    const name = typeof originalName === 'string' ? originalName : '';
    if (normalizedType === 'application/json' || name.toLowerCase().endsWith('.json')) {
        return 'json';
    }
    const dotIndex = name.lastIndexOf('.');
    if (dotIndex < 0) {
        return 'text';
    }
    const extension = name.slice(dotIndex + 1).toLowerCase();
    const extensionMap = {
        js: 'javascript',
        mjs: 'javascript',
        cjs: 'javascript',
        ts: 'typescript',
        py: 'python',
        go: 'go',
        cs: 'csharp',
        md: 'text',
        txt: 'text',
        yaml: 'text',
        yml: 'text',
        xml: 'text',
        html: 'text',
        css: 'text',
        sh: 'text',
    };
    const mapped = extensionMap[extension];
    if (mapped) {
        return mapped;
    }
    return 'text';
}

function normalizePresentation(value) {
    if (value === 'html' || value === 'markdown' || value === 'code') {
        return value;
    }
    return 'code';
}

function normalizeViewMode(value, presentation) {
    if (presentation === 'code') {
        return 'source';
    }
    if (value === 'preview' || value === 'source') {
        return value;
    }
    return 'preview';
}

export class PlatformDocumentTextViewer extends PlatformElement {
    static i18nNamespace = 'platform';

    static properties = {
        streamUrl: { type: String, attribute: 'stream-url' },
        saveUrl: { type: String, attribute: 'save-url' },
        originalName: { type: String, attribute: 'original-name' },
        contentType: { type: String, attribute: 'content-type' },
        editMode: { type: Boolean, attribute: 'edit-mode' },
        presentation: { type: String },
        viewMode: { type: String, attribute: 'view-mode' },
    };

    static styles = [
        PlatformElement.styles,
        css`
            :host {
                display: flex;
                flex-direction: column;
                flex: 1;
                min-width: 0;
                min-height: 0;
                height: 100%;
            }
            .state {
                display: flex;
                align-items: center;
                justify-content: center;
                flex: 1;
                color: var(--text-secondary);
                font-size: var(--text-sm);
            }
            .state-error {
                color: var(--danger);
            }
            .toolbar {
                display: flex;
                align-items: center;
                gap: var(--space-2);
                padding: var(--space-2) var(--space-3);
                border-bottom: 1px solid var(--glass-border-subtle);
                background: var(--glass-solid-medium);
            }
            .status {
                color: var(--text-tertiary);
                font-size: var(--text-xs);
            }
            .editor-shell {
                display: flex;
                flex: 1;
                min-height: 0;
            }
            platform-json-editor,
            platform-code-editor,
            platform-markdown-editor {
                flex: 1;
                min-height: 0;
            }
            .html-preview-frame {
                flex: 1;
                min-width: 0;
                min-height: 0;
                width: 100%;
                height: 100%;
                border: 0;
                background: #fff;
            }
            .markdown-preview-shell {
                display: flex;
                flex: 1;
                min-height: 0;
                overflow: auto;
                padding: var(--space-4);
                background: var(--bg-primary);
            }
            .markdown-preview-shell platform-markdown-editor {
                width: 100%;
                max-width: 920px;
                margin: 0 auto;
                --markdown-editor-min-height: 0;
                --markdown-editor-body-min-height: 0;
                --markdown-editor-body-max-height: none;
            }
        `,
    ];

    constructor() {
        super();
        this.streamUrl = '';
        this.saveUrl = '';
        this.originalName = '';
        this.contentType = '';
        this.editMode = false;
        this.presentation = 'code';
        this.viewMode = 'source';
        this._content = '';
        this._loading = false;
        this._error = '';
        this._saveStatus = '';
        this._loadGeneration = 0;
    }

    connectedCallback() {
        super.connectedCallback();
        void this._loadContent();
    }

    updated(changed) {
        super.updated?.(changed);
        if (changed.has('streamUrl')) {
            void this._loadContent();
        }
    }

    get _resolvedPresentation() {
        return normalizePresentation(this.presentation);
    }

    get _resolvedViewMode() {
        return normalizeViewMode(this.viewMode, this._resolvedPresentation);
    }

    get _isPreviewMode() {
        const presentation = this._resolvedPresentation;
        return this._resolvedViewMode === 'preview'
            && (presentation === 'html' || presentation === 'markdown');
    }

    async _loadContent() {
        const streamUrl = this.streamUrl;
        if (typeof streamUrl !== 'string' || streamUrl.length === 0) {
            this._error = this.t('document_viewer.missing_stream_url');
            this.requestUpdate();
            return;
        }
        const generation = this._loadGeneration + 1;
        this._loadGeneration = generation;
        this._loading = true;
        this._error = '';
        this._saveStatus = '';
        this.requestUpdate();
        let response;
        try {
            response = await fetch(streamUrl);
        } catch (loadError) {
            if (generation !== this._loadGeneration) return;
            this._loading = false;
            this._error = loadError instanceof Error ? loadError.message : String(loadError);
            this.requestUpdate();
            return;
        }
        if (generation !== this._loadGeneration) return;
        if (!response.ok) {
            this._loading = false;
            this._error = this.t('document_viewer.load_failed', { status: String(response.status) });
            this.requestUpdate();
            return;
        }
        const text = await response.text();
        if (generation !== this._loadGeneration) return;
        this._content = text;
        this._loading = false;
        this.requestUpdate();
    }

    async _saveContent(value) {
        if (this._isPreviewMode) {
            return;
        }
        const saveUrl = this.saveUrl;
        if (typeof saveUrl !== 'string' || saveUrl.length === 0) {
            return;
        }
        this._saveStatus = this.t('document_viewer.saving');
        this.requestUpdate();
        const response = await fetch(saveUrl, {
            method: 'POST',
            headers: { 'Content-Type': 'text/plain; charset=utf-8' },
            body: value,
        });
        if (!response.ok) {
            this._saveStatus = this.t('document_viewer.save_failed', { status: String(response.status) });
            this.requestUpdate();
            this.emit('editor-error', { message: this._saveStatus });
            return;
        }
        this._content = value;
        this._saveStatus = this.t('document_viewer.saved');
        this.requestUpdate();
        this.emit('document-state', { dirty: false });
    }

    _onSave(event) {
        if (this._isPreviewMode) {
            return;
        }
        const detail = event.detail;
        if (!detail || typeof detail.value !== 'string') {
            return;
        }
        void this._saveContent(detail.value);
    }

    _onChange(event) {
        if (this._isPreviewMode) {
            return;
        }
        const detail = event.detail;
        if (!detail || typeof detail.value !== 'string') {
            return;
        }
        this._content = detail.value;
        this.emit('document-state', { dirty: true });
    }

    _renderHtmlPreview() {
        return html`
            <iframe
                class="html-preview-frame"
                title=${this.originalName || this.t('document_viewer.html_preview')}
                sandbox=""
                srcdoc=${this._content}
            ></iframe>
        `;
    }

    _renderMarkdownPreview() {
        return html`
            <div class="markdown-preview-shell">
                <platform-markdown-editor
                    readonly
                    view-mode="preview"
                    .value=${this._content}
                    ?show-primary=${false}
                    ?show-attach=${false}
                    ?show-discard=${false}
                    ?show-format-toggle=${false}
                ></platform-markdown-editor>
            </div>
        `;
    }

    _renderSourceEditor() {
        const language = languageFromFileName(this.originalName, this.contentType);
        const readonly = !this.editMode;
        const showToolbar = this.editMode && typeof this.saveUrl === 'string' && this.saveUrl.length > 0;
        return html`
            ${showToolbar ? html`
                <div class="toolbar">
                    <span class="status">${this._saveStatus || this.t('document_viewer.save_hint')}</span>
                </div>
            ` : nothing}
            <div class="editor-shell">
                ${language === 'json' ? html`
                    <platform-json-editor
                        fill-parent
                        .value=${this._content}
                        .readonly=${readonly}
                        .showToolbar=${false}
                        .minHeight=${120}
                        @save=${this._onSave}
                        @change=${this._onChange}
                    ></platform-json-editor>
                ` : html`
                    <platform-code-editor
                        fill-parent
                        .value=${this._content}
                        .language=${language}
                        .readonly=${readonly}
                        .lineWrapping=${true}
                        .minHeight=${120}
                        @save=${this._onSave}
                        @change=${this._onChange}
                    ></platform-code-editor>
                `}
            </div>
        `;
    }

    render() {
        if (this._loading) {
            return html`<div class="state">${this.t('document_viewer.loading')}</div>`;
        }
        if (this._error) {
            return html`<div class="state state-error">${this._error}</div>`;
        }
        if (this._isPreviewMode && this._resolvedPresentation === 'html') {
            return this._renderHtmlPreview();
        }
        if (this._isPreviewMode && this._resolvedPresentation === 'markdown') {
            return this._renderMarkdownPreview();
        }
        return this._renderSourceEditor();
    }
}

customElements.define('platform-document-text-viewer', PlatformDocumentTextViewer);
