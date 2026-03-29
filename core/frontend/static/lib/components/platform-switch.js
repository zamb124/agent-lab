import { html, css } from 'lit';
import { PlatformElement } from '../platform-element/index.js';

export class PlatformSwitch extends PlatformElement {
    static properties = {
        checked: { type: Boolean, reflect: true },
        disabled: { type: Boolean, reflect: true },
        label: { type: String },
        size: { type: String, reflect: true },
    };

    static styles = [
        PlatformElement.styles,
        css`
            :host {
                display: inline-flex;
                align-items: center;
                gap: var(--space-2);
            }

            .switch {
                position: relative;
                width: 44px;
                height: 26px;
                border: none;
                border-radius: var(--radius-full, 999px);
                padding: 0;
                background: var(--glass-tint-strong, rgba(255, 255, 255, 0.12));
                cursor: pointer;
                transition: background var(--duration-fast, 0.2s) ease;
                flex-shrink: 0;
            }

            .switch::after {
                content: '';
                position: absolute;
                top: 3px;
                left: 3px;
                width: 20px;
                height: 20px;
                border-radius: 50%;
                background: #fff;
                box-shadow: 0 1px 4px rgba(0, 0, 0, 0.25);
                transition: transform var(--duration-fast, 0.2s) ease;
            }

            :host([checked]) .switch {
                background: var(--accent-gradient, linear-gradient(135deg, #14B8A6 0%, #0EA5A4 100%));
            }

            :host([checked]) .switch::after {
                transform: translateX(18px);
            }

            :host([size="sm"]) .switch {
                width: 36px;
                height: 20px;
            }

            :host([size="sm"]) .switch::after {
                width: 14px;
                height: 14px;
                top: 3px;
                left: 3px;
            }

            :host([size="sm"][checked]) .switch::after {
                transform: translateX(16px);
            }

            .label {
                font-size: var(--text-sm);
                color: var(--text-primary);
                user-select: none;
            }

            :host([disabled]) .switch {
                opacity: 0.45;
                cursor: not-allowed;
            }

            .switch:focus-visible {
                outline: 2px solid var(--accent, #99a6f9);
                outline-offset: 2px;
            }
        `,
    ];

    constructor() {
        super();
        this.checked = false;
        this.disabled = false;
        this.label = '';
        this.size = 'md';
    }

    _toggle() {
        if (this.disabled) {
            return;
        }
        this.checked = !this.checked;
        this.dispatchEvent(new CustomEvent('change', {
            detail: { value: this.checked },
            bubbles: true,
            composed: true,
        }));
    }

    render() {
        return html`
            <button
                type="button"
                class="switch"
                role="switch"
                aria-checked=${this.checked ? 'true' : 'false'}
                ?disabled=${this.disabled}
                @click=${this._toggle}
            ></button>
            ${this.label ? html`<span class="label">${this.label}</span>` : ''}
        `;
    }
}

customElements.define('platform-switch', PlatformSwitch);
