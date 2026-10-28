import { html, css, nothing } from 'lit';
import type { CSSResultGroup, PropertyDeclarations, PropertyValues, TemplateResult } from '../lit-shim.js';
import { PlatformModal } from './glass-modal.js';
import { registerModalKind } from '../utils/modal-registry.js';
import { FILES_EVENTS } from '../events/reducers/files.js';
import type { PlatformEvent } from '../events/contract.js';
import { isPlainRecord } from '../events/payload.js';
import { resolveFileIconKey } from '../utils/file-icons.js';
import './platform-icon.js';
import './platform-document-viewer-host.js';

const SYNC_TIMEOUT_MS = 20000;

function _asNonEmptyString(value: unknown): string {
    return typeof value === 'string' && value.length > 0 ? value : '';
}

export class PlatformFileViewerModal extends PlatformModal {
    static modalKind = 'platform.file_viewer';
    static i18nNamespace = 'platform';

    static override properties: PropertyDeclarations = {
        ...PlatformModal.properties,
        fileId: { type: String, attribute: 'file-id' },
        file: { type: Object },
        config: { type: Object },
        minimized: { type: Boolean, reflect: true },
        _dirty: { state: true },
        _syncing: { state: true },
        _error: { state: true },
        _closeSyncComplete: { state: true },
        _headerDragging: { state: true },
        _viewMode: { state: true },
        _viewModeFileId: { state: true },
    };
    declare fileId: string;
    declare file: Record<string, unknown> | null;
    declare config: Record<string, unknown> | null;
    declare minimized: boolean;
    declare _dirty: boolean | null;
    declare _syncing: boolean;
    declare _error: string;
    declare _closeSyncComplete: boolean;
    declare _headerDragging: boolean;
    declare _viewMode: string;
    declare _viewModeFileId: string;

    private _headerDragState: { dx: number; dy: number; width: number; height: number } | null;
    private _boundHeaderMouseMove: (e: MouseEvent) => void;
    private _boundHeaderMouseUp: () => void;

    static override styles: CSSResultGroup = [
        ...(Array.isArray(PlatformModal.styles) ? PlatformModal.styles : [PlatformModal.styles]),
        css`
            :host([open]),
            :host([closing]) {
                pointer-events: none;
            }

            :host([minimized][open]),
            :host([minimized][closing]) {
                inset: auto;
                width: 0;
                height: 0;
                overflow: visible;
            }

            .modal-overlay {
                padding: 0;
                pointer-events: none;
            }

            :host([minimized]) .modal-overlay {
                position: fixed;
                inset: auto;
                width: 0;
                height: 0;
                overflow: visible;
                opacity: 1;
                visibility: visible;
                animation: none;
            }

            .modal-scrim {
                background: transparent;
                backdrop-filter: none;
                -webkit-backdrop-filter: none;
                pointer-events: none;
            }

            :host([minimized]) .modal-scrim {
                display: none;
            }

            .modal {
                width: 100vw !important;
                max-width: 100vw !important;
                height: 100dvh !important;
                max-height: 100dvh !important;
                border: 0;
                border-radius: 0;
                background: transparent;
                box-shadow: none;
                backdrop-filter: none;
                -webkit-backdrop-filter: none;
                pointer-events: none;
                overflow: visible;
                --modal-content-inset: 0;
                --modal-content-radius: 0;
            }

            .modal::before,
            .modal::after {
                display: none;
            }

            .modal-header {
                position: fixed;
                top: var(--file-viewer-header-top, max(12px, env(safe-area-inset-top, 0px)));
                right: var(--file-viewer-header-right, max(12px, env(safe-area-inset-right, 0px)));
                left: var(--file-viewer-header-left, auto);
                align-self: auto;
                box-sizing: border-box;
                width: fit-content;
                max-width: calc(100vw - 24px);
                min-width: 0;
                min-height: 42px;
                padding: 6px;
                border: 1px solid rgba(255, 255, 255, 0.16);
                border-radius: 999px;
                background: rgba(18, 24, 38, 0.58);
                color: rgba(255, 255, 255, 0.94);
                box-shadow: 0 12px 34px rgba(15, 23, 42, 0.24);
                backdrop-filter: blur(22px) saturate(140%);
                -webkit-backdrop-filter: blur(22px) saturate(140%);
                pointer-events: auto;
                z-index: 5;
                flex-wrap: wrap;
                overflow: hidden;
            }

            :host([data-header-dragging]) .modal-header {
                cursor: grabbing;
            }

            .modal-title {
                flex: 0 1 auto;
                min-width: 0;
                max-width: 14rem;
                font-size: 13px;
                font-weight: 600;
                letter-spacing: 0;
            }

            .file-title {
                min-width: 0;
                display: flex;
                align-items: center;
                gap: 8px;
            }

            .drag-dots {
                width: 13px;
                height: 18px;
                flex: 0 0 auto;
                opacity: 0.52;
                background-image:
                    radial-gradient(circle, currentColor 1.3px, transparent 1.5px),
                    radial-gradient(circle, currentColor 1.3px, transparent 1.5px);
                background-size: 6px 6px;
                background-position: 0 0, 6px 0;
            }

            .file-title platform-icon {
                flex: 0 0 auto;
                opacity: 0.92;
            }

            .file-name {
                min-width: 0;
                overflow: hidden;
                text-overflow: ellipsis;
                white-space: nowrap;
            }

            .header-buttons {
                flex: 1 1 auto;
                min-width: 0;
                flex-wrap: wrap;
                justify-content: flex-end;
                gap: 4px;
            }

            .header-type-actions {
                display: inline-flex;
                flex-wrap: wrap;
                align-items: center;
                gap: 4px;
                min-width: 0;
                max-width: 100%;
                margin-right: 2px;
                padding-right: 8px;
                border-right: 1px solid rgba(255, 255, 255, 0.18);
            }

            .header-btn {
                width: 30px;
                height: 30px;
                color: rgba(255, 255, 255, 0.78);
                background: rgba(255, 255, 255, 0.08);
            }

            .header-btn.header-btn-label {
                width: auto;
                min-width: 30px;
                padding: 0 10px;
                font-size: 11px;
                font-weight: 600;
                letter-spacing: 0.01em;
            }

            .header-btn.header-btn-active {
                color: #fff;
                background: rgba(255, 255, 255, 0.22);
            }

            .header-btn:hover {
                color: #fff;
                background: rgba(255, 255, 255, 0.16);
            }

            .header-btn:disabled {
                opacity: 0.5;
                cursor: default;
                transform: none;
            }

            .fullscreen-btn,
            .modal-actions {
                display: none;
            }

            .modal-content {
                margin: 0;
                padding: 0;
                border-radius: 0;
                overflow: hidden;
                pointer-events: auto;
            }

            .viewer-shell {
                position: fixed;
                inset: 0;
                display: flex;
                min-width: 0;
                min-height: 0;
                background: var(--documents-stage-ambient, var(--bg-primary));
                overflow: hidden;
                z-index: 1;
                padding: 0.5rem;
                box-sizing: border-box;
            }

            .viewer-shell-data-table {
                padding-top: 3.25rem;
            }

            platform-onlyoffice-host,
            platform-document-viewer-host {
                flex: 1 1 auto;
                width: 100%;
                min-width: 0;
                min-height: 0;
                border-radius: var(--documents-stage-host-radius, 12px);
                overflow: hidden;
                box-shadow: var(--documents-stage-host-shadow, none);
                background: var(--documents-stage-host-bg, #f0f4f9);
            }

            .viewer-status,
            .viewer-error,
            .sync-state {
                position: fixed;
                left: 50%;
                z-index: 6;
                transform: translateX(-50%);
                border: 1px solid rgba(255, 255, 255, 0.18);
                border-radius: 999px;
                background: rgba(18, 24, 38, 0.72);
                color: rgba(255, 255, 255, 0.92);
                box-shadow: 0 14px 38px rgba(15, 23, 42, 0.26);
                backdrop-filter: blur(18px) saturate(140%);
                -webkit-backdrop-filter: blur(18px) saturate(140%);
                pointer-events: none;
            }

            .viewer-status,
            .sync-state {
                bottom: max(18px, env(safe-area-inset-bottom, 0px));
                padding: 8px 14px;
                font-size: 13px;
            }

            .viewer-error {
                bottom: max(18px, env(safe-area-inset-bottom, 0px));
                max-width: min(640px, calc(100vw - 32px));
                padding: 10px 14px;
                font-size: 13px;
            }

            :host([minimized]) .modal {
                position: fixed;
                left: auto !important;
                top: auto !important;
                right: max(16px, env(safe-area-inset-right, 0px));
                bottom: max(16px, env(safe-area-inset-bottom, 0px));
                width: min(320px, calc(100vw - 32px)) !important;
                max-width: min(320px, calc(100vw - 32px)) !important;
                height: 56px !important;
                max-height: 56px !important;
                border: 1px solid rgba(255, 255, 255, 0.16);
                border-radius: 16px;
                background: rgba(18, 24, 38, 0.72);
                box-shadow: 0 16px 44px rgba(15, 23, 42, 0.28);
                backdrop-filter: blur(22px) saturate(140%);
                -webkit-backdrop-filter: blur(22px) saturate(140%);
                pointer-events: auto;
                transform: none !important;
                overflow: hidden;
            }

            :host([minimized]) .modal-header {
                position: relative;
                inset: auto;
                width: auto;
                min-height: 0;
                height: 100%;
                border: 0;
                border-radius: 0;
                background: transparent;
                box-shadow: none;
                backdrop-filter: none;
                -webkit-backdrop-filter: none;
            }

            :host([minimized]) .modal-title {
                font-size: 12px;
            }

            :host([minimized]) .modal-content {
                display: none;
                position: fixed;
                width: 0;
                height: 0;
                opacity: 0;
                overflow: hidden;
                pointer-events: none;
            }

            :host([minimized]) .viewer-shell,
            :host([minimized]) .viewer-status,
            :host([minimized]) .viewer-error,
            :host([minimized]) .sync-state {
                width: 1px;
                height: 1px;
                opacity: 0;
                overflow: hidden;
                pointer-events: none;
            }

            :host-context([data-theme="light"]) .modal-header,
            :host-context([data-theme="light"]):host([minimized]) .modal {
                background: rgba(255, 255, 255, 0.72);
                color: rgba(15, 23, 42, 0.94);
                border-color: rgba(15, 23, 42, 0.12);
                box-shadow: 0 14px 36px rgba(15, 23, 42, 0.16);
            }

            :host-context([data-theme="light"]) .header-type-actions {
                border-right-color: rgba(15, 23, 42, 0.14);
            }

            :host-context([data-theme="light"]) .header-btn {
                color: rgba(15, 23, 42, 0.68);
                background: rgba(15, 23, 42, 0.06);
            }

            :host-context([data-theme="light"]) .header-btn.header-btn-active {
                color: rgba(15, 23, 42, 0.95);
                background: rgba(15, 23, 42, 0.14);
            }

            :host-context([data-theme="light"]) .header-btn:hover {
                color: rgba(15, 23, 42, 0.95);
                background: rgba(15, 23, 42, 0.12);
            }

            @media (max-width: 640px) {
                .modal-header {
                    width: calc(100vw - 16px);
                    max-width: calc(100vw - 16px);
                    top: max(8px, env(safe-area-inset-top, 0px));
                    right: max(8px, env(safe-area-inset-right, 0px));
                }

                .file-name {
                    max-width: 12rem;
                }
            }
        `,
    ];

    constructor() {
        super();
        this.size = 'full';
        this.fileId = '';
        this.file = null;
        this.config = null;
        this.minimized = false;
        this._dirty = null;
        this._syncing = false;
        this._error = '';
        this._closeSyncComplete = false;
        this._headerDragging = false;
        this._headerDragState = null;
        this._viewMode = '';
        this._viewModeFileId = '';
        this._boundHeaderMouseMove = this._handleHeaderMouseMove.bind(this);
        this._boundHeaderMouseUp = this._handleHeaderMouseUp.bind(this);
    }

    override willUpdate(changed: PropertyValues<this>): void {
        super.willUpdate?.(changed);
        if (changed.has('config') || changed.has('fileId') || changed.has('file')) {
            this._syncViewModeFromConfig();
        }
    }

    _isDataTable(): boolean {
        const config = this.config;
        return Boolean(config && config.handler === 'data_table' && config.data_table);
    }

    _textPresentation(): string {
        const config = this.config;
        const text = config !== null && isPlainRecord(config.text) ? config.text : null;
        if (!config || config.handler !== 'text' || !text) {
            return '';
        }
        const presentation = text.presentation;
        if (presentation === 'html' || presentation === 'markdown') {
            return presentation;
        }
        return '';
    }

    _defaultViewModeFromConfig(): 'preview' | 'source' {
        const config = this.config;
        const text = config !== null && isPlainRecord(config.text) ? config.text : null;
        if (!text) {
            return 'source';
        }
        const mode = text.default_view_mode;
        if (mode === 'preview' || mode === 'source') {
            return mode;
        }
        return 'source';
    }

    _syncViewModeFromConfig(): void {
        const fileId = this._resolvedFileId();
        const presentation = this._textPresentation();
        if (!presentation) {
            this._viewMode = '';
            this._viewModeFileId = fileId;
            return;
        }
        if (fileId !== this._viewModeFileId || this._viewMode.length === 0) {
            this._viewMode = this._defaultViewModeFromConfig();
            this._viewModeFileId = fileId;
        }
    }

    _setViewMode(mode: string): void {
        if (mode !== 'preview' && mode !== 'source') {
            throw new Error(`platform-file-viewer-modal: invalid viewMode ${mode}`);
        }
        if (!this._textPresentation()) {
            throw new Error('platform-file-viewer-modal: viewMode unavailable for this file');
        }
        this._viewMode = mode;
    }

    override disconnectedCallback(): void {
        this._endHeaderDrag();
        super.disconnectedCallback();
    }

    _resolvedFileId(): string {
        return _asNonEmptyString(this.fileId)
            || _asNonEmptyString(this.file?.file_id)
            || _asNonEmptyString(this.file?.id);
    }

    _fileName(): string {
        const file = this.file;
        return _asNonEmptyString(file === null ? undefined : file.original_name)
            || _asNonEmptyString(file === null ? undefined : file.filename)
            || _asNonEmptyString(file === null ? undefined : file.name)
            || _asNonEmptyString(this.title)
            || 'file';
    }

    _toggleMinimized(): void {
        if (this._syncing) return;
        const next = !this.minimized;
        this.minimized = next;
        if (!next) {
            this._position = { x: null, y: null };
        }
    }

    _eventStartedOnInteractiveNode(event: Event): boolean {
        for (const node of event.composedPath()) {
            if (node === this.shadowRoot || node === this) {
                break;
            }
            if (node instanceof HTMLElement) {
                const tag = node.tagName;
                if (
                    tag === 'BUTTON'
                    || tag === 'INPUT'
                    || tag === 'TEXTAREA'
                    || tag === 'SELECT'
                    || tag === 'A'
                    || node.getAttribute('role') === 'button'
                ) {
                    return true;
                }
            }
        }
        return false;
    }

    override _handleMouseDown(event: MouseEvent): void {
        if (this.minimized) {
            super._handleMouseDown(event);
            return;
        }
        if (event.button !== 0 || this._syncing || this._eventStartedOnInteractiveNode(event)) {
            return;
        }
        const header = this.shadowRoot?.querySelector('.modal-header');
        if (!(header instanceof HTMLElement)) {
            return;
        }
        const rect = header.getBoundingClientRect();
        this._headerDragState = {
            dx: event.clientX - rect.left,
            dy: event.clientY - rect.top,
            width: rect.width,
            height: rect.height,
        };
        this._headerDragging = true;
        this.toggleAttribute('data-header-dragging', true);
        document.addEventListener('mousemove', this._boundHeaderMouseMove);
        document.addEventListener('mouseup', this._boundHeaderMouseUp);
        event.preventDefault();
    }

    _handleHeaderMouseMove(event: MouseEvent): void {
        if (!this._headerDragging || !this._headerDragState) {
            return;
        }
        const margin = 8;
        const maxX = Math.max(margin, window.innerWidth - this._headerDragState.width - margin);
        const maxY = Math.max(margin, window.innerHeight - this._headerDragState.height - margin);
        const left = Math.min(maxX, Math.max(margin, event.clientX - this._headerDragState.dx));
        const top = Math.min(maxY, Math.max(margin, event.clientY - this._headerDragState.dy));
        this.style.setProperty('--file-viewer-header-left', `${Math.round(left)}px`);
        this.style.setProperty('--file-viewer-header-top', `${Math.round(top)}px`);
        this.style.setProperty('--file-viewer-header-right', 'auto');
    }

    override _handleMouseMove(event: MouseEvent): void {
        if (this.minimized && this._isDragging) {
            const modal = this.shadowRoot?.querySelector('.modal');
            const rect = modal instanceof HTMLElement ? modal.getBoundingClientRect() : null;
            const halfW = rect && rect.width > 0 ? rect.width / 2 : 160;
            const halfH = rect && rect.height > 0 ? rect.height / 2 : 28;
            const margin = 8;
            const minX = halfW + margin;
            const maxX = Math.max(minX, window.innerWidth - halfW - margin);
            const minY = halfH + margin;
            const maxY = Math.max(minY, window.innerHeight - halfH - margin);
            const nextX = event.clientX - this._dragStart.x;
            const nextY = event.clientY - this._dragStart.y;
            this._position = {
                x: Math.min(maxX, Math.max(minX, nextX)),
                y: Math.min(maxY, Math.max(minY, nextY)),
            };
            this.requestUpdate();
            return;
        }
        super._handleMouseMove(event);
    }

    _handleHeaderMouseUp(): void {
        this._endHeaderDrag();
    }

    _endHeaderDrag(): void {
        if (!this._headerDragging && !this._headerDragState) {
            return;
        }
        this._headerDragging = false;
        this._headerDragState = null;
        this.toggleAttribute('data-header-dragging', false);
        document.removeEventListener('mousemove', this._boundHeaderMouseMove);
        document.removeEventListener('mouseup', this._boundHeaderMouseUp);
    }

    _onEditorError(event: CustomEvent<{ detail?: unknown; code?: unknown }>): void {
        const detail = event.detail;
        const message = detail === undefined || detail === null
            ? this.t('file_viewer.close_failed')
            : (_asNonEmptyString(detail.detail) || _asNonEmptyString(detail.code) || this.t('file_viewer.close_failed'));
        this._error = message;
        this.toast('file_viewer.open_failed', { type: 'error', namespace: 'platform', vars: { message } });
    }

    _onDocumentState(event: CustomEvent<{ dirty?: unknown }>): void {
        const detail = event.detail;
        this._dirty = detail !== undefined && detail !== null && Boolean(detail.dirty);
    }

    _requestEditorSync({ close, settleMs }: { close?: boolean; settleMs?: number }): Promise<unknown> {
        const fileId = this._resolvedFileId();
        if (!fileId) {
            return Promise.reject(new Error('file_id required'));
        }
        const correlation = `file_viewer_${Date.now()}_${Math.random().toString(36).slice(2)}`;
        return new Promise((resolve, reject) => {
            let doneUnsub: (() => void) | null = null;
            let failUnsub: (() => void) | null = null;
            let timer: number | null = null;
            const cleanup = () => {
                if (doneUnsub) doneUnsub();
                if (failUnsub) failUnsub();
                if (timer !== null) window.clearTimeout(timer);
            };
            doneUnsub = this.bus.subscribeType(FILES_EVENTS.EDITOR_SYNC_COMPLETED, (event: PlatformEvent) => {
                if (event.meta?.correlation_id !== correlation) return;
                cleanup();
                const payload = event.payload;
                const result = isPlainRecord(payload) ? payload.result : null;
                resolve(result === undefined || result === null ? null : result);
            });
            failUnsub = this.bus.subscribeType(FILES_EVENTS.EDITOR_SYNC_FAILED, (event: PlatformEvent) => {
                if (event.meta?.correlation_id !== correlation) return;
                cleanup();
                const message = isPlainRecord(event.payload) ? event.payload.message : undefined;
                reject(new Error(typeof message === 'string' && message.length > 0 ? message : this.t('file_viewer.close_failed')));
            });
            timer = window.setTimeout(() => {
                cleanup();
                reject(new Error(this.t('file_viewer.close_failed')));
            }, SYNC_TIMEOUT_MS);
            this.dispatch(
                FILES_EVENTS.EDITOR_SYNC_REQUESTED,
                {
                    file_id: fileId,
                    close: close === true,
                    settle_ms: typeof settleMs === 'number' ? settleMs : 900,
                    dirty: this._dirty,
                },
                { source: 'local', correlation_id: correlation },
            );
        });
    }

    async _syncBeforeClose(): Promise<void> {
        if (this._closeSyncComplete || !this.config) return;
        const capabilities = isPlainRecord(this.config.capabilities) ? this.config.capabilities : null;
        if (!capabilities || capabilities.sync_on_close !== true) {
            this._closeSyncComplete = true;
            return;
        }
        this._syncing = true;
        this._error = '';
        try {
            await this._requestEditorSync({ close: true, settleMs: 900 });
            this._closeSyncComplete = true;
        } finally {
            this._syncing = false;
        }
    }

    override close(): void {
        if (this._syncing) return;
        void (async () => {
            try {
                await this._syncBeforeClose();
                super.close();
            } catch (err) {
                this._error = err instanceof Error ? err.message : String(err);
                this.toast('file_viewer.close_failed', { type: 'error', namespace: 'platform', duration: 4500 });
            }
        })();
    }

    override async requestPlatformClose(): Promise<void> {
        if (!this._closeSyncComplete && this.config) {
            try {
                await this._syncBeforeClose();
            } catch (err) {
                this._error = err instanceof Error ? err.message : String(err);
            }
        }
        return super.requestPlatformClose();
    }

    override _getModalStyle(): string {
        if (this.minimized && this._position.x !== null && this._position.y !== null) {
            return `position: fixed !important; left: ${this._position.x}px !important; top: ${this._position.y}px !important; right: auto !important; bottom: auto !important; z-index: 2; transform: translate(-50%, -50%) scale(1) !important;`;
        }
        return super._getModalStyle();
    }

    override renderHeader(): TemplateResult {
        const name = this._fileName();
        const mimeType = _asNonEmptyString(this.file?.content_type) || _asNonEmptyString(this.file?.mime_type);
        return html`
            <span class="file-title">
                <span class="drag-dots" aria-hidden="true"></span>
                <platform-icon file-icon name=${resolveFileIconKey(name, mimeType)} size="18"></platform-icon>
                <span class="file-name">${name}</span>
            </span>
        `;
    }

    _resolveDownloadUrl(): string {
        const config = this.config;
        if (!config || typeof config !== 'object') {
            return '';
        }
        if (typeof config.download_url === 'string' && config.download_url.length > 0) {
            return config.download_url;
        }
        const binary = isPlainRecord(config.binary) ? config.binary : null;
        if (binary && typeof binary.download_url === 'string' && binary.download_url.length > 0) {
            return binary.download_url;
        }
        return '';
    }

    _onDownloadClick(): void {
        const downloadUrl = this._resolveDownloadUrl();
        if (downloadUrl.length === 0) {
            return;
        }
        window.open(downloadUrl, '_blank', 'noopener,noreferrer');
    }

    _renderTypeHeaderActions(): unknown {
        if (this._isDataTable()) {
            return nothing;
        }
        const presentation = this._textPresentation();
        if (!presentation) {
            return nothing;
        }
        const viewMode = this._viewMode.length > 0 ? this._viewMode : this._defaultViewModeFromConfig();
        const previewLabel = this.t('file_viewer.view_preview');
        const rawLabel = this.t('file_viewer.view_raw');
        return html`
            <div class="header-type-actions" role="group" aria-label=${this.t('file_viewer.view_mode_group')}>
                <button
                    type="button"
                    class="header-btn header-btn-label ${viewMode === 'preview' ? 'header-btn-active' : ''}"
                    title=${previewLabel}
                    aria-label=${previewLabel}
                    aria-pressed=${viewMode === 'preview' ? 'true' : 'false'}
                    ?disabled=${this._syncing}
                    @click=${() => this._setViewMode('preview')}
                >${previewLabel}</button>
                <button
                    type="button"
                    class="header-btn header-btn-label ${viewMode === 'source' ? 'header-btn-active' : ''}"
                    title=${rawLabel}
                    aria-label=${rawLabel}
                    aria-pressed=${viewMode === 'source' ? 'true' : 'false'}
                    ?disabled=${this._syncing}
                    @click=${() => this._setViewMode('source')}
                >${rawLabel}</button>
            </div>
        `;
    }

    override renderHeaderActions(): TemplateResult {
        const title = this.minimized ? this.t('file_viewer.restore') : this.t('file_viewer.minimize');
        const downloadUrl = this._resolveDownloadUrl();
        return html`
            ${this._renderTypeHeaderActions()}
            ${downloadUrl.length > 0 && !this._isDataTable() ? html`
                <button
                    type="button"
                    class="header-btn"
                    title=${this.t('file_viewer.download')}
                    aria-label=${this.t('file_viewer.download')}
                    ?disabled=${this._syncing}
                    @click=${this._onDownloadClick}
                >
                    <platform-icon name="download" size="16"></platform-icon>
                </button>
            ` : nothing}
            <button
                type="button"
                class="header-btn"
                title=${title}
                aria-label=${title}
                ?disabled=${this._syncing}
                @click=${this._toggleMinimized}
            >
                <platform-icon name=${this.minimized ? 'fullscreen' : 'minimize'} size="16"></platform-icon>
            </button>
        `;
    }

    override renderBody(): TemplateResult {
        const fileId = this._resolvedFileId();
        const presentation = this._textPresentation();
        const viewMode = presentation
            ? (this._viewMode.length > 0 ? this._viewMode : this._defaultViewModeFromConfig())
            : '';
        return html`
            <div class="viewer-shell ${this._isDataTable() ? 'viewer-shell-data-table' : ''}">
                ${this.config
                    ? html`
                        <platform-document-viewer-host
                            .fileId=${fileId}
                            .openConfig=${this.config}
                            .viewMode=${viewMode}
                            .suspended=${this.minimized}
                            @editor-error=${this._onEditorError}
                            @document-state=${this._onDocumentState}
                        >
                            <span slot="loading">${this.t('file_viewer.loading')}</span>
                        </platform-document-viewer-host>
                    `
                    : html`<div class="viewer-status">${this.t('file_viewer.loading')}</div>`}
                ${this._syncing ? html`<div class="sync-state">${this.t('file_viewer.syncing')}</div>` : nothing}
                ${this._error ? html`<div class="viewer-error">${this._error}</div>` : nothing}
            </div>
        `;
    }
}

customElements.define('platform-file-viewer-modal', PlatformFileViewerModal);
registerModalKind(PlatformFileViewerModal.modalKind, 'platform-file-viewer-modal');
