/**
 * OfficeDocumentEditorPage — тонкая обёртка над `<platform-onlyoffice-host>`.
 *
 * Маршрут `/documents/edit/:bindingId` (parameter передаётся как `.bindingId`
 * из `OfficeApp.renderRoute`). Фабрика `useOp('office/document_editor_config')`
 * по `bindingId` достаёт JWT и URL DocsAPI, передаёт результат как `config`
 * в `<platform-onlyoffice-host>`. Все iframe-портал и обозреватели изолированы в host.
 *
 * Простая защита от мусорного сегмента в URL — `_isPlausibleBindingId`:
 * не допускает слэши, `..`, расширения; иначе показывает ошибку без
 * запроса конфигурации.
 */

import { html, css, nothing } from 'lit';
import { PlatformPage } from '@platform/lib/base/PlatformPage.js';
import '@platform/lib/components/platform-breadcrumbs.js';
import '@platform/lib/components/platform-onlyoffice-host.js';

const BAD_BINDING_PATTERNS = [/\//, /\.\./, /\.html?$/i, /^\s*$/];

function _isPlausibleBindingId(id) {
    if (typeof id !== 'string' || id.length === 0) return false;
    if (id.length > 256) return false;
    for (const pat of BAD_BINDING_PATTERNS) {
        if (pat.test(id)) return false;
    }
    return true;
}

export class OfficeDocumentEditorPage extends PlatformPage {
    static i18nNamespace = 'documents';

    static properties = {
        bindingId: { type: String },
        embedded: { type: Boolean },
        _editorError: { state: true },
    };

    static styles = [
        PlatformPage.styles,
        css`
            :host {
                display: flex;
                flex-direction: column;
                width: 100%;
                height: 100%;
                min-width: 0;
                min-height: 0;
            }
            .breadcrumbs-wrap {
                padding: var(--space-2) var(--space-3) 0;
                flex-shrink: 0;
            }
            .toolbar {
                display: flex;
                align-items: center;
                gap: var(--space-2);
                padding: var(--space-2) var(--space-3);
                background: var(--glass-solid-medium);
                border-bottom: 1px solid var(--glass-border-subtle);
                flex-shrink: 0;
            }
            .toolbar .back {
                background: transparent;
                border: none;
                color: var(--text-secondary);
                cursor: pointer;
                padding: var(--space-1) var(--space-2);
                display: inline-flex; align-items: center;
                gap: var(--space-2);
                font-size: var(--text-sm);
            }
            .toolbar .back:hover { color: var(--text-primary); }
            .editor-area { flex: 1; display: flex; min-height: 0; }
            :host([embedded]) .editor-area,
            :host-context([embedded]) .editor-area {
                height: 100%;
            }
            .error {
                color: var(--text-secondary);
                padding: var(--space-3);
                font-size: var(--text-sm);
            }
            .loading {
                color: var(--text-secondary);
                padding: var(--space-3);
                font-size: var(--text-sm);
            }
        `,
    ];

    constructor() {
        super();
        this.bindingId = '';
        this.embedded = false;
        this._editorError = '';
        this._editor = this.useOp('office/document_editor_config');
    }

    updated(changed) {
        super.updated && super.updated(changed);
        if (changed.has('bindingId')) {
            this._editorError = '';
            const id = (this.bindingId || '').trim();
            if (!_isPlausibleBindingId(id)) {
                this._editorError = this.t('editor.errInvalidBindingId');
                return;
            }
            this._editor.run({ bindingId: id, namespace: this._namespaceFromLocation() });
        }
    }

    _back() { this.navigate('documents_list'); }

    _namespaceFromLocation() {
        if (typeof window === 'undefined') return '';
        const raw = new URLSearchParams(window.location.search).get('namespace');
        return typeof raw === 'string' ? raw.trim() : '';
    }

    _onEditorError(e) {
        const detail = e.detail || {};
        const code = typeof detail.code === 'string' ? detail.code : '';
        const messageMap = {
            bad_config:    this.t('editor.errBadConfig'),
            docs_api:      this.t('editor.errDocsApi'),
            ds_error:      this.t('editor.eventError'),
            open_timeout:  this.t('editor.errOpenTimeout'),
        };
        this._editorError = messageMap[code] || this.t('editor.eventError');
        this.toast('editor.eventError', { type: 'error' });
    }

    _docTitle() {
        const config = this._editor.lastResult;
        if (!config || !config.document) return '';
        const title = config.document.title;
        return typeof title === 'string' && title.length > 0 ? title : '';
    }

    render() {
        if (!this.bindingId) {
            return html`<div class="error">${this.t('editor.errNoId')}</div>`;
        }
        if (this._editorError) {
            return html`
                ${this.embedded ? nothing : html`
                    <div class="breadcrumbs-wrap">
                        <platform-breadcrumbs current-label=${this._docTitle()}></platform-breadcrumbs>
                    </div>
                    <div class="toolbar">
                        <button class="back" type="button" @click=${this._back}>← ${this.t('editor.back')}</button>
                    </div>
                `}
                <div class="error">${this._editorError}</div>
            `;
        }
        const config = this._editor.lastResult;
        const showLoading = this._editor.busy && !config;
        return html`
            ${this.embedded ? nothing : html`
                <div class="breadcrumbs-wrap">
                    <platform-breadcrumbs current-label=${this._docTitle()}></platform-breadcrumbs>
                </div>
                <div class="toolbar">
                    <button class="back" type="button" @click=${this._back}>← ${this.t('editor.back')}</button>
                </div>
            `}
            <div class="editor-area">
                ${showLoading
                    ? html`<div class="loading">${this.t('editor.loading')}</div>`
                    : (config
                        ? html`<platform-onlyoffice-host
                                .bindingId=${this.bindingId}
                                .config=${config}
                                @editor-error=${this._onEditorError}
                            ></platform-onlyoffice-host>`
                        : nothing)}
            </div>
        `;
    }
}

customElements.define('office-document-editor-page', OfficeDocumentEditorPage);
