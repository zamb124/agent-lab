/**
 * platform-field -- универсальный компонент для ввода и отображения
 * типизированных значений атрибутов.
 *
 * Делегирует рендеринг типовому подкомпоненту (platform-field-string,
 * platform-field-number и т.д.) на основании свойства `type`.
 */
import { html, css } from 'lit';
import { PlatformElement } from '../../platform-element/index.js';

import './platform-field-string.js';
import './platform-field-text.js';
import './platform-field-number.js';
import './platform-field-boolean.js';
import './platform-field-date.js';
import './platform-field-enum.js';
import './platform-field-array.js';
import './platform-field-object.js';

const FIELD_TYPE_MAP = {
    string:   'platform-field-string',
    text:     'platform-field-text',
    number:   'platform-field-number',
    integer:  'platform-field-number',
    boolean:  'platform-field-boolean',
    date:     'platform-field-date',
    datetime: 'platform-field-date',
    enum:     'platform-field-enum',
    array:    'platform-field-array',
    object:   'platform-field-object',
};

export class PlatformField extends PlatformElement {
    static properties = {
        type: { type: String },
        value: {},
        mode: { type: String },
        label: { type: String },
        disabled: { type: Boolean },
        config: { type: Object },
        placeholder: { type: String },
    };

    static styles = [
        PlatformElement.styles,
        css`
            :host { display: block; }

            .field-label {
                display: block;
                font-size: var(--text-xs);
                font-weight: var(--font-semibold);
                color: var(--text-tertiary);
                margin-bottom: var(--space-1);
                text-transform: uppercase;
                letter-spacing: 0.06em;
            }
        `,
    ];

    constructor() {
        super();
        this.type = 'string';
        this.value = null;
        this.mode = 'view';
        this.label = '';
        this.disabled = false;
        this.config = {};
        this.placeholder = '';
    }

    _onChange(e) {
        e.stopPropagation();
        this.dispatchEvent(new CustomEvent('change', {
            detail: e.detail,
            bubbles: true,
            composed: true,
        }));
    }

    _renderField() {
        const tagName = FIELD_TYPE_MAP[this.type];
        if (!tagName) {
            return html`<platform-field-string
                .value=${this.value != null ? String(this.value) : ''}
                .mode=${this.mode}
                .placeholder=${this.placeholder}
                ?disabled=${this.disabled}
                @change=${this._onChange}
            ></platform-field-string>`;
        }

        switch (this.type) {
            case 'string':
                return html`<platform-field-string
                    .value=${this.value ?? ''}
                    .mode=${this.mode}
                    .placeholder=${this.placeholder}
                    ?disabled=${this.disabled}
                    @change=${this._onChange}
                ></platform-field-string>`;

            case 'text':
                return html`<platform-field-text
                    .value=${this.value ?? ''}
                    .mode=${this.mode}
                    .placeholder=${this.placeholder}
                    ?disabled=${this.disabled}
                    @change=${this._onChange}
                ></platform-field-text>`;

            case 'number':
                return html`<platform-field-number
                    .value=${this.value}
                    .mode=${this.mode}
                    .placeholder=${this.placeholder}
                    ?disabled=${this.disabled}
                    @change=${this._onChange}
                ></platform-field-number>`;

            case 'integer':
                return html`<platform-field-number
                    .value=${this.value}
                    .mode=${this.mode}
                    .placeholder=${this.placeholder}
                    ?disabled=${this.disabled}
                    ?integer=${true}
                    @change=${this._onChange}
                ></platform-field-number>`;

            case 'boolean':
                return html`<platform-field-boolean
                    .value=${this.value}
                    .mode=${this.mode}
                    ?disabled=${this.disabled}
                    @change=${this._onChange}
                ></platform-field-boolean>`;

            case 'date':
                return html`<platform-field-date
                    .value=${this.value}
                    .mode=${this.mode}
                    ?disabled=${this.disabled}
                    @change=${this._onChange}
                ></platform-field-date>`;

            case 'datetime':
                return html`<platform-field-date
                    .value=${this.value}
                    .mode=${this.mode}
                    ?disabled=${this.disabled}
                    ?datetime=${true}
                    @change=${this._onChange}
                ></platform-field-date>`;

            case 'enum':
                return html`<platform-field-enum
                    .value=${this.value ?? ''}
                    .mode=${this.mode}
                    .config=${this.config}
                    ?disabled=${this.disabled}
                    @change=${this._onChange}
                ></platform-field-enum>`;

            case 'array':
                return html`<platform-field-array
                    .value=${this.value}
                    .mode=${this.mode}
                    ?disabled=${this.disabled}
                    @change=${this._onChange}
                ></platform-field-array>`;

            case 'object':
                return html`<platform-field-object
                    .value=${this.value}
                    .mode=${this.mode}
                    ?disabled=${this.disabled}
                    @change=${this._onChange}
                ></platform-field-object>`;

            default:
                return html`<platform-field-string
                    .value=${this.value != null ? String(this.value) : ''}
                    .mode=${this.mode}
                    .placeholder=${this.placeholder}
                    ?disabled=${this.disabled}
                    @change=${this._onChange}
                ></platform-field-string>`;
        }
    }

    render() {
        return html`
            ${this.label ? html`<span class="field-label">${this.label}</span>` : ''}
            ${this._renderField()}
        `;
    }
}

customElements.define('platform-field', PlatformField);
