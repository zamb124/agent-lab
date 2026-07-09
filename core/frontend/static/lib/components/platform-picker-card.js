/**
 * platform-picker-card — selectable glass card для picker modals (policy, preset, library).
 */
import { html, css, nothing } from 'lit';
import { PlatformElement } from '../platform-element/index.js';
import { glassStyles } from '../styles/shared/glass.styles.js';
import './platform-icon.js';

export class PlatformPickerCard extends PlatformElement {
    static properties = {
        selected: { type: Boolean, reflect: true },
        icon: { type: String },
        title: { type: String },
        subtitle: { type: String },
        value: { type: String },
        disabled: { type: Boolean, reflect: true },
    };

    static styles = [
        PlatformElement.styles,
        glassStyles,
        css`
            :host {
                display: block;
                min-width: 0;
            }

            .picker-card {
                display: flex;
                flex-direction: column;
                align-items: flex-start;
                gap: var(--space-2);
                width: 100%;
                height: 100%;
                box-sizing: border-box;
                padding: var(--platform-picker-card-padding, var(--space-4, 1rem));
                border-radius: var(--radius-xl);
                text-align: left;
                cursor: pointer;
                color: inherit;
                font: inherit;
                min-width: 0;
                overflow: hidden;
            }

            :host([disabled]) .picker-card {
                opacity: 0.45;
                cursor: not-allowed;
                pointer-events: none;
            }

            :host([selected]) .picker-card {
                border-color: color-mix(in srgb, var(--accent), transparent 40%);
                background: color-mix(in srgb, var(--accent-subtle), var(--glass-solid-subtle) 55%);
                box-shadow: var(--glass-shadow-medium), 0 0 0 1px color-mix(in srgb, var(--accent), transparent 55%);
            }

            .picker-icon {
                width: 44px;
                height: 44px;
                display: inline-flex;
                align-items: center;
                justify-content: center;
                border-radius: var(--radius-lg);
                background: var(--glass-solid-medium);
                color: var(--accent);
                flex-shrink: 0;
            }

            .picker-icon ::slotted(svg) {
                width: 28px;
                height: 28px;
            }

            .picker-title {
                font-size: var(--text-sm);
                font-weight: var(--font-semibold);
                color: var(--text-primary);
                width: 100%;
                min-width: 0;
                word-break: break-word;
            }

            .picker-subtitle {
                font-size: var(--text-xs);
                line-height: 1.45;
                color: var(--text-secondary);
                width: 100%;
                min-width: 0;
                word-break: break-word;
            }

            ::slotted(:not([slot='icon'])) {
                width: 100%;
                min-width: 0;
            }
        `,
    ];

    constructor() {
        super();
        this.selected = false;
        this.icon = '';
        this.title = '';
        this.subtitle = '';
        this.value = '';
        this.disabled = false;
    }

    _onActivate(event) {
        if (this.disabled) {
            return;
        }
        event.preventDefault();
        this.emit('select', { value: this.value });
    }

    _onClick(event) {
        this._onActivate(event);
    }

    _onKeydown(event) {
        if (event.key !== 'Enter' && event.key !== ' ') {
            return;
        }
        this._onActivate(event);
    }

    render() {
        const iconSlot = html`
            <div class="picker-icon">
                <slot name="icon">
                    ${this.icon.length > 0
                        ? html`<platform-icon name=${this.icon} size="22"></platform-icon>`
                        : nothing}
                </slot>
            </div>
        `;

        return html`
            <article
                class="picker-card glass-subtle glass-interactive"
                tabindex=${this.disabled ? '-1' : '0'}
                role="button"
                aria-pressed=${this.selected ? 'true' : 'false'}
                @click=${this._onClick}
                @keydown=${this._onKeydown}
            >
                ${iconSlot}
                <div class="picker-title">${this.title}</div>
                ${this.subtitle.length > 0
                    ? html`<div class="picker-subtitle">${this.subtitle}</div>`
                    : nothing}
                <slot></slot>
            </article>
        `;
    }
}

customElements.define('platform-picker-card', PlatformPickerCard);
