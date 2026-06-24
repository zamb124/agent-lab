/**
 * Компактная icon-only кнопка действия (Linear-style toolbar).
 */

import { html, css } from 'lit';
import { PlatformElement } from '@platform/lib/platform-element/index.js';
import '@platform/lib/components/platform-icon.js';

export class WorktrackerIconAction extends PlatformElement {
    static properties = {
        icon: { type: String },
        title: { type: String },
        disabled: { type: Boolean, reflect: true },
        active: { type: Boolean, reflect: true },
        size: { type: Number },
    };

    static styles = [
        PlatformElement.styles,
        css`
            :host {
                display: inline-flex;
            }
            button {
                display: inline-flex;
                align-items: center;
                justify-content: center;
                width: 32px;
                height: 32px;
                padding: 0;
                border: 1px solid transparent;
                border-radius: var(--radius-md);
                background: transparent;
                color: var(--text-secondary);
                cursor: pointer;
                transition: var(--motion-transition-interactive);
            }
            button:hover:not(:disabled) {
                background: var(--glass-solid-medium);
                color: var(--text-primary);
                border-color: var(--glass-border-subtle);
            }
            :host([active]) button {
                background: var(--glass-solid-medium);
                color: var(--text-primary);
            }
            button:disabled {
                opacity: 0.45;
                cursor: not-allowed;
            }
            button:focus-visible {
                outline: 2px solid var(--accent);
                outline-offset: 2px;
            }
        `,
    ];

    constructor() {
        super();
        this.icon = 'plus';
        this.title = '';
        this.disabled = false;
        this.active = false;
        this.size = 18;
    }

    render() {
        return html`
            <button
                type="button"
                title=${this.title}
                aria-label=${this.title}
                ?disabled=${this.disabled}
                @click=${() => this.emit('action')}
            >
                <platform-icon name=${this.icon} size=${this.size}></platform-icon>
            </button>
        `;
    }
}

customElements.define('worktracker-icon-action', WorktrackerIconAction);
