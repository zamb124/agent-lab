import { html, css } from 'lit';
import { PlatformElement } from '../../platform-element/index.js';
import '../platform-date-picker.js';

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
        this.datetime = false;
    }

    _onChange(e) {
        this.dispatchEvent(new CustomEvent('change', {
            detail: { value: e.target.value },
            bubbles: true,
            composed: true,
        }));
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

        return html`
            <platform-date-picker
                mode=${pickerMode}
                value-format="iso"
                .value=${this.value || null}
                ?disabled=${this.disabled}
                @change=${this._onChange}
            ></platform-date-picker>
        `;
    }
}

customElements.define('platform-field-date', PlatformFieldDate);
