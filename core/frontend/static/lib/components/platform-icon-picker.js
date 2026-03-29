import { html, css } from 'lit';
import { PlatformElement } from '../platform-element/index.js';
import './platform-icon.js';

export class PlatformIconPicker extends PlatformElement {
    static properties = {
        value: { type: String },
        icons: { type: Array },
        placeholder: { type: String },
        disabled: { type: Boolean, reflect: true },
        _open: { state: true },
    };

    static styles = [
        PlatformElement.styles,
        css`
            :host {
                display: block;
                position: relative;
                width: 100%;
            }

            .trigger {
                width: 100%;
                min-height: 44px;
                border: 1px solid var(--crm-stroke, var(--border-subtle));
                border-radius: var(--radius-xl, 14px);
                background: var(--crm-surface-elevated, var(--glass-solid-subtle));
                color: var(--text-primary);
                padding: var(--space-2) var(--space-3);
                display: flex;
                align-items: center;
                justify-content: space-between;
                gap: var(--space-2);
                cursor: pointer;
            }

            .trigger:focus-visible {
                outline: none;
                border-color: var(--accent, #3b82f6);
                box-shadow: 0 0 0 1px var(--accent, #3b82f6);
            }

            :host([disabled]) .trigger {
                opacity: 0.6;
                cursor: not-allowed;
            }

            .value-wrap {
                min-width: 0;
                display: inline-flex;
                align-items: center;
                gap: var(--space-2);
                color: var(--text-primary);
            }

            .value-text {
                overflow: hidden;
                text-overflow: ellipsis;
                white-space: nowrap;
                font-size: var(--text-base);
            }

            .chevron {
                color: var(--text-secondary);
                flex-shrink: 0;
            }

            .panel {
                position: absolute;
                top: calc(100% + var(--space-2));
                left: 0;
                z-index: 1000;
                width: min(560px, 100%);
                max-height: 280px;
                overflow: auto;
                border: 1px solid var(--crm-stroke, var(--border-subtle));
                border-radius: var(--radius-xl, 14px);
                background: var(--crm-surface, var(--glass-solid));
                box-shadow: var(--shadow-lg);
                padding: var(--space-2);
                display: grid;
                grid-template-columns: repeat(auto-fill, minmax(132px, 1fr));
                gap: var(--space-2);
            }

            .option {
                border: 1px solid var(--crm-stroke, var(--border-subtle));
                border-radius: var(--radius-md);
                background: var(--crm-surface-elevated, var(--glass-solid-subtle));
                color: var(--text-primary);
                min-height: 36px;
                padding: 0 var(--space-2);
                display: inline-flex;
                align-items: center;
                gap: var(--space-2);
                cursor: pointer;
                font-size: var(--text-sm);
            }

            .option:hover {
                border-color: var(--crm-selected-stroke, var(--accent));
            }

            .option.active {
                border-color: var(--crm-selected-stroke, var(--accent));
                background: var(--crm-selected-bg, rgba(59, 130, 246, 0.12));
                color: var(--crm-selected-text, var(--text-primary));
            }

            .option-label {
                overflow: hidden;
                text-overflow: ellipsis;
                white-space: nowrap;
            }
        `,
    ];

    constructor() {
        super();
        this.value = '';
        this.icons = [];
        this.placeholder = 'Выберите иконку';
        this.disabled = false;
        this._open = false;
        this._onWindowPointerDown = this._handleWindowPointerDown.bind(this);
    }

    connectedCallback() {
        super.connectedCallback();
        window.addEventListener('pointerdown', this._onWindowPointerDown);
    }

    disconnectedCallback() {
        window.removeEventListener('pointerdown', this._onWindowPointerDown);
        super.disconnectedCallback();
    }

    _handleWindowPointerDown(event) {
        if (!this._open) {
            return;
        }
        const path = event.composedPath();
        if (!path.includes(this)) {
            this._open = false;
        }
    }

    _toggleOpen() {
        if (this.disabled) {
            return;
        }
        this._open = !this._open;
    }

    _selectIcon(iconName) {
        if (this.disabled) {
            return;
        }
        this.value = iconName;
        this._open = false;
        this.dispatchEvent(new CustomEvent('change', {
            detail: { value: iconName },
            bubbles: true,
            composed: true,
        }));
    }

    _onTriggerKeyDown(event) {
        if (event.key === 'Enter' || event.key === ' ') {
            event.preventDefault();
            this._toggleOpen();
        }
        if (event.key === 'Escape') {
            this._open = false;
        }
    }

    _renderCurrentValue() {
        const selected = typeof this.value === 'string' ? this.value.trim() : '';
        if (!selected) {
            return html`<span class="value-text">${this.placeholder}</span>`;
        }
        return html`
            <platform-icon name=${selected} size="18"></platform-icon>
            <span class="value-text">${selected}</span>
        `;
    }

    render() {
        const options = Array.isArray(this.icons) ? this.icons : [];
        return html`
            <button
                type="button"
                class="trigger"
                ?disabled=${this.disabled}
                @click=${this._toggleOpen}
                @keydown=${this._onTriggerKeyDown}
                aria-expanded=${this._open ? 'true' : 'false'}
            >
                <span class="value-wrap">${this._renderCurrentValue()}</span>
                <platform-icon class="chevron" name="chevron-down" size="16"></platform-icon>
            </button>

            ${this._open ? html`
                <div class="panel">
                    ${options.map((iconName) => html`
                        <button
                            type="button"
                            class="option ${this.value === iconName ? 'active' : ''}"
                            @click=${() => this._selectIcon(iconName)}
                        >
                            <platform-icon name=${iconName} size="16"></platform-icon>
                            <span class="option-label">${iconName}</span>
                        </button>
                    `)}
                </div>
            ` : ''}
        `;
    }
}

customElements.define('platform-icon-picker', PlatformIconPicker);
