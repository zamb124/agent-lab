import { html, css, nothing, render as litRender } from '../lit-shim.js';
import { PlatformElement } from '../platform-element/index.js';
import '../components/platform-icon.js';
import { formatFileSize } from '../utils/format-file-size.js';

function asArray(value) {
    return Array.isArray(value) ? value : [];
}

function asString(value) {
    return typeof value === 'string' ? value : value == null ? '' : String(value);
}

function isPlainObject(value) {
    return Boolean(value) && typeof value === 'object' && !Array.isArray(value);
}

const OFFICE_EXT_RE = /\.(docx?|odt|rtf|txt|xlsx?|ods|csv|pptx?|odp)$/i;
const OFFICE_MIME_RE = /(word|excel|spreadsheet|presentation|powerpoint|officedocument|opendocument|text\/csv|text\/plain)/i;
const EDITOR_VIEWPORT_MARGIN = 16;
const EDITOR_MIN_WIDTH = 420;
const EDITOR_MIN_HEIGHT = 320;
const EDITOR_COLLAPSED_HEIGHT = 48;
const EDITOR_PORTAL_STYLE_ID = 'flows-file-editor-portal-styles';
const EDITOR_IFRAME_ALLOW = 'clipboard-read; clipboard-write; fullscreen; unload';

function ensureEditorPortalStyles() {
    if (typeof document === 'undefined' || document.getElementById(EDITOR_PORTAL_STYLE_ID)) {
        return;
    }
    const style = document.createElement('style');
    style.id = EDITOR_PORTAL_STYLE_ID;
    style.textContent = `
        .flows-file-editor-shell {
            position: fixed;
            inset: 76px 20px 20px 20px;
            z-index: 90;
            min-height: 0;
            display: flex;
            flex-direction: column;
            overflow: hidden;
            border: 1px solid var(--glass-border-subtle, rgba(15, 23, 42, 0.12));
            border-radius: var(--radius-lg, 14px);
            background: var(--bg-primary, #fff);
            box-shadow: 0 30px 90px rgba(15, 23, 42, 0.24);
            pointer-events: auto;
            box-sizing: border-box;
        }
        .flows-file-editor-shell[data-floating] {
            right: auto;
            bottom: auto;
        }
        .flows-file-editor-shell[data-collapsed] {
            min-height: 0;
        }
        .flows-file-editor-shell[data-closing] .flows-file-editor-bar {
            cursor: default;
        }
        .flows-file-editor-bar {
            height: 46px;
            display: flex;
            align-items: center;
            justify-content: space-between;
            gap: var(--space-2, 8px);
            padding: 0 var(--space-3, 12px);
            border-bottom: 1px solid var(--glass-border-subtle, rgba(15, 23, 42, 0.12));
            flex-shrink: 0;
            cursor: grab;
            user-select: none;
            touch-action: none;
            box-sizing: border-box;
        }
        .flows-file-editor-shell[data-dragging] .flows-file-editor-bar {
            cursor: grabbing;
        }
        .flows-file-editor-title {
            min-width: 0;
            overflow: hidden;
            text-overflow: ellipsis;
            white-space: nowrap;
            font-size: var(--text-sm, 14px);
            color: var(--text-secondary, #667085);
        }
        .flows-file-editor-actions {
            display: inline-flex;
            align-items: center;
            gap: var(--space-2, 8px);
            flex-shrink: 0;
        }
        .flows-file-editor-icon-btn {
            width: 34px;
            height: 34px;
            display: inline-flex;
            align-items: center;
            justify-content: center;
            border: 1px solid var(--glass-border-subtle, rgba(15, 23, 42, 0.12));
            border-radius: 999px;
            background: color-mix(in srgb, var(--bg-primary, #fff) 90%, transparent);
            color: var(--text-secondary, #667085);
            cursor: pointer;
            -webkit-backdrop-filter: blur(14px);
            backdrop-filter: blur(14px);
        }
        .flows-file-editor-icon-btn:hover {
            color: var(--text-primary, #101828);
            background: var(--bg-primary, #fff);
        }
        .flows-file-editor-icon-btn:disabled {
            cursor: default;
            opacity: 0.72;
        }
        .flows-file-editor-spinner {
            width: 16px;
            height: 16px;
            border-radius: 999px;
            border: 2px solid color-mix(in srgb, currentColor 24%, transparent);
            border-top-color: currentColor;
            animation: flowsChatFilesEditorSpin 0.8s linear infinite;
            box-sizing: border-box;
        }
        @keyframes flowsChatFilesEditorSpin {
            to { transform: rotate(360deg); }
        }
        .flows-file-editor-shell iframe {
            flex: 1;
            min-height: 0;
            width: 100%;
            border: 0;
            background: #fff;
        }
        .flows-file-editor-resize-handle {
            position: absolute;
            right: 5px;
            bottom: 5px;
            width: 20px;
            height: 20px;
            padding: 0;
            border: none;
            border-radius: var(--radius-sm, 6px);
            background: color-mix(in srgb, var(--bg-primary, #fff) 72%, transparent);
            color: var(--text-tertiary, #98a2b3);
            cursor: nwse-resize;
            opacity: 0.72;
            display: inline-flex;
            align-items: center;
            justify-content: center;
            touch-action: none;
        }
        .flows-file-editor-resize-handle::before,
        .flows-file-editor-resize-handle::after {
            content: '';
            position: absolute;
            right: 5px;
            bottom: 5px;
            width: 10px;
            height: 1px;
            border-radius: 999px;
            background: currentColor;
            transform: rotate(-45deg);
            transform-origin: right center;
        }
        .flows-file-editor-resize-handle::after {
            right: 4px;
            bottom: 10px;
            width: 6px;
        }
        .flows-file-editor-resize-handle:hover {
            opacity: 1;
            color: var(--text-primary, #101828);
            background: var(--bg-primary, #fff);
        }
        .flows-file-editor-shell[data-collapsed] .flows-file-editor-resize-handle,
        .flows-file-editor-shell[data-collapsed] iframe {
            display: none;
        }
        @media (max-width: 960px) {
            .flows-file-editor-shell {
                inset: 58px 8px 8px 8px;
                border-radius: var(--radius-md, 10px);
            }
        }
    `;
    document.head.appendChild(style);
}

function fileKey(file) {
    const fid = asString(file?.file_id);
    if (fid.length > 0) return fid;
    return asString(file?.url) || asString(file?.original_name);
}

function documentCapability(file) {
    if (!isPlainObject(file)) return null;
    const caps = isPlainObject(file.capabilities) ? file.capabilities : {};
    if (isPlainObject(caps.document)) return caps.document;
    if (isPlainObject(file.document)) return file.document;
    return null;
}

function withDocumentCapability(file, raw, namespace) {
    const caps = isPlainObject(file.capabilities) ? file.capabilities : {};
    const doc = {
        kind: 'onlyoffice',
        binding_id: asString(raw.binding_id),
        file_id: asString(raw.file_id),
        catalog_id: asString(raw.catalog_id),
        document_type: asString(raw.document_type),
        title: asString(raw.title),
        namespace,
        editor_url: asString(raw.editor_url),
        editable: true,
    };
    return {
        ...file,
        file_id: doc.file_id || asString(file.file_id),
        capabilities: { ...caps, document: doc },
        document: doc,
    };
}

function editorFrameUrl(url, documentBaseUrl = '') {
    const raw = asString(url);
    if (raw.length === 0) return '';
    try {
        const baseOrigin = asString(documentBaseUrl).replace(/\/+$/, '');
        const fallbackOrigin = typeof window !== 'undefined' && window.location?.origin
            ? window.location.origin
            : 'https://localhost';
        const parsed = new URL(raw, baseOrigin ? `${baseOrigin}/` : fallbackOrigin);
        if (raw.startsWith('/')) {
            if (baseOrigin) {
                return parsed.toString();
            }
            return `${parsed.pathname}${parsed.search}${parsed.hash}`;
        }
        return parsed.toString();
    } catch {
        return raw;
    }
}

function canOpenInDocuments(file) {
    if (!isPlainObject(file)) return false;
    if (documentCapability(file)) return true;
    const fid = asString(file.file_id);
    if (fid.length === 0) return false;
    const originalName = asString(file.original_name);
    const contentType = asString(file.content_type);
    return OFFICE_EXT_RE.test(originalName) || OFFICE_MIME_RE.test(contentType);
}

function fileHref(file) {
    return asString(file?.url);
}

function isImageFile(file) {
    const originalName = asString(file?.original_name).toLowerCase();
    const contentType = asString(file?.content_type);
    return contentType.startsWith('image/') || /\.(avif|gif|heic|heif|jpe?g|png|webp)$/i.test(originalName);
}

export class FlowsChatFilesPanel extends PlatformElement {
    static properties = {
        files: { type: Array },
        inline: { type: Boolean, reflect: true },
        activeCompanyId: { type: String, attribute: 'active-company-id' },
        documentBaseUrl: { type: String, attribute: 'document-base-url' },
        _expanded: { state: true },
        _selectedKey: { state: true },
        _editorUrl: { state: true },
        _editorCollapsed: { state: true },
        _busyKey: { state: true },
        _closingEditor: { state: true },
        _error: { state: true },
    };

    static styles = [
        PlatformElement.styles,
        css`
            :host {
                position: absolute;
                top: var(--space-3, 12px);
                right: var(--space-3, 12px);
                z-index: 35;
                display: block;
                pointer-events: none;
            }
            :host([inline]) {
                position: relative;
                top: auto;
                right: auto;
                display: inline-flex;
                pointer-events: auto;
            }
            .widget {
                position: relative;
                display: flex;
                align-items: flex-end;
                flex-direction: column;
                pointer-events: auto;
            }
            .trigger {
                height: 42px;
                display: flex;
                align-items: center;
                justify-content: center;
                gap: var(--space-2, 8px);
                padding: 0 var(--space-3, 12px);
                border: 1px solid color-mix(in srgb, var(--glass-border-subtle, rgba(148, 163, 184, 0.22)) 75%, transparent);
                border-radius: 999px;
                background: color-mix(in srgb, var(--bg-primary, #fff) 84%, transparent);
                box-shadow: 0 14px 34px rgba(15, 23, 42, 0.12);
                color: var(--text-primary, #101828);
                cursor: pointer;
                font-size: var(--text-sm, 14px);
                font-weight: var(--font-semibold, 600);
                -webkit-backdrop-filter: blur(16px);
                backdrop-filter: blur(16px);
                transition:
                    transform var(--duration-fast, 150ms) var(--easing-default, ease),
                    box-shadow var(--duration-fast, 150ms) var(--easing-default, ease),
                    background var(--duration-fast, 150ms) var(--easing-default, ease);
            }
            .trigger:hover {
                transform: translateY(-1px);
                background: color-mix(in srgb, var(--bg-primary, #fff) 94%, transparent);
                box-shadow: 0 18px 46px rgba(15, 23, 42, 0.16);
            }
            .count {
                color: var(--text-tertiary, #98a2b3);
                font-weight: var(--font-medium, 500);
            }
            .icon-btn {
                width: 34px;
                height: 34px;
                display: inline-flex;
                align-items: center;
                justify-content: center;
                border: 1px solid var(--glass-border-subtle, rgba(148, 163, 184, 0.22));
                border-radius: 999px;
                background: color-mix(in srgb, var(--bg-primary, #fff) 90%, transparent);
                color: var(--text-secondary, #667085);
                cursor: pointer;
                -webkit-backdrop-filter: blur(14px);
                backdrop-filter: blur(14px);
            }
            .icon-btn:hover {
                color: var(--text-primary, #101828);
                background: var(--bg-primary, #fff);
            }
            .tray {
                position: absolute;
                top: calc(100% + var(--space-2, 8px));
                right: 0;
                width: min(460px, calc(100vw - 32px));
                max-height: min(68vh, 640px);
                overflow: auto;
                display: flex;
                flex-direction: column;
                align-items: flex-end;
                gap: var(--space-3, 12px);
                padding: var(--space-2, 8px) 0 var(--space-3, 12px) var(--space-4, 16px);
                pointer-events: auto;
            }
            .file-row {
                --stagger: 0px;
                display: grid;
                grid-template-columns: minmax(0, max-content) 54px;
                align-items: center;
                justify-content: end;
                gap: var(--space-2, 8px);
                max-width: 100%;
                border: 0;
                background: transparent;
                color: inherit;
                text-align: left;
                cursor: pointer;
                transform: translateX(calc(-1 * var(--stagger)));
                transition:
                    transform var(--duration-fast, 150ms) var(--easing-default, ease),
                    opacity var(--duration-fast, 150ms) var(--easing-default, ease);
            }
            .file-row:hover {
                transform: translateX(calc(-1 * var(--stagger))) translateY(-1px);
            }
            .file-pill {
                min-width: 0;
                max-width: min(330px, calc(100vw - 132px));
                display: flex;
                align-items: center;
                gap: var(--space-2, 8px);
                padding: 7px 14px;
                border: 1px solid color-mix(in srgb, var(--glass-border-subtle, rgba(148, 163, 184, 0.22)) 58%, transparent);
                border-radius: 999px;
                background: color-mix(in srgb, var(--bg-primary, #fff) 90%, transparent);
                box-shadow: 0 16px 42px rgba(15, 23, 42, 0.12);
                -webkit-backdrop-filter: blur(18px);
                backdrop-filter: blur(18px);
            }
            .file-row.active .file-pill {
                border-color: color-mix(in srgb, var(--accent, #6366f1) 48%, var(--glass-border-subtle, rgba(148, 163, 184, 0.22)));
                box-shadow: 0 18px 48px rgba(79, 70, 229, 0.18);
            }
            .file-name {
                min-width: 0;
                overflow: hidden;
                text-overflow: ellipsis;
                white-space: nowrap;
                font-size: var(--text-base, 16px);
                color: var(--text-primary, #101828);
            }
            .file-meta {
                font-size: var(--text-xs, 12px);
                color: var(--text-tertiary, #98a2b3);
                white-space: nowrap;
            }
            .thumb {
                width: 52px;
                height: 64px;
                display: flex;
                align-items: center;
                justify-content: center;
                overflow: hidden;
                border: 1px solid color-mix(in srgb, var(--glass-border-subtle, rgba(148, 163, 184, 0.22)) 70%, transparent);
                border-radius: var(--radius-md, 10px);
                background: var(--bg-primary, #fff);
                box-shadow: 0 12px 32px rgba(15, 23, 42, 0.18);
                color: var(--text-tertiary, #98a2b3);
            }
            .thumb img {
                width: 100%;
                height: 100%;
                object-fit: cover;
                display: block;
            }
            .empty,
            .error {
                max-width: 260px;
                padding: 8px 13px;
                border-radius: 999px;
                background: color-mix(in srgb, var(--bg-primary, #fff) 90%, transparent);
                box-shadow: 0 14px 34px rgba(15, 23, 42, 0.10);
                font-size: var(--text-sm, 14px);
                color: var(--text-tertiary, #98a2b3);
                -webkit-backdrop-filter: blur(16px);
                backdrop-filter: blur(16px);
            }
            .error {
                color: var(--danger, #ef4444);
            }
            .editor-shell {
                position: fixed;
                inset: 76px 20px 20px 20px;
                z-index: 90;
                min-height: 0;
                display: flex;
                flex-direction: column;
                overflow: hidden;
                border: 1px solid var(--glass-border-subtle, rgba(148, 163, 184, 0.22));
                border-radius: var(--radius-lg, 14px);
                background: var(--bg-primary, #fff);
                box-shadow: 0 30px 90px rgba(15, 23, 42, 0.24);
                pointer-events: auto;
            }
            .editor-shell[data-floating] {
                right: auto;
                bottom: auto;
            }
            .editor-shell[data-collapsed] {
                min-height: 0;
            }
            .editor-bar {
                height: 46px;
                display: flex;
                align-items: center;
                justify-content: space-between;
                gap: var(--space-2, 8px);
                padding: 0 var(--space-3, 12px);
                border-bottom: 1px solid var(--glass-border-subtle, rgba(148, 163, 184, 0.22));
                flex-shrink: 0;
                cursor: grab;
                user-select: none;
                touch-action: none;
            }
            .editor-shell[data-dragging] .editor-bar {
                cursor: grabbing;
            }
            .editor-title {
                min-width: 0;
                overflow: hidden;
                text-overflow: ellipsis;
                white-space: nowrap;
                font-size: var(--text-sm, 14px);
                color: var(--text-secondary, #667085);
            }
            .editor-actions {
                display: inline-flex;
                align-items: center;
                gap: var(--space-2, 8px);
                flex-shrink: 0;
            }
            iframe {
                flex: 1;
                min-height: 0;
                width: 100%;
                border: 0;
                background: #fff;
            }
            .editor-resize-handle {
                position: absolute;
                right: 5px;
                bottom: 5px;
                width: 20px;
                height: 20px;
                padding: 0;
                border: none;
                border-radius: var(--radius-sm, 6px);
                background: color-mix(in srgb, var(--bg-primary, #fff) 72%, transparent);
                color: var(--text-tertiary, #98a2b3);
                cursor: nwse-resize;
                opacity: 0.72;
                display: inline-flex;
                align-items: center;
                justify-content: center;
                touch-action: none;
            }
            .editor-resize-handle::before,
            .editor-resize-handle::after {
                content: '';
                position: absolute;
                right: 5px;
                bottom: 5px;
                width: 10px;
                height: 1px;
                border-radius: 999px;
                background: currentColor;
                transform: rotate(-45deg);
                transform-origin: right center;
            }
            .editor-resize-handle::after {
                right: 4px;
                bottom: 10px;
                width: 6px;
            }
            .editor-resize-handle:hover {
                opacity: 1;
                color: var(--text-primary, #101828);
                background: var(--bg-primary, #fff);
            }
            .editor-shell[data-collapsed] .editor-resize-handle,
            .editor-shell[data-collapsed] iframe {
                display: none;
            }
            @media (max-width: 960px) {
                :host {
                    top: var(--space-2, 8px);
                    right: var(--space-2, 8px);
                }
                :host([inline]) {
                    top: auto;
                    right: auto;
                }
                .tray {
                    width: calc(100vw - 16px);
                    max-height: 58vh;
                    padding-left: var(--space-2, 8px);
                }
                .file-row {
                    transform: none;
                }
                .file-row:hover {
                    transform: translateY(-1px);
                }
                .file-pill {
                    max-width: calc(100vw - 96px);
                }
                .editor-shell {
                    inset: 58px 8px 8px 8px;
                    border-radius: var(--radius-md, 10px);
                }
            }
        `,
    ];

    constructor() {
        super();
        this.files = [];
        this.inline = false;
        this.activeCompanyId = '';
        this.documentBaseUrl = '';
        this._expanded = false;
        this._selectedKey = '';
        this._editorUrl = '';
        this._editorCollapsed = false;
        this._editorRect = null;
        this._editorRestoreHeight = 0;
        this._editorZIndex = 90;
        this._editorPortal = null;
        this._editorDocument = null;
        this._editorDirty = false;
        this._editorDirtyBindingId = '';
        this._closingEditor = false;
        this._editorDragState = null;
        this._editorResizeState = null;
        this._boundEditorPointerMove = (e) => this._onEditorPointerMove(e);
        this._boundEditorPointerUp = () => this._endEditorPointerInteraction();
        this._boundViewportResize = () => this._clampEditorToViewport();
        this._boundOfficeMessage = (e) => this._onOfficeEditorMessage(e);
        this._busyKey = '';
        this._error = '';
    }

    connectedCallback() {
        super.connectedCallback();
        ensureEditorPortalStyles();
        if (typeof window !== 'undefined') {
            window.addEventListener('resize', this._boundViewportResize);
            window.addEventListener('message', this._boundOfficeMessage);
        }
    }

    disconnectedCallback() {
        this._endEditorPointerInteraction();
        this._clearEditorPortal();
        if (typeof window !== 'undefined') {
            window.removeEventListener('resize', this._boundViewportResize);
            window.removeEventListener('message', this._boundOfficeMessage);
        }
        super.disconnectedCallback();
    }

    _onOfficeEditorMessage(event) {
        if (typeof window === 'undefined' || event.origin !== window.location.origin) {
            return;
        }
        const data = event.data;
        if (!isPlainObject(data) || data.type !== 'platform.office.document-state') {
            return;
        }
        const bindingId = asString(data.bindingId);
        const currentBindingId = asString(documentCapability(this._selectedFile())?.binding_id)
            || asString(this._editorDocument?.binding_id);
        if (!bindingId || bindingId !== currentBindingId) {
            return;
        }
        this._editorDirtyBindingId = bindingId;
        this._editorDirty = Boolean(data.dirty);
    }

    _ensureEditorPortal() {
        if (typeof document === 'undefined') {
            return null;
        }
        ensureEditorPortalStyles();
        if (this._editorPortal && this._editorPortal.isConnected) {
            return this._editorPortal;
        }
        const portal = document.createElement('div');
        portal.className = 'flows-file-editor-portal';
        document.body.appendChild(portal);
        this._editorPortal = portal;
        return portal;
    }

    _clearEditorPortal() {
        const portal = this._editorPortal;
        this._editorPortal = null;
        if (!portal) {
            return;
        }
        try {
            litRender(nothing, portal);
        } catch {
            /* noop */
        }
        portal.remove();
    }

    _editorShellEl() {
        const portalShell = this._editorPortal?.querySelector('.flows-file-editor-shell');
        if (portalShell instanceof HTMLElement) {
            return portalShell;
        }
        const localShell = this.renderRoot?.querySelector('.editor-shell');
        return localShell instanceof HTMLElement ? localShell : null;
    }

    _syncEditorPortal() {
        if (this._editorUrl.length === 0) {
            this._clearEditorPortal();
            return;
        }
        const portal = this._ensureEditorPortal();
        if (!portal) {
            return;
        }
        const selected = this._selectedFile();
        litRender(html`
            <div
                class="flows-file-editor-shell"
                ?data-floating=${Boolean(this._editorRect)}
                ?data-collapsed=${this._editorCollapsed}
                ?data-dragging=${Boolean(this._editorDragState)}
                ?data-resizing=${Boolean(this._editorResizeState)}
                ?data-closing=${this._closingEditor}
                style=${this._editorShellStyle()}
            >
                <div class="flows-file-editor-bar" @pointerdown=${(e) => this._onEditorBarPointerDown(e)}>
                    <div class="flows-file-editor-title">${selected ? asString(selected.original_name) : ''}</div>
                    <div class="flows-file-editor-actions">
                        <button
                            type="button"
                            class="flows-file-editor-icon-btn"
                            title=${this._editorCollapsed ? 'Restore' : 'Minimize'}
                            ?disabled=${this._closingEditor}
                            @click=${() => this._toggleEditorCollapsed()}
                        >
                            <platform-icon
                                name=${this._editorCollapsed ? 'fullscreen' : 'minus'}
                                size="16"
                            ></platform-icon>
                        </button>
                        <button
                            type="button"
                            class="flows-file-editor-icon-btn"
                            title=${this._closingEditor ? 'Saving before close' : 'Close'}
                            ?disabled=${this._closingEditor}
                            @click=${() => this._closeEditor()}
                        >
                            ${this._closingEditor
                                ? html`<span class="flows-file-editor-spinner" aria-label="Saving"></span>`
                                : html`<platform-icon name="close" size="16"></platform-icon>`}
                        </button>
                    </div>
                </div>
                ${this._editorCollapsed
                    ? nothing
                    : html`
                        <iframe
                            title=${selected ? asString(selected.original_name) : 'Document editor'}
                            src=${this._editorUrl}
                            allow=${EDITOR_IFRAME_ALLOW}
                            allowfullscreen
                        ></iframe>
                    `}
                ${this._editorCollapsed
                    ? nothing
                    : html`
                        <button
                            type="button"
                            class="flows-file-editor-resize-handle"
                            title="Resize"
                            aria-label="Resize"
                            @pointerdown=${(e) => this._onEditorResizePointerDown(e)}
                        ></button>
                    `}
            </div>
        `, portal);
    }

    _editorViewport() {
        if (typeof window === 'undefined') {
            return { width: 1280, height: 900 };
        }
        const doc = window.document && window.document.documentElement;
        return {
            width: window.innerWidth || (doc ? doc.clientWidth : 1280) || 1280,
            height: window.innerHeight || (doc ? doc.clientHeight : 900) || 900,
        };
    }

    _editorMinWidth() {
        const viewport = this._editorViewport();
        return Math.max(280, Math.min(EDITOR_MIN_WIDTH, viewport.width - EDITOR_VIEWPORT_MARGIN * 2));
    }

    _editorMinHeight(collapsed = this._editorCollapsed) {
        if (collapsed) {
            return EDITOR_COLLAPSED_HEIGHT;
        }
        const viewport = this._editorViewport();
        return Math.max(220, Math.min(EDITOR_MIN_HEIGHT, viewport.height - EDITOR_VIEWPORT_MARGIN * 2));
    }

    _clampEditorRect(rect, collapsed = this._editorCollapsed) {
        const viewport = this._editorViewport();
        const margin = EDITOR_VIEWPORT_MARGIN;
        const minWidth = this._editorMinWidth();
        const minHeight = this._editorMinHeight(collapsed);
        const maxWidth = Math.max(minWidth, viewport.width - margin * 2);
        const maxHeight = Math.max(minHeight, viewport.height - margin * 2);
        const width = Math.min(Math.max(Number(rect.width) || minWidth, minWidth), maxWidth);
        const rawHeight = collapsed ? EDITOR_COLLAPSED_HEIGHT : Number(rect.height) || minHeight;
        const height = Math.min(Math.max(rawHeight, minHeight), maxHeight);
        const left = Math.min(
            Math.max(Number(rect.left) || margin, margin),
            Math.max(margin, viewport.width - width - margin),
        );
        const top = Math.min(
            Math.max(Number(rect.top) || margin, margin),
            Math.max(margin, viewport.height - height - margin),
        );
        return { left, top, width, height };
    }

    _defaultEditorRect(collapsed = this._editorCollapsed) {
        const viewport = this._editorViewport();
        const margin = EDITOR_VIEWPORT_MARGIN;
        const width = Math.min(Math.max(this._editorMinWidth(), viewport.width * 0.78), viewport.width - margin * 2);
        const height = collapsed
            ? EDITOR_COLLAPSED_HEIGHT
            : Math.min(Math.max(this._editorMinHeight(false), viewport.height * 0.76), viewport.height - margin * 2);
        return this._clampEditorRect({
            left: (viewport.width - width) / 2,
            top: Math.max(58, (viewport.height - height) / 2),
            width,
            height,
        }, collapsed);
    }

    _readEditorRect() {
        const shell = this._editorShellEl();
        const rect = shell ? shell.getBoundingClientRect() : null;
        if (rect && rect.width > 0 && rect.height > 0) {
            return this._clampEditorRect({
                left: rect.left,
                top: rect.top,
                width: rect.width,
                height: rect.height,
            });
        }
        return this._defaultEditorRect();
    }

    _bringEditorToFront() {
        this._editorZIndex = Math.max(Number(this._editorZIndex) + 1 || 91, 91);
        const shell = this._editorShellEl();
        if (shell) {
            shell.style.zIndex = String(this._editorZIndex);
        }
    }

    _applyEditorRect(rect, { bringToFront = false } = {}) {
        const clamped = this._clampEditorRect(rect);
        this._editorRect = clamped;
        if (bringToFront) {
            this._bringEditorToFront();
        }
        const shell = this._editorShellEl();
        if (shell) {
            shell.style.left = `${Math.round(clamped.left)}px`;
            shell.style.top = `${Math.round(clamped.top)}px`;
            shell.style.right = 'auto';
            shell.style.bottom = 'auto';
            shell.style.width = `${Math.round(clamped.width)}px`;
            shell.style.height = `${Math.round(clamped.height)}px`;
            shell.style.zIndex = String(this._editorZIndex);
        }
    }

    _editorShellStyle() {
        const z = Number(this._editorZIndex) || 90;
        if (!this._editorRect) {
            return `z-index: ${z}`;
        }
        const rect = this._clampEditorRect(this._editorRect);
        return [
            `left: ${Math.round(rect.left)}px`,
            `top: ${Math.round(rect.top)}px`,
            'right: auto',
            'bottom: auto',
            `width: ${Math.round(rect.width)}px`,
            `height: ${Math.round(rect.height)}px`,
            `z-index: ${z}`,
        ].join('; ');
    }

    _ensureEditorRect({ bringToFront = false } = {}) {
        const rect = this._editorRect || this._readEditorRect();
        this._applyEditorRect(rect, { bringToFront });
        return this._editorRect;
    }

    _clampEditorToViewport() {
        if (!this._editorRect || this._editorUrl.length === 0) {
            return;
        }
        this._applyEditorRect(this._editorRect);
        this.requestUpdate();
    }

    _isEditorControlTarget(target) {
        if (!(target instanceof Element)) {
            return false;
        }
        return Boolean(target.closest('button,a,input,textarea,select,.editor-resize-handle'));
    }

    _onEditorBarPointerDown(e) {
        if (e.button !== 0 || this._isEditorControlTarget(e.target)) {
            return;
        }
        e.preventDefault();
        this._endEditorPointerInteraction();
        const rect = this._ensureEditorRect({ bringToFront: true });
        this._editorDragState = {
            startX: e.clientX,
            startY: e.clientY,
            startRect: { ...rect },
            pointerId: e.pointerId,
            target: e.currentTarget,
        };
        if (e.currentTarget && typeof e.currentTarget.setPointerCapture === 'function') {
            try {
                e.currentTarget.setPointerCapture(e.pointerId);
            } catch {
                /* noop */
            }
        }
        window.addEventListener('pointermove', this._boundEditorPointerMove);
        window.addEventListener('pointerup', this._boundEditorPointerUp);
        window.addEventListener('pointercancel', this._boundEditorPointerUp);
        this.requestUpdate();
    }

    _onEditorResizePointerDown(e) {
        if (e.button !== 0) {
            return;
        }
        e.preventDefault();
        e.stopPropagation();
        this._endEditorPointerInteraction();
        if (this._editorCollapsed) {
            this._editorCollapsed = false;
        }
        const rect = this._ensureEditorRect({ bringToFront: true });
        this._editorResizeState = {
            startX: e.clientX,
            startY: e.clientY,
            startRect: { ...rect },
            pointerId: e.pointerId,
            target: e.currentTarget,
        };
        if (e.currentTarget && typeof e.currentTarget.setPointerCapture === 'function') {
            try {
                e.currentTarget.setPointerCapture(e.pointerId);
            } catch {
                /* noop */
            }
        }
        window.addEventListener('pointermove', this._boundEditorPointerMove);
        window.addEventListener('pointerup', this._boundEditorPointerUp);
        window.addEventListener('pointercancel', this._boundEditorPointerUp);
        this.requestUpdate();
    }

    _onEditorPointerMove(e) {
        if (this._editorDragState) {
            const dx = e.clientX - this._editorDragState.startX;
            const dy = e.clientY - this._editorDragState.startY;
            this._applyEditorRect({
                ...this._editorDragState.startRect,
                left: this._editorDragState.startRect.left + dx,
                top: this._editorDragState.startRect.top + dy,
            });
            return;
        }
        if (this._editorResizeState) {
            const dx = e.clientX - this._editorResizeState.startX;
            const dy = e.clientY - this._editorResizeState.startY;
            this._applyEditorRect({
                ...this._editorResizeState.startRect,
                width: this._editorResizeState.startRect.width + dx,
                height: this._editorResizeState.startRect.height + dy,
            });
        }
    }

    _endEditorPointerInteraction() {
        const states = [this._editorDragState, this._editorResizeState];
        for (const state of states) {
            const target = state && state.target;
            if (target && typeof target.releasePointerCapture === 'function' && typeof state.pointerId === 'number') {
                try {
                    target.releasePointerCapture(state.pointerId);
                } catch {
                    /* noop */
                }
            }
        }
        this._editorDragState = null;
        this._editorResizeState = null;
        if (typeof window !== 'undefined') {
            window.removeEventListener('pointermove', this._boundEditorPointerMove);
            window.removeEventListener('pointerup', this._boundEditorPointerUp);
            window.removeEventListener('pointercancel', this._boundEditorPointerUp);
        }
        this.requestUpdate();
    }

    _toggleEditorCollapsed() {
        const shouldCollapse = !this._editorCollapsed;
        const rect = this._ensureEditorRect({ bringToFront: true });
        if (shouldCollapse) {
            this._editorRestoreHeight = Math.max(rect.height, this._editorMinHeight(false));
            this._editorCollapsed = true;
            this._applyEditorRect({ ...rect, height: EDITOR_COLLAPSED_HEIGHT });
        } else {
            this._editorCollapsed = false;
            this._applyEditorRect({
                ...rect,
                height: Math.max(this._editorRestoreHeight || this._editorMinHeight(false), this._editorMinHeight(false)),
            });
        }
        this.requestUpdate();
    }

    _toggle() {
        this._expanded = !this._expanded;
    }

    _stopOuterPanelEvent(event) {
        if (event && typeof event.stopPropagation === 'function') {
            event.stopPropagation();
        }
    }

    _toggleFromEvent(event) {
        this._stopOuterPanelEvent(event);
        this._toggle();
    }

    _selectedFile() {
        const key = this._selectedKey;
        return asArray(this.files).find((file) => fileKey(file) === key) || null;
    }

    updated(changedProperties) {
        if (changedProperties.has('files') && this._editorUrl.length > 0) {
            const selected = this._selectedFile();
            const cap = documentCapability(selected);
            const nextUrl = cap ? editorFrameUrl(cap.editor_url, this.documentBaseUrl) : '';
            if (nextUrl.length > 0 && nextUrl !== this._editorUrl) {
                this._editorUrl = nextUrl;
            }
            if (cap) {
                this._editorDocument = cap;
            }
        }
        this._syncEditorPortal();
    }

    async _open(file, event = null) {
        this._stopOuterPanelEvent(event);
        const cap = documentCapability(file);
        const fileId = asString(file?.file_id) || asString(cap?.file_id);
        if (fileId.length > 0 && canOpenInDocuments(file)) {
            this._editorUrl = '';
            this._selectedKey = '';
            this._editorDocument = null;
            this._clearEditorPortal();
            this.openFile({
                ...file,
                file_id: fileId,
                original_name: asString(file?.original_name) || asString(cap?.title),
            }, { source: 'flows_chat_files_panel' });
            this._expanded = false;
            return;
        }
        const href = fileHref(file);
        if (href.length > 0) {
            window.open(href, '_blank', 'noopener');
        }
    }

    async _waitForEditorChangesToFlush(bindingId) {
        if (!this._editorDirty || this._editorDirtyBindingId !== bindingId) {
            return;
        }
        const deadline = Date.now() + 4000;
        while (this._editorDirty && this._editorDirtyBindingId === bindingId && Date.now() < deadline) {
            await new Promise((resolve) => setTimeout(resolve, 150));
        }
    }

    async _syncEditorBeforeClose() {
        return true;
    }

    async _closeEditor() {
        if (this._closingEditor) {
            return;
        }
        this._endEditorPointerInteraction();
        this._closingEditor = true;
        this._syncEditorPortal();
        const synced = await this._syncEditorBeforeClose();
        this._closingEditor = false;
        if (!synced) {
            this._syncEditorPortal();
            return;
        }
        this._editorUrl = '';
        this._selectedKey = '';
        this._editorDocument = null;
        this._editorCollapsed = false;
        this._editorRect = null;
        this._editorRestoreHeight = 0;
        this._editorDirty = false;
        this._editorDirtyBindingId = '';
        this._error = '';
        this._clearEditorPortal();
    }

    _fileIcon(file) {
        const originalName = asString(file.original_name).toLowerCase();
        if (/\.(xlsx?|ods|csv)$/.test(originalName)) return 'table';
        if (/\.(pptx?|odp)$/.test(originalName)) return 'presentation';
        return 'file-text';
    }

    _renderFile(file) {
        const key = fileKey(file);
        const canOpen = canOpenInDocuments(file);
        const active = key.length > 0 && key === this._selectedKey;
        const busy = key.length > 0 && key === this._busyKey;
        const size = Number(file.file_size);
        const href = fileHref(file);
        const thumb = isImageFile(file) && href.length > 0
            ? html`<img src=${href} alt="" loading="lazy">`
            : html`<platform-icon name=${this._fileIcon(file)} size="22"></platform-icon>`;
        return html`
            <button
                type="button"
                class=${active ? 'file-row active' : 'file-row'}
                ?disabled=${busy}
                @pointerdown=${this._stopOuterPanelEvent}
                @click=${(event) => this._open(file, event)}
                title=${canOpen ? asString(file.original_name) : 'Download'}
                style=${`--stagger: ${Math.min(asArray(this.files).indexOf(file) * 10, 110)}px`}
            >
                <span class="file-pill">
                    <span class="file-name">${asString(file.original_name) || key}</span>
                    ${Number.isFinite(size) && size > 0
                        ? html`<span class="file-meta">${formatFileSize(size)}</span>`
                        : nothing}
                </span>
                <span class="thumb">
                    ${busy
                        ? html`<platform-icon name="hourglass-top" size="20"></platform-icon>`
                        : thumb}
                </span>
            </button>
        `;
    }

    render() {
        const files = asArray(this.files);
        if (files.length === 0 && this._editorUrl.length === 0) {
            return nothing;
        }
        return html`
            <div
                class="widget"
                @pointerdown=${this._stopOuterPanelEvent}
                @click=${this._stopOuterPanelEvent}
            >
                <button type="button" class="trigger" @click=${this._toggleFromEvent}>
                    <platform-icon name="paperclip" size="18"></platform-icon>
                    <span>Files <span class="count">${files.length}</span></span>
                    <platform-icon name=${this._expanded ? 'chevron-up' : 'chevron-down'} size="16"></platform-icon>
                </button>
                ${this._expanded
                    ? html`
                        <div
                            class="tray"
                            @pointerdown=${this._stopOuterPanelEvent}
                            @click=${this._stopOuterPanelEvent}
                        >
                        ${files.map((file) => this._renderFile(file))}
                        ${this._error ? html`<div class="error">${this._error}</div>` : nothing}
                        </div>
                    `
                    : nothing}
            </div>
        `;
    }
}

customElements.define('flows-chat-files-panel', FlowsChatFilesPanel);
