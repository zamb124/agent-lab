import { html, css } from 'lit';
import { PlatformElement } from '../../platform-element/index.js';
import { formStyles } from '../../styles/shared/form.styles.js';

export class PlatformFieldNumber extends PlatformElement {
    static properties = {
        value: {},
        mode: { type: String },
        disabled: { type: Boolean },
        placeholder: { type: String },
        integer: { type: Boolean },
        flat: { type: Boolean, reflect: true },
    };

    static styles = [
        PlatformElement.styles,
        formStyles,
        css`
            :host { display: block; }

            .view-value {
                font-size: var(--text-sm);
                color: var(--text-primary);
                font-variant-numeric: tabular-nums;
            }

            .empty {
                color: var(--text-disabled);
                font-style: italic;
            }
        `,
    ];

    constructor() {
        super();
        this.value = null;
        this.mode = 'view';
        this.disabled = false;
        this.placeholder = '';
        this.integer = false;
        this.flat = false;
    }

    _onInput(e) {
        const raw = e.target.value;
        if (raw === '') {
            this.dispatchEvent(new CustomEvent('change', {
                detail: { value: null },
                bubbles: true,
                composed: true,
            }));
            return;
        }

        const parsed = this.integer ? parseInt(raw, 10) : parseFloat(raw);
        if (Number.isNaN(parsed)) return;

        this.dispatchEvent(new CustomEvent('change', {
            detail: { value: parsed },
            bubbles: true,
            composed: true,
        }));
    }

    _formatDisplay(val) {
        if (val == null) return null;
        if (typeof val === 'number') {
            return this.integer ? String(Math.round(val)) : String(val);
        }
        return String(val);
    }

    render() {
        if (this.mode === 'view') {
            const formatted = this._formatDisplay(this.value);
            return formatted != null
                ? html`<span class="view-value">${formatted}</span>`
                : html`<span class="view-value empty">${(this.t('platform_field.empty_value') || 'platform_field.empty_value')}</span>`;
        }

        return html`
            <input
                type="number"
                class="form-input"
                step=${this.integer ? '1' : 'any'}
                .value=${this.value != null ? String(this.value) : ''}
                placeholder=${this.placeholder}
                ?disabled=${this.disabled}
                @input=${this._onInput}
            />
        `;
    }
}

customElements.define('platform-field-number', PlatformFieldNumber);
