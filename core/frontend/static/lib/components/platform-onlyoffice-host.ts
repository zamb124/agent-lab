/**
 * OnlyOfficeHost — изолированный лайфцикл OnlyOffice DocEditor.
 *
 * Принимает `config` (Object из `office/document_editor_config` ответа):
 *   - document_server_url: публичный origin Document Server
 *   - token: JWT для DocsAPI.DocEditor
 *   - + claims из payload токена (document, editorConfig, type, ...)
 *
 * Жизненный цикл:
 *   1. При смене `config` (или первом mount) подгружает api.js singleton'ом
 *      по `document_server_url`, переинициализирует DocEditor в плейсхолдере
 *      внутри `document.body` (требование `getElementById` API), затем
 *      переносит iframe[name="frameEditor"] в `#oo-editor-target` shadow-host.
 *   2. MutationObserver на body отслеживает появление iframe; ResizeObserver
 *      и `window.resize` синхронизируют размеры. Запасной режим — fixed
 *      positioning по getBoundingClientRect.
 *   3. На любую ошибку (загрузка api.js, отсутствие DocsAPI, onError DS,
 *      timeout) эмитит `editor-error` с `{ code, detail }` — родитель
 *      решает что показать (toast + сообщение).
 *   4. `disconnectedCallback` корректно убивает редактор и observers.
 */

import { html, css, nothing } from 'lit';
import { guard } from 'lit/directives/guard.js';
import { PlatformElement } from '../platform-element/index.js';
import { isPlainRecord } from '../events/payload.js';
import type {CSSResultGroup, PropertyDeclarations, PropertyValues, TemplateResult} from 'lit';

interface OnlyOfficeDocEditor {
    destroyEditor?: () => void;
}

interface OnlyOfficeDocsApi {
    DocEditor?: new (placeholderId: string, init: Record<string, unknown>) => OnlyOfficeDocEditor;
}

declare global {
    interface Window {
        DocsAPI?: OnlyOfficeDocsApi;
        __ooDocsApiOrigin?: string;
    }
}

const BOOT_WATCH_TIMEOUT_MS = 120_000;
const UI_FALLBACK_TIMEOUT_MS = 2_500;
const ONLYOFFICE_IFRAME_ALLOW_FEATURES = ['clipboard-read', 'clipboard-write', 'fullscreen', 'unload'];

function ooFrameIdKey(id: string): string {
    if (!id || !id.startsWith('oo-embed-')) {
        return id.toLowerCase();
    }
    return `oo-embed-${id.slice('oo-embed-'.length).replace(/-/g, '').toLowerCase()}`;
}

function parseJwtPayloadClaims(jwt: unknown): Record<string, unknown> {
    if (typeof jwt !== 'string' || !jwt.includes('.')) {
        throw new Error('parseJwtPayloadClaims: jwt must be a non-empty string with payload segment');
    }
    const part = jwt.split('.')[1];
    if (!part) {
        throw new Error('parseJwtPayloadClaims: jwt has no payload segment');
    }
    const b64 = part.replace(/-/g, '+').replace(/_/g, '/');
    const pad = b64.length % 4;
    const padded = pad ? b64 + '='.repeat(4 - pad) : b64;
    const json = atob(padded);
    const claims: unknown = JSON.parse(json);
    if (!isPlainRecord(claims)) {
        throw new Error('parseJwtPayloadClaims: payload is not a JSON object');
    }
    return claims;
}

function documentRecord(value: unknown): Record<string, unknown> | null {
    if (value === undefined || value === null) return null;
    if (!isPlainRecord(value)) {
        throw new Error('platform-onlyoffice-host: config.document must be an object');
    }
    return value;
}

function frameEditorIframe(node: Element | null | undefined): HTMLIFrameElement | null {
    if (node === null || node === undefined) return null;
    if (!(node instanceof HTMLIFrameElement)) {
        throw new Error('platform-onlyoffice-host: frameEditor is not an iframe');
    }
    return node;
}

function ensureOnlyOfficeIframePermissions(iframe: HTMLElement | null | undefined): void {
    if (!iframe) {
        return;
    }
    const allow = iframe.getAttribute('allow');
    const entries = (allow === null ? '' : allow)
        .split(';')
        .map((entry) => entry.trim())
        .filter(Boolean);
    for (const feature of ONLYOFFICE_IFRAME_ALLOW_FEATURES) {
        if (!entries.some((entry) => entry.split(/\s+/)[0] === feature)) {
            entries.push(feature);
        }
    }
    iframe.setAttribute('allow', entries.join('; '));
    iframe.setAttribute('allowfullscreen', '');
}

function isLocalDocumentServerHost(hostname: unknown): boolean {
    const host = (typeof hostname === 'string' ? hostname : '').toLowerCase();
    return host === 'localhost' || host === '127.0.0.1' || host === '::1';
}

function browserSafeDocumentServerUrl(raw: unknown): string {
    const value = typeof raw === 'string' ? raw.trim().replace(/\/$/, '') : '';
    if (!value || typeof window === 'undefined') {
        return value;
    }
    const url = new URL(value, window.location.href);
    if (
        window.location.protocol === 'https:'
        && url.protocol === 'http:'
        && !isLocalDocumentServerHost(url.hostname)
    ) {
        url.protocol = 'https:';
    }
    return url.toString().replace(/\/$/, '');
}

let _ooEmbedCounter = 0;

export class PlatformOnlyOfficeHost extends PlatformElement {
    static override properties: PropertyDeclarations = {
        config: { type: Object },
        fileId: { type: String, attribute: 'file-id' },
        suspended: { type: Boolean, reflect: true },
        _initializing: { state: true },
    }
    declare config: Record<string, unknown> | null;
    declare fileId: string;
    declare suspended: boolean;
    declare _initializing: boolean;

    private _docEditor: OnlyOfficeDocEditor | null;
    private _configKey: string | null;
    private _bootWatchTimer: ReturnType<typeof setTimeout> | null;
    private _uiFallbackTimer: ReturnType<typeof setTimeout> | null;
    private _ooPlaceholder: HTMLElement | null;
    private _ooAnchor: Element | null;
    private _ooResizeObserver: ResizeObserver | null;
    private _ooIframeAttrObserver: MutationObserver | null;
    private _ooBodyObserver: MutationObserver | null;
    private _ooIframeMount: Element | null;
    private _onDocScrollCapture: () => void;

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
                max-height: min(100dvh, var(--app-vh, 100vh));
            }
            .editor-host {
                position: relative;
                flex: 1;
                display: flex;
                flex-direction: column;
                min-width: 0;
                min-height: 0;
                width: 100%;
                height: 100%;
                background: var(--documents-stage-host-bg);
                border-radius: var(--documents-stage-host-radius);
                overflow: hidden;
            }
            .editor-loading-overlay {
                position: absolute;
                inset: 0;
                z-index: 50;
                display: flex;
                flex-direction: column;
                align-items: stretch;
                justify-content: flex-start;
                gap: 0.75rem;
                padding: 2.5rem 2rem;
                background: var(--documents-stage-host-bg);
                pointer-events: none;
                transition: opacity 220ms ease;
            }
            .editor-loading-overlay .paper-line {
                height: 0.75rem;
                border-radius: 999px;
                background: var(--documents-stage-skeleton);
                background-size: 200% 100%;
                animation: oo-paper-shimmer 1.2s ease-in-out infinite;
            }
            .editor-loading-overlay .paper-line.w60 { width: 60%; }
            .editor-loading-overlay .paper-line.w80 { width: 80%; }
            .editor-loading-overlay .paper-line.w45 { width: 45%; }
            .editor-loading-overlay .paper-sheet {
                flex: 1;
                margin-top: 0.75rem;
                border-radius: 4px;
                background: var(--documents-stage-paper);
                box-shadow: var(--documents-stage-host-shadow);
                position: relative;
                overflow: hidden;
            }
            .editor-loading-overlay .paper-sheet::after {
                content: '';
                position: absolute;
                inset: 0;
                background: var(--documents-stage-skeleton);
                background-size: 200% 100%;
                animation: oo-paper-shimmer 1.2s ease-in-out infinite;
                opacity: 0.55;
            }
            @keyframes oo-paper-shimmer {
                0% { background-position: 100% 0; }
                100% { background-position: -100% 0; }
            }
            .oo-doc-root {
                flex: 1;
                min-width: 0;
                min-height: 0;
                width: 100%;
                position: relative;
                display: flex;
                flex-direction: column;
            }
        `,
    ];

    constructor() {
        super();
        this.config = null;
        this.fileId = '';
        this.suspended = false;
        this._initializing = false;
        this._docEditor = null;
        this._configKey = null;
        this._bootWatchTimer = null;
        this._uiFallbackTimer = null;
        this._ooPlaceholder = null;
        this._ooAnchor = null;
        this._ooResizeObserver = null;
        this._ooIframeAttrObserver = null;
        this._ooBodyObserver = null;
        this._ooIframeMount = null;
        this._onDocScrollCapture = () => {
            requestAnimationFrame(() => this._syncOoLayout());
        };
    }

    override firstUpdated(): void {
        this._bootIfConfigChanged();
    }

    override updated(changed: PropertyValues<this>): void {
        super.updated(changed);
        if (changed.has('config')) {
            this._bootIfConfigChanged();
        }
        if (changed.has('suspended')) {
            if (this.suspended) {
                this._syncOoLayout();
            } else {
                requestAnimationFrame(() => this._syncOoLayout());
            }
        }
    }

    _bootIfConfigChanged() {
        if (!this.config) {
            return;
        }
        const key = this._computeConfigKey(this.config);
        if (key !== this._configKey) {
            this._configKey = key;
            void this._bootEditor();
        }
    }

    override disconnectedCallback(): void {
        this._clearAllEditorTimers();
        super.disconnectedCallback();
        this._destroyEditor();
    }

    _computeConfigKey(config: Record<string, unknown> | null): string | null {
        if (!config || typeof config !== 'object') return null;
        const ds = browserSafeDocumentServerUrl(config.document_server_url);
        const token = typeof config.token === 'string' ? config.token : '';
        if (token.length > 0) return `${ds}#${token}`;
        return ds;
    }

    _emitError(code: string, detail: unknown): void {
        this.emit('editor-error', { code, detail });
    }

    _emitDocumentState(dirty: unknown): void {
        const documentConfig = this.config ? documentRecord(this.config.document) : null;
        const fileId = typeof this.fileId === 'string' && this.fileId.length > 0
            ? this.fileId
            : (documentConfig && typeof documentConfig.key === 'string' ? documentConfig.key : '');
        if (!fileId) {
            return;
        }
        this.emit('document-state', { fileId, dirty: Boolean(dirty) });
        if (typeof window === 'undefined' || window.parent === window) {
            return;
        }
        window.parent.postMessage(
            {
                type: 'platform.office.document-state',
                fileId,
                dirty: Boolean(dirty),
                sentAt: Date.now(),
            },
            window.location.origin,
        );
    }

    _clearBootWatch(): void {
        if (this._bootWatchTimer != null) {
            clearTimeout(this._bootWatchTimer);
            this._bootWatchTimer = null;
        }
    }

    _clearAllEditorTimers(): void {
        this._clearBootWatch();
        if (this._uiFallbackTimer != null) {
            clearTimeout(this._uiFallbackTimer);
            this._uiFallbackTimer = null;
        }
    }

    _markEditorUiVisible(): void {
        this._clearAllEditorTimers();
        this._initializing = false;
        this.requestUpdate();
    }

    _detachOoBodyObserver(): void {
        if (this._ooBodyObserver) {
            this._ooBodyObserver.disconnect();
            this._ooBodyObserver = null;
        }
    }

    _teardownOoDom(): void {
        this._detachOoBodyObserver();
        if (this._ooIframeAttrObserver) {
            this._ooIframeAttrObserver.disconnect();
            this._ooIframeAttrObserver = null;
        }
        if (this._ooResizeObserver) {
            this._ooResizeObserver.disconnect();
            this._ooResizeObserver = null;
        }
        if (this._ooPlaceholder && this._ooPlaceholder.parentNode) {
            this._ooPlaceholder.remove();
        }
        this._ooPlaceholder = null;
        this._ooAnchor = null;
        this._ooIframeMount = null;
    }

    _pickFrameEditorIframe(): HTMLIFrameElement | null {
        const wantId = this._ooPlaceholder ? this._ooPlaceholder.id : null;
        if (!wantId) {
            return frameEditorIframe(document.querySelector('iframe[name="frameEditor"]'));
        }
        const key = ooFrameIdKey(wantId);
        const list = document.querySelectorAll('iframe[name="frameEditor"]');
        for (const f of list) {
            const src = f.getAttribute('src');
            if (!src) continue;
            if (!URL.canParse(src, document.baseURI)) continue;
            const fid = new URL(src, document.baseURI).searchParams.get('frameEditorId');
            if (fid && ooFrameIdKey(fid) === key) {
                return frameEditorIframe(f);
            }
        }
        return list.length === 1 ? frameEditorIframe(list[0]) : null;
    }

    _pinIframeToHost(iframe: HTMLElement): void {
        const imp = 'important';
        ensureOnlyOfficeIframePermissions(iframe);
        iframe.removeAttribute('width');
        iframe.removeAttribute('height');
        iframe.removeAttribute('align');
        iframe.style.setProperty('position', 'relative', imp);
        iframe.style.setProperty('left', 'auto', imp);
        iframe.style.setProperty('top', 'auto', imp);
        iframe.style.setProperty('width', '100%', imp);
        iframe.style.setProperty('height', '100%', imp);
        iframe.style.setProperty('max-width', 'none', imp);
        iframe.style.setProperty('max-height', 'none', imp);
        iframe.style.setProperty('z-index', 'auto', imp);
        iframe.style.setProperty('flex', '1', imp);
        iframe.style.setProperty('min-height', '0', imp);
        iframe.style.setProperty('border', '0', imp);
        iframe.style.setProperty('margin', '0', imp);
        iframe.style.setProperty('box-sizing', 'border-box', imp);
        iframe.style.setProperty('display', 'block', imp);
        iframe.style.setProperty('opacity', '1', imp);
        iframe.style.setProperty('pointer-events', 'auto', imp);
    }

    _pinIframeToViewport(iframe: HTMLElement, left: number, top: number, w: number, h: number): void {
        const imp = 'important';
        ensureOnlyOfficeIframePermissions(iframe);
        iframe.removeAttribute('width');
        iframe.removeAttribute('height');
        iframe.removeAttribute('align');
        iframe.style.setProperty('position', 'fixed', imp);
        iframe.style.setProperty('left', `${left}px`, imp);
        iframe.style.setProperty('top', `${top}px`, imp);
        iframe.style.setProperty('width', `${w}px`, imp);
        iframe.style.setProperty('height', `${h}px`, imp);
        iframe.style.setProperty('max-width', `${w}px`, imp);
        iframe.style.setProperty('max-height', `${h}px`, imp);
        iframe.style.setProperty('z-index', '41', imp);
        iframe.style.setProperty('border', '0', imp);
        iframe.style.setProperty('margin', '0', imp);
        iframe.style.setProperty('box-sizing', 'border-box', imp);
        iframe.style.setProperty('opacity', '1', imp);
        iframe.style.setProperty('pointer-events', 'auto', imp);
    }

    _parkIframeOffscreen(iframe: HTMLElement | null | undefined): void {
        if (!iframe) return;
        const imp = 'important';
        ensureOnlyOfficeIframePermissions(iframe);
        iframe.style.setProperty('position', 'fixed', imp);
        iframe.style.setProperty('left', '-2px', imp);
        iframe.style.setProperty('top', '-2px', imp);
        iframe.style.setProperty('width', '1px', imp);
        iframe.style.setProperty('height', '1px', imp);
        iframe.style.setProperty('max-width', '1px', imp);
        iframe.style.setProperty('max-height', '1px', imp);
        iframe.style.setProperty('z-index', '-1', imp);
        iframe.style.setProperty('opacity', '0', imp);
        iframe.style.setProperty('pointer-events', 'none', imp);
        iframe.style.setProperty('border', '0', imp);
    }

    _ensureIframeAttrObserver(iframe: Element | null | undefined): void {
        if (this._ooIframeAttrObserver || !(iframe && iframe.isConnected)) {
            return;
        }
        this._ooIframeAttrObserver = new MutationObserver(() => {
            requestAnimationFrame(() => this._syncOoLayout());
        });
        this._ooIframeAttrObserver.observe(iframe, {
            attributes: true,
            attributeFilter: ['width', 'height'],
        });
    }

    _tryReparentOoIframe(): void {
        const mount = this._ooIframeMount;
        if (!(mount && mount.isConnected)) return;
        if (mount.querySelector('iframe[name="frameEditor"]')) {
            this._detachOoBodyObserver();
            return;
        }
        const iframe = this._pickFrameEditorIframe();
        if (!iframe || !iframe.isConnected) return;
        if (mount.contains(iframe)) {
            this._detachOoBodyObserver();
            return;
        }
        mount.appendChild(iframe);
        this._detachOoBodyObserver();
    }

    _minimalOoPlaceholderStyle(): string {
        return [
            'position:absolute', 'left:0', 'top:0', 'width:0', 'height:0',
            'overflow:hidden', 'opacity:0', 'pointer-events:none',
            'clip:rect(0,0,0,0)', 'border:0', 'padding:0', 'margin:0',
        ].join(';');
    }

    _syncOoLayout(): void {
        this._tryReparentOoIframe();
        const anchor = this._ooAnchor;
        const ph = this._ooPlaceholder;
        const mount = this._ooIframeMount;
        if (!(anchor && anchor.isConnected) || !(ph && ph.isConnected)) return;
        const iframeInMount = mount && mount.isConnected
            ? frameEditorIframe(mount.querySelector('iframe[name="frameEditor"]'))
            : null;
        if (this.suspended) {
            ph.style.cssText = this._minimalOoPlaceholderStyle();
            this._parkIframeOffscreen(iframeInMount || this._pickFrameEditorIframe());
            return;
        }
        if (iframeInMount) {
            ph.style.cssText = this._minimalOoPlaceholderStyle();
            this._pinIframeToHost(iframeInMount);
            this._ensureIframeAttrObserver(iframeInMount);
            return;
        }
        const r = anchor.getBoundingClientRect();
        if (r.width < 4 || r.height < 4) return;
        const left = Math.round(r.left);
        const top = Math.round(r.top);
        const w = Math.round(r.width);
        const h = Math.round(r.height);
        ph.style.cssText = [
            `position:fixed`, `left:${left}px`, `top:${top}px`,
            `width:${w}px`, `height:${h}px`,
            `z-index:40`, `opacity:0`, `pointer-events:none`,
            `overflow:hidden`, `box-sizing:border-box`,
        ].join(';');
        const iframe = this._pickFrameEditorIframe();
        if (iframe) {
            this._pinIframeToViewport(iframe, left, top, w, h);
            this._ensureIframeAttrObserver(iframe);
        }
    }

    _startOoLayout(anchor: Element, placeholder: HTMLElement, iframeMountEl: Element): void {
        this._teardownOoDom();
        this._ooAnchor = anchor;
        this._ooPlaceholder = placeholder;
        this._ooIframeMount = iframeMountEl;
        document.body.appendChild(placeholder);
        this._ooBodyObserver = new MutationObserver(() => {
            this._tryReparentOoIframe();
            requestAnimationFrame(() => this._syncOoLayout());
        });
        this._ooBodyObserver.observe(document.body, { childList: true, subtree: true });
        this._ooResizeObserver = new ResizeObserver(() => {
            requestAnimationFrame(() => this._syncOoLayout());
        });
        this._ooResizeObserver.observe(anchor);
        this._ooResizeObserver.observe(this);
        this._ooResizeObserver.observe(document.documentElement);
        this.useDomEvent(document, 'scroll', this._onDocScrollCapture, true);
        requestAnimationFrame(() => this._syncOoLayout());
    }

    _destroyEditor(): void {
        if (this._docEditor && typeof this._docEditor.destroyEditor === 'function') {
            this._docEditor.destroyEditor();
        }
        this._docEditor = null;
        this._teardownOoDom();
        const target = this.renderRoot ? this.renderRoot.querySelector('#oo-editor-target') : null;
        if (target) target.innerHTML = '';
    }

    async _injectOoScript(scriptSrc: string, logicalDsOrigin: string): Promise<void> {
        const base = logicalDsOrigin.replace(/\/$/, '');
        if (typeof window.DocsAPI !== 'undefined' && window.__ooDocsApiOrigin === base) {
            return;
        }
        if (typeof window.DocsAPI !== 'undefined' && window.__ooDocsApiOrigin !== base) {
            if (!Reflect.deleteProperty(window, 'DocsAPI')) {
                throw new Error('platform-onlyoffice-host: window.DocsAPI is not configurable');
            }
            delete window.__ooDocsApiOrigin;
        }
        await new Promise<void>((resolve, reject) => {
            const s = document.createElement('script');
            s.src = scriptSrc;
            s.async = true;
            s.onload = () => {
                window.__ooDocsApiOrigin = base;
                resolve();
            };
            s.onerror = () => reject(new Error(`Document editor api.js: ${scriptSrc}`));
            document.head.appendChild(s);
        });
    }

    async _ensureDocsApi(dsOrigin: string): Promise<void> {
        const ds = dsOrigin.replace(/\/$/, '');
        await this._injectOoScript(`${ds}/web-apps/apps/api/documents/api.js`, ds);
    }

    async _bootEditor(): Promise<void> {
        const config = this.config;
        if (!config) return;
        const dsUrl = browserSafeDocumentServerUrl(config.document_server_url);
        const token = typeof config.token === 'string' ? config.token : '';
        if (!dsUrl || !token) {
            this._emitError('bad_config', null);
            return;
        }
        this._clearAllEditorTimers();
        this._destroyEditor();
        this._initializing = true;
        try {
            await this._ensureDocsApi(dsUrl);
            if (typeof window.DocsAPI === 'undefined' || !window.DocsAPI.DocEditor) {
                throw new Error('DocsAPI.DocEditor is not available after api.js load');
            }
            await this.updateComplete;
            await new Promise<unknown>((resolve) => requestAnimationFrame(() => requestAnimationFrame(resolve)));
            const host = this.renderRoot.querySelector('.editor-host');
            const target = this.renderRoot.querySelector('#oo-editor-target');
            if (!host || !target) {
                throw new Error('editor-host or #oo-editor-target not found');
            }
            for (let i = 0; i < 24; i++) {
                const r = host.getBoundingClientRect();
                if (r.width >= 200 && r.height >= 80) break;
                await new Promise<unknown>((resolve) => requestAnimationFrame(resolve));
            }
            target.innerHTML = '';
            _ooEmbedCounter += 1;
            const placeholder = document.createElement('div');
            placeholder.id = `oo-embed-${_ooEmbedCounter}-${Date.now()}`;
            this._startOoLayout(host, placeholder, target);
            this._syncOoLayout();
            const claims = parseJwtPayloadClaims(token);
            const onFatal = (code: string, detail: unknown) => {
                this._clearAllEditorTimers();
                this._destroyEditor();
                this._initializing = false;
                this.requestUpdate();
                this._emitError(code, detail);
            };
            const editorInit = {
                ...claims,
                token,
                type: typeof claims.type === 'string' ? claims.type : 'desktop',
                events: {
                    onAppReady: () => this._markEditorUiVisible(),
                    onDocumentReady: () => this._markEditorUiVisible(),
                    onInfo: () => this._markEditorUiVisible(),
                    onDocumentStateChange: (event: { data?: unknown } | null) => {
                        this._emitDocumentState(Boolean(event && event.data));
                    },
                    onError: (event: { data?: unknown; message?: string } | null) => {
                        const d = event && event.data;
                        let detail = '';
                        if (isPlainRecord(d)) {
                            const code = d.errorCode;
                            const desc = d.errorDescription;
                            if (code != null || desc != null) {
                                detail = [
                                    code != null ? String(code) : '',
                                    desc != null ? String(desc) : '',
                                ].filter(Boolean).join(': ');
                            }
                        }
                        if (!detail) {
                            detail = typeof d === 'string'
                                ? d
                                : (event && typeof event.message === 'string' ? event.message : '');
                        }
                        onFatal('ds_error', detail);
                    },
                },
            };
            this._docEditor = new window.DocsAPI.DocEditor!(placeholder.id, editorInit);
            this._tryReparentOoIframe();
            requestAnimationFrame(() => {
                this._tryReparentOoIframe();
                this._syncOoLayout();
                requestAnimationFrame(() => {
                    this._tryReparentOoIframe();
                    this._syncOoLayout();
                });
            });
            this._uiFallbackTimer = setTimeout(() => {
                this._uiFallbackTimer = null;
                if (this._initializing) {
                    this._initializing = false;
                    this.requestUpdate();
                }
            }, UI_FALLBACK_TIMEOUT_MS);
            this._bootWatchTimer = setTimeout(() => {
                this._bootWatchTimer = null;
                if (!this._initializing) return;
                onFatal('open_timeout', null);
            }, BOOT_WATCH_TIMEOUT_MS);
        } catch (e) {
            const msg = e instanceof Error ? e.message : String(e);
            this._initializing = false;
            this.requestUpdate();
            this._emitError('docs_api', msg);
        }
    }

    override render(): TemplateResult {
        return html`
            <div class="editor-host">
                ${guard(
                    [this._configKey],
                    () => html`<div id="oo-editor-target" class="oo-doc-root" style="width:100%;height:100%;"></div>`,
                )}
                ${this._initializing
                    ? html`<div class="editor-loading-overlay" role="status" aria-live="polite">
                            <slot name="loading">
                                <div class="paper-line w60"></div>
                                <div class="paper-line w80"></div>
                                <div class="paper-line w45"></div>
                                <div class="paper-sheet"></div>
                            </slot>
                        </div>`
                    : nothing}
            </div>
        `;
    }
}

customElements.define('platform-onlyoffice-host', PlatformOnlyOfficeHost);
