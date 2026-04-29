import { html, css } from 'lit';
import { PlatformElement } from '../../platform-element/index.js';
import '../platform-switch.js';

export class PlatformFieldBoolean extends PlatformElement {
    static properties = {
        value: { type: Boolean },
        mode: { type: String },
        disabled: { type: Boolean },
        flat: { type: Boolean, reflect: true },
    };

    static styles = [
        PlatformElement.styles,
        css`
            :host { display: block; }

            :host([flat]) {
                padding: 2px 0;
            }

            .view-value {
                font-size: var(--text-sm);
                color: var(--text-primary);
            }

            .view-true { color: var(--success); }
            .view-false { color: var(--text-secondary); }

            .empty {
                color: var(--text-disabled);
                font-style: italic;
            }
        `,
    ];

    constructor() {
        super();
        this.value = false;
        this.mode = 'view';
        this.disabled = false;
        this.flat = false;
    }

    _onChange(e) {
        this.dispatchEvent(new CustomEvent('change', {
            detail: { value: e.detail.value },
            bubbles: true,
            composed: true,
        }));
    }

    render() {
        if (this.mode === 'view') {
            if (this.value == null) {
                return html`<span class="view-value empty">${(this.t('platform_field.empty_value') || 'platform_field.empty_value')}</span>`;
            }
            const label = this.value
                ? (this.t('platform_field.boolean_true') || 'platform_field.boolean_true')
                : (this.t('platform_field.boolean_false') || 'platform_field.boolean_false');
            const cls = this.value ? 'view-true' : 'view-false';
            return html`<span class="view-value ${cls}">${label}</span>`;
        }

        return html`
            <platform-switch
                ?checked=${!!this.value}
                ?disabled=${this.disabled}
                @change=${this._onChange}
            ></platform-switch>
        `;
    }
}

customElements.define('platform-field-boolean', PlatformFieldBoolean);
