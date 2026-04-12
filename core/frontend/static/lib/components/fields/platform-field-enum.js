import { html, css } from 'lit';
import { PlatformElement } from '../../platform-element/index.js';
import { formStyles } from '../../styles/shared/form.styles.js';

export class PlatformFieldEnum extends PlatformElement {
    static properties = {
        value: { type: String },
        mode: { type: String },
        disabled: { type: Boolean },
        config: { type: Object },
    };

    static styles = [
        PlatformElement.styles,
        formStyles,
        css`
            :host { display: block; }

            .view-value {
                font-size: var(--text-sm);
                color: var(--text-primary);
            }

            .enum-chip {
                display: inline-flex;
                align-items: center;
                padding: var(--space-1) var(--space-3);
                font-size: var(--text-xs);
                background: var(--accent-subtle);
                color: var(--text-primary);
                border-radius: var(--radius-full);
            }

            .empty {
                color: var(--text-disabled);
                font-style: italic;
            }
        `,
    ];

    constructor() {
        super();
        this.value = '';
        this.mode = 'view';
        this.disabled = false;
        this.config = {};
    }

    get _enumValues() {
        return this.config?.values || [];
    }

    _onChange(e) {
        this.dispatchEvent(new CustomEvent('change', {
            detail: { value: e.target.value },
            bubbles: true,
            composed: true,
        }));
    }

    render() {
        if (this.mode === 'view') {
            if (this.value == null || this.value === '') {
                return html`<span class="view-value empty">${this.i18n.t('platform_field.empty_value', {}, 'platform')}</span>`;
            }
            return html`<span class="enum-chip">${this.value}</span>`;
        }

        return html`
            <select
                class="form-select"
                .value=${this.value ?? ''}
                ?disabled=${this.disabled}
                @change=${this._onChange}
            >
                <option value="">--</option>
                ${this._enumValues.map(v => html`
                    <option value=${v} ?selected=${this.value === v}>${v}</option>
                `)}
            </select>
        `;
    }
}

customElements.define('platform-field-enum', PlatformFieldEnum);
