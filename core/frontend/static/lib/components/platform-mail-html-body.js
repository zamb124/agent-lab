/**
 * Тело письма: sanitized HTML в iframe или plaintext pre-wrap.
 */
import { html, css, nothing } from 'lit';
import { unsafeHTML } from 'lit/directives/unsafe-html.js';
import { PlatformElement } from '../platform-element/index.js';
import {
    autolinkPlaintext,
    hasRemoteImages,
    mailIframeSandbox,
    sanitizeMailHtml,
} from '../utils/mail-html.js';
import './platform-button.js';

export class PlatformMailHtmlBody extends PlatformElement {
    static i18nNamespace = 'mail';

    static properties = {
        html: { type: String },
        text: { type: String },
        cidMap: { attribute: false },
        _remoteUnlocked: { state: true },
    };

    static styles = [
        PlatformElement.styles,
        css`
            :host {
                display: block;
                min-width: 0;
            }

            .mail-html-banner {
                display: flex;
                flex-wrap: wrap;
                align-items: center;
                gap: var(--space-2);
                margin-bottom: var(--space-2);
                padding: 8px 10px;
                border-radius: var(--radius-md);
                border: 1px solid var(--border-subtle);
                background: var(--bg-elevated);
                color: var(--text-secondary);
                font-size: 0.8125rem;
            }

            .mail-html-frame {
                display: block;
                width: 100%;
                border: 0;
                background: #ffffff;
                min-height: 40px;
            }

            .mail-plain {
                margin: 0;
                white-space: pre-wrap;
                overflow-wrap: anywhere;
                word-break: break-word;
                max-width: 72ch;
                color: var(--text-primary);
                font-size: 0.9375rem;
                line-height: 1.55;
            }

            .mail-plain a {
                color: var(--accent);
            }
        `,
    ];

    constructor() {
        super();
        this.html = '';
        this.text = '';
        this.cidMap = {};
        this._remoteUnlocked = false;
        this._iframeResizeObserver = null;
    }

    disconnectedCallback() {
        this._disconnectIframeObserver();
        super.disconnectedCallback();
    }

    _disconnectIframeObserver() {
        if (this._iframeResizeObserver !== null) {
            this._iframeResizeObserver.disconnect();
            this._iframeResizeObserver = null;
        }
    }

    _requireBodyStrings() {
        if (typeof this.html !== 'string') {
            throw new Error('platform-mail-html-body: html string required');
        }
        if (typeof this.text !== 'string') {
            throw new Error('platform-mail-html-body: text string required');
        }
        if (this.cidMap === null || typeof this.cidMap !== 'object' || Array.isArray(this.cidMap)) {
            throw new Error('platform-mail-html-body: cidMap object required');
        }
    }

    _onLoadImages() {
        this._remoteUnlocked = true;
    }

    _onIframeLoad(event) {
        const iframe = event.currentTarget;
        if (!(iframe instanceof HTMLIFrameElement)) {
            throw new Error('platform-mail-html-body: iframe load target required');
        }
        this._syncIframeHeight(iframe);
    }

    _syncIframeHeight(iframe) {
        const doc = iframe.contentDocument;
        if (doc === null || doc.documentElement === null) {
            return;
        }
        const apply = () => {
            const bodyHeight = doc.body !== null ? doc.body.scrollHeight : 0;
            const height = Math.max(doc.documentElement.scrollHeight, bodyHeight, 40);
            iframe.style.height = `${height}px`;
        };
        apply();
        for (const img of doc.images) {
            img.addEventListener('load', apply);
        }
        this._disconnectIframeObserver();
        if (typeof ResizeObserver !== 'function') {
            return;
        }
        this._iframeResizeObserver = new ResizeObserver(apply);
        this._iframeResizeObserver.observe(doc.documentElement);
        if (doc.body !== null) {
            this._iframeResizeObserver.observe(doc.body);
        }
    }

    render() {
        this._requireBodyStrings();
        const bodyHtml = this.html;
        const bodyText = this.text;
        if (bodyHtml.length === 0 && bodyText.length === 0) {
            return nothing;
        }
        if (bodyHtml.length > 0) {
            const allowRemoteImages = this._remoteUnlocked === true;
            const srcdoc = sanitizeMailHtml(bodyHtml, {
                allowRemoteImages,
                cidMap: this.cidMap,
            });
            const showBanner = !allowRemoteImages && hasRemoteImages(bodyHtml);
            return html`
                ${showBanner
                    ? html`
                        <div class="mail-html-banner">
                            <span>${this.t('images_blocked_hint')}</span>
                            <platform-button
                                variant="secondary"
                                density="compact"
                                @click=${this._onLoadImages}
                            >
                                ${this.t('load_images')}
                            </platform-button>
                        </div>
                    `
                    : nothing}
                <iframe
                    class="mail-html-frame"
                    sandbox=${mailIframeSandbox()}
                    referrerpolicy="no-referrer"
                    title=${this.t('html_frame_title')}
                    .srcdoc=${srcdoc}
                    @load=${this._onIframeLoad}
                ></iframe>
            `;
        }
        return html`
            <div class="mail-plain">${unsafeHTML(autolinkPlaintext(bodyText))}</div>
        `;
    }
}

customElements.define('platform-mail-html-body', PlatformMailHtmlBody);
