/**
 * Glass Button Component
 * Кнопка с glass morphism эффектом
 */
import { html, css } from 'lit';
import { classMap } from 'lit/directives/class-map.js';
import { PlatformElement } from '../platform-element/index.js';

export class GlassButton extends PlatformElement {
    static styles = [
        PlatformElement.styles,
        css`
            :host {
                display: inline-block;
            }
            
            button {
                display: inline-flex;
                align-items: center;
                justify-content: center;
                gap: var(--space-2);
                padding: var(--space-2) var(--space-4);
                font-size: var(--text-sm);
                font-weight: var(--font-medium);
                border-radius: var(--radius-md);
                border: 1px solid transparent;
                cursor: pointer;
                transition: all var(--duration-fast) var(--easing-default);
                white-space: nowrap;
                text-decoration: none;
                user-select: none;
            }
            
            button:disabled {
                opacity: 0.5;
                cursor: not-allowed;
                pointer-events: none;
            }
            
            .primary {
                color: white;
                background: var(--accent);
                border-color: var(--accent);
            }
            
            .primary:hover:not(:disabled) {
                background: var(--accent-hover);
                border-color: var(--accent-hover);
                box-shadow: var(--accent-glow);
            }
            
            .secondary {
                color: var(--text-secondary);
                background: var(--glass-tint-subtle);
                border-color: var(--border-subtle);
            }
            
            .secondary:hover:not(:disabled) {
                color: var(--text-primary);
                background: var(--glass-tint-medium);
                border-color: var(--border-default);
            }
            
            .danger {
                color: white;
                background: var(--error);
                border-color: var(--error);
            }
            
            .danger:hover:not(:disabled) {
                background: #dc2626;
                box-shadow: var(--error-glow);
            }
            
            .ghost {
                color: var(--text-secondary);
                background: transparent;
                border-color: transparent;
            }
            
            .ghost:hover:not(:disabled) {
                color: var(--text-primary);
                background: var(--glass-tint-subtle);
            }
            
            .sm {
                padding: var(--space-1) var(--space-2);
                font-size: var(--text-xs);
            }
            
            .md {
                padding: var(--space-2) var(--space-4);
                font-size: var(--text-sm);
            }
            
            .lg {
                padding: var(--space-3) var(--space-6);
                font-size: var(--text-base);
            }
            
            .icon-only {
                padding: var(--space-2);
                aspect-ratio: 1;
            }
            
            .loading {
                position: relative;
                color: transparent;
                pointer-events: none;
            }
            
            .loading::after {
                content: '';
                position: absolute;
                width: 16px;
                height: 16px;
                border: 2px solid currentColor;
                border-right-color: transparent;
                border-radius: 50%;
                animation: spin 0.6s linear infinite;
            }
            
            @keyframes spin {
                to {
                    transform: rotate(360deg);
                }
            }
        `
    ];

    static properties = {
        variant: { type: String },
        size: { type: String },
        disabled: { type: Boolean },
        loading: { type: Boolean },
        iconOnly: { type: Boolean },
        type: { type: String },
    };

    constructor() {
        super();
        this.variant = 'primary';
        this.size = 'md';
        this.disabled = false;
        this.loading = false;
        this.iconOnly = false;
        this.type = 'button';
    }

    render() {
        const classes = {
            [this.variant]: true,
            [this.size]: true,
            'icon-only': this.iconOnly,
            'loading': this.loading,
        };

        return html`
            <button
                type=${this.type}
                class=${classMap(classes)}
                ?disabled=${this.disabled || this.loading}
            >
                <slot></slot>
            </button>
        `;
    }
}

customElements.define('glass-button', GlassButton);

