/**
 * SchemaFieldBuilder — управляемый редактор массива полей JSON Schema.
 *
 * Чистый presentational PlatformElement: входы — `rows` и `schemaOptions`,
 * выход — событие `rows-changed` (через `emit`). Без HTTP, без store,
 * без DI. Применяется в templates-page для секций `required_fields` и
 * `optional_fields` шаблонов.
 *
 * Вспомогательные функции `createEmptySchemaFieldRow`, `normalizeSchemaRows`
 * и `buildSchemaFromRows` экспортируются для родителя — они выполняют
 * двустороннюю конвертацию rows ↔ JSON Schema объект и валидацию.
 */

import { html, css } from 'lit';
import { PlatformElement } from '@platform/lib/platform-element/index.js';

export function createEmptySchemaFieldRow(defaultType) {
    if (typeof defaultType !== 'string' || defaultType.length === 0) {
        throw new Error('createEmptySchemaFieldRow: defaultType required');
    }
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
            Object.entries(rawValue).filter(
                ([key]) => !['type', 'label', 'description', 'values', 'enum_set_id'].includes(key),
            ),
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

export function buildSchemaFromRows(rows, sectionLabel, schemaOptions, t) {
    if (!Array.isArray(rows)) {
        throw new Error(`${sectionLabel} rows must be array`);
    }
    if (typeof t !== 'function') {
        throw new Error('buildSchemaFromRows: t function required');
    }
    const schema = {};
    const seenKeys = new Set();
    const optsFieldTypes = schemaOptions && Array.isArray(schemaOptions.field_types) ? schemaOptions.field_types : [];
    const optsEnumSets = schemaOptions && Array.isArray(schemaOptions.enum_sets) ? schemaOptions.enum_sets : [];
    const fieldTypes = new Set(optsFieldTypes.map((item) => item.type_id));
    const enumSetsMap = new Map(
        optsEnumSets.map((item) => [item.enum_set_id, item.values]),
    );
    const limits = schemaOptions && schemaOptions.validation_limits;
    const maxFieldsPerSection = limits && typeof limits.max_fields_per_section === 'number'
        ? limits.max_fields_per_section
        : 0;
    if (maxFieldsPerSection > 0 && rows.length > maxFieldsPerSection) {
        throw new Error(t('errors.field_limit', { section: sectionLabel, max: String(maxFieldsPerSection) }));
    }
    for (const row of rows) {
        const key = String((row && row.key) || '').trim();
        if (key.length === 0) {
            continue;
        }
        if (!/^[a-zA-Z_][a-zA-Z0-9_]*$/.test(key)) {
            throw new Error(t('errors.bad_key', { section: sectionLabel, key }));
        }
        if (seenKeys.has(key)) {
            throw new Error(t('errors.dup_key', { section: sectionLabel, key }));
        }
        seenKeys.add(key);
        const typeId = String((row && row.type) || '').trim();
        if (fieldTypes.size > 0 && !fieldTypes.has(typeId)) {
            throw new Error(t('errors.unknown_type', { section: sectionLabel, type: typeId, key }));
        }
        const descriptor = {
            ...(row && row.extra && typeof row.extra === 'object' ? row.extra : {}),
            type: typeId,
        };
        const label = String((row && row.label) || '').trim();
        if (label.length > 0) {
            descriptor.label = label;
        }
        const description = String((row && row.description) || '').trim();
        if (description.length > 0) {
            descriptor.description = description;
        }
        if (typeId === 'enum') {
            const enumSetId = String((row && row.enum_set_id) || '').trim();
            if (enumSetId.length > 0) {
                if (enumSetsMap.size > 0 && !enumSetsMap.has(enumSetId)) {
                    throw new Error(t('errors.enum_set_missing', { section: sectionLabel, id: enumSetId }));
                }
                descriptor.enum_set_id = enumSetId;
                if (enumSetsMap.has(enumSetId)) {
                    descriptor.values = enumSetsMap.get(enumSetId);
                }
            } else {
                const values = String((row && row.enum_values_text) || '')
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
    static i18nNamespace = 'crm';

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

            .fields-list {
                display: flex;
                flex-direction: column;
                gap: var(--space-2);
            }

            .field-card {
                border: 1px solid var(--glass-border-subtle);
                border-radius: var(--radius-md);
                background: var(--glass-solid-medium);
                padding: var(--space-2);
                display: grid;
                gap: var(--space-2);
            }

            .field-row {
                display: grid;
                gap: var(--space-2);
                grid-template-columns: 1fr 1fr;
            }

            .field-inline {
                display: flex;
                align-items: center;
                gap: var(--space-2);
                flex-wrap: wrap;
            }

            .empty {
                color: var(--text-tertiary);
                font-size: var(--text-sm);
            }

            .add-row {
                display: flex;
                margin-top: var(--space-1);
            }

            .input,
            .select {
                border: 1px solid var(--glass-border-subtle);
                border-radius: var(--radius-md);
                background: var(--glass-solid-medium);
                color: var(--text-primary);
                padding: var(--space-2) var(--space-3);
                font: inherit;
                font-size: var(--text-sm);
                width: 100%;
                box-sizing: border-box;
            }

            .input:disabled,
            .select:disabled {
                opacity: 0.6;
                cursor: not-allowed;
            }

            .mono {
                font-family: var(--font-mono, ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace);
                font-size: var(--text-xs);
            }

            .btn {
                display: inline-flex;
                align-items: center;
                justify-content: center;
                gap: var(--space-2);
                border-radius: var(--radius-md);
                padding: var(--space-2) var(--space-4);
                cursor: pointer;
                font: inherit;
                font-size: var(--text-sm);
                font-weight: var(--font-medium);
                border: 1px solid transparent;
            }

            .btn-soft {
                background: var(--glass-solid-medium);
                color: var(--text-primary);
                border-color: var(--glass-border-subtle);
            }

            .btn-soft:hover:not(:disabled) {
                border-color: var(--accent);
            }

            .btn-danger {
                background: transparent;
                color: var(--color-danger, #ef4444);
                border-color: var(--color-danger, #ef4444);
            }

            .btn-danger:hover:not(:disabled) {
                background: var(--color-danger, #ef4444);
                color: white;
            }

            .btn:disabled {
                opacity: 0.5;
                cursor: not-allowed;
            }

            @media (max-width: 767px) {
                .field-row {
                    grid-template-columns: 1fr;
                }
            }
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
        const types = this.schemaOptions && this.schemaOptions.field_types;
        if (Array.isArray(types) && types.length > 0 && typeof types[0].type_id === 'string') {
            return types[0].type_id;
        }
        return 'string';
    }

    _emitRows(rows) {
        this.emit('rows-changed', { rows });
    }

    _addRow() {
        const next = Array.isArray(this.rows) ? [...this.rows] : [];
        next.push(createEmptySchemaFieldRow(this._defaultFieldType()));
        this._emitRows(next);
    }

    _removeRow(index) {
        const next = (Array.isArray(this.rows) ? this.rows : []).filter((_, i) => i !== index);
        this._emitRows(next);
    }

    _updateRow(index, patch) {
        const next = (Array.isArray(this.rows) ? this.rows : []).map(
            (row, i) => (i === index ? { ...row, ...patch } : row),
        );
        this._emitRows(next);
    }

    render() {
        const rows = Array.isArray(this.rows) ? this.rows : [];
        const fieldTypes = this.schemaOptions && Array.isArray(this.schemaOptions.field_types) ? this.schemaOptions.field_types : [];
        const enumSets = this.schemaOptions && Array.isArray(this.schemaOptions.enum_sets) ? this.schemaOptions.enum_sets : [];
        return html`
            <div class="fields-list">
                ${rows.length > 0 ? rows.map((row, index) => html`
                    <div class="field-card">
                        <div class="field-row">
                            <input
                                class="input mono"
                                placeholder=${this.t('schema_builder.ph_key')}
                                .value=${row.key || ''}
                                ?disabled=${this.disabled}
                                @input=${(e) => this._updateRow(index, { key: e.target.value })}
                            />
                            <input
                                class="input"
                                placeholder=${this.t('schema_builder.ph_label')}
                                .value=${row.label || ''}
                                ?disabled=${this.disabled}
                                @input=${(e) => this._updateRow(index, { label: e.target.value })}
                            />
                        </div>
                        <div class="field-row">
                            <select
                                class="select"
                                .value=${row.type || this._defaultFieldType()}
                                ?disabled=${this.disabled}
                                @change=${(e) => this._updateRow(index, { type: e.target.value })}
                            >
                                ${fieldTypes.map((typeItem) => html`
                                    <option value=${typeItem.type_id}>${typeItem.label}</option>
                                `)}
                            </select>
                            <input
                                class="input"
                                placeholder=${this.t('schema_builder.ph_desc')}
                                .value=${row.description || ''}
                                ?disabled=${this.disabled}
                                @input=${(e) => this._updateRow(index, { description: e.target.value })}
                            />
                        </div>
                        ${row.type === 'enum' ? html`
                            <div class="field-row">
                                <select
                                    class="select"
                                    .value=${row.enum_set_id || ''}
                                    ?disabled=${this.disabled}
                                    @change=${(e) => this._updateRow(index, { enum_set_id: e.target.value })}
                                >
                                    <option value="">${this.t('schema_builder.enum_local')}</option>
                                    ${enumSets.map((setItem) => html`
                                        <option value=${setItem.enum_set_id}>${setItem.label}</option>
                                    `)}
                                </select>
                                <input
                                    class="input"
                                    placeholder=${this.t('schema_builder.ph_enum_values')}
                                    .value=${row.enum_values_text || ''}
                                    ?disabled=${this.disabled || Boolean(row.enum_set_id)}
                                    @input=${(e) => this._updateRow(index, { enum_values_text: e.target.value })}
                                />
                            </div>
                        ` : ''}
                        <div class="field-inline">
                            <button
                                class="btn btn-danger"
                                type="button"
                                ?disabled=${this.disabled}
                                @click=${() => this._removeRow(index)}
                            >
                                ${this.t('schema_builder.remove')}
                            </button>
                        </div>
                    </div>
                `) : html`<div class="empty">${this.t('schema_builder.no_fields')}</div>`}
            </div>
            <div class="add-row">
                <button
                    class="btn btn-soft"
                    type="button"
                    ?disabled=${this.disabled}
                    @click=${this._addRow}
                >
                    ${this.t('schema_builder.add_field')}
                </button>
            </div>
        `;
    }
}

customElements.define('crm-schema-field-builder', SchemaFieldBuilder);
