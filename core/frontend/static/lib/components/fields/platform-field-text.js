import { html, css } from 'lit';
import { PlatformElement } from '../../platform-element/index.js';
import { formStyles } from '../../styles/shared/form.styles.js';

export class PlatformFieldText extends PlatformElement {
    static properties = {
        value: { type: String },
        mode: { type: String },
        disabled: { type: Boolean },
        placeholder: { type: String },
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
                white-space: pre-wrap;
                word-break: break-word;
                line-height: 1.5;
            }

            .empty {
                color: var(--text-disabled);
                font-style: italic;
            }

            .form-textarea {
                min-height: 80px;
                resize: vertical;
            }
        `,
    ];

    constructor() {
        super();
        this.value = '';
        this.mode = 'view';
        this.disabled = false;
        this.placeholder = '';
        this.flat = false;
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
                : html`<span class="view-value empty">${(this.t('platform_field.empty_value') || 'platform_field.empty_value')}</span>`;
        }

        return html`
            <textarea
                class="form-textarea"
                .value=${this.value ?? ''}
                placeholder=${this.placeholder}
                ?disabled=${this.disabled}
                @input=${this._onInput}
            ></textarea>
        `;
    }
}

customElements.define('platform-field-text', PlatformFieldText);
