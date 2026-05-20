/**
 * PlatformButton — унифицированная кнопка платформы
 * Варианты: primary (violet), accent (orange), secondary, danger, ghost
 */
import { html, css, nothing } from 'lit';
import { PlatformElement } from '../platform-element/index.js';

export class PlatformButton extends PlatformElement {
    static styles = css`
        :host {
            display: inline-flex;
        }

        :host([icon-only]) {
            flex: 0 0 auto;
        }
        
        button {
            display: inline-flex;
            align-items: center;
            justify-content: center;
            gap: var(--space-2, 8px);
            padding: var(--btn-padding, 8px 24px);
            font-size: var(--btn-font-size, 16px);
            font-weight: var(--btn-font-weight, 400);
            font-family: inherit;
            line-height: var(--btn-line-height, 20px);
            border-radius: var(--btn-radius, 22px);
            border: none;
            cursor: pointer;
            transition: var(--motion-transition-interactive);
            white-space: nowrap;
            box-sizing: border-box;
        }

        :host([density="compact"]) button {
            padding: var(--btn-padding, 6px 14px);
            font-size: var(--btn-font-size, var(--text-sm, 14px));
        }

        :host([density="dense"]) button {
            padding: var(--btn-padding, 4px 10px);
            font-size: var(--btn-font-size, var(--text-xs, 12px));
        }

        :host([icon-only]) button {
            width: var(--platform-button-icon-size, 36px);
            min-width: var(--platform-button-icon-size, 36px);
            height: var(--platform-button-icon-size, 36px);
            padding: 0;
            border-radius: var(--platform-button-icon-radius, var(--radius-full, 999px));
            line-height: 1;
        }

        :host([icon-only][density="compact"]) {
            --platform-button-icon-size: 32px;
        }

        :host([icon-only][density="dense"]) {
            --platform-button-icon-size: 28px;
        }
        
        button:disabled {
            opacity: 0.5;
            cursor: not-allowed;
        }
        
        /* Primary — violet */
        button.primary {
            color: var(--platform-btn-primary-text, #ffffff);
            background: var(--platform-btn-primary-bg, #99A6F9);
            box-shadow: var(--platform-btn-primary-shadow, none);
        }

        button.primary:hover:not(:disabled) {
            background: var(--platform-btn-primary-bg-hover, #8794F0);
            box-shadow: var(--platform-btn-primary-shadow-hover, 0 0 10px rgba(153, 166, 249, 0.6));
        }

        /* Accent — orange */
        button.accent {
            color: var(--platform-btn-accent-text, #ffffff);
            background: var(--platform-btn-accent-bg, #FF885C);
            box-shadow: var(--platform-btn-accent-shadow, none);
        }

        button.accent:hover:not(:disabled) {
            background: var(--platform-btn-accent-bg-hover, #F2784A);
            box-shadow: var(--platform-btn-accent-shadow-hover, 0 0 10px rgba(255, 136, 92, 0.6));
        }
        
        /* Secondary */
        button.secondary {
            color: var(--platform-btn-secondary-text, #99A6F9);
            background: var(--platform-btn-secondary-bg, rgba(153, 166, 249, 0.15));
            border: none;
        }
        
        button.secondary:hover:not(:disabled) {
            background: var(--platform-btn-secondary-bg-hover, rgba(153, 166, 249, 0.1));
            box-shadow: var(--platform-btn-secondary-shadow-hover, 0 0 10px rgba(153, 166, 249, 0.2));
        }
        
        /* Danger */
        button.danger {
            color: white;
            background: var(--error, #f43f5e);
        }
        
        button.danger:hover:not(:disabled) {
            background: #e11d48;
            box-shadow: 0 0 10px rgba(244, 63, 94, 0.4);
        }
        
        /* Ghost */
        button.ghost {
            color: var(--text-secondary, rgba(255, 255, 255, 0.65));
            background: transparent;
        }
        
        button.ghost:hover:not(:disabled) {
            color: var(--text-primary, rgba(255, 255, 255, 0.95));
            background: var(--glass-tint-subtle, rgba(255, 255, 255, 0.04));
        }
        
        /* Светлая тема */
        :host-context([data-theme="light"]) button.secondary {
            color: var(--platform-btn-secondary-text, #8794F0);
            background: var(--platform-btn-secondary-bg, rgba(135, 148, 240, 0.12));
        }
        
        :host-context([data-theme="light"]) button.secondary:hover:not(:disabled) {
            background: var(--platform-btn-secondary-bg-hover, rgba(135, 148, 240, 0.08));
        }
        
        :host-context([data-theme="light"]) button.ghost {
            color: var(--text-secondary, #475569);
        }
        
        :host-context([data-theme="light"]) button.ghost:hover:not(:disabled) {
            color: var(--text-primary, #1e293b);
            background: var(--glass-tint-subtle, rgba(0, 0, 0, 0.02));
        }
    `;

    static properties = {
        variant: { type: String },
        disabled: { type: Boolean },
        loading: { type: Boolean },
        type: { type: String },
        density: { type: String, reflect: true },
        iconOnly: { type: Boolean, attribute: 'icon-only', reflect: true },
        ariaLabel: { type: String, attribute: 'aria-label' },
        primary: { type: Boolean, reflect: true },
        accent: { type: Boolean, reflect: true },
        secondary: { type: Boolean, reflect: true },
        danger: { type: Boolean, reflect: true },
        ghost: { type: Boolean, reflect: true },
    };

    constructor() {
        super();
        this.variant = 'primary';
        this.disabled = false;
        this.loading = false;
        this.type = 'button';
        this.density = 'default';
        this.iconOnly = false;
        this.ariaLabel = '';
        this.primary = false;
        this.accent = false;
        this.secondary = false;
        this.danger = false;
        this.ghost = false;
    }

    _effectiveVariant() {
        if (this.danger) return 'danger';
        if (this.accent) return 'accent';
        if (this.secondary) return 'secondary';
        if (this.ghost) return 'ghost';
        if (this.primary) return 'primary';
        return this.variant;
    }

    render() {
        const label =
            typeof this.ariaLabel === 'string' && this.ariaLabel.length > 0
                ? this.ariaLabel
                : (typeof this.title === 'string' && this.title.length > 0 ? this.title : '');
        return html`
            <button 
                type="${this.type}"
                class="${this._effectiveVariant()}"
                aria-label=${label.length > 0 ? label : nothing}
                title=${label.length > 0 ? label : nothing}
                ?disabled=${this.disabled || this.loading}
            >
                ${this.loading ? html`<span>...</span>` : ''}
                <slot></slot>
            </button>
        `;
    }
}

customElements.define('platform-button', PlatformButton);
