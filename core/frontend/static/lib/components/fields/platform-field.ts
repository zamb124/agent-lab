/**
 * platform-field -- универсальный компонент для ввода и отображения
 * типизированных значений атрибутов.
 *
 * Делегирует рендеринг типовому подкомпоненту (platform-field-string,
 * platform-field-number и т.д.) на основании свойства `type`.
 * Оболочка — <platform-field-shell>: floating label с notch в бордере,
 * фокус-ринг, error-сообщение.
 */
import { html, css } from '../../lit-shim.js';
import type { CSSResultGroup, PropertyDeclarations, PropertyValues, TemplateResult } from '../../lit-shim.js';
import { PlatformElement } from '../../platform-element/index.js';
import './platform-field-shell.js';

import './platform-field-string.js';
import './platform-field-text.js';
import './platform-field-number.js';
import './platform-field-boolean.js';
import './platform-field-date.js';
import './platform-field-enum.js';
import './platform-field-array.js';
import './platform-field-object.js';
import './platform-field-external-refs.js';

const FIELD_TYPE_MAP: Record<string, string> = {
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

function presentValue(value: unknown): unknown {
    return value === undefined || value === null ? '' : value;
}

export class PlatformField extends PlatformElement {
    static override properties: PropertyDeclarations = {
        type: { type: String },
        value: {},
        mode: { type: String },
        label: { type: String },
        disabled: { type: Boolean },
        config: { type: Object },
        placeholder: { type: String },
        inputType: { type: String, attribute: 'input-type' },
        suggestions: { type: Array },
        hint: { type: String },
        hintSummary: { type: String, attribute: 'hint-summary' },
        hintDetails: { type: String, attribute: 'hint-details' },
        hintDocHref: { type: String, attribute: 'hint-doc-href' },
        hintDocLabel: { type: String, attribute: 'hint-doc-label' },
        pillDensity: { type: String, attribute: 'pill-density' },
        pillEmbed: { type: Boolean, attribute: 'pill-embed' },
        error: { type: String },
        _focused: { type: Boolean, state: true },
    };

    declare type: string;
    declare value: unknown;
    declare mode: string;
    declare label: string;
    declare disabled: boolean;
    declare config: Record<string, unknown>;
    declare placeholder: string;
    declare inputType: string;
    declare suggestions: unknown[];
    declare hint: string;
    declare hintSummary: string;
    declare hintDetails: string;
    declare hintDocHref: string;
    declare hintDocLabel: string;
    declare pillDensity: string;
    declare pillEmbed: boolean;
    declare error: string;
    declare _focused: boolean;

    private _focusOutTimer: ReturnType<typeof setTimeout> | undefined;
    private _onFocusIn: () => void;
    private _onFocusOut: () => void;

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
        this.type = 'string';
        this.value = null;
        this.mode = 'view';
        this.label = '';
        this.disabled = false;
        this.config = {};
        this.placeholder = '';
        this.inputType = 'text';
        this.suggestions = [];
        this.hint = '';
        this.hintSummary = '';
        this.hintDetails = '';
        this.hintDocHref = '';
        this.hintDocLabel = '';
        this.pillDensity = 'default';
        this.pillEmbed = false;
        this.error = '';
        this._focused = false;
        this._focusOutTimer = undefined;
        this._onFocusIn = () => {
            if (!this._focused) {
                this._focused = true;
            }
        };
        this._onFocusOut = () => {
            clearTimeout(this._focusOutTimer);
            this._focusOutTimer = setTimeout(() => {
                this._focused = this.matches(':focus-within');
            }, 0);
        };
    }

    override connectedCallback(): void {
        super.connectedCallback();
        this.addEventListener('focusin', this._onFocusIn);
        this.addEventListener('focusout', this._onFocusOut);
    }

    override disconnectedCallback(): void {
        super.disconnectedCallback();
        this.removeEventListener('focusin', this._onFocusIn);
        this.removeEventListener('focusout', this._onFocusOut);
        clearTimeout(this._focusOutTimer);
    }

    override willUpdate(changedProps: PropertyValues<this>): void {
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

    _onChange(e: CustomEvent<unknown>): void {
        e.stopPropagation();
        this.dispatchEvent(new CustomEvent('change', {
            detail: e.detail,
            bubbles: true,
            composed: true,
        }));
    }

    _hasValue(): boolean {
        const v = this.value;
        switch (this.type) {
            case 'number':
            case 'integer':
            case 'boolean':
            case 'object':
            case 'external_refs':
                return v != null;
            case 'array':
                return Array.isArray(v) && v.length > 0;
            default:
                return typeof v === 'string' ? v !== '' : v != null;
        }
    }

    /** label «улетел» на бордер: значение, view-режим или фокус внутри. */
    get _floated(): boolean {
        return this.mode === 'view' || this._hasValue() || this._focused;
    }

    get _hasLabel(): boolean {
        return typeof this.label === 'string' && this.label !== '';
    }

    /**
     * Placeholder виден, только когда label улетел (Material-поведение):
     * resting label сам занимает место placeholder. Полю без label — как есть.
     */
    get _effectivePlaceholder(): string {
        if (this._hasLabel && !this._floated) {
            return '';
        }
        return this.placeholder;
    }

    _renderField(): TemplateResult {
        const ph = this._effectivePlaceholder;
        const tagName = FIELD_TYPE_MAP[this.type];
        if (!tagName) {
            return html`<platform-field-string
                .value=${this.value != null ? String(this.value) : ''}
                .mode=${this.mode}
                .placeholder=${ph}
                .inputType=${this.inputType}
                .suggestions=${this.suggestions}
                ?disabled=${this.disabled}
                @change=${this._onChange}
            ></platform-field-string>`;
        }

        switch (this.type) {
            case 'string':
                return html`<platform-field-string
                    .value=${presentValue(this.value)}
                    .mode=${this.mode}
                    .placeholder=${ph}
                    .inputType=${this.inputType}
                    .suggestions=${this.suggestions}
                    ?disabled=${this.disabled}
                    @change=${this._onChange}
                ></platform-field-string>`;

            case 'text':
                return html`<platform-field-text
                    .value=${presentValue(this.value)}
                    .mode=${this.mode}
                    .placeholder=${ph}
                    ?disabled=${this.disabled}
                    @change=${this._onChange}
                ></platform-field-text>`;

            case 'number':
                return html`<platform-field-number
                    .value=${this.value}
                    .mode=${this.mode}
                    .placeholder=${ph}
                    ?disabled=${this.disabled}
                    @change=${this._onChange}
                ></platform-field-number>`;

            case 'integer':
                return html`<platform-field-number
                    .value=${this.value}
                    .mode=${this.mode}
                    .placeholder=${ph}
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
                    .placeholder=${ph}
                    ?disabled=${this.disabled}
                    @change=${this._onChange}
                ></platform-field-date>`;

            case 'datetime':
                return html`<platform-field-date
                    .value=${this.value}
                    .mode=${this.mode}
                    .placeholder=${ph}
                    ?disabled=${this.disabled}
                    ?datetime=${true}
                    @change=${this._onChange}
                ></platform-field-date>`;

            case 'enum':
                return html`<platform-field-enum
                    .value=${presentValue(this.value)}
                    .mode=${this.mode}
                    .config=${this.config}
                    .placeholder=${ph}
                    ?disabled=${this.disabled}
                    @change=${this._onChange}
                ></platform-field-enum>`;

            case 'array':
                return html`<platform-field-array
                    .value=${this.value}
                    .mode=${this.mode}
                    .config=${this.config}
                    .placeholder=${ph}
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
                    .placeholder=${ph}
                    .inputType=${this.inputType}
                    .suggestions=${this.suggestions}
                    ?disabled=${this.disabled}
                    @change=${this._onChange}
                ></platform-field-string>`;
        }
    }

    override render(): TemplateResult {
        const multiline = this.type === 'text' || this.type === 'object';
        return html`
            <platform-field-shell
                .label=${this.label}
                ?floated=${this.mode === 'view' || this._hasValue()}
                density=${this.pillDensity}
                ?embed=${this.pillEmbed}
                ?editable=${this.mode === 'edit'}
                ?disabled=${this.disabled}
                ?multiline=${multiline}
                .error=${this.error}
                .hint=${this.hint}
                .hintSummary=${this.hintSummary}
                .hintDetails=${this.hintDetails}
                .hintDocHref=${this.hintDocHref}
                .hintDocLabel=${this.hintDocLabel}
            >
                <slot name="prefix" slot="prefix"></slot>
                ${this._renderField()}
                <slot name="suffix" slot="suffix"></slot>
            </platform-field-shell>
        `;
    }
}

customElements.define('platform-field', PlatformField);
