/**
 * platform-schema-parameter-card — одна карточка параметра JSON Schema object.
 * Presentational: row in / row-change out.
 */

import { html, css, nothing } from 'lit';
import { PlatformElement } from '../../platform-element/index.js';
import '../fields/platform-field.js';
import '../platform-button.js';
import '../platform-icon.js';
import '../platform-switch.js';
import '../tag-input.js';
import { SCHEMA_UI_TYPES, createEmptyParameterRow } from './schema-model.js';

const NESTED_UI_TYPES = Object.freeze(['string', 'number', 'integer', 'boolean', 'enum']);
const ITEMS_UI_TYPES = Object.freeze(['string', 'number', 'integer', 'boolean', 'enum']);

export class PlatformSchemaParameterCard extends PlatformElement {
    static i18nNamespace = 'platform';

    static properties = {
        row: { type: Object },
        index: { type: Number },
        readonly: { type: Boolean },
        canMoveUp: { type: Boolean },
        canMoveDown: { type: Boolean },
    };

    static styles = [
        PlatformElement.styles,
        css`
            :host {
                display: block;
            }
            .card {
                display: flex;
                flex-direction: column;
                gap: var(--space-2);
                padding: var(--space-3);
                border: 1px solid var(--glass-border-subtle);
                border-radius: var(--radius-md);
                background: var(--glass-solid-medium);
            }
            .card-head {
                display: flex;
                align-items: flex-start;
                gap: var(--space-2);
                min-width: 0;
            }
            .card-main {
                flex: 1 1 auto;
                min-width: 0;
                display: flex;
                flex-direction: column;
                gap: var(--space-2);
            }
            .card-actions {
                display: inline-flex;
                align-items: center;
                gap: var(--space-1);
                flex-shrink: 0;
            }
            .row-2 {
                display: grid;
                grid-template-columns: minmax(0, 1.2fr) minmax(0, 1fr) auto;
                gap: var(--space-2);
                align-items: end;
            }
            .required-wrap {
                display: flex;
                align-items: center;
                min-height: 40px;
                padding-bottom: 2px;
            }
            .section-label {
                font-size: var(--text-xs);
                font-weight: var(--font-semibold);
                color: var(--text-tertiary);
                text-transform: uppercase;
                letter-spacing: 0.04em;
            }
            .enum-wrap,
            .items-wrap {
                display: flex;
                flex-direction: column;
                gap: var(--space-2);
            }
            .nested-wrap {
                display: flex;
                flex-direction: column;
                gap: var(--space-2);
                margin-top: var(--space-1);
                margin-left: var(--space-2);
                padding: var(--space-2) var(--space-2) var(--space-2) var(--space-3);
                border-left: 3px solid var(--accent);
                border-radius: 0 var(--radius-md) var(--radius-md) 0;
                background: color-mix(in srgb, var(--accent) 6%, var(--glass-solid-subtle));
                box-sizing: border-box;
            }
            .nested-wrap > .section-label {
                display: inline-flex;
                align-items: center;
                gap: var(--space-1);
                color: var(--accent);
            }
            .nested-list {
                display: flex;
                flex-direction: column;
                gap: var(--space-1);
            }
            .nested-card {
                display: grid;
                gap: var(--space-1);
                padding: var(--space-2);
                border: 1px solid color-mix(in srgb, var(--accent) 22%, var(--glass-border-subtle));
                border-radius: var(--radius-sm);
                background: var(--bg-elevated, var(--glass-solid-medium));
                box-shadow: none;
                max-width: 36rem;
            }
            .nested-card platform-field {
                font-size: var(--text-xs);
            }
            .nested-head {
                display: grid;
                grid-template-columns: minmax(0, 1.1fr) minmax(0, 0.9fr) auto auto;
                gap: var(--space-1);
                align-items: end;
            }
            .nested-required-wrap {
                display: flex;
                align-items: center;
                min-height: 32px;
                padding-bottom: 1px;
            }
            .nested-required-wrap .label,
            .nested-required-wrap platform-switch {
                font-size: var(--text-xs);
            }
            .nested-add {
                align-self: flex-start;
            }
            @media (max-width: 767px) {
                .row-2,
                .nested-head {
                    grid-template-columns: 1fr;
                }
                .nested-wrap {
                    margin-left: 0;
                }
                .nested-card {
                    max-width: none;
                }
            }
        `,
    ];

    constructor() {
        super();
        this.row = createEmptyParameterRow();
        this.index = 0;
        this.readonly = false;
        this.canMoveUp = false;
        this.canMoveDown = false;
    }

    /**
     * @param {Partial<ReturnType<typeof createEmptyParameterRow>>} patch
     */
    _emitPatch(patch) {
        const current = this.row && typeof this.row === 'object' ? this.row : createEmptyParameterRow();
        this.emit('row-change', {
            index: this.index,
            row: { ...current, ...patch },
        });
    }

    _uiTypeEnumConfig(types) {
        return {
            values: types.map((value) => ({
                value,
                label: this.t(`schema_editor.type_${value}`),
            })),
        };
    }

    _onKeyChange(e) {
        this._emitPatch({ key: typeof e.detail?.value === 'string' ? e.detail.value : '' });
    }

    _onDescriptionChange(e) {
        this._emitPatch({
            description: typeof e.detail?.value === 'string' ? e.detail.value : '',
        });
    }

    _onTypeChange(e) {
        const value = typeof e.detail?.value === 'string' ? e.detail.value : 'string';
        if (!SCHEMA_UI_TYPES.includes(value)) {
            throw new Error(`platform-schema-parameter-card: unknown uiType ${value}`);
        }
        this._emitPatch({ uiType: value });
    }

    _onRequiredChange(e) {
        this._emitPatch({ required: Boolean(e.detail?.value) });
    }

    _onEnumTagsChange(e) {
        const tags = Array.isArray(e.detail?.tags) ? e.detail.tags : [];
        this._emitPatch({ enumValues: tags });
    }

    _onItemsTypeChange(e) {
        const value = typeof e.detail?.value === 'string' ? e.detail.value : 'string';
        if (!ITEMS_UI_TYPES.includes(value)) {
            throw new Error(`platform-schema-parameter-card: unknown itemsUiType ${value}`);
        }
        this._emitPatch({ itemsUiType: value });
    }

    _onItemsEnumChange(e) {
        const tags = Array.isArray(e.detail?.tags) ? e.detail.tags : [];
        this._emitPatch({ itemsEnumValues: tags });
    }

    _addNested() {
        const current = this.row && typeof this.row === 'object' ? this.row : createEmptyParameterRow();
        const nestedRows = Array.isArray(current.nestedRows) ? [...current.nestedRows] : [];
        nestedRows.push({
            key: '',
            required: false,
            uiType: 'string',
            description: '',
            enumValues: [],
            extra: {},
        });
        this._emitPatch({ nestedRows });
    }

    /**
     * @param {number} nestedIndex
     * @param {Record<string, unknown>} patch
     */
    _patchNested(nestedIndex, patch) {
        const current = this.row && typeof this.row === 'object' ? this.row : createEmptyParameterRow();
        const nestedRows = (Array.isArray(current.nestedRows) ? current.nestedRows : []).map(
            (nested, i) => (i === nestedIndex ? { ...nested, ...patch } : nested),
        );
        this._emitPatch({ nestedRows });
    }

    _removeNested(nestedIndex) {
        const current = this.row && typeof this.row === 'object' ? this.row : createEmptyParameterRow();
        const nestedRows = (Array.isArray(current.nestedRows) ? current.nestedRows : []).filter(
            (_, i) => i !== nestedIndex,
        );
        this._emitPatch({ nestedRows });
    }

    _renderEnumEditor(tags, onChange) {
        return html`
            <div class="enum-wrap">
                <span class="section-label">${this.t('schema_editor.enum_values')}</span>
                <tag-input
                    preserve-case
                    .tags=${tags}
                    .placeholder=${this.t('schema_editor.enum_placeholder')}
                    ?readonly=${this.readonly}
                    @change=${onChange}
                ></tag-input>
            </div>
        `;
    }

    _renderItemsEditor(row) {
        return html`
            <div class="items-wrap">
                <platform-field
                    mode="edit"
                    type="enum"
                    .label=${this.t('schema_editor.items_type')}
                    .value=${row.itemsUiType}
                    .config=${this._uiTypeEnumConfig(ITEMS_UI_TYPES)}
                    ?disabled=${this.readonly}
                    @change=${this._onItemsTypeChange}
                ></platform-field>
                ${row.itemsUiType === 'enum'
                    ? this._renderEnumEditor(row.itemsEnumValues, this._onItemsEnumChange)
                    : nothing}
            </div>
        `;
    }

    _renderNestedEditor(row) {
        const nestedRows = Array.isArray(row.nestedRows) ? row.nestedRows : [];
        return html`
            <div class="nested-wrap" data-nested>
                <span class="section-label">
                    <platform-icon name="chevron-right" size="12"></platform-icon>
                    ${this.t('schema_editor.nested_properties')}
                </span>
                <div class="nested-list">
                    ${nestedRows.map((nested, nestedIndex) => html`
                        <div class="nested-card">
                            <div class="nested-head">
                                <platform-field
                                    mode="edit"
                                    type="string"
                                    pill-density="dense"
                                    .label=${this.t('schema_editor.field_key')}
                                    .value=${nested.key}
                                    ?disabled=${this.readonly}
                                    @change=${(e) => {
                                        this._patchNested(nestedIndex, {
                                            key: typeof e.detail?.value === 'string' ? e.detail.value : '',
                                        });
                                    }}
                                ></platform-field>
                                <platform-field
                                    mode="edit"
                                    type="enum"
                                    pill-density="dense"
                                    .label=${this.t('schema_editor.field_type')}
                                    .value=${nested.uiType}
                                    .config=${this._uiTypeEnumConfig(NESTED_UI_TYPES)}
                                    ?disabled=${this.readonly}
                                    @change=${(e) => {
                                        const value =
                                            typeof e.detail?.value === 'string' ? e.detail.value : 'string';
                                        if (!NESTED_UI_TYPES.includes(value)) {
                                            throw new Error(
                                                `platform-schema-parameter-card: nested uiType ${value}`,
                                            );
                                        }
                                        this._patchNested(nestedIndex, { uiType: value });
                                    }}
                                ></platform-field>
                                <div class="nested-required-wrap">
                                    <platform-switch
                                        size="sm"
                                        .checked=${Boolean(nested.required)}
                                        .label=${this.t('schema_editor.field_required')}
                                        ?disabled=${this.readonly}
                                        @change=${(e) => {
                                            this._patchNested(nestedIndex, {
                                                required: Boolean(e.detail?.value),
                                            });
                                        }}
                                    ></platform-switch>
                                </div>
                                ${this.readonly
                                    ? nothing
                                    : html`
                                        <platform-button
                                            variant="ghost"
                                            icon-only
                                            density="compact"
                                            title=${this.t('schema_editor.remove_nested')}
                                            aria-label=${this.t('schema_editor.remove_nested')}
                                            @click=${() => this._removeNested(nestedIndex)}
                                        >
                                            <platform-icon name="trash" size="12"></platform-icon>
                                        </platform-button>
                                    `}
                            </div>
                            <platform-field
                                mode="edit"
                                type="text"
                                pill-density="dense"
                                .label=${this.t('schema_editor.field_description')}
                                .value=${nested.description}
                                ?disabled=${this.readonly}
                                @change=${(e) => {
                                    this._patchNested(nestedIndex, {
                                        description:
                                            typeof e.detail?.value === 'string' ? e.detail.value : '',
                                    });
                                }}
                            ></platform-field>
                            ${nested.uiType === 'enum'
                                ? this._renderEnumEditor(
                                    Array.isArray(nested.enumValues) ? nested.enumValues : [],
                                    (e) => {
                                        const tags = Array.isArray(e.detail?.tags) ? e.detail.tags : [];
                                        this._patchNested(nestedIndex, { enumValues: tags });
                                    },
                                )
                                : nothing}
                        </div>
                    `)}
                </div>
                ${this.readonly
                    ? nothing
                    : html`
                        <platform-button
                            class="nested-add"
                            variant="secondary"
                            density="compact"
                            @click=${this._addNested}
                        >
                            <platform-icon name="plus" size="12"></platform-icon>
                            ${this.t('schema_editor.add_nested')}
                        </platform-button>
                    `}
            </div>
        `;
    }

    render() {
        const row = this.row && typeof this.row === 'object' ? this.row : createEmptyParameterRow();
        return html`
            <div class="card">
                <div class="card-head">
                    <div class="card-main">
                        <div class="row-2">
                            <platform-field
                                mode="edit"
                                type="string"
                                .label=${this.t('schema_editor.field_key')}
                                .value=${row.key}
                                ?disabled=${this.readonly}
                                @change=${this._onKeyChange}
                            ></platform-field>
                            <platform-field
                                mode="edit"
                                type="enum"
                                .label=${this.t('schema_editor.field_type')}
                                .value=${row.uiType}
                                .config=${this._uiTypeEnumConfig(SCHEMA_UI_TYPES)}
                                ?disabled=${this.readonly}
                                @change=${this._onTypeChange}
                            ></platform-field>
                            <div class="required-wrap">
                                <platform-switch
                                    size="sm"
                                    .checked=${Boolean(row.required)}
                                    .label=${this.t('schema_editor.field_required')}
                                    ?disabled=${this.readonly}
                                    @change=${this._onRequiredChange}
                                ></platform-switch>
                            </div>
                        </div>
                        <platform-field
                            mode="edit"
                            type="text"
                            .label=${this.t('schema_editor.field_description')}
                            .value=${row.description}
                            ?disabled=${this.readonly}
                            @change=${this._onDescriptionChange}
                        ></platform-field>
                        ${row.uiType === 'enum'
                            ? this._renderEnumEditor(
                                Array.isArray(row.enumValues) ? row.enumValues : [],
                                this._onEnumTagsChange,
                            )
                            : nothing}
                        ${row.uiType === 'array' ? this._renderItemsEditor(row) : nothing}
                        ${row.uiType === 'object' ? this._renderNestedEditor(row) : nothing}
                    </div>
                    <div class="card-actions">
                        <platform-button
                            variant="ghost"
                            icon-only
                            density="compact"
                            ?disabled=${this.readonly || !this.canMoveUp}
                            title=${this.t('schema_editor.move_up')}
                            aria-label=${this.t('schema_editor.move_up')}
                            @click=${() => this.emit('row-move', { index: this.index, direction: -1 })}
                        >
                            <platform-icon name="chevron-up" size="14"></platform-icon>
                        </platform-button>
                        <platform-button
                            variant="ghost"
                            icon-only
                            density="compact"
                            ?disabled=${this.readonly || !this.canMoveDown}
                            title=${this.t('schema_editor.move_down')}
                            aria-label=${this.t('schema_editor.move_down')}
                            @click=${() => this.emit('row-move', { index: this.index, direction: 1 })}
                        >
                            <platform-icon name="chevron-down" size="14"></platform-icon>
                        </platform-button>
                        ${this.readonly
                            ? nothing
                            : html`
                                <platform-button
                                    variant="ghost"
                                    icon-only
                                    density="compact"
                                    title=${this.t('schema_editor.remove_parameter')}
                                    aria-label=${this.t('schema_editor.remove_parameter')}
                                    @click=${() => this.emit('row-remove', { index: this.index })}
                                >
                                    <platform-icon name="trash" size="14"></platform-icon>
                                </platform-button>
                            `}
                    </div>
                </div>
            </div>
        `;
    }
}

customElements.define('platform-schema-parameter-card', PlatformSchemaParameterCard);
