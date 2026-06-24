/**
 * platform-document-media-viewer — Lit viewer для media handler (без iframe).
 */
import { html, css } from 'lit';
import { PlatformElement } from '../platform-element/index.js';

export class PlatformDocumentMediaViewer extends PlatformElement {
    static i18nNamespace = 'platform';

    static properties = {
        streamUrl: { type: String, attribute: 'stream-url' },
        kind: { type: String },
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
                background: #000;
            }
            video {
                width: 100%;
                height: 100%;
            }
            audio {
                width: min(640px, 92vw);
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
        this.kind = 'audio';
        this.originalName = '';
    }

    render() {
        const streamUrl = this.streamUrl;
        if (typeof streamUrl !== 'string' || streamUrl.length === 0) {
            return html`<div class="state">${this.t('document_viewer.missing_stream_url')}</div>`;
        }
        if (this.kind === 'video') {
            return html`<video controls src=${streamUrl}></video>`;
        }
        return html`<audio controls src=${streamUrl}></audio>`;
    }
}

customElements.define('platform-document-media-viewer', PlatformDocumentMediaViewer);
