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
import { PlatformElement } from '@platform/lib/platform-element/index.js';

const BOOT_WATCH_TIMEOUT_MS = 120_000;
const UI_FALLBACK_TIMEOUT_MS = 2_500;
const ONLYOFFICE_IFRAME_ALLOW_FEATURES = ['clipboard-read', 'clipboard-write', 'fullscreen', 'unload'];

function ooFrameIdKey(id) {
    if (!id || !id.startsWith('oo-embed-')) {
        return id.toLowerCase();
    }
    return `oo-embed-${id.slice('oo-embed-'.length).replace(/-/g, '').toLowerCase()}`;
}

function parseJwtPayloadClaims(jwt) {
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
    const claims = JSON.parse(json);
    if (!claims || typeof claims !== 'object' || Array.isArray(claims)) {
        throw new Error('parseJwtPayloadClaims: payload is not a JSON object');
    }
    return claims;
}

function ensureOnlyOfficeIframePermissions(iframe) {
    if (!iframe) {
        return;
    }
    const entries = (iframe.getAttribute('allow') || '')
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

let _ooEmbedCounter = 0;

export class OnlyOfficeHost extends PlatformElement {
    static properties = {
        config: { type: Object },
        bindingId: { type: String, attribute: 'binding-id' },
        _initializing: { state: true },
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
                background: #e8eaed;
                overflow: hidden;
            }
            .editor-loading-overlay {
                position: absolute;
                inset: 0;
                z-index: 50;
                display: flex;
                align-items: center;
                justify-content: center;
                background: rgba(232, 234, 237, 0.85);
                color: var(--text-secondary);
                font-size: var(--text-sm);
                pointer-events: none;
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
        this.bindingId = '';
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

    updated(changed) {
        super.updated(changed);
        if (changed.has('config') && this.config) {
            const key = this._computeConfigKey(this.config);
            if (key !== this._configKey) {
                this._configKey = key;
                void this._bootEditor();
            }
        }
    }

    disconnectedCallback() {
        this._clearAllEditorTimers();
        super.disconnectedCallback();
        this._destroyEditor();
    }

    _computeConfigKey(config) {
        if (!config || typeof config !== 'object') return null;
        const ds = typeof config.document_server_url === 'string' ? config.document_server_url : '';
        const token = typeof config.token === 'string' ? config.token : '';
        if (token.length > 0) return `${ds}#${token}`;
        return ds;
    }

    _emitError(code, detail) {
        this.emit('editor-error', { code, detail });
    }

    _emitDocumentState(dirty) {
        const bindingId = typeof this.bindingId === 'string' && this.bindingId.length > 0
            ? this.bindingId
            : (typeof this.config?.document?.key === 'string' ? this.config.document.key : '');
        if (!bindingId || typeof window === 'undefined' || window.parent === window) {
            return;
        }
        window.parent.postMessage(
            {
                type: 'platform.office.document-state',
                bindingId,
                dirty: Boolean(dirty),
                sentAt: Date.now(),
            },
            window.location.origin,
        );
    }

    _clearBootWatch() {
        if (this._bootWatchTimer != null) {
            clearTimeout(this._bootWatchTimer);
            this._bootWatchTimer = null;
        }
    }

    _clearAllEditorTimers() {
        this._clearBootWatch();
        if (this._uiFallbackTimer != null) {
            clearTimeout(this._uiFallbackTimer);
            this._uiFallbackTimer = null;
        }
    }

    _markEditorUiVisible() {
        this._clearAllEditorTimers();
        this._initializing = false;
        this.requestUpdate();
    }

    _detachOoBodyObserver() {
        if (this._ooBodyObserver) {
            this._ooBodyObserver.disconnect();
            this._ooBodyObserver = null;
        }
    }

    _teardownOoDom() {
        document.removeEventListener('scroll', this._onDocScrollCapture, true);
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

    _pickFrameEditorIframe() {
        const wantId = this._ooPlaceholder ? this._ooPlaceholder.id : null;
        if (!wantId) {
            return document.querySelector('iframe[name="frameEditor"]');
        }
        const key = ooFrameIdKey(wantId);
        const list = document.querySelectorAll('iframe[name="frameEditor"]');
        for (const f of list) {
            const src = f.getAttribute('src');
            if (!src) continue;
            try {
                const u = new URL(src, document.baseURI);
                const fid = u.searchParams.get('frameEditorId');
                if (fid && ooFrameIdKey(fid) === key) {
                    return f;
                }
            } catch {
                continue;
            }
        }
        return list.length === 1 ? list[0] : null;
    }

    _pinIframeToHost(iframe) {
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

    _pinIframeToViewport(iframe, left, top, w, h) {
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

    _ensureIframeAttrObserver(iframe) {
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

    _tryReparentOoIframe() {
        const mount = this._ooIframeMount;
        if (!(mount && mount.isConnected)) return;
        if (mount.querySelector('iframe[name="frameEditor"]')) {
            this._detachOoBodyObserver();
            return;
        }
        const iframe = this._pickFrameEditorIframe();
        if (!(iframe && iframe.isConnected)) return;
        if (mount.contains(iframe)) {
            this._detachOoBodyObserver();
            return;
        }
        mount.appendChild(iframe);
        this._detachOoBodyObserver();
    }

    _minimalOoPlaceholderStyle() {
        return [
            'position:absolute', 'left:0', 'top:0', 'width:0', 'height:0',
            'overflow:hidden', 'opacity:0', 'pointer-events:none',
            'clip:rect(0,0,0,0)', 'border:0', 'padding:0', 'margin:0',
        ].join(';');
    }

    _syncOoLayout() {
        this._tryReparentOoIframe();
        const anchor = this._ooAnchor;
        const ph = this._ooPlaceholder;
        const mount = this._ooIframeMount;
        if (!(anchor && anchor.isConnected) || !(ph && ph.isConnected)) return;
        const iframeInMount = mount && mount.isConnected
            ? mount.querySelector('iframe[name="frameEditor"]')
            : null;
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

    _startOoLayout(anchor, placeholder, iframeMountEl) {
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
        document.addEventListener('scroll', this._onDocScrollCapture, true);
        requestAnimationFrame(() => this._syncOoLayout());
    }

    _destroyEditor() {
        if (this._docEditor && typeof this._docEditor.destroyEditor === 'function') {
            try { this._docEditor.destroyEditor(); } catch { /* ignore */ }
        }
        this._docEditor = null;
        this._teardownOoDom();
        const target = this.renderRoot ? this.renderRoot.querySelector('#oo-editor-target') : null;
        if (target) target.innerHTML = '';
    }

    async _injectOoScript(scriptSrc, logicalDsOrigin) {
        const base = logicalDsOrigin.replace(/\/$/, '');
        if (typeof window.DocsAPI !== 'undefined' && window.__ooDocsApiOrigin === base) {
            return;
        }
        if (typeof window.DocsAPI !== 'undefined' && window.__ooDocsApiOrigin !== base) {
            try { delete window.DocsAPI; } catch { /* ignore */ }
            delete window.__ooDocsApiOrigin;
        }
        await new Promise((resolve, reject) => {
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

    async _ensureDocsApi(dsOrigin) {
        const ds = dsOrigin.replace(/\/$/, '');
        await this._injectOoScript(`${ds}/web-apps/apps/api/documents/api.js`, ds);
    }

    async _bootEditor() {
        const config = this.config;
        if (!config) return;
        const dsUrl = typeof config.document_server_url === 'string'
            ? config.document_server_url.trim().replace(/\/$/, '')
            : '';
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
            await new Promise((resolve) => requestAnimationFrame(() => requestAnimationFrame(resolve)));
            const host = this.renderRoot.querySelector('.editor-host');
            const target = this.renderRoot.querySelector('#oo-editor-target');
            if (!host || !target) {
                throw new Error('editor-host or #oo-editor-target not found');
            }
            for (let i = 0; i < 24; i++) {
                const r = host.getBoundingClientRect();
                if (r.width >= 200 && r.height >= 80) break;
                await new Promise((resolve) => requestAnimationFrame(resolve));
            }
            target.innerHTML = '';
            _ooEmbedCounter += 1;
            const placeholder = document.createElement('div');
            placeholder.id = `oo-embed-${_ooEmbedCounter}-${Date.now()}`;
            this._startOoLayout(host, placeholder, target);
            this._syncOoLayout();
            const claims = parseJwtPayloadClaims(token);
            const onFatal = (code, detail) => {
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
                    onDocumentStateChange: (event) => {
                        this._emitDocumentState(Boolean(event && event.data));
                    },
                    onError: (event) => {
                        const d = event && event.data;
                        let detail = '';
                        if (d != null && typeof d === 'object') {
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
            this._docEditor = new window.DocsAPI.DocEditor(placeholder.id, editorInit);
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

    render() {
        return html`
            <div class="editor-host">
                ${guard(
                    [this._configKey],
                    () => html`<div id="oo-editor-target" class="oo-doc-root" style="width:100%;height:100%;"></div>`,
                )}
                ${this._initializing
                    ? html`<div class="editor-loading-overlay" role="status" aria-live="polite">
                            <slot name="loading">…</slot>
                        </div>`
                    : nothing}
            </div>
        `;
    }
}

customElements.define('onlyoffice-host', OnlyOfficeHost);
