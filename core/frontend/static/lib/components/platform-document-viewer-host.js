/**
 * DocumentViewerHost — единая surface для viewer handlers (OnlyOffice, image, media, text, binary).
 *
 * Принимает `openConfig` из `GET …/editor-config` (DocumentOpenConfigResponse):
 *   handler + typed payload + capabilities.
 *
 * OnlyOffice → platform-onlyoffice-host (Document Server embed).
 * Остальные handlers → нативные Lit viewers без iframe.
 */

import { html, css, nothing } from '../../assets/js/lit/lit.min.js';
import { PlatformElement } from '../platform-element/index.js';
import './platform-onlyoffice-host.js';
import './platform-document-text-viewer.js';
import './platform-document-image-viewer.js';
import './platform-document-media-viewer.js';
import './platform-document-binary-viewer.js';

function handlerPayload(openConfig) {
    if (!openConfig || typeof openConfig !== 'object') {
        return null;
    }
    const handler = openConfig.handler;
    if (typeof handler !== 'string' || handler.length === 0) {
        return null;
    }
    const payload = openConfig[handler];
    if (!payload || typeof payload !== 'object') {
        return null;
    }
    return payload;
}

export class PlatformDocumentViewerHost extends PlatformElement {
    static properties = {
        openConfig: { type: Object, attribute: false },
        bindingId: { type: String, attribute: 'binding-id' },
        suspended: { type: Boolean, reflect: true },
    };

    static styles = [
        PlatformElement.styles,
        css`
            :host {
                display: flex;
                flex-direction: column;
                flex: 1;
                align-self: stretch;
                width: 100%;
                min-width: 0;
                min-height: 0;
                height: 100%;
            }
        `,
    ];

    constructor() {
        super();
        this.openConfig = null;
        this.bindingId = '';
        this.suspended = false;
    }

    _onlyofficeHostConfig() {
        const payload = handlerPayload(this.openConfig);
        if (!payload || this.openConfig?.handler !== 'onlyoffice') {
            return null;
        }
        const documentServerUrl = payload.document_server_url;
        const token = payload.token;
        if (typeof documentServerUrl !== 'string' || documentServerUrl.length === 0) {
            return null;
        }
        if (typeof token !== 'string' || token.length === 0) {
            return null;
        }
        return {
            document_server_url: documentServerUrl,
            token,
        };
    }

    _onEditorError(event) {
        this.emit('editor-error', event.detail || {});
    }

    _onDocumentState(event) {
        this.emit('document-state', event.detail || {});
    }

    _renderNativeViewer() {
        const openConfig = this.openConfig;
        if (!openConfig) {
            return nothing;
        }
        const payload = handlerPayload(openConfig);
        if (!payload) {
            return nothing;
        }
        if (openConfig.handler === 'text') {
            return html`
                <platform-document-text-viewer
                    stream-url=${payload.stream_url || ''}
                    save-url=${payload.save_url || ''}
                    original-name=${openConfig.original_name || ''}
                    content-type=${payload.content_type || openConfig.content_type || ''}
                    ?edit-mode=${payload.edit_mode === true}
                    @editor-error=${this._onEditorError}
                    @document-state=${this._onDocumentState}
                ></platform-document-text-viewer>
            `;
        }
        if (openConfig.handler === 'image') {
            return html`
                <platform-document-image-viewer
                    stream-url=${payload.stream_url || ''}
                    original-name=${openConfig.original_name || ''}
                ></platform-document-image-viewer>
            `;
        }
        if (openConfig.handler === 'media') {
            return html`
                <platform-document-media-viewer
                    stream-url=${payload.stream_url || ''}
                    kind=${payload.kind || 'audio'}
                    original-name=${openConfig.original_name || ''}
                ></platform-document-media-viewer>
            `;
        }
        if (openConfig.handler === 'binary') {
            return html`
                <platform-document-binary-viewer
                    download-url=${payload.download_url || ''}
                    original-name=${openConfig.original_name || ''}
                    content-type=${payload.content_type || openConfig.content_type || ''}
                    file-size=${payload.file_size || 0}
                ></platform-document-binary-viewer>
            `;
        }
        return nothing;
    }

    render() {
        const openConfig = this.openConfig;
        if (!openConfig) {
            return nothing;
        }
        if (openConfig.handler === 'onlyoffice') {
            const hostConfig = this._onlyofficeHostConfig();
            if (!hostConfig) {
                return nothing;
            }
            return html`
                <platform-onlyoffice-host
                    .bindingId=${this.bindingId}
                    .config=${hostConfig}
                    .suspended=${this.suspended}
                    @editor-error=${this._onEditorError}
                    @document-state=${this._onDocumentState}
                >
                    <slot name="loading"></slot>
                </platform-onlyoffice-host>
            `;
        }
        return this._renderNativeViewer();
    }
}

customElements.define('platform-document-viewer-host', PlatformDocumentViewerHost);
