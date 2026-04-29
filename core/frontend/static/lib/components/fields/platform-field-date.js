import { html, css } from 'lit';
import { PlatformElement } from '../../platform-element/index.js';
import { formStyles } from '../../styles/shared/form.styles.js';
import '../glass-input.js';
import '../platform-date-picker.js';

const ISO_DATE_VALUE = /^(\d{4})-(\d{2})-(\d{2})$/;
const ISO_DATETIME_VALUE = /^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2})$/;

export class PlatformFieldDate extends PlatformElement {
    static properties = {
        value: { type: String },
        mode: { type: String },
        disabled: { type: Boolean },
        datetime: { type: Boolean },
        flat: { type: Boolean, reflect: true },
    };

    static styles = [
        PlatformElement.styles,
        formStyles,
        css`
            :host { display: block; }

            :host([flat]) {
                width: 100%;
            }

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
        this.datetime = false;
        this.flat = false;
    }

    _onChange(e) {
        this.dispatchEvent(new CustomEvent('change', {
            detail: { value: e.target.value },
            bubbles: true,
            composed: true,
        }));
    }

    _onGlassInputChange(e) {
        const v = e.detail && typeof e.detail.value === 'string' ? e.detail.value : '';
        this.dispatchEvent(new CustomEvent('change', {
            detail: { value: v },
            bubbles: true,
            composed: true,
        }));
    }

    _onFreeformDateInput(e) {
        const t = e.target;
        const v = t && typeof t.value === 'string' ? t.value : '';
        this.dispatchEvent(new CustomEvent('change', {
            detail: { value: v },
            bubbles: true,
            composed: true,
        }));
    }

    _storedStringMatchesIsoFormat(val) {
        if (val === null || val === undefined) return true;
        if (typeof val !== 'string') return false;
        if (val.length === 0) return true;
        return this.datetime ? ISO_DATETIME_VALUE.test(val) : ISO_DATE_VALUE.test(val);
    }

    _formatDisplay(val) {
        if (!val) return null;
        if (this.datetime && val.includes('T')) {
            const [datePart, timePart] = val.split('T');
            return `${datePart} ${timePart}`;
        }
        return val;
    }

    render() {
        if (this.mode === 'view') {
            const formatted = this._formatDisplay(this.value);
            return formatted
                ? html`<span class="view-value">${formatted}</span>`
                : html`<span class="view-value empty">${(this.t('platform_field.empty_value') || 'platform_field.empty_value')}</span>`;
        }

        const pickerMode = this.datetime ? 'datetime' : 'date';
        const raw = this.value;

        if (!this._storedStringMatchesIsoFormat(raw)) {
            const display = typeof raw === 'string' ? raw : String(raw);
            if (this.flat === true) {
                return html`
                    <input
                        type="text"
                        class="form-input"
                        .value=${display}
                        ?disabled=${this.disabled}
                        @input=${this._onFreeformDateInput}
                    />
                `;
            }
            return html`
                <glass-input
                    .value=${display}
                    ?disabled=${this.disabled}
                    @change=${this._onGlassInputChange}
                ></glass-input>
            `;
        }

        return html`
            <platform-date-picker
                mode=${pickerMode}
                value-format="iso"
                .value=${raw || null}
                ?disabled=${this.disabled}
                ?embedded=${this.flat === true}
                @change=${this._onChange}
            ></platform-date-picker>
        `;
    }
}

customElements.define('platform-field-date', PlatformFieldDate);
