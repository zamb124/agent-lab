import { html, css } from 'lit';
import { PlatformElement } from '@platform/lib/platform-element/index.js';

export function createEmptySchemaFieldRow(defaultType = 'string') {
    return {
        key: '',
        label: '',
        type: defaultType,
        description: '',
        enum_set_id: '',
        enum_values_text: '',
        extra: {},
    };
}

export function normalizeSchemaRows(schemaValue) {
    if (!schemaValue || typeof schemaValue !== 'object' || Array.isArray(schemaValue)) {
        return [];
    }
    return Object.entries(schemaValue).map(([fieldKey, rawValue]) => {
        if (!rawValue || typeof rawValue !== 'object' || Array.isArray(rawValue)) {
            throw new Error(`Schema field "${fieldKey}" must be object`);
        }
        const typeId = typeof rawValue.type === 'string' && rawValue.type.trim().length > 0
            ? rawValue.type.trim()
            : 'string';
        if (rawValue.values !== undefined && !Array.isArray(rawValue.values)) {
            throw new Error(`Schema field "${fieldKey}".values must be array`);
        }
        const enumValues = Array.isArray(rawValue.values) ? rawValue.values : [];
        const normalizedValues = enumValues
            .map((item) => (typeof item === 'string' ? item.trim() : ''))
            .filter((item) => item.length > 0);
        if (rawValue.enum_set_id !== undefined && typeof rawValue.enum_set_id !== 'string') {
            throw new Error(`Schema field "${fieldKey}".enum_set_id must be string`);
        }
        const extra = Object.fromEntries(
            Object.entries(rawValue).filter(([key]) => !['type', 'label', 'description', 'values', 'enum_set_id'].includes(key))
        );
        return {
            key: fieldKey,
            label: typeof rawValue.label === 'string' ? rawValue.label : '',
            type: typeId,
            description: typeof rawValue.description === 'string' ? rawValue.description : '',
            enum_set_id: typeof rawValue.enum_set_id === 'string' ? rawValue.enum_set_id : '',
            enum_values_text: normalizedValues.join(', '),
            extra,
        };
    });
}

/**
 * @param {Array} rows - массив строк поля
 * @param {string} sectionLabel - название секции для сообщений об ошибках
 * @param {Object|null} schemaOptions - опции схемы из API
 * @param {Function} t - функция перевода i18n
 * @returns {Object} - JSON-объект для required_fields / optional_fields
 */
export function buildSchemaFromRows(rows, sectionLabel, schemaOptions, t) {
    if (!Array.isArray(rows)) {
        throw new Error(`${sectionLabel} rows must be array`);
    }
    const schema = {};
    const seenKeys = new Set();
    const fieldTypes = new Set((schemaOptions?.field_types || []).map((item) => item.type_id));
    const enumSetsMap = new Map((schemaOptions?.enum_sets || []).map((item) => [item.enum_set_id, item.values]));
    const maxFieldsPerSection = Number(schemaOptions?.validation_limits?.max_fields_per_section || 0);
    if (maxFieldsPerSection > 0 && rows.length > maxFieldsPerSection) {
        throw new Error(t('errors.field_limit', { section: sectionLabel, max: String(maxFieldsPerSection) }));
    }

    for (const row of rows) {
        const key = String(row?.key || '').trim();
        if (!key) {
            continue;
        }
        if (!/^[a-zA-Z_][a-zA-Z0-9_]*$/.test(key)) {
            throw new Error(t('errors.bad_key', { section: sectionLabel, key }));
        }
        if (seenKeys.has(key)) {
            throw new Error(t('errors.dup_key', { section: sectionLabel, key }));
        }
        seenKeys.add(key);
        const typeId = String(row?.type || '').trim();
        if (fieldTypes.size > 0 && !fieldTypes.has(typeId)) {
            throw new Error(t('errors.unknown_type', { section: sectionLabel, type: typeId, key }));
        }
        const descriptor = {
            ...(row?.extra && typeof row.extra === 'object' ? row.extra : {}),
            type: typeId,
        };
        const label = String(row?.label || '').trim();
        if (label) {
            descriptor.label = label;
        }
        const description = String(row?.description || '').trim();
        if (description) {
            descriptor.description = description;
        }
        if (typeId === 'enum') {
            const enumSetId = String(row?.enum_set_id || '').trim();
            if (enumSetId) {
                if (enumSetsMap.size > 0 && !enumSetsMap.has(enumSetId)) {
                    throw new Error(t('errors.enum_set_missing', { section: sectionLabel, id: enumSetId }));
                }
                descriptor.enum_set_id = enumSetId;
                if (enumSetsMap.has(enumSetId)) {
                    descriptor.values = enumSetsMap.get(enumSetId);
                }
            } else {
                const values = String(row?.enum_values_text || '')
                    .split(/[\n,]/)
                    .map((v) => v.trim())
                    .filter((v) => v.length > 0);
                if (values.length === 0) {
                    throw new Error(t('errors.enum_needs_values', { section: sectionLabel, key }));
                }
                descriptor.values = values;
            }
        }
        schema[key] = descriptor;
    }
    return schema;
}

export class SchemaFieldBuilder extends PlatformElement {
    static properties = {
        rows: { type: Array },
        schemaOptions: { type: Object },
        required: { type: Boolean },
        disabled: { type: Boolean },
    };

    static styles = [
        PlatformElement.styles,
        css`
            :host { display: block; }
            .fields-list { display: flex; flex-direction: column; gap: var(--space-2); }
            .schema-field-card { border: 1px solid var(--crm-stroke); border-radius: var(--radius-md); background: var(--crm-surface-elevated); padding: var(--space-2); display: grid; gap: var(--space-2); }
            .schema-field-row { display: grid; gap: var(--space-2); grid-template-columns: 1fr 1fr; }
            .schema-field-inline { display: flex; align-items: center; gap: var(--space-2); flex-wrap: wrap; }
            .schema-empty { color: var(--text-tertiary); font-size: var(--text-sm); }
            .add-row { display: flex; margin-top: var(--space-1); }
            .form-input, .form-select { border: 1px solid var(--crm-stroke); border-radius: var(--radius-md); background: var(--crm-surface-elevated); color: var(--text-primary); padding: var(--space-2) var(--space-3); font-size: var(--text-sm); width: 100%; box-sizing: border-box; }
            .form-input:disabled, .form-select:disabled { opacity: 0.6; cursor: not-allowed; }
            .mono { font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, "Liberation Mono", "Courier New", monospace; font-size: var(--text-xs); }
            .save-btn { display: inline-flex; align-items: center; justify-content: center; gap: var(--space-2); border: 1px solid var(--accent); background: var(--accent); color: var(--platform-btn-primary-text); border-radius: var(--radius-md); padding: var(--space-2) var(--space-4); cursor: pointer; font-size: var(--text-sm); }
            .save-btn:disabled { opacity: 0.5; cursor: not-allowed; }
            .soft-btn { border-color: var(--crm-stroke); background: var(--crm-surface-elevated); color: var(--text-primary); }
            .danger-btn { border-color: #B91C1C; background: #7F1D1D; color: #FEE2E2; }
            @media (max-width: 767px) { .schema-field-row { grid-template-columns: 1fr; } }
        `,
    ];

    constructor() {
        super();
        this.rows = [];
        this.schemaOptions = null;
        this.required = false;
        this.disabled = false;
    }

    _defaultFieldType() {
        return this.schemaOptions?.field_types?.[0]?.type_id || 'string';
    }

    _emit(rows) {
        this.dispatchEvent(new CustomEvent('rows-changed', { detail: { rows }, bubbles: false, composed: false }));
    }

    _addRow() {
        this._emit([...(this.rows || []), createEmptySchemaFieldRow(this._defaultFieldType())]);
    }

    _removeRow(index) {
        this._emit((this.rows || []).filter((_, i) => i !== index));
    }

    _updateRow(index, patch) {
        this._emit((this.rows || []).map((row, i) => (i === index ? { ...row, ...patch } : row)));
    }

    render() {
        const rows = Array.isArray(this.rows) ? this.rows : [];
        const fieldTypes = this.schemaOptions?.field_types || [];
        const enumSets = this.schemaOptions?.enum_sets || [];
        const t = (key, vars) => this.i18n.t(key, vars);

        return html`
            <div class="fields-list">
                ${rows.length > 0
                    ? rows.map((row, index) => html`
                        <div class="schema-field-card">
                            <div class="schema-field-row">
                                <input
                                    class="form-input mono"
                                    placeholder=${t('schema_builder.ph_key')}
                                    .value=${row.key || ''}
                                    ?disabled=${this.disabled}
                                    @input=${(e) => this._updateRow(index, { key: e.target.value })}
                                />
                                <input
                                    class="form-input"
                                    placeholder=${t('schema_builder.ph_label')}
                                    .value=${row.label || ''}
                                    ?disabled=${this.disabled}
                                    @input=${(e) => this._updateRow(index, { label: e.target.value })}
                                />
                            </div>
                            <div class="schema-field-row">
                                <select
                                    class="form-select"
                                    .value=${row.type || this._defaultFieldType()}
                                    ?disabled=${this.disabled}
                                    @change=${(e) => this._updateRow(index, { type: e.target.value })}
                                >
                                    ${fieldTypes.map((typeItem) => html`<option value=${typeItem.type_id}>${typeItem.label}</option>`)}
                                </select>
                                <input
                                    class="form-input"
                                    placeholder=${t('schema_builder.ph_desc')}
                                    .value=${row.description || ''}
                                    ?disabled=${this.disabled}
                                    @input=${(e) => this._updateRow(index, { description: e.target.value })}
                                />
                            </div>
                            ${row.type === 'enum' ? html`
                                <div class="schema-field-row">
                                    <select
                                        class="form-select"
                                        .value=${row.enum_set_id || ''}
                                        ?disabled=${this.disabled}
                                        @change=${(e) => this._updateRow(index, { enum_set_id: e.target.value })}
                                    >
                                        <option value="">${t('schema_builder.enum_local')}</option>
                                        ${enumSets.map((setItem) => html`<option value=${setItem.enum_set_id}>${setItem.label}</option>`)}
                                    </select>
                                    <input
                                        class="form-input"
                                        placeholder="values: high, medium, low"
                                        .value=${row.enum_values_text || ''}
                                        ?disabled=${this.disabled || Boolean(row.enum_set_id)}
                                        @input=${(e) => this._updateRow(index, { enum_values_text: e.target.value })}
                                    />
                                </div>
                            ` : ''}
                            <div class="schema-field-inline">
                                <button
                                    class="save-btn danger-btn"
                                    type="button"
                                    ?disabled=${this.disabled}
                                    @click=${() => this._removeRow(index)}
                                >${t('schema_builder.remove')}</button>
                            </div>
                        </div>
                    `)
                    : html`<div class="schema-empty">${t('schema_builder.no_fields')}</div>`
                }
            </div>
            <div class="add-row">
                <button
                    class="save-btn soft-btn"
                    type="button"
                    ?disabled=${this.disabled}
                    @click=${this._addRow}
                >${t('schema_builder.add_field')}</button>
            </div>
        `;
    }
}

customElements.define('schema-field-builder', SchemaFieldBuilder);
