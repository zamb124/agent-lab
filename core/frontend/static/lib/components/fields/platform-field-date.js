import { html, css } from 'lit';
import { PlatformElement } from '../../platform-element/index.js';
import '../platform-date-picker.js';

const ISO_DATE_VALUE = /^(\d{4})-(\d{2})-(\d{2})$/;
const ISO_DATETIME_VALUE = /^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2})$/;

export class PlatformFieldDate extends PlatformElement {
    static properties = {
        value: { type: String },
        mode: { type: String },
        disabled: { type: Boolean },
        datetime: { type: Boolean },
    };

    static styles = [
        PlatformElement.styles,
        css`
            :host {
                display: block;
                width: 100%;
                min-width: 0;
            }

            .field-pill-readonly-text {
                font-variant-numeric: tabular-nums;
            }

            platform-date-picker {
                width: 100%;
            }
        `,
    ];

    constructor() {
        super();
        this.value = null;
        this.mode = 'view';
        this.disabled = false;
        this.datetime = false;
    }

    _onChange(e) {
        this.dispatchEvent(new CustomEvent('change', {
            detail: { value: e.target.value },
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
                ? html`<span class="field-pill-readonly-text">${formatted}</span>`
                : html`<span class="field-pill-empty">${(this.t('platform_field.empty_value') || 'platform_field.empty_value')}</span>`;
        }

        const pickerMode = this.datetime ? 'datetime' : 'date';
        const raw = this.value;

        if (!this._storedStringMatchesIsoFormat(raw)) {
            const display = typeof raw === 'string' ? raw : String(raw);
            return html`
                <input
                    type="text"
                    class="field-pill-input"
                    .value=${display}
                    ?disabled=${this.disabled}
                    @input=${this._onFreeformDateInput}
                />
            `;
        }

        return html`
            <platform-date-picker
                mode=${pickerMode}
                value-format="iso"
                .value=${raw || null}
                ?disabled=${this.disabled}
                ?embedded=${true}
                @change=${this._onChange}
            ></platform-date-picker>
        `;
    }
}

customElements.define('platform-field-date', PlatformFieldDate);
