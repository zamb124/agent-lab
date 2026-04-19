/**
 * Версия деплоя — берётся из state.pwa.deploymentVersion (заполняется pwa.effect).
 * Атрибут base-url принимается для совместимости с шаблонами; реально не используется.
 */
import { html, css } from 'lit';
import { PlatformElement } from '../platform-element/index.js';

export class PlatformDeploymentVersion extends PlatformElement {
    static properties = {
        baseUrl: { attribute: 'base-url' },
        footer: { type: Boolean, reflect: true },
    };

    static styles = [
        PlatformElement.styles,
        css`
            :host { display: block; }
            :host([footer]) { width: 100%; }
            .line {
                font-size: 10px; line-height: 1.3;
                color: var(--text-muted);
                font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
                padding: 2px 0 6px 0;
                word-break: break-all;
            }
            :host([footer]) .line { text-align: center; padding: 2px 0 0 0; }
        `,
    ];

    constructor() {
        super();
        this.baseUrl = '';
        this.footer = false;
        this._versionSel = this.select((s) => s.pwa.deploymentVersion);
    }

    render() {
        const raw = this._versionSel.value;
        if (!raw) return html``;
        const text = raw.length > 12 ? raw.slice(0, 7) : raw;
        return html`<div class="line" title=${raw}>${text}</div>`;
    }
}

customElements.define('platform-deployment-version', PlatformDeploymentVersion);
