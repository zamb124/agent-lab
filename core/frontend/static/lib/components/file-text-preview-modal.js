/**
 * Модалка превью текста, извлечённого из загруженного файла (общий компонент платформы).
 * GET {apiBaseUrl}/files/{file_id}/preview — ответ FileReadPreviewResponse.
 */
import { html, css } from 'lit';
import { PlatformModal } from './glass-modal.js';
import { buttonStyles } from '../styles/shared/button.styles.js';
import { BaseService } from '../services/BaseService.js';
import { I18nNs } from '../utils/i18n-namespace.js';
import './platform-button.js';

export class FileTextPreviewModal extends PlatformModal {
    static styles = [
        PlatformModal.styles,
        buttonStyles,
        css`
            :host .fullscreen-btn {
                display: none !important;
            }
            .preview-wrap {
                display: flex;
                flex-direction: column;
                gap: var(--space-3, 12px);
                min-height: 200px;
                max-height: min(60vh, 520px);
            }
            .preview-meta {
                font-size: var(--text-sm, 14px);
                color: var(--text-tertiary, rgba(255, 255, 255, 0.45));
            }
            .preview-warnings {
                font-size: var(--text-sm, 14px);
                color: var(--warning, #f59e0b);
                white-space: pre-wrap;
            }
            .preview-note {
                font-size: var(--text-sm, 14px);
                color: var(--text-secondary, rgba(255, 255, 255, 0.65));
            }
            textarea.preview-text {
                flex: 1;
                min-height: 160px;
                width: 100%;
                box-sizing: border-box;
                padding: var(--space-3, 12px);
                border-radius: var(--radius-lg, 12px);
                border: 1px solid var(--crm-stroke, rgba(255, 255, 255, 0.12));
                background: var(--crm-surface-muted, rgba(0, 0, 0, 0.25));
                color: var(--text-primary, #fff);
                font-family: var(--font-mono, ui-monospace, monospace);
                font-size: var(--text-sm, 13px);
                line-height: 1.45;
                resize: vertical;
            }
            .preview-loading,
            .preview-error {
                padding: var(--space-4, 16px);
                color: var(--text-secondary, rgba(255, 255, 255, 0.65));
            }
            .preview-error {
                color: var(--error, #f43f5e);
            }
        `,
    ];

    static properties = {
        ...PlatformModal.properties,
        apiBaseUrl: { type: String, attribute: 'api-base-url' },
        fileId: { type: String, attribute: 'file-id' },
        modalHeading: { type: String, attribute: 'modal-heading' },
        _loading: { type: Boolean, state: true },
        _error: { type: String, state: true },
        _truncated: { type: Boolean, state: true },
        _previewNote: { type: String, state: true },
        _warnings: { type: Array, state: true },
        _editedText: { type: String, state: true },
    };

    constructor() {
        super();
        this.modalHeading = '';
        this.apiBaseUrl = '';
        this.fileId = '';
        this._loading = false;
        this._error = '';
        this._truncated = false;
        this._previewNote = '';
        this._warnings = [];
        this._editedText = '';
        this._initialLoadedText = '';
        this.size = 'lg';
    }

    _t(key) {
        return (this.t(`file_preview_modal.${key}`, {}, I18nNs.PLATFORM) || `file_preview_modal.${key}`, {}, I18nNs.PLATFORM);
    }

    _resolveBaseUrl() {
        const explicit = (this.apiBaseUrl || '').trim();
        if (explicit) {
            return explicit.replace(/\/$/, '');
        }
        const crm = null;  /* CRM functionality moved to dispatch in CRM-specific components */
        if (crm && typeof crm.baseUrl === 'string' && crm.baseUrl.trim()) {
            return crm.baseUrl.replace(/\/$/, '');
        }
        throw new Error('file-text-preview-modal: задайте api-base-url или зарегистрируйте crmApi');
    }

    async _loadPreview() {
        const fid = (this.fileId || '').trim();
        if (!fid) {
            this._error = this._t('error_no_file');
            return;
        }
        this._loading = true;
        this._error = '';
        this._editedText = '';
        this._initialLoadedText = '';
        this._warnings = [];
        this._previewNote = '';
        this._truncated = false;
        try {
            const client = new BaseService(this._resolveBaseUrl());
            const data = await client.get(`/files/${encodeURIComponent(fid)}/preview`);
            if (!data || typeof data !== 'object') {
                throw new Error(this._t('error_bad_response'));
            }
            const text = typeof data.text === 'string' ? data.text : '';
            this._editedText = text;
            this._initialLoadedText = text;
            this._truncated = Boolean(data.truncated);
            this._previewNote = typeof data.preview_note === 'string' ? data.preview_note : '';
            this._warnings = Array.isArray(data.warnings) ? data.warnings : [];
        } catch (e) {
            const msg = e instanceof Error ? e.message : String(e);
            this._error = msg;
        } finally {
            this._loading = false;
        }
    }

    updated(changed) {
        super.updated?.(changed);
        if (changed.has('open') && this.open) {
            this._loadPreview();
        }
        if (changed.has('fileId') && this.open && this.fileId && !changed.has('open')) {
            this._loadPreview();
        }
    }

    renderHeader() {
        const h = (this.modalHeading || '').trim();
        return h || this._t('title');
    }

    renderBody() {
        if (this._loading) {
            return html`<div class="preview-loading">${this._t('loading')}</div>`;
        }
        if (this._error) {
            return html`<div class="preview-error">${this._error}</div>`;
        }
        return html`
            <div class="preview-wrap">
                ${this._truncated ? html`<div class="preview-meta">${this._t('truncated_hint')}</div>` : null}
                ${this._previewNote ? html`<div class="preview-note">${this._previewNote}</div>` : null}
                ${this._warnings.length
                    ? html`<div class="preview-warnings">${this._warnings.join('\n')}</div>`
                    : null}
                <textarea
                    class="preview-text"
                    .value=${this._editedText}
                    @input=${(e) => {
                        this._editedText = e.target.value;
                    }}
                ></textarea>
            </div>
        `;
    }

    renderFooter() {
        if (this._loading) {
            return html`
                <platform-button variant="secondary" @click=${() => this.close()}>
                    ${this._t('cancel')}
                </platform-button>
            `;
        }
        if (this._error) {
            return html`
                <platform-button variant="secondary" @click=${() => this.close()}>
                    ${this._t('cancel')}
                </platform-button>
            `;
        }
        return html`
            <platform-button variant="secondary" @click=${() => this._onCancel()}>
                ${this._t('cancel')}
            </platform-button>
            <platform-button variant="primary" @click=${() => this._onConfirm()}>
                ${this._t('confirm')}
            </platform-button>
        `;
    }

    _onConfirm() {
        const fid = (this.fileId || '').trim();
        if (!fid) {
            return;
        }
        this.emit('file-text-preview-confirm', {
            fileId: fid,
            text: this._editedText,
            initialText: this._initialLoadedText,
            truncated: this._truncated,
        });
        this.close();
    }

    _onCancel() {
        this.emit('file-text-preview-cancel', { fileId: this.fileId });
        this.close();
    }
}

customElements.define('file-text-preview-modal', FileTextPreviewModal);
