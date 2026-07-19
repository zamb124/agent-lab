/**
 * OfficeDocumentEditorPage — immersive Paper Stage вокруг document viewer.
 *
 * Маршрут `/documents/edit/:fileId` (parameter → `.fileId` из OfficeApp).
 * Фабрика `office/document_editor_config` → JWT/DocsAPI →
 * `<platform-document-viewer-host>`. Sidebar shell скрыт на этом маршруте.
 */

import { html, css, nothing } from 'lit';
import { PlatformPage } from '@platform/lib/base/PlatformPage.js';
import '@platform/lib/components/platform-document-viewer-host.js';
import '@platform/lib/components/platform-icon.js';

const BAD_FILE_ID_PATTERNS = [/\//, /\.\./, /\.html?$/i, /^\s*$/];

function _isPlausibleFileId(id) {
    if (typeof id !== 'string' || id.length === 0) return false;
    if (id.length > 256) return false;
    for (const pat of BAD_FILE_ID_PATTERNS) {
        if (pat.test(id)) return false;
    }
    return true;
}

export class OfficeDocumentEditorPage extends PlatformPage {
    static i18nNamespace = 'documents';

    static properties = {
        fileId: { type: String },
        embedded: { type: Boolean },
        _editorError: { state: true },
        _dirty: { state: true },
        _savePulse: { state: true },
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
                background: var(--documents-stage-ambient);
                animation: stage-enter 220ms var(--motion-ease-out, ease-out) both;
            }
            @keyframes stage-enter {
                from { opacity: 0; transform: translateY(6px); }
                to { opacity: 1; transform: translateY(0); }
            }
            @keyframes chip-pulse {
                0%, 100% { transform: scale(1); opacity: 1; }
                40% { transform: scale(1.04); opacity: 0.92; }
            }
            .stage-bar {
                display: flex;
                align-items: center;
                gap: var(--space-3);
                padding: 0.5rem 0.875rem;
                background: var(--documents-stage-bar-bg);
                border-bottom: 1px solid var(--documents-stage-bar-border);
                backdrop-filter: blur(16px) saturate(140%);
                -webkit-backdrop-filter: blur(16px) saturate(140%);
                flex-shrink: 0;
                min-width: 0;
                z-index: 2;
            }
            .stage-back {
                display: inline-flex;
                align-items: center;
                justify-content: center;
                width: 2rem;
                height: 2rem;
                border: none;
                border-radius: 999px;
                background: transparent;
                color: var(--text-secondary);
                cursor: pointer;
                flex-shrink: 0;
                transition: background 160ms ease, color 160ms ease;
            }
            .stage-back:hover {
                background: var(--documents-stage-chip-bg);
                color: var(--text-primary);
            }
            .stage-title {
                flex: 1;
                min-width: 0;
                font-size: var(--text-base);
                font-weight: 500;
                color: var(--text-primary);
                letter-spacing: -0.01em;
                white-space: nowrap;
                overflow: hidden;
                text-overflow: ellipsis;
            }
            .stage-chip {
                flex-shrink: 0;
                padding: 0.25rem 0.625rem;
                border-radius: 999px;
                font-size: var(--text-xs);
                font-weight: 500;
                background: var(--documents-stage-chip-bg);
                color: var(--text-secondary);
                transition: background 180ms ease, color 180ms ease;
            }
            .stage-chip[data-dirty='true'] {
                background: var(--documents-stage-chip-dirty);
                color: var(--documents-stage-chip-dirty-text);
            }
            .stage-chip[data-pulse='true'] {
                animation: chip-pulse 420ms ease;
            }
            .editor-area {
                flex: 1;
                display: flex;
                min-height: 0;
                padding: 0.5rem 0.625rem 0.625rem;
                box-sizing: border-box;
            }
            :host([embedded]) .editor-area,
            :host-context([embedded]) .editor-area {
                height: 100%;
                padding: 0;
            }
            .editor-area platform-document-viewer-host {
                flex: 1;
                min-width: 0;
                min-height: 0;
                border-radius: var(--documents-stage-host-radius);
                overflow: hidden;
                box-shadow: var(--documents-stage-host-shadow);
                background: var(--documents-stage-host-bg);
            }
            .error {
                color: var(--text-secondary);
                padding: var(--space-3);
                font-size: var(--text-sm);
            }
            .loading-shell {
                flex: 1;
                display: flex;
                flex-direction: column;
                gap: 0.75rem;
                padding: 2.5rem 2rem;
                border-radius: var(--documents-stage-host-radius);
                background: var(--documents-stage-host-bg);
                box-shadow: var(--documents-stage-host-shadow);
            }
            .skeleton-line {
                height: 0.75rem;
                border-radius: 999px;
                background: var(--documents-stage-skeleton);
                background-size: 200% 100%;
                animation: skeleton-shimmer 1.2s ease-in-out infinite;
            }
            .skeleton-line.w60 { width: 60%; }
            .skeleton-line.w80 { width: 80%; }
            .skeleton-line.w40 { width: 40%; }
            .skeleton-page {
                flex: 1;
                margin-top: 1rem;
                border-radius: 4px;
                background: var(--documents-stage-paper);
                box-shadow: var(--documents-stage-host-shadow);
                position: relative;
                overflow: hidden;
            }
            .skeleton-page::after {
                content: '';
                position: absolute;
                inset: 0;
                background: var(--documents-stage-skeleton);
                background-size: 200% 100%;
                animation: skeleton-shimmer 1.2s ease-in-out infinite;
                opacity: 0.55;
            }
            @keyframes skeleton-shimmer {
                0% { background-position: 100% 0; }
                100% { background-position: -100% 0; }
            }
        `,
    ];

    constructor() {
        super();
        this.fileId = '';
        this.embedded = false;
        this._editorError = '';
        this._dirty = false;
        this._savePulse = false;
        this._pulseTimer = null;
        this._editor = this.useOp('office/document_editor_config');
    }

    disconnectedCallback() {
        if (this._pulseTimer != null) {
            clearTimeout(this._pulseTimer);
            this._pulseTimer = null;
        }
        super.disconnectedCallback();
    }

    updated(changed) {
        super.updated && super.updated(changed);
        if (changed.has('fileId')) {
            this._editorError = '';
            this._dirty = false;
            const id = (this.fileId || '').trim();
            if (!_isPlausibleFileId(id)) {
                this._editorError = this.t('editor.errInvalidFileId');
                return;
            }
            this._editor.run({ fileId: id, namespace: this._namespaceFromLocation() });
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

    _onDocumentState(e) {
        const detail = e.detail || {};
        const dirty = detail.dirty === true;
        const wasDirty = this._dirty;
        this._dirty = dirty;
        if (wasDirty && !dirty) {
            this._savePulse = true;
            if (this._pulseTimer != null) clearTimeout(this._pulseTimer);
            this._pulseTimer = setTimeout(() => {
                this._pulseTimer = null;
                this._savePulse = false;
            }, 420);
        }
    }

    _docTitle() {
        const openConfig = this._editor.lastResult;
        if (!openConfig || typeof openConfig.title !== 'string' || openConfig.title.length === 0) {
            return this.t('editor.stage.untitled');
        }
        return openConfig.title;
    }

    _renderStageBar() {
        return html`
            <div class="stage-bar">
                <button
                    class="stage-back"
                    type="button"
                    aria-label=${this.t('editor.stage.backAria')}
                    title=${this.t('editor.back')}
                    @click=${this._back}
                >
                    <platform-icon name="chevron-left" size="18"></platform-icon>
                </button>
                <div class="stage-title">${this._docTitle()}</div>
                <span
                    class="stage-chip"
                    data-dirty=${this._dirty ? 'true' : 'false'}
                    data-pulse=${this._savePulse ? 'true' : 'false'}
                >${this._dirty ? this.t('editor.stage.saving') : this.t('editor.stage.saved')}</span>
            </div>
        `;
    }

    _renderPaperSkeleton() {
        return html`
            <div class="loading-shell" role="status" aria-live="polite">
                <div class="skeleton-line w60"></div>
                <div class="skeleton-line w80"></div>
                <div class="skeleton-line w40"></div>
                <div class="skeleton-page"></div>
            </div>
        `;
    }

    render() {
        if (!this.fileId) {
            return html`<div class="error">${this.t('editor.errNoId')}</div>`;
        }
        if (this._editorError) {
            return html`
                ${this.embedded ? nothing : this._renderStageBar()}
                <div class="error">${this._editorError}</div>
            `;
        }
        const openConfig = this._editor.lastResult;
        const showLoading = this._editor.busy && !openConfig;
        return html`
            ${this.embedded ? nothing : this._renderStageBar()}
            <div class="editor-area">
                ${showLoading
                    ? this._renderPaperSkeleton()
                    : (openConfig
                        ? html`<platform-document-viewer-host
                                .fileId=${this.fileId}
                                .openConfig=${openConfig}
                                @editor-error=${this._onEditorError}
                                @document-state=${this._onDocumentState}
                            ></platform-document-viewer-host>`
                        : nothing)}
            </div>
        `;
    }
}

customElements.define('office-document-editor-page', OfficeDocumentEditorPage);
