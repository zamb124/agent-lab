import { html, css, nothing } from 'lit';
import { PlatformElement } from '../../platform-element/index.js';

const ALLOWED_INPUT_TYPES = Object.freeze(['text', 'email', 'password', 'url', 'tel', 'search']);

export class PlatformFieldString extends PlatformElement {
    static i18nNamespace = 'platform';

    static properties = {
        value: { type: String },
        mode: { type: String },
        disabled: { type: Boolean },
        placeholder: { type: String },
        inputType: { type: String, attribute: 'input-type' },
        suggestions: { type: Array },
    };

    static styles = [
        PlatformElement.styles,
        css`
            :host {
                display: block;
                min-width: 0;
                flex: 1;
            }

            .field-pill-readonly-text,
            .field-pill-empty {
                display: block;
                width: 100%;
                min-width: 0;
                box-sizing: border-box;
            }
        `,
    ];

    constructor() {
        super();
        this.value = '';
        this.mode = 'view';
        this.disabled = false;
        this.placeholder = '';
        this.inputType = 'text';
        this.suggestions = [];
        this._listId = `platform-field-string-${Math.random().toString(36).slice(2, 10)}`;
    }

    _onInput(e) {
        this.dispatchEvent(new CustomEvent('change', {
            detail: { value: e.target.value },
            bubbles: true,
            composed: true,
        }));
    }

    _onManagedFocusIn() {
        this.dispatchEvent(new CustomEvent('platform-field-managed-focus-in', {
            bubbles: true,
            composed: true,
        }));
    }

    /** @param {FocusEvent} e */
    _onManagedFocusOut(e) {
        this.dispatchEvent(new CustomEvent('platform-field-managed-focus-out', {
            bubbles: true,
            composed: true,
            detail: { relatedTarget: e.relatedTarget },
        }));
    }

    _resolvedInputType() {
        if (typeof this.inputType !== 'string' || this.inputType.length === 0) {
            return 'text';
        }
        if (!ALLOWED_INPUT_TYPES.includes(this.inputType)) {
            throw new Error(
                `platform-field-string: inputType "${this.inputType}" is not allowed. Allowed: ${ALLOWED_INPUT_TYPES.join(', ')}.`,
            );
        }
        return this.inputType;
    }

    _normalizedSuggestions() {
        return Array.isArray(this.suggestions)
            ? this.suggestions.filter((item) => typeof item === 'string' && item.length > 0).slice(0, 120)
            : [];
    }

    render() {
        if (this.mode === 'view') {
            const display = this.value != null && this.value !== '';
            if (!display) {
                return html`<span class="field-pill-empty">${(this.t('platform_field.empty_value') || 'platform_field.empty_value')}</span>`;
            }
            const masked = this.inputType === 'password';
            const text = masked ? '\u2022'.repeat(Math.min(String(this.value).length, 12)) : this.value;
            return html`<span class="field-pill-readonly-text">${text}</span>`;
        }

        const t = this._resolvedInputType();
        const suggestions = this._normalizedSuggestions();
        return html`
            <input
                type=${t}
                class="field-pill-input"
                .value=${this.value ?? ''}
                placeholder=${this.placeholder}
                list=${suggestions.length > 0 ? this._listId : nothing}
                ?disabled=${this.disabled}
                @input=${this._onInput}
                @focusin=${this._onManagedFocusIn}
                @focusout=${this._onManagedFocusOut}
            />
            ${suggestions.length > 0
                ? html`
                    <datalist id=${this._listId}>
                        ${suggestions.map((value) => html`<option value=${value}></option>`)}
                    </datalist>
                `
                : nothing}
        `;
    }
}

customElements.define('platform-field-string', PlatformFieldString);
