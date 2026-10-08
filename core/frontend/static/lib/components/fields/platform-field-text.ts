import { html, css } from '../../lit-shim.js';
import type { CSSResultGroup, PropertyDeclarations, TemplateResult } from '../../lit-shim.js';
import { PlatformElement } from '../../platform-element/index.js';

export class PlatformFieldText extends PlatformElement {
    static i18nNamespace = 'platform';

    static override properties: PropertyDeclarations = {
        value: { type: String },
        mode: { type: String },
        disabled: { type: Boolean },
        placeholder: { type: String },
    };

    declare value: string | null;
    declare mode: string;
    declare disabled: boolean;
    declare placeholder: string;

    static override styles: CSSResultGroup = [
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

    _onInput(e: InputEvent): void {
        this.dispatchEvent(new CustomEvent('change', {
            detail: { value: (e.target as HTMLTextAreaElement).value },
            bubbles: true,
            composed: true,
        }));
    }

    override render(): TemplateResult {
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
