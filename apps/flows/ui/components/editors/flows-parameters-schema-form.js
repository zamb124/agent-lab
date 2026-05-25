/**
 * flows-parameters-schema-form — форма по parameters_schema.properties.
 *
 * Schema: { key: { type, description?, default?, required?, enum?, items?, properties? } }
 * Типы: string | number | integer | boolean | object | array | <enum>.
 *
 * Property API:
 *   - schema: object
 *   - values: object
 *   - readonly: boolean
 *
 * Events (emit):
 *   - 'change' { values }
 */

import { html, css } from 'lit';
import { PlatformElement } from '@platform/lib/platform-element/index.js';
import '@platform/lib/components/fields/platform-field.js';
import './flows-json-field-editor.js';

export class FlowsParametersSchemaForm extends PlatformElement {
    static i18nNamespace = 'flows';

    static properties = {
        schema: { type: Object },
        values: { type: Object },
        readonly: { type: Boolean },
    };

    static styles = [
        PlatformElement.styles,
        css`
            :host { display: block; }
            .field { display: flex; flex-direction: column; gap: var(--space-1); margin-bottom: var(--space-2); }
            .row { display: flex; align-items: center; gap: var(--space-2); }
            label { font-size: var(--text-sm); color: var(--text-secondary); }
            label .req { color: var(--error); margin-left: 2px; }
            .desc { font-size: var(--text-xs); color: var(--text-tertiary); }
            input[type="checkbox"] { width: auto; }
            .empty {
                font-size: var(--text-sm);
                color: var(--text-tertiary);
                padding: var(--space-2);
            }
        `,
    ];

    constructor() {
        super();
        this.schema = null;
        this.values = null;
        this.readonly = false;
    }

    _entries() {
        const s = this.schema;
        if (!s || typeof s !== 'object') return [];
        return Object.entries(s).map(([key, raw]) => {
            const def = raw && typeof raw === 'object' ? raw : {};
            return {
                key,
                type: typeof def.type === 'string' ? def.type : 'string',
                description: typeof def.description === 'string' ? def.description : '',
                required: Boolean(def.required),
                defaultValue: 'default' in def ? def.default : undefined,
                enumValues: Array.isArray(def.enum) ? def.enum : null,
            };
        });
    }

    _value(key, def) {
        const v = this.values && typeof this.values === 'object' ? this.values[key] : undefined;
        if (v !== undefined) return v;
        return def;
    }

    _emit(key, value) {
        const base = this.values && typeof this.values === 'object' ? this.values : {};
        const next = { ...base, [key]: value };
        this.emit('change', { values: next });
    }

    _renderField(it) {
        const value = this._value(it.key, it.defaultValue);
        if (it.enumValues) {
            const enumStrings = it.enumValues.map((opt) => String(opt));
            const optObjects = enumStrings.map((s) => ({ value: s, label: s }));
            const strVal = value === undefined || value === null ? '' : String(value);
            return html`<platform-field
                type="enum"
                mode="edit"
                label=""
                ?disabled=${this.readonly}
                .value=${strVal}
                .config=${{ values: optObjects }}
                @change=${(e) => this._emit(it.key, e.detail.value)}
            ></platform-field>`;
        }
        if (it.type === 'boolean') {
            return html`<input
                type="checkbox"
                ?disabled=${this.readonly}
                .checked=${Boolean(value)}
                @change=${(e) => this._emit(it.key, e.target.checked)}
            />`;
        }
        if (it.type === 'number' || it.type === 'integer') {
            const numVal = value === undefined || value === null
                ? null
                : (typeof value === 'number' && Number.isFinite(value) ? value : null);
            return html`<platform-field
                type=${it.type === 'integer' ? 'integer' : 'number'}
                mode="edit"
                label=""
                ?disabled=${this.readonly}
                .value=${numVal}
                @change=${(e) => this._emit(it.key, e.detail.value)}
            ></platform-field>`;
        }
        if (it.type === 'object' || it.type === 'array') {
            const json = value === undefined || value === null
                ? (it.type === 'array' ? '[]' : '{}')
                : JSON.stringify(value, null, 2);
            return html`<flows-json-field-editor
                ?readonly=${this.readonly}
                .value=${json}
                @change=${(e) => {
                    if (e.detail && 'parsed' in e.detail) this._emit(it.key, e.detail.parsed);
                }}
            ></flows-json-field-editor>`;
        }
        return html`<platform-field
            type="string"
            mode="edit"
            label=""
            ?disabled=${this.readonly}
            .value=${value === undefined || value === null ? '' : String(value)}
            @change=${(e) => this._emit(it.key, typeof e.detail.value === 'string' ? e.detail.value : '')}
        ></platform-field>`;
    }

    render() {
        const items = this._entries();
        if (items.length === 0) {
            return html`<div class="empty">${this.t('parameters_schema_form.empty')}</div>`;
        }
        return html`
            ${items.map((it) => html`
                <div class="field">
                    <label>${it.key}${it.required ? html`<span class="req">*</span>` : ''}</label>
                    ${this._renderField(it)}
                    ${it.description ? html`<div class="desc">${it.description}</div>` : ''}
                </div>
            `)}
        `;
    }
}

customElements.define('flows-parameters-schema-form', FlowsParametersSchemaForm);
