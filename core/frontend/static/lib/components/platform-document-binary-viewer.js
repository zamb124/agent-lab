/**
 * platform-document-binary-viewer — Lit viewer для binary handler (без iframe).
 */
import { html, css } from 'lit';
import { PlatformElement } from '../platform-element/index.js';
import { formatFileSize } from '../utils/format-file-size.js';

export class PlatformDocumentBinaryViewer extends PlatformElement {
    static i18nNamespace = 'platform';

    static properties = {
        downloadUrl: { type: String, attribute: 'download-url' },
        originalName: { type: String, attribute: 'original-name' },
        contentType: { type: String, attribute: 'content-type' },
        fileSize: { type: Number, attribute: 'file-size' },
    };

    static styles = [
        PlatformElement.styles,
        css`
            :host {
                display: flex;
                flex: 1;
                min-width: 0;
                min-height: 0;
                height: 100%;
                align-items: center;
                justify-content: center;
                background: var(--bg-secondary);
            }
            .panel {
                display: flex;
                flex-direction: column;
                align-items: center;
                gap: var(--space-3);
                padding: var(--space-6);
                border-radius: var(--radius-lg);
                border: 1px solid var(--glass-border-subtle);
                background: var(--glass-solid-medium);
                max-width: min(480px, 92vw);
                text-align: center;
            }
            .name {
                font-size: var(--text-base);
                font-weight: var(--font-semibold);
                color: var(--text-primary);
                word-break: break-word;
            }
            .meta {
                color: var(--text-secondary);
                font-size: var(--text-sm);
            }
            .download-link {
                display: inline-flex;
                align-items: center;
                justify-content: center;
                padding: var(--space-2) var(--space-4);
                border-radius: var(--radius-md);
                background: var(--accent);
                color: var(--accent-contrast, #fff);
                text-decoration: none;
                font-size: var(--text-sm);
                font-weight: var(--font-medium);
            }
            .state {
                color: var(--text-secondary);
                font-size: var(--text-sm);
            }
        `,
    ];

    constructor() {
        super();
        this.downloadUrl = '';
        this.originalName = '';
        this.contentType = '';
        this.fileSize = 0;
        this._localeSel = this.select((s) => (s.i18n && s.i18n.locale ? s.i18n.locale : 'ru'));
    }

    render() {
        const downloadUrl = this.downloadUrl;
        if (typeof downloadUrl !== 'string' || downloadUrl.length === 0) {
            return html`<div class="state">${this.t('document_viewer.missing_download_url')}</div>`;
        }
        const locale = this._localeSel.value;
        const sizeLabel = formatFileSize(this.fileSize, locale);
        const typeLabel = this.contentType || this.t('document_viewer.unknown_type');
        return html`
            <div class="panel">
                <div class="name">${this.originalName}</div>
                <div class="meta">${typeLabel} · ${sizeLabel}</div>
                <a class="download-link" href=${downloadUrl} download=${this.originalName}>
                    ${this.t('document_viewer.download')}
                </a>
            </div>
        `;
    }
}

customElements.define('platform-document-binary-viewer', PlatformDocumentBinaryViewer);
