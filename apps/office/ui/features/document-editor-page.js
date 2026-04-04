/**
 * OnlyOffice DocsAPI: первый аргумент — строка id элемента в document (getElementById не смотрит в shadow DOM).
 * См. https://api.onlyoffice.com/docs/docs-api/usage-api/config/
 * api.js обычно вставляет iframe под body; опции «родитель — наш div» в API нет — переносим iframe в #oo-editor-target.
 */
import { html, css, nothing } from 'lit';
import { guard } from 'lit/directives/guard.js';
import { PlatformElement } from '@platform/lib/platform-element/index.js';

/**
 * frameEditorId в URL от DS часто без дефисов в UUID, id плейсхолдера — с дефисами.
 * @param {string} id
 */
function ooFrameIdKey(id) {
    if (!id || !id.startsWith('oo-embed-')) {
        return id.toLowerCase();
    }
    return `oo-embed-${id.slice('oo-embed-'.length).replace(/-/g, '').toLowerCase()}`;
}

function parseJwtPayloadClaims(jwt) {
    if (typeof jwt !== 'string' || !jwt.includes('.')) {
        return {};
    }
    try {
        const part = jwt.split('.')[1];
        const b64 = part.replace(/-/g, '+').replace(/_/g, '/');
        const pad = b64.length % 4;
        const padded = pad ? b64 + '='.repeat(4 - pad) : b64;
        const json = atob(padded);
        return JSON.parse(json);
    } catch {
        return {};
    }
}

export class DocumentEditorPage extends PlatformElement {
    static properties = {
        bindingId: { type: String, attribute: 'binding-id' },
        _loadError: { state: true },
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
                border: none;
                border-radius: 0;
                overflow: hidden;
                background: #e8eaed;
                box-shadow: none;
            }
            .editor-loading-overlay {
                position: absolute;
                inset: 0;
                z-index: 50;
                display: flex;
                align-items: center;
                justify-content: center;
                gap: var(--space-3);
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
        this.bindingId = '';
        this._loadError = null;
        this._initializing = true;
        this._docEditor = null;
        /** @type {ReturnType<typeof setTimeout> | null} */
        this._bootWatchTimer = null;
        /** @type {ReturnType<typeof setTimeout> | null} */
        this._uiFallbackTimer = null;
        /** @type {HTMLDivElement | null} */
        this._ooPlaceholder = null;
        /** @type {HTMLElement | null} */
        this._ooAnchor = null;
        /** @type {ResizeObserver | null} */
        this._ooResizeObserver = null;
        /** @type {MutationObserver | null} */
        this._ooIframeAttrObserver = null;
        /** @type {MutationObserver | null} */
        this._ooBodyObserver = null;
        /** @type {HTMLElement | null} */
        this._ooIframeMount = null;
        this._onWinResize = () => {
            requestAnimationFrame(() => this._syncOoLayout());
        };
        /** Событие scroll не всплывает с overflow-контейнеров (например `.main` в office-app). */
        this._onDocScrollCapture = () => {
            requestAnimationFrame(() => this._syncOoLayout());
        };
    }

    updated(changed) {
        super.updated(changed);
        if (changed.has('bindingId') && this.bindingId) {
            void this._bootEditor();
        }
    }

    disconnectedCallback() {
        this._clearAllEditorTimers();
        super.disconnectedCallback();
        this._destroyEditor();
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
        window.removeEventListener('resize', this._onWinResize);
        this._detachOoBodyObserver();
        if (this._ooIframeAttrObserver) {
            this._ooIframeAttrObserver.disconnect();
            this._ooIframeAttrObserver = null;
        }
        if (this._ooResizeObserver) {
            this._ooResizeObserver.disconnect();
            this._ooResizeObserver = null;
        }
        if (this._ooPlaceholder?.parentNode) {
            this._ooPlaceholder.remove();
        }
        this._ooPlaceholder = null;
        this._ooAnchor = null;
        this._ooIframeMount = null;
    }

    /**
     * @returns {HTMLIFrameElement | null}
     */
    _pickFrameEditorIframe() {
        const wantId = this._ooPlaceholder?.id;
        if (!wantId) {
            return document.querySelector('iframe[name="frameEditor"]');
        }
        const key = ooFrameIdKey(wantId);
        const list = document.querySelectorAll('iframe[name="frameEditor"]');
        for (const f of list) {
            const src = f.getAttribute('src');
            if (!src) {
                continue;
            }
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

    /**
     * @param {HTMLIFrameElement} iframe
     */
    _pinIframeToHost(iframe) {
        const imp = 'important';
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
        if (this._ooIframeAttrObserver || !iframe?.isConnected) {
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
        if (!mount?.isConnected) {
            return;
        }
        if (mount.querySelector('iframe[name="frameEditor"]')) {
            this._detachOoBodyObserver();
            return;
        }
        const iframe = this._pickFrameEditorIframe();
        if (!iframe?.isConnected) {
            return;
        }
        if (mount.contains(iframe)) {
            this._detachOoBodyObserver();
            return;
        }
        mount.appendChild(iframe);
        this._detachOoBodyObserver();
    }

    _minimalOoPlaceholderStyle() {
        return [
            'position:absolute',
            'left:0',
            'top:0',
            'width:0',
            'height:0',
            'overflow:hidden',
            'opacity:0',
            'pointer-events:none',
            'clip:rect(0,0,0,0)',
            'border:0',
            'padding:0',
            'margin:0',
        ].join(';');
    }

    _syncOoLayout() {
        this._tryReparentOoIframe();

        const anchor = this._ooAnchor;
        const ph = this._ooPlaceholder;
        const mount = this._ooIframeMount;
        if (!anchor?.isConnected || !ph?.isConnected) {
            return;
        }

        const iframeInMount =
            mount?.isConnected ? mount.querySelector('iframe[name="frameEditor"]') : null;
        if (iframeInMount) {
            ph.style.cssText = this._minimalOoPlaceholderStyle();
            this._pinIframeToHost(iframeInMount);
            this._ensureIframeAttrObserver(iframeInMount);
            return;
        }

        const r = anchor.getBoundingClientRect();
        if (r.width < 4 || r.height < 4) {
            return;
        }
        const left = Math.round(r.left);
        const top = Math.round(r.top);
        const w = Math.round(r.width);
        const h = Math.round(r.height);
        ph.style.cssText = [
            `position:fixed`,
            `left:${left}px`,
            `top:${top}px`,
            `width:${w}px`,
            `height:${h}px`,
            `z-index:40`,
            `opacity:0`,
            `pointer-events:none`,
            `overflow:hidden`,
            `box-sizing:border-box`,
        ].join(';');
        const iframe = this._pickFrameEditorIframe();
        if (iframe) {
            this._pinIframeToViewport(iframe, left, top, w, h);
            this._ensureIframeAttrObserver(iframe);
        }
    }

    /**
     * @param {HTMLElement} anchor — .editor-host
     * @param {HTMLDivElement} placeholder
     * @param {HTMLElement} iframeMountEl — #oo-editor-target
     */
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
        window.addEventListener('resize', this._onWinResize);
        document.addEventListener('scroll', this._onDocScrollCapture, true);
        requestAnimationFrame(() => this._syncOoLayout());
    }

    _destroyEditor() {
        if (this._docEditor && typeof this._docEditor.destroyEditor === 'function') {
            try {
                this._docEditor.destroyEditor();
            } catch {
                /* ignore */
            }
        }
        this._docEditor = null;
        this._teardownOoDom();
        const target = this.renderRoot?.querySelector('#oo-editor-target');
        if (target) {
            target.innerHTML = '';
        }
    }

    /**
     * @param {string} origin
     */
    async _ensureDocsApi(origin) {
        const base = origin.replace(/\/$/, '');
        if (typeof window.DocsAPI !== 'undefined' && window.__ooDocsApiOrigin === base) {
            return;
        }
        if (typeof window.DocsAPI !== 'undefined' && window.__ooDocsApiOrigin !== base) {
            try {
                delete window.DocsAPI;
            } catch {
                /* ignore */
            }
            delete window.__ooDocsApiOrigin;
        }
        const src = `${base}/web-apps/apps/api/documents/api.js`;
        await new Promise((resolve, reject) => {
            const s = document.createElement('script');
            s.src = src;
            s.async = true;
            s.onload = () => {
                window.__ooDocsApiOrigin = base;
                resolve();
            };
            s.onerror = () => reject(new Error(`OnlyOffice api.js: ${src}`));
            document.head.appendChild(s);
        });
    }

    async _bootEditor() {
        const id = (this.bindingId || '').trim();
        if (!id) {
            this._loadError = this.i18n.t('editor.errNoId');
            this._initializing = false;
            this.requestUpdate();
            return;
        }
        this._clearAllEditorTimers();
        this._destroyEditor();
        this._loadError = null;
        this._initializing = true;
        const api = this.services.officeApi;
        if (!api) {
            this._loadError = this.i18n.t('editor.errNoApi');
            this._initializing = false;
            this.requestUpdate();
            return;
        }
        try {
            const cfg = await api.getEditorConfig(id);
            const dsUrl = (cfg.document_server_url || '').trim().replace(/\/$/, '');
            const token = cfg.token;
            if (!dsUrl || !token) {
                throw new Error(this.i18n.t('editor.errBadConfig'));
            }
            await this._ensureDocsApi(dsUrl);
            if (typeof window.DocsAPI === 'undefined' || !window.DocsAPI.DocEditor) {
                throw new Error(this.i18n.t('editor.errDocsApi'));
            }
            await this.updateComplete;
            await new Promise((resolve) =>
                requestAnimationFrame(() => requestAnimationFrame(resolve)),
            );
            const host = this.renderRoot.querySelector('.editor-host');
            const target = this.renderRoot.querySelector('#oo-editor-target');
            if (!host || !target) {
                throw new Error(this.i18n.t('editor.errHost'));
            }
            for (let i = 0; i < 24; i++) {
                const r = host.getBoundingClientRect();
                if (r.width >= 200 && r.height >= 80) {
                    break;
                }
                await new Promise((resolve) => requestAnimationFrame(resolve));
            }
            target.innerHTML = '';
            const frameH = Math.max(480, Math.min(Math.round(window.innerHeight - 140), 920));
            const box = host.getBoundingClientRect();
            const wPx = `${Math.max(320, Math.round(box.width))}px`;
            const hPx = `${Math.max(320, Math.round(box.height > 48 ? box.height : frameH))}px`;
            const placeholder = document.createElement('div');
            placeholder.id = `oo-embed-${id.replace(/[^a-zA-Z0-9_-]/g, '_')}`;
            this._startOoLayout(host, placeholder, target);
            this._syncOoLayout();
            const t = (k) => this.i18n.t(k);
            const onFatal = (message) => {
                this._clearAllEditorTimers();
                this._loadError = message;
                this._initializing = false;
                this._destroyEditor();
                this.error(message);
                this.requestUpdate();
            };
            const claims = parseJwtPayloadClaims(token);
            const editorInit = {
                ...claims,
                token,
                width: wPx,
                height: hPx,
                type: typeof claims.type === 'string' ? claims.type : 'desktop',
                events: {
                    onAppReady: () => this._markEditorUiVisible(),
                    onDocumentReady: () => this._markEditorUiVisible(),
                    onInfo: () => this._markEditorUiVisible(),
                    onError: (event) => {
                        const d = event?.data;
                        let msg = '';
                        if (d != null && typeof d === 'object') {
                            const code = d.errorCode;
                            const desc = d.errorDescription;
                            if (code != null || desc != null) {
                                msg = [code != null ? String(code) : '', desc != null ? String(desc) : '']
                                    .filter(Boolean)
                                    .join(': ');
                            }
                        }
                        if (!msg) {
                            msg =
                                typeof d === 'string'
                                    ? d
                                    : typeof event?.message === 'string'
                                      ? event.message
                                      : t('editor.eventError');
                        }
                        onFatal(msg);
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
            }, 2500);
            this._bootWatchTimer = setTimeout(() => {
                this._bootWatchTimer = null;
                if (!this._initializing) {
                    return;
                }
                onFatal(t('editor.errOpenTimeout'));
            }, 120000);
        } catch (e) {
            const msg = e instanceof Error ? e.message : String(e);
            this._loadError = msg;
            this.error(msg);
        } finally {
            if (!this._docEditor) {
                this._initializing = false;
            }
            this.requestUpdate();
        }
    }

    render() {
        const tr = (k) => this.i18n.t(k);
        return html`
            ${this._loadError
                ? html`<p style="color:var(--text-secondary);margin:0 0 var(--space-3);">${this._loadError}</p>`
                : null}
            <div class="editor-host">
                ${this._loadError
                    ? nothing
                    : guard(
                          [this.bindingId],
                          () => html`
                              <div
                                  id="oo-editor-target"
                                  class="oo-doc-root"
                                  style="width:100%;height:100%;"
                              ></div>
                          `,
                      )}
                ${!this._loadError && this._initializing
                    ? html`
                          <div class="editor-loading-overlay" role="status" aria-live="polite">
                              <span>${tr('editor.loading')}</span>
                          </div>
                      `
                    : null}
            </div>
        `;
    }
}

customElements.define('document-editor-page', DocumentEditorPage);
