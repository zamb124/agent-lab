import { html, css } from 'lit';
import { PlatformElement } from '../../platform-element/index.js';
import { formStyles } from '../../styles/shared/form.styles.js';

export class PlatformFieldString extends PlatformElement {
    static properties = {
        value: { type: String },
        mode: { type: String },
        disabled: { type: Boolean },
        placeholder: { type: String },
    };

    static styles = [
        PlatformElement.styles,
        formStyles,
        css`
            :host { display: block; }

            .view-value {
                font-size: var(--text-sm);
                color: var(--text-primary);
                word-break: break-word;
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
        this.placeholder = '';
    }

    _onInput(e) {
        this.dispatchEvent(new CustomEvent('change', {
            detail: { value: e.target.value },
            bubbles: true,
            composed: true,
        }));
    }

    render() {
        if (this.mode === 'view') {
            const display = this.value != null && this.value !== '';
            return display
                ? html`<span class="view-value">${this.value}</span>`
                : html`<span class="view-value empty">${this.i18n.t('platform_field.empty_value', {}, 'platform')}</span>`;
        }

        return html`
            <input
                type="text"
                class="form-input"
                .value=${this.value ?? ''}
                placeholder=${this.placeholder}
                ?disabled=${this.disabled}
                @input=${this._onInput}
            />
        `;
    }
}

customElements.define('platform-field-string', PlatformFieldString);
