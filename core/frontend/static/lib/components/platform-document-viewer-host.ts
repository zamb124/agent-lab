/**
 * DocumentViewerHost — единая surface для viewer handlers (OnlyOffice, image, media, text, binary, viz, data_table).
 *
 * Принимает `openConfig` из `GET …/editor-config` (DocumentOpenConfigResponse):
 *   handler + typed payload + capabilities.
 *
 * OnlyOffice → platform-onlyoffice-host (Document Server embed).
 * Остальные handlers → нативные Lit viewers без iframe.
 */

import { html, css, nothing } from 'lit';
import type { CSSResultGroup, PropertyDeclarations, PropertyValues, TemplateResult } from '../lit-shim.js';
import { isPlainRecord } from '../events/payload.js';
import { PlatformElement } from '../platform-element/index.js';
import './platform-onlyoffice-host.js';
import './platform-document-text-viewer.js';
import './platform-document-image-viewer.js';
import './platform-document-media-viewer.js';
import './platform-document-binary-viewer.js';
import './platform-viz-host.js';
import './platform-data-table-host.js';

interface DocumentOpenConfig extends Record<string, unknown> {
    handler?: string;
    original_name?: string;
    content_type?: string;
    file_id?: string;
}

type HandlerPayload = Record<string, unknown>;

function textOrEmpty(value: unknown): string {
    return typeof value === 'string' ? value : '';
}

function firstText(primary: unknown, secondary: unknown): string {
    if (typeof primary === 'string' && primary.length > 0) return primary;
    return textOrEmpty(secondary);
}

function byteCount(value: unknown): number {
    return typeof value === 'number' && Number.isFinite(value) ? value : 0;
}

function handlerPayload(openConfig: DocumentOpenConfig | null | undefined): HandlerPayload | null {
    if (!openConfig || typeof openConfig !== 'object') {
        return null;
    }
    const handler = openConfig.handler;
    if (typeof handler !== 'string' || handler.length === 0) {
        return null;
    }
    const payload = openConfig[handler];
    if (!isPlainRecord(payload)) {
        return null;
    }
    return payload;
}

export class PlatformDocumentViewerHost extends PlatformElement {
    static override properties: PropertyDeclarations = {
        openConfig: { type: Object, attribute: false },
        fileId: { type: String, attribute: 'file-id' },
        viewMode: { type: String, attribute: 'view-mode' },
        suspended: { type: Boolean, reflect: true },
    };
    declare openConfig: DocumentOpenConfig | null;
    declare fileId: string;
    declare viewMode: string;
    declare suspended: boolean;

    static override styles: CSSResultGroup = [
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
        this.fileId = '';
        this.viewMode = '';
        this.suspended = false;
    }

    _textViewMode(payload: HandlerPayload): string {
        if (typeof this.viewMode === 'string' && this.viewMode.length > 0) {
            return this.viewMode;
        }
        if (payload && typeof payload.default_view_mode === 'string' && payload.default_view_mode.length > 0) {
            return payload.default_view_mode;
        }
        return 'source';
    }

    _textPresentation(payload: HandlerPayload): string {
        if (payload && typeof payload.presentation === 'string' && payload.presentation.length > 0) {
            return payload.presentation;
        }
        return 'code';
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

    _onEditorError(event: CustomEvent<unknown>): void {
        this.emit('editor-error', isPlainRecord(event.detail) ? event.detail : {});
    }

    _onDocumentState(event: CustomEvent<unknown>): void {
        this.emit('document-state', isPlainRecord(event.detail) ? event.detail : {});
    }

    _renderNativeViewer(): TemplateResult | typeof nothing {
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
                    stream-url=${textOrEmpty(payload.stream_url)}
                    save-url=${textOrEmpty(payload.save_url)}
                    original-name=${textOrEmpty(openConfig.original_name)}
                    content-type=${firstText(payload.content_type, openConfig.content_type)}
                    presentation=${this._textPresentation(payload)}
                    view-mode=${this._textViewMode(payload)}
                    ?edit-mode=${payload.edit_mode === true}
                    @editor-error=${this._onEditorError}
                    @document-state=${this._onDocumentState}
                ></platform-document-text-viewer>
            `;
        }
        if (openConfig.handler === 'image') {
            return html`
                <platform-document-image-viewer
                    stream-url=${textOrEmpty(payload.stream_url)}
                    original-name=${textOrEmpty(openConfig.original_name)}
                ></platform-document-image-viewer>
            `;
        }
        if (openConfig.handler === 'media') {
            return html`
                <platform-document-media-viewer
                    stream-url=${textOrEmpty(payload.stream_url)}
                    kind=${payload.kind || 'audio'}
                    original-name=${textOrEmpty(openConfig.original_name)}
                ></platform-document-media-viewer>
            `;
        }
        if (openConfig.handler === 'binary') {
            return html`
                <platform-document-binary-viewer
                    download-url=${textOrEmpty(payload.download_url)}
                    original-name=${textOrEmpty(openConfig.original_name)}
                    content-type=${firstText(payload.content_type, openConfig.content_type)}
                    file-size=${byteCount(payload.file_size)}
                ></platform-document-binary-viewer>
            `;
        }
        if (openConfig.handler === 'viz') {
            return html`
                <platform-viz-host
                    .openConfig=${openConfig}
                    .fileId=${textOrEmpty(openConfig.file_id)}
                    ?suspended=${this.suspended}
                    @editor-error=${this._onEditorError}
                    @document-state=${this._onDocumentState}
                ></platform-viz-host>
            `;
        }
        if (openConfig.handler === 'data_table') {
            return html`
                <platform-data-table-host
                    .openConfig=${openConfig}
                    .fileId=${textOrEmpty(openConfig.file_id)}
                    ?suspended=${this.suspended}
                    @editor-error=${this._onEditorError}
                    @document-state=${this._onDocumentState}
                ></platform-data-table-host>
            `;
        }
        return nothing;
    }

    override render(): TemplateResult | typeof nothing {
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
                    .fileId=${this.fileId}
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
