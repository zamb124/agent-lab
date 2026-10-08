/**
 * Единый спиннер платформы.
 * Вращающийся логотип Linnex. Заменяет glass-spinner и app-loader.
 */
import { html, css } from '../lit-shim.js';
import type { CSSResultGroup, PropertyDeclarations, TemplateResult } from '../lit-shim.js';
import { PlatformElement } from '../platform-element/index.js';

const SPINNER_LOGO_SRC = '/static/core/assets/service_logos/linnex_spinner_logo.png';

const SIZE_PX: Record<string, number> = {
    xs: 32,
    sm: 40,
    md: 48,
    lg: 64,
    xl: 96,
};

export class PlatformSpinner extends PlatformElement {
    static override styles: CSSResultGroup = [
        PlatformElement.styles,
        css`
            :host {
                display: inline-flex;
                align-items: center;
                justify-content: center;
                flex-shrink: 0;
                vertical-align: middle;
            }

            .spinner-logo {
                width: var(--spinner-size, 24px);
                height: var(--spinner-size, 24px);
                min-width: var(--spinner-size, 24px);
                min-height: var(--spinner-size, 24px);
                object-fit: contain;
                display: block;
                animation: platform-spin var(--spinner-duration, 1.2s) linear infinite;
                transform-origin: center center;
                will-change: transform;
            }

            .spinner-text {
                margin-top: 16px;
                font-family: var(--font-sans);
                font-size: 14px;
                font-weight: 500;
                color: var(--text-secondary, rgba(255, 255, 255, 0.5));
                letter-spacing: 0.05em;
                text-align: center;
            }

            :host([fullscreen]) {
                position: fixed;
                inset: 0;
                z-index: 9999;
                flex-direction: column;
                background: #0F0F0F;
                transition: opacity 0.4s cubic-bezier(0.4, 0, 0.2, 1);
            }

            :host([fullscreen]) .spinner-logo {
                width: 192px;
                height: 192px;
                min-width: 192px;
                min-height: 192px;
            }

            :host(.hidden) {
                opacity: 0;
                pointer-events: none;
            }

            :host([overlay]) {
                position: absolute;
                inset: 0;
                z-index: 20;
                flex-direction: column;
                background: var(--spinner-overlay-bg, rgba(15, 15, 15, 0.55));
                backdrop-filter: blur(2px);
            }

            @keyframes platform-spin {
                to {
                    transform: rotate(360deg);
                }
            }

            @media (prefers-reduced-motion: reduce) {
                .spinner-logo {
                    animation: none;
                }
            }
        `,
    ];

    static override properties: PropertyDeclarations = {
        size: { type: String },
        text: { type: String },
        fullscreen: { type: Boolean, reflect: true },
        overlay: { type: Boolean, reflect: true },
    };

    declare size: string;
    declare text: string;
    declare fullscreen: boolean;
    declare overlay: boolean;

    constructor() {
        super();
        this.size = 'md';
        this.text = '';
        this.fullscreen = false;
        this.overlay = false;
    }

    override updated(): void {
        const sizeKey = this.size;
        const namedPx = SIZE_PX[sizeKey];
        if (namedPx) {
            this.style.setProperty('--spinner-size', `${namedPx}px`);
            return;
        }
        const numericPx = Number(sizeKey);
        if (Number.isFinite(numericPx) && numericPx > 0) {
            this.style.setProperty('--spinner-size', `${numericPx}px`);
        }
    }

    _logoSrc(): string {
        const hostWithOrigin = this.closest('[platform-ui-origin]');
        const rawOrigin =
            hostWithOrigin instanceof HTMLElement
                ? hostWithOrigin.getAttribute('platform-ui-origin')
                : null;
        const origin =
            typeof rawOrigin === 'string' ? rawOrigin.trim().replace(/\/+$/, '') : '';
        return origin !== '' ? `${origin}${SPINNER_LOGO_SRC}` : SPINNER_LOGO_SRC;
    }

    override render(): TemplateResult {
        return html`
            <img class="spinner-logo" src="${this._logoSrc()}" alt="" aria-hidden="true" draggable="false" />
            ${this.text ? html`<div class="spinner-text">${this.text}</div>` : ''}
        `;
    }
}

customElements.define('platform-spinner', PlatformSpinner);
