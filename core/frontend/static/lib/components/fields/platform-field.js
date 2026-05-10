/**
 * platform-field -- универсальный компонент для ввода и отображения
 * типизированных значений атрибутов.
 *
 * Делегирует рендеринг типовому подкомпоненту (platform-field-string,
 * platform-field-number и т.д.) на основании свойства `type`.
 */
import { html, css, nothing } from 'lit';
import { PlatformElement } from '../../platform-element/index.js';
import '../platform-help-hint.js';

import './platform-field-string.js';
import './platform-field-text.js';
import './platform-field-number.js';
import './platform-field-boolean.js';
import './platform-field-date.js';
import './platform-field-enum.js';
import './platform-field-array.js';
import './platform-field-object.js';
import './platform-field-external-refs.js';

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
    external_refs: 'platform-field-external-refs',
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
        inputType: { type: String, attribute: 'input-type' },
        hint: { type: String },
        pillDensity: { type: String, attribute: 'pill-density' },
        pillEmbed: { type: Boolean, attribute: 'pill-embed' },
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
        this.type = 'string';
        this.value = null;
        this.mode = 'view';
        this.label = '';
        this.disabled = false;
        this.config = {};
        this.placeholder = '';
        this.inputType = 'text';
        this.hint = '';
        this.pillDensity = 'default';
        this.pillEmbed = false;
    }

    willUpdate(changedProps) {
        super.willUpdate(changedProps);
        if (changedProps.has('pillDensity')) {
            const v = this.pillDensity;
            if (v !== 'default' && v !== 'compact' && v !== 'dense') {
                throw new Error(
                    `platform-field: pillDensity must be "default", "compact" or "dense", got "${v}"`,
                );
            }
        }
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
                .inputType=${this.inputType}
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
                    .inputType=${this.inputType}
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
                    .placeholder=${this.placeholder}
                    ?disabled=${this.disabled}
                    @change=${this._onChange}
                ></platform-field-enum>`;

            case 'array':
                return html`<platform-field-array
                    .value=${this.value}
                    .mode=${this.mode}
                    .config=${this.config}
                    .placeholder=${this.placeholder}
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

            case 'external_refs':
                return html`<platform-field-external-refs
                    .value=${this.value}
                    .mode=${this.mode}
                    ?disabled=${this.disabled}
                ></platform-field-external-refs>`;

            default:
                return html`<platform-field-string
                    .value=${this.value != null ? String(this.value) : ''}
                    .mode=${this.mode}
                    .placeholder=${this.placeholder}
                    .inputType=${this.inputType}
                    ?disabled=${this.disabled}
                    @change=${this._onChange}
                ></platform-field-string>`;
        }
    }

    render() {
        const hasLabel = typeof this.label === 'string' && this.label !== '';
        const hasHint = typeof this.hint === 'string' && this.hint !== '';
        const density =
            this.pillDensity === 'dense'
                ? 'field-pill--compact field-pill--dense'
                : this.pillDensity === 'compact'
                  ? 'field-pill--compact'
                  : '';
        const embedCls = this.pillEmbed ? 'field-pill--embed' : '';
        return html`
            <div class="field-pill ${density} ${embedCls}" data-mode=${this.mode}>
                ${hasLabel
                    ? html`
                        <div class="field-pill-head">
                            <span class="field-pill-label">${this.label}</span>
                            ${hasHint
                                ? html`<platform-help-hint .text=${this.hint}></platform-help-hint>`
                                : nothing}
                        </div>
                    `
                    : nothing}
                <div class="field-pill-control">
                    <slot name="prefix"></slot>
                    <div class="field-pill-control-main">${this._renderField()}</div>
                    <slot name="suffix"></slot>
                </div>
            </div>
        `;
    }
}

customElements.define('platform-field', PlatformField);
