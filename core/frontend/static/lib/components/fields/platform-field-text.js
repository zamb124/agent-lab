import { html, css } from 'lit';
import { PlatformElement } from '../../platform-element/index.js';

export class PlatformFieldText extends PlatformElement {
    static properties = {
        value: { type: String },
        mode: { type: String },
        disabled: { type: Boolean },
        placeholder: { type: String },
    };

    static styles = [
        PlatformElement.styles,
        css`
            :host {
                display: block;
                min-width: 0;
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
                ? html`<span class="field-pill-readonly-text">${this.value}</span>`
                : html`<span class="field-pill-empty">${(this.t('platform_field.empty_value') || 'platform_field.empty_value')}</span>`;
        }

        return html`
            <textarea
                class="field-pill-textarea"
                .value=${this.value ?? ''}
                placeholder=${this.placeholder}
                ?disabled=${this.disabled}
                @input=${this._onInput}
            ></textarea>
        `;
    }
}

customElements.define('platform-field-text', PlatformFieldText);
