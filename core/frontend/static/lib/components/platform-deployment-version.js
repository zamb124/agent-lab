/**
 * Версия деплоя из GET {baseUrl}/health (поле deployment_version).
 * Атрибут base-url совпадает с getBaseUrl() приложения: /sync, /crm, …
 */
import { html, css } from 'lit';
import { PlatformElement } from '../platform-element/index.js';

export class PlatformDeploymentVersion extends PlatformElement {
    static properties = {
        baseUrl: { attribute: 'base-url' },
        footer: { type: Boolean, reflect: true },
        _text: { state: true },
        _title: { state: true },
    };

    static styles = [
        PlatformElement.styles,
        css`
            :host {
                display: block;
            }
            :host([footer]) {
                width: 100%;
            }
            .line {
                font-size: 10px;
                line-height: 1.3;
                color: var(--text-muted);
                font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
                padding: 2px 0 6px 0;
                word-break: break-all;
            }
            :host([footer]) .line {
                text-align: center;
                padding: 2px 0 0 0;
            }
        `,
    ];

    constructor() {
        super();
        this.baseUrl = '';
        this.footer = false;
        this._text = '';
        this._title = '';
    }

    connectedCallback() {
        super.connectedCallback();
        this._load();
    }

    async _load() {
        const trimmed = (this.baseUrl || '').trim().replace(/\/$/, '');
        const url = trimmed ? `${trimmed}/health` : '/health';
        try {
            const res = await fetch(url, { credentials: 'same-origin' });
            if (!res.ok) {
                return;
            }
            const data = await res.json();
            const raw = data.deployment_version;
            if (typeof raw !== 'string' || raw.length === 0) {
                return;
            }
            this._title = raw;
            this._text = raw.length > 12 ? raw.slice(0, 7) : raw;
        } catch {
            return;
        }
    }

    render() {
        if (!this._text) {
            return html``;
        }
        return html`<div class="line" title=${this._title}>${this._text}</div>`;
    }
}

customElements.define('platform-deployment-version', PlatformDeploymentVersion);
