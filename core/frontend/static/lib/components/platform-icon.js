/**
 * Platform Icon Component
 * Использует IconService для загрузки иконок
 */
import { html, css } from 'lit';
import { unsafeHTML } from 'lit/directives/unsafe-html.js';
import { PlatformElement } from '../platform-element/index.js';

export class PlatformIcon extends PlatformElement {
    static styles = [
        PlatformElement.styles,
        css`
            :host {
                display: inline-flex;
                align-items: center;
                justify-content: center;
                width: var(--icon-size, 20px);
                height: var(--icon-size, 20px);
                color: inherit;
            }
            
            svg {
                width: 100%;
                height: 100%;
                fill: none;
                stroke: currentColor;
                stroke-width: 2;
                stroke-linecap: round;
                stroke-linejoin: round;
            }
            
            :host([filled]) svg {
                fill: currentColor;
                stroke: none;
            }
        `
    ];

    static properties = {
        name: { type: String },
        size: { type: Number },
        filled: { type: Boolean, reflect: true },
    };

    constructor() {
        super();
        this.name = '';
        this.size = 20;
        this.filled = false;
        this._svg = '';
    }

    updated(changedProperties) {
        if (changedProperties.has('name') && this.name) {
            this._loadIcon();
        }
        if (changedProperties.has('size')) {
            this.style.setProperty('--icon-size', `${this.size}px`);
        }
    }

    async _loadIcon() {
        try {
            this._svg = await this.icon.load(this.name);
            this.requestUpdate();
        } catch (error) {
            console.error(`Failed to load icon "${this.name}":`, error);
            this._svg = '';
        }
    }

    render() {
        return html`${unsafeHTML(this._svg)}`;
    }
}

customElements.define('platform-icon', PlatformIcon);

