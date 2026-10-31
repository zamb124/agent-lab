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
import '@platform/lib/components/fields/platform-field.js';
import '@platform/lib/components/platform-empty-state.js';
import { isPlainRecord } from '@platform/lib/events/payload.js';
import type {
    CSSResultGroup,
    PropertyDeclarations,
    TemplateResult,
} from 'lit';

export interface SchemaFieldRow {
    key: string;
    label: string;
    type: string;
    description: string;
    enum_set_id: string;
    enum_values_text: string;
    extra: Record<string, unknown>;
}

export function isSchemaFieldRow(value: unknown): value is SchemaFieldRow {
    if (value === null || typeof value !== 'object' || Array.isArray(value)) return false;
    if (!('key' in value) || typeof value.key !== 'string') return false;
    if (!('label' in value) || typeof value.label !== 'string') return false;
    if (!('type' in value) || typeof value.type !== 'string') return false;
    if (!('description' in value) || typeof value.description !== 'string') return false;
    if (!('enum_set_id' in value) || typeof value.enum_set_id !== 'string') return false;
    if (!('enum_values_text' in value) || typeof value.enum_values_text !== 'string') return false;
    if (!('extra' in value) || value.extra === null || typeof value.extra !== 'object' || Array.isArray(value.extra)) return false;
    return true;
}

function optionRecords(value: unknown): Record<string, unknown>[] {
    if (!Array.isArray(value)) return [];
    const rows: Record<string, unknown>[] = [];
    for (const item of value) {
        if (!isPlainRecord(item)) {
            throw new Error('schema-field-builder: option must be an object');
        }
        rows.push(item);
    }
    return rows;
}

export function createEmptySchemaFieldRow(defaultType: unknown): SchemaFieldRow {
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

export function normalizeSchemaRows(schemaValue: unknown): SchemaFieldRow[] {
    if (!schemaValue || typeof schemaValue !== 'object' || Array.isArray(schemaValue)) {
        return [];
    }
    return Object.entries(schemaValue).map(([fieldKey, rawValue]) => {
        if (!isPlainRecord(rawValue)) {
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
            .map((item: unknown) => (typeof item === 'string' ? item.trim() : ''))
            .filter((item: string) => item.length > 0);
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

export function buildSchemaFromRows(rows: unknown, sectionLabel: string, schemaOptions: Record<string, unknown> | null | undefined, t: (key: string, vars?: Record<string, string>) => string): Record<string, unknown> {
    if (!Array.isArray(rows)) {
        throw new Error(`${sectionLabel} rows must be array`);
    }
    if (typeof t !== 'function') {
        throw new Error('buildSchemaFromRows: t function required');
    }
    const schema: Record<string, Record<string, unknown>> = {};
    const seenKeys = new Set();
    const optsFieldTypes = optionRecords(schemaOptions == null ? undefined : schemaOptions.field_types);
    const optsEnumSets = optionRecords(schemaOptions == null ? undefined : schemaOptions.enum_sets);
    const fieldTypeIds = new Set<string>();
    for (const item of optsFieldTypes) {
        if (typeof item.type_id !== 'string' || item.type_id.length === 0) {
            throw new Error('schema-field-builder: field type id required');
        }
        fieldTypeIds.add(item.type_id);
    }
    const enumSetsMap = new Map<string, unknown>();
    for (const item of optsEnumSets) {
        if (typeof item.enum_set_id !== 'string' || item.enum_set_id.length === 0) {
            throw new Error('schema-field-builder: enum_set_id required');
        }
        enumSetsMap.set(item.enum_set_id, item.values);
    }
    const limitsValue = schemaOptions == null ? undefined : schemaOptions.validation_limits;
    const limits = isPlainRecord(limitsValue) ? limitsValue : null;
    const maxFieldsPerSection = limits !== null && typeof limits.max_fields_per_section === 'number'
        ? limits.max_fields_per_section
        : 0;
    if (maxFieldsPerSection > 0 && rows.length > maxFieldsPerSection) {
        throw new Error(t('errors.field_limit', { section: sectionLabel, max: String(maxFieldsPerSection) }));
    }
    for (const row of rows) {
        if (!isSchemaFieldRow(row)) {
            throw new Error(`${sectionLabel}: schema row required`);
        }
        const key = row.key.trim();
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
        const typeId = row.type.trim();
        if (fieldTypeIds.size > 0 && !fieldTypeIds.has(typeId)) {
            throw new Error(t('errors.unknown_type', { section: sectionLabel, type: typeId, key }));
        }
        const descriptor: Record<string, unknown> = {
            ...(row && row.extra && typeof row.extra === 'object' ? row.extra : {}),
            type: typeId,
        };
        const label = row.label.trim();
        if (label.length > 0) {
            descriptor.label = label;
        }
        const description = row.description.trim();
        if (description.length > 0) {
            descriptor.description = description;
        }
        if (typeId === 'enum') {
            const enumSetId = row.enum_set_id.trim();
            if (enumSetId.length > 0) {
                if (enumSetsMap.size > 0 && !enumSetsMap.has(enumSetId)) {
                    throw new Error(t('errors.enum_set_missing', { section: sectionLabel, id: enumSetId }));
                }
                descriptor.enum_set_id = enumSetId;
                if (enumSetsMap.has(enumSetId)) {
                    descriptor.values = enumSetsMap.get(enumSetId);
                }
            } else {
                const values = row.enum_values_text
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

    static override properties: PropertyDeclarations = {
        rows: { type: Array },
        schemaOptions: { type: Object },
        required: { type: Boolean },
        disabled: { type: Boolean },
    };
    declare rows: SchemaFieldRow[];
    declare schemaOptions: Record<string, unknown> | null;
    declare required: boolean;
    declare disabled: boolean;

    static override styles: CSSResultGroup = [
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

            .field-row platform-field {
                min-width: 0;
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
        const types = optionRecords(this.schemaOptions == null ? undefined : this.schemaOptions.field_types);
        const first = types[0];
        if (first !== undefined && typeof first.type_id === 'string') {
            return first.type_id;
        }
        return 'string';
    }

    _emitRows(rows: SchemaFieldRow[]) {
        this.emit('rows-changed', { rows });
    }

    _addRow() {
        const next = Array.isArray(this.rows) ? [...this.rows] : [];
        next.push(createEmptySchemaFieldRow(this._defaultFieldType()));
        this._emitRows(next);
    }

    _removeRow(index: number) {
        const next = (Array.isArray(this.rows) ? this.rows : []).filter((_, i) => i !== index);
        this._emitRows(next);
    }

    _updateRow(index: number, patch: Partial<SchemaFieldRow>) {
        const next = (Array.isArray(this.rows) ? this.rows : []).map(
            (row, i) => (i === index ? { ...row, ...patch } : row),
        );
        this._emitRows(next);
    }

    _fieldTypeEnumConfig(fieldTypes: Record<string, unknown>[]): { values: { value: string; label: string }[] } {
        const values = fieldTypes.map((ti) => {
            const id = typeof ti.type_id === 'string' ? ti.type_id : '';
            const lb = typeof ti.label === 'string' && ti.label.length > 0 ? ti.label : id;
            return { value: id, label: lb };
        });
        return { values };
    }

    _enumSetEnumConfig(enumSets: Record<string, unknown>[]): { values: { value: string; label: string }[] } {
        const local = { value: '', label: this.t('schema_builder.enum_local') };
        const rest = enumSets.map((si) => {
            const id = typeof si.enum_set_id === 'string' ? si.enum_set_id : '';
            const lb = typeof si.label === 'string' && si.label.length > 0 ? si.label : id;
            return { value: id, label: lb };
        });
        return { values: [local, ...rest] };
    }

    override render(): TemplateResult {
        const rows = Array.isArray(this.rows) ? this.rows : [];
        const fieldTypes = optionRecords(this.schemaOptions == null ? undefined : this.schemaOptions.field_types);
        const enumSets = optionRecords(this.schemaOptions == null ? undefined : this.schemaOptions.enum_sets);
        return html`
            <div class="fields-list">
                ${rows.length > 0 ? rows.map((row, index) => {
                        const rowKey = typeof row.key === 'string' ? row.key : '';
                        const rowLabel = typeof row.label === 'string' ? row.label : '';
                        const rowType = typeof row.type === 'string' ? row.type : this._defaultFieldType();
                        const rowDesc = typeof row.description === 'string' ? row.description : '';
                        const rowEnumSet = typeof row.enum_set_id === 'string' ? row.enum_set_id : '';
                        const rowEnumText = typeof row.enum_values_text === 'string' ? row.enum_values_text : '';
                        return html`
                    <div class="field-card">
                        <div class="field-row">
                            <platform-field
                                type="string"
                                mode="edit"
                                input-type="text"
                                .placeholder=${this.t('schema_builder.ph_key')}
                                .value=${rowKey}
                                ?disabled=${this.disabled}
                                @change=${(e: CustomEvent<{ value?: unknown }>) => this._updateRow(
                                    index,
                                    { key: typeof e.detail.value === 'string' ? e.detail.value : '' },
                                )}
                            ></platform-field>
                            <platform-field
                                type="string"
                                mode="edit"
                                input-type="text"
                                .placeholder=${this.t('schema_builder.ph_label')}
                                .value=${rowLabel}
                                ?disabled=${this.disabled}
                                @change=${(e: CustomEvent<{ value?: unknown }>) => this._updateRow(
                                    index,
                                    { label: typeof e.detail.value === 'string' ? e.detail.value : '' },
                                )}
                            ></platform-field>
                        </div>
                        <div class="field-row">
                            <platform-field
                                type="enum"
                                mode="edit"
                                .config=${this._fieldTypeEnumConfig(fieldTypes)}
                                .value=${rowType}
                                ?disabled=${this.disabled}
                                @change=${(e: CustomEvent<{ value?: unknown }>) => this._updateRow(
                                    index,
                                    { type: typeof e.detail.value === 'string' ? e.detail.value : this._defaultFieldType() },
                                )}
                            ></platform-field>
                            <platform-field
                                type="string"
                                mode="edit"
                                input-type="text"
                                .placeholder=${this.t('schema_builder.ph_desc')}
                                .value=${rowDesc}
                                ?disabled=${this.disabled}
                                @change=${(e: CustomEvent<{ value?: unknown }>) => this._updateRow(
                                    index,
                                    { description: typeof e.detail.value === 'string' ? e.detail.value : '' },
                                )}
                            ></platform-field>
                        </div>
                        ${rowType === 'enum' ? html`
                            <div class="field-row">
                                <platform-field
                                    type="enum"
                                    mode="edit"
                                    .config=${this._enumSetEnumConfig(enumSets)}
                                    .value=${rowEnumSet}
                                    ?disabled=${this.disabled}
                                    @change=${(e: CustomEvent<{ value?: unknown }>) => this._updateRow(
                                        index,
                                        { enum_set_id: typeof e.detail.value === 'string' ? e.detail.value : '' },
                                    )}
                                ></platform-field>
                                <platform-field
                                    type="string"
                                    mode="edit"
                                    input-type="text"
                                    .placeholder=${this.t('schema_builder.ph_enum_values')}
                                    .value=${rowEnumText}
                                    ?disabled=${this.disabled || Boolean(row.enum_set_id)}
                                    @change=${(e: CustomEvent<{ value?: unknown }>) => this._updateRow(
                                        index,
                                        { enum_values_text: typeof e.detail.value === 'string' ? e.detail.value : '' },
                                    )}
                                ></platform-field>
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
                `;
                }) : html`<platform-empty-state icon="text-fields" title=${this.t('schema_builder.no_fields')}></platform-empty-state>`}
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
