/**
 * Glass Toast Component
 * Всплывающее уведомление
 */
import { html, css } from 'lit';
import { classMap } from 'lit/directives/class-map.js';
import { PlatformElement } from '../platform-element/index.js';

export class GlassToast extends PlatformElement {
    static styles = [
        PlatformElement.styles,
        css`
            :host {
                display: block;
                position: fixed;
                top: max(var(--space-6), env(safe-area-inset-top, 0px));
                right: max(var(--space-6), env(safe-area-inset-right, 0px));
                z-index: var(--z-toast);
                max-width: 400px;
                animation: slideIn 0.3s var(--easing-spring);
            }
            
            :host([closing]) {
                animation: slideOut 0.2s var(--easing-default);
            }
            
            .toast {
                display: flex;
                align-items: center;
                gap: var(--space-3);
                padding: var(--space-4);
                background: var(--glass-solid-strong);
                backdrop-filter: blur(var(--glass-blur-strong));
                border: 1px solid var(--glass-border-medium);
                border-radius: var(--radius-lg);
                box-shadow: var(--glass-shadow-strong);
                color: var(--text-primary);
            }
            
            .toast.success {
                border-left: 3px solid var(--success);
            }
            
            .toast.error {
                border-left: 3px solid var(--error);
            }
            
            .toast.warning {
                border-left: 3px solid var(--warning);
            }
            
            .toast.info {
                border-left: 3px solid var(--info);
            }
            
            .icon {
                flex-shrink: 0;
                width: 20px;
                height: 20px;
            }
            
            .message {
                flex: 1;
                font-size: var(--text-sm);
            }
            
            .close {
                flex-shrink: 0;
                width: 20px;
                height: 20px;
                padding: 0;
                background: none;
                border: none;
                color: var(--text-secondary);
                cursor: pointer;
                transition: color var(--duration-fast);
            }
            
            .close:hover {
                color: var(--text-primary);
            }
            
            @keyframes slideIn {
                from {
                    transform: translateX(calc(100% + var(--space-6)));
                    opacity: 0;
                }
                to {
                    transform: translateX(0);
                    opacity: 1;
                }
            }
            
            @keyframes slideOut {
                from {
                    transform: translateX(0);
                    opacity: 1;
                }
                to {
                    transform: translateX(calc(100% + var(--space-6)));
                    opacity: 0;
                }
            }
        `
    ];

    static properties = {
        message: { type: String },
        type: { type: String },
        duration: { type: Number },
        closing: { type: Boolean, reflect: true },
    };

    constructor() {
        super();
        this.message = '';
        this.type = 'info';
        this.duration = 3000;
        this.closing = false;
        this._timeout = null;
    }

    connectedCallback() {
        super.connectedCallback();
        if (this.duration > 0) {
            this._timeout = setTimeout(() => this.close(), this.duration);
        }
    }

    disconnectedCallback() {
        super.disconnectedCallback();
        if (this._timeout) {
            clearTimeout(this._timeout);
        }
    }

    close() {
        this.closing = true;
        setTimeout(() => {
            this.dispatchEvent(new CustomEvent('close', { bubbles: true, composed: true }));
            this.remove();
        }, 200);
    }

    render() {
        const classes = {
            toast: true,
            [this.type]: true,
        };

        return html`
            <div class=${classMap(classes)}>
                <span class="icon">${this._getIcon()}</span>
                <div class="message">${this.message}</div>
                <button class="close" @click=${this.close}>×</button>
            </div>
        `;
    }

    _getIcon() {
        const icons = {
            success: '✓',
            error: '✕',
            warning: '⚠',
            info: 'ℹ',
        };
        return icons[this.type] || icons.info;
    }
}

customElements.define('glass-toast', GlassToast);

