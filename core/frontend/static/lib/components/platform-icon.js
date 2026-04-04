/**
 * Platform Icon Component
 * Использует IconService: load() для UI, loadFileIcon() при attribute file-icon
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
            }

            /* Не задавать fill на корне svg: fill наследуется, иначе точки в list.svg и др.
               превращаются в «ободки», а обводка дублирует рамку слота в сайдбаре. */
            :host(:not([colored]):not([file-icon])) svg {
                stroke: currentColor;
                stroke-width: 2;
                stroke-linecap: round;
                stroke-linejoin: round;
            }

            :host([filled]:not([colored]):not([file-icon])) svg {
                fill: currentColor;
                stroke: none;
            }
        `,
    ];

    static properties = {
        name: { type: String },
        size: { type: Number },
        filled: { type: Boolean, reflect: true },
        colored: { type: Boolean, reflect: true },
        /** Иконка из core/.../icons/files_icons (цветная, отдельный кеш в IconService) */
        fileIcon: { type: Boolean, reflect: true, attribute: 'file-icon' },
    };

    constructor() {
        super();
        this.name = '';
        this.size = 20;
        this.filled = false;
        this.colored = false;
        this.fileIcon = false;
        this._svg = '';
    }

    firstUpdated(changedProperties) {
        super.firstUpdated(changedProperties);
        if (this.name && !this._svg) {
            this._loadIcon();
        }
    }

    updated(changedProperties) {
        if (
            (changedProperties.has('name') && this.name) ||
            changedProperties.has('fileIcon')
        ) {
            this._loadIcon();
        }
        if (changedProperties.has('size')) {
            this.style.setProperty('--icon-size', `${this.size}px`);
        }
    }

    async _loadIcon() {
        if (!this.name) {
            this._svg = '';
            this.requestUpdate();
            return;
        }
        try {
            const svg = this.fileIcon
                ? await this.icon.loadFileIcon(this.name)
                : await this.icon.load(this.name);
            this._svg = svg;
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
