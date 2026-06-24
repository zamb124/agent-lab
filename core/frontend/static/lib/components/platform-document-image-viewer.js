/**
 * platform-document-image-viewer — Lit viewer для image handler (без iframe).
 */
import { html, css } from 'lit';
import { PlatformElement } from '../platform-element/index.js';

export class PlatformDocumentImageViewer extends PlatformElement {
    static i18nNamespace = 'platform';

    static properties = {
        streamUrl: { type: String, attribute: 'stream-url' },
        originalName: { type: String, attribute: 'original-name' },
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
                background: #0f172a;
            }
            img {
                max-width: 100%;
                max-height: 100%;
                object-fit: contain;
            }
            .state {
                color: var(--text-secondary);
                font-size: var(--text-sm);
            }
        `,
    ];

    constructor() {
        super();
        this.streamUrl = '';
        this.originalName = '';
        this._failed = false;
    }

    _onError() {
        this._failed = true;
        this.requestUpdate();
    }

    render() {
        const streamUrl = this.streamUrl;
        if (typeof streamUrl !== 'string' || streamUrl.length === 0) {
            return html`<div class="state">${this.t('document_viewer.missing_stream_url')}</div>`;
        }
        if (this._failed) {
            return html`<div class="state">${this.t('document_viewer.load_failed', { status: 'image' })}</div>`;
        }
        return html`
            <img
                src=${streamUrl}
                alt=${this.originalName || ''}
                @error=${this._onError}
            />
        `;
    }
}

customElements.define('platform-document-image-viewer', PlatformDocumentImageViewer);
