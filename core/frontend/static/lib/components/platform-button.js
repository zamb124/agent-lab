/**
 * PlatformButton - унифицированная кнопка платформы
 */
import { html, css, LitElement } from 'lit';

export class PlatformButton extends LitElement {
    static styles = css`
        :host {
            display: inline-flex;
        }
        
        button {
            display: inline-flex;
            align-items: center;
            justify-content: center;
            gap: var(--space-2, 8px);
            padding: var(--space-2, 8px) var(--space-4, 16px);
            font-size: var(--text-sm, 14px);
            font-weight: var(--font-medium, 500);
            font-family: inherit;
            line-height: 1.4;
            border-radius: var(--radius-md, 8px);
            border: 1px solid transparent;
            cursor: pointer;
            transition: all var(--duration-fast, 0.15s) var(--easing-default, ease);
            white-space: nowrap;
        }
        
        button:disabled {
            opacity: 0.5;
            cursor: not-allowed;
        }
        
        /* Primary: сервис может задать --platform-btn-primary-* (см. documents index.html) */
        button.primary {
            color: var(--platform-btn-primary-text, white);
            background: var(--platform-btn-primary-bg, var(--accent, #10b981));
            border-color: var(--platform-btn-primary-border, var(--accent, #10b981));
            box-shadow: var(--platform-btn-primary-shadow, none);
        }

        button.primary:hover:not(:disabled) {
            background: var(
                --platform-btn-primary-bg-hover,
                var(--accent-hover, #059669)
            );
            border-color: var(
                --platform-btn-primary-border-hover,
                var(--accent-hover, #059669)
            );
            box-shadow: var(
                --platform-btn-primary-shadow-hover,
                var(--platform-btn-primary-shadow, none)
            );
        }
        
        /* Secondary */
        button.secondary {
            color: var(--text-primary, rgba(255, 255, 255, 0.95));
            background: var(--glass-tint-medium, rgba(255, 255, 255, 0.08));
            border-color: var(--border-default, rgba(255, 255, 255, 0.1));
        }
        
        button.secondary:hover:not(:disabled) {
            background: var(--glass-tint-strong, rgba(255, 255, 255, 0.12));
            border-color: var(--border-strong, rgba(255, 255, 255, 0.15));
        }
        
        /* Danger */
        button.danger {
            color: white;
            background: var(--error, #f43f5e);
            border-color: var(--error, #f43f5e);
        }
        
        button.danger:hover:not(:disabled) {
            background: var(--error-hover, #e11d48);
            border-color: var(--error-hover, #e11d48);
        }
        
        /* Ghost */
        button.ghost {
            color: var(--text-secondary, rgba(255, 255, 255, 0.65));
            background: transparent;
            border-color: transparent;
        }
        
        button.ghost:hover:not(:disabled) {
            color: var(--text-primary, rgba(255, 255, 255, 0.95));
            background: var(--glass-tint-subtle, rgba(255, 255, 255, 0.04));
        }
        
        /* Light theme */
        :host-context([data-theme="light"]) button.secondary {
            color: var(--text-primary, #1e293b);
            background: var(--glass-tint-medium, rgba(0, 0, 0, 0.04));
            border-color: var(--border-default, rgba(0, 0, 0, 0.08));
        }
        
        :host-context([data-theme="light"]) button.secondary:hover:not(:disabled) {
            background: var(--glass-tint-strong, rgba(0, 0, 0, 0.06));
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
    };

    constructor() {
        super();
        this.variant = 'primary';
        this.disabled = false;
        this.loading = false;
        this.type = 'button';
    }

    render() {
        return html`
            <button 
                type="${this.type}"
                class="${this.variant}"
                ?disabled=${this.disabled || this.loading}
            >
                ${this.loading ? html`<span>...</span>` : ''}
                <slot></slot>
            </button>
        `;
    }
}

customElements.define('platform-button', PlatformButton);

