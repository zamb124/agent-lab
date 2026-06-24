import { html, css, nothing } from 'lit';
import { PlatformModal } from './glass-modal.js';
import { registerModalKind } from '../utils/modal-registry.js';
import { FILES_EVENTS } from '../events/reducers/files.js';
import { resolveFileIconKey } from '../utils/file-icons.js';
import './platform-icon.js';
import './platform-document-viewer-host.js';

const SYNC_TIMEOUT_MS = 20000;

function _asNonEmptyString(value) {
    return typeof value === 'string' && value.length > 0 ? value : '';
}

export class PlatformFileViewerModal extends PlatformModal {
    static modalKind = 'platform.file_viewer';
    static i18nNamespace = 'platform';

    static properties = {
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
    };

    static styles = [
        ...PlatformModal.styles,
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
                width: min(460px, calc(100vw - 24px));
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
            }

            :host([data-header-dragging]) .modal-header {
                cursor: grabbing;
            }

            .modal-title {
                min-width: 0;
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
                gap: 4px;
            }

            .header-btn {
                width: 30px;
                height: 30px;
                color: rgba(255, 255, 255, 0.78);
                background: rgba(255, 255, 255, 0.08);
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
                background: #e8eaed;
                overflow: hidden;
                z-index: 1;
            }

            platform-onlyoffice-host {
                flex: 1 1 auto;
                width: 100%;
                min-width: 0;
                min-height: 0;
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

            :host-context([data-theme="light"]) .header-btn {
                color: rgba(15, 23, 42, 0.68);
                background: rgba(15, 23, 42, 0.06);
            }

            :host-context([data-theme="light"]) .header-btn:hover {
                color: rgba(15, 23, 42, 0.95);
                background: rgba(15, 23, 42, 0.12);
            }

            @media (max-width: 640px) {
                .modal-header {
                    width: min(360px, calc(100vw - 16px));
                    top: max(8px, env(safe-area-inset-top, 0px));
                    right: max(8px, env(safe-area-inset-right, 0px));
                }

                .file-name {
                    max-width: 190px;
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
        this._boundHeaderMouseMove = this._handleHeaderMouseMove.bind(this);
        this._boundHeaderMouseUp = this._handleHeaderMouseUp.bind(this);
    }

    disconnectedCallback() {
        this._endHeaderDrag();
        super.disconnectedCallback();
    }

    _resolvedFileId() {
        return _asNonEmptyString(this.fileId)
            || _asNonEmptyString(this.file?.file_id)
            || _asNonEmptyString(this.file?.id);
    }

    _fileName() {
        const file = this.file || {};
        return _asNonEmptyString(file.original_name)
            || _asNonEmptyString(file.filename)
            || _asNonEmptyString(file.name)
            || _asNonEmptyString(this.title)
            || 'file';
    }

    _toggleMinimized() {
        if (this._syncing) return;
        const next = !this.minimized;
        this.minimized = next;
        if (!next) {
            this._position = { x: null, y: null };
        }
    }

    _eventStartedOnInteractiveNode(event) {
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

    _handleMouseDown(event) {
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

    _handleHeaderMouseMove(event) {
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

    _handleMouseMove(event) {
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

    _handleHeaderMouseUp() {
        this._endHeaderDrag();
    }

    _endHeaderDrag() {
        if (!this._headerDragging && !this._headerDragState) {
            return;
        }
        this._headerDragging = false;
        this._headerDragState = null;
        this.toggleAttribute('data-header-dragging', false);
        document.removeEventListener('mousemove', this._boundHeaderMouseMove);
        document.removeEventListener('mouseup', this._boundHeaderMouseUp);
    }

    _onEditorError(event) {
        const detail = event.detail || {};
        const message = _asNonEmptyString(detail.detail) || _asNonEmptyString(detail.code) || this.t('file_viewer.close_failed');
        this._error = message;
        this.toast('file_viewer.open_failed', { type: 'error', namespace: 'platform', vars: { message } });
    }

    _onDocumentState(event) {
        const detail = event.detail || {};
        this._dirty = Boolean(detail.dirty);
    }

    _requestEditorSync({ close, settleMs }) {
        const fileId = this._resolvedFileId();
        if (!fileId) {
            return Promise.reject(new Error('file_id required'));
        }
        const correlation = `file_viewer_${Date.now()}_${Math.random().toString(36).slice(2)}`;
        return new Promise((resolve, reject) => {
            let doneUnsub = null;
            let failUnsub = null;
            let timer = null;
            const cleanup = () => {
                if (doneUnsub) doneUnsub();
                if (failUnsub) failUnsub();
                if (timer !== null) window.clearTimeout(timer);
            };
            doneUnsub = this.bus.subscribeType(FILES_EVENTS.EDITOR_SYNC_COMPLETED, (event) => {
                if (event.meta?.correlation_id !== correlation) return;
                cleanup();
                resolve(event.payload?.result || null);
            });
            failUnsub = this.bus.subscribeType(FILES_EVENTS.EDITOR_SYNC_FAILED, (event) => {
                if (event.meta?.correlation_id !== correlation) return;
                cleanup();
                reject(new Error(event.payload?.message || this.t('file_viewer.close_failed')));
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

    async _syncBeforeClose() {
        if (this._closeSyncComplete || !this.config) return;
        const capabilities = this.config.capabilities;
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

    close() {
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

    async requestPlatformClose() {
        if (!this._closeSyncComplete && this.config) {
            try {
                await this._syncBeforeClose();
            } catch (err) {
                this._error = err instanceof Error ? err.message : String(err);
            }
        }
        return super.requestPlatformClose();
    }

    _getModalStyle() {
        if (this.minimized && this._position.x !== null && this._position.y !== null) {
            return `position: fixed !important; left: ${this._position.x}px !important; top: ${this._position.y}px !important; right: auto !important; bottom: auto !important; z-index: 2; transform: translate(-50%, -50%) scale(1) !important;`;
        }
        return super._getModalStyle();
    }

    renderHeader() {
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

    _resolveDownloadUrl() {
        const config = this.config;
        if (!config || typeof config !== 'object') {
            return '';
        }
        if (typeof config.download_url === 'string' && config.download_url.length > 0) {
            return config.download_url;
        }
        if (config.binary && typeof config.binary.download_url === 'string' && config.binary.download_url.length > 0) {
            return config.binary.download_url;
        }
        return '';
    }

    _onDownloadClick() {
        const downloadUrl = this._resolveDownloadUrl();
        if (downloadUrl.length === 0) {
            return;
        }
        window.open(downloadUrl, '_blank', 'noopener,noreferrer');
    }

    renderHeaderActions() {
        const title = this.minimized ? this.t('file_viewer.restore') : this.t('file_viewer.minimize');
        const downloadUrl = this._resolveDownloadUrl();
        return html`
            ${downloadUrl.length > 0 ? html`
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

    renderBody() {
        const fileId = this._resolvedFileId();
        return html`
            <div class="viewer-shell">
                ${this.config
                    ? html`
                        <platform-document-viewer-host
                            .bindingId=${fileId}
                            .openConfig=${this.config}
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
