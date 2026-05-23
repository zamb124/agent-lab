/**
 * crm-entity-type-editor — общий редактор типа сущности.
 *
 * Используется и в `templates-page` (тип внутри шаблона), и в
 * `namespace-detail-page` (тип компании, привязанный к namespace).
 *
 * Props:
 *   - typeDraft: { type_id, name, description, prompt, parent_type_id, icon,
 *                  color, is_event, check_duplicates, is_context_anchor,
 *                  is_voice_target, weight_coefficient, required_fields_rows,
 *                  optional_fields_rows, namespace_ids }
 *   - entityTypeCatalogRows: { type_id, parent_type_id }[] для определения ветки note
 *   - schemaOptions: { field_types[], enum_sets[], operators[], ... }
 *   - namespaces: list[{ name, description? }]
 *   - parentTypeOptions: string[]
 *   - editingTypeId: string ('' если создаём новый)
 *   - savingType: boolean
 *   - showNamespaces: boolean (true для templates-page; false для namespace-detail
 *                     где namespace задан контекстом и редактируется одним
 *                     toggle снаружи)
 *   - compactChrome: boolean — без внешней .panel и без верхнего panel-header
 *     (шапка рисует родитель, напр. `namespace-detail-page`).
 *
 * События (через emit):
 *   - draft-changed: { typeDraft }
 *   - schema-rows-changed: { section: 'required_fields_rows'|'optional_fields_rows', rows }
 *   - namespace-toggled: { namespaceName, enabled }
 *   - submit
 *   - cancel
 */

import { html, css } from 'lit';
import { PlatformElement } from '@platform/lib/platform-element/index.js';
import '@platform/lib/components/platform-icon.js';
import '@platform/lib/components/platform-switch.js';
import '@platform/lib/components/platform-icon-picker.js';
import '@platform/lib/components/platform-palette-color-picker.js';
import '@platform/lib/components/platform-help-hint.js';
import '@platform/lib/components/fields/platform-field.js';
import { listAvailableUiIcons } from '@platform/lib/utils/file-icons.js';
import './schema-field-builder.js';
import { buildSchemaFromRows } from './schema-field-builder.js';
import { entityTypeNoteSubtreeLocked } from '../utils/entity-type-note-subtree-lock.js';

const ENTITY_TYPE_UI_ICON_NAMES = Object.freeze(listAvailableUiIcons());

export class CRMEntityTypeEditor extends PlatformElement {
    static i18nNamespace = 'crm';

    static properties = {
        typeDraft: { attribute: false },
        schemaOptions: { attribute: false },
        namespaces: { attribute: false },
        parentTypeOptions: { attribute: false },
        entityTypeCatalogRows: { attribute: false },
        editingTypeId: { type: String },
        savingType: { type: Boolean },
        showNamespaces: { type: Boolean },
        compactChrome: { type: Boolean, attribute: 'compact-chrome' },
    };

    static styles = [
        PlatformElement.styles,
        css`
            :host { display: block; }

            .panel {
                background: var(--glass-solid-subtle);
                border: 1px solid var(--glass-border-subtle);
                border-radius: var(--radius-xl);
                padding: var(--space-4);
                display: flex;
                flex-direction: column;
                gap: var(--space-3);
                min-width: 0;
            }
            .root-compact {
                display: flex;
                flex-direction: column;
                gap: var(--space-3);
                min-width: 0;
            }
            .panel-header {
                display: flex;
                align-items: center;
                justify-content: space-between;
                gap: var(--space-2);
            }
            .panel-title {
                display: inline-flex;
                align-items: center;
                gap: var(--space-2);
                font-weight: 600;
                color: var(--text-primary);
            }

            .grid-2 {
                display: grid;
                grid-template-columns: 1fr 1fr;
                gap: var(--space-3);
            }
            @media (max-width: 980px) { .grid-2 { grid-template-columns: 1fr; } }

            .field { display: grid; gap: var(--space-1); }
            .field-label {
                font-size: var(--text-xs);
                color: var(--text-tertiary);
                text-transform: uppercase;
                letter-spacing: 0.04em;
            }
            .field-label-row {
                display: flex;
                align-items: center;
                gap: var(--space-2);
                flex-wrap: wrap;
            }
            .field-label-row .field-label {
                margin: 0;
            }
            .schema-section-title-row {
                display: flex;
                align-items: center;
                gap: var(--space-2);
                flex-wrap: wrap;
            }
            .schema-section-title-row .panel-title {
                margin: 0;
            }

            .flags-col {
                display: flex;
                flex-direction: column;
                gap: var(--space-3);
            }
            .flag-row {
                display: flex;
                align-items: center;
                justify-content: flex-start;
                gap: var(--space-2);
                width: 100%;
                min-width: 0;
            }
            .flag-row platform-switch {
                flex: 1;
                min-width: 0;
            }
            .flag-row platform-help-hint {
                flex-shrink: 0;
            }

            .schema-grid {
                display: grid;
                grid-template-columns: 1fr 1fr;
                gap: var(--space-3);
            }
            @media (max-width: 980px) { .schema-grid { grid-template-columns: 1fr; } }
            .schema-section {
                display: grid;
                gap: var(--space-2);
                padding: var(--space-3);
                border: 1px solid var(--crm-stroke);
                border-radius: var(--radius-md);
                background: var(--glass-tint-subtle);
            }
            .hint { color: var(--text-tertiary); font-size: var(--text-xs); }
            .empty {
                padding: var(--space-3);
                text-align: center;
                color: var(--text-tertiary);
                font-size: var(--text-sm);
            }

            .namespace-pills {
                display: flex;
                flex-wrap: wrap;
                gap: var(--space-1);
            }
            .ns-pill {
                padding: 4px 10px;
                border-radius: var(--radius-full);
                background: var(--glass-tint-medium);
                color: var(--text-secondary);
                border: 1px solid var(--glass-border-subtle);
                font-size: var(--text-xs);
                cursor: pointer;
            }
            .ns-pill.active {
                background: var(--accent);
                color: white;
                border-color: var(--accent);
            }

            .preview {
                background: var(--glass-solid-medium);
                padding: var(--space-2);
                border-radius: var(--radius-md);
                font-family: var(--font-mono);
                font-size: var(--text-xs);
                white-space: pre-wrap;
                color: var(--text-secondary);
                max-height: 240px;
                overflow: auto;
            }

            .actions-row {
                display: flex;
                justify-content: flex-end;
                gap: var(--space-2);
                margin-top: var(--space-3);
            }
            .btn {
                display: inline-flex;
                align-items: center;
                gap: 6px;
                padding: var(--space-2) var(--space-4);
                border-radius: var(--radius-md);
                border: 1px solid var(--crm-stroke);
                background: var(--crm-surface);
                color: var(--text-secondary);
                font-size: var(--text-sm);
                cursor: pointer;
            }
            .btn:hover:not(:disabled) {
                background: var(--crm-surface-muted);
                color: var(--text-primary);
            }
            .btn-primary {
                background: var(--accent);
                color: white;
                border-color: var(--accent);
            }
            .btn-primary:hover:not(:disabled) { filter: brightness(1.05); }
            .btn-soft {
                background: var(--glass-tint-medium);
                color: var(--text-secondary);
                border-color: transparent;
            }
            .btn-soft:hover:not(:disabled) {
                background: var(--glass-tint-strong);
                color: var(--text-primary);
            }
            .btn:disabled { opacity: 0.5; cursor: not-allowed; }
        `,
    ];

    constructor() {
        super();
        this.typeDraft = null;
        this.schemaOptions = null;
        this.namespaces = [];
        this.parentTypeOptions = [];
        this.entityTypeCatalogRows = [];
        this.editingTypeId = '';
        this.savingType = false;
        this.showNamespaces = true;
    }

    _emitDraftField(field, value) {
        if (field === 'is_context_anchor' || field === 'is_voice_target') {
            if (entityTypeNoteSubtreeLocked(this.typeDraft, this.entityTypeCatalogRows)) {
                return;
            }
        }
        const next = { ...this.typeDraft, [field]: value };
        this.emit('draft-changed', { typeDraft: next });
    }

    _parentEnumConfig() {
        const none = { value: '', label: this.t('templates_page.field_parent_none') };
        const ids = Array.isArray(this.parentTypeOptions) ? this.parentTypeOptions : [];
        const opts = ids.map((typeId) => ({ value: typeId, label: typeId }));
        return { values: [none, ...opts] };
    }

    _onParentTypeDetailChange(value) {
        const v = typeof value === 'string' ? value : '';
        const next = { ...this.typeDraft, parent_type_id: v };
        if (entityTypeNoteSubtreeLocked(next, this.entityTypeCatalogRows)) {
            next.is_context_anchor = false;
            next.is_voice_target = false;
        }
        this.emit('draft-changed', { typeDraft: next });
    }

    _weightCoefficientNumeric() {
        const n = parseFloat(String(this.typeDraft.weight_coefficient));
        return Number.isFinite(n) ? n : null;
    }

    _onWeightCoefficientChange(e) {
        const v = e.detail.value;
        if (v === null) {
            this._emitDraftField('weight_coefficient', '');
            return;
        }
        if (typeof v !== 'number' || Number.isNaN(v)) {
            throw new Error('CRMEntityTypeEditor: weight_coefficient change requires a finite number');
        }
        this._emitDraftField('weight_coefficient', String(v));
    }

    _onSchemaRowsChanged(section, rows) {
        this.emit('schema-rows-changed', { section, rows });
    }

    _onTogglePill(name, enabled) {
        this.emit('namespace-toggled', { namespaceName: name, enabled });
    }

    _iconPickerIcons(current) {
        const cur = typeof current === 'string' ? current.trim() : '';
        if (cur.length > 0 && !ENTITY_TYPE_UI_ICON_NAMES.includes(cur)) {
            return [cur, ...ENTITY_TYPE_UI_ICON_NAMES];
        }
        return ENTITY_TYPE_UI_ICON_NAMES;
    }

    _onIconPickerChange(event) {
        const v = event && event.detail && event.detail.value;
        this._emitDraftField('icon', typeof v === 'string' ? v : '');
    }

    _onPaletteColorChange(event) {
        const v = event && event.detail && event.detail.value;
        this._emitDraftField('color', typeof v === 'string' ? v : '');
    }

    _fieldLabelWithHint(labelKey, hintKey) {
        return html`
            <div class="field-label-row">
                <span class="field-label">${this.t(labelKey)}</span>
                <platform-help-hint
                    .text=${this.t(hintKey)}
                    label=${this.t('templates_page.field_hint_button_aria')}
                ></platform-help-hint>
            </div>
        `;
    }

    _getSchemaPreview(sectionKey, sectionLabel) {
        const rows = Array.isArray(this.typeDraft[sectionKey]) ? this.typeDraft[sectionKey] : [];
        try {
            const schema = buildSchemaFromRows(rows, sectionLabel, this.schemaOptions, (k, v) => this.t(k, v));
            return JSON.stringify(schema, null, 2);
        } catch (error) {
            const msg = error instanceof Error ? error.message : String(error);
            return this.t('errors.preview_prefix', { message: msg });
        }
    }

    render() {
        if (this.typeDraft === null) {
            return html`<div class="empty">${this.t('templates_page.loading_schema')}</div>`;
        }
        const editing = typeof this.editingTypeId === 'string' && this.editingTypeId.length > 0;
        const schemaReady = this.schemaOptions !== null
            && Array.isArray(this.schemaOptions.field_types);
        const compact = this.compactChrome === true;
        const rootClass = compact ? 'root-compact' : 'panel';
        const semanticsLocked = entityTypeNoteSubtreeLocked(this.typeDraft, this.entityTypeCatalogRows);
        const anchorChecked = semanticsLocked ? false : this.typeDraft.is_context_anchor === true;
        const voiceChecked = semanticsLocked ? false : this.typeDraft.is_voice_target === true;
        return html`
            <div class=${rootClass}>
                ${compact
                    ? ''
                    : html`
                    <div class="panel-header">
                        <span class="panel-title">
                            <platform-icon name="plus" size="18"></platform-icon>
                            ${editing
                                ? this.t('templates_page.type_form_edit_title', { type_id: this.editingTypeId })
                                : this.t('templates_page.type_form_create_title')}
                        </span>
                        ${editing
                            ? html`
                            <button class="btn btn-soft" type="button" @click=${() => this.emit('cancel')}>
                                ${this.t('templates_page.btn_cancel')}
                            </button>
                        `
                            : ''}
                    </div>
                `}
                ${!schemaReady ? html`<div class="empty">${this.t('templates_page.loading_schema')}</div>` : ''}
                <div class="grid-2">
                    <platform-field
                        type="string"
                        mode="edit"
                        .label=${this.t('templates_page.field_type_id')}
                        .hint=${this.t('templates_page.field_type_id_hint')}
                        .value=${this.typeDraft.type_id}
                        ?disabled=${editing || this.savingType}
                        @change=${(e) => this._emitDraftField('type_id', typeof e.detail.value === 'string' ? e.detail.value : '')}
                    ></platform-field>
                    <platform-field
                        type="string"
                        mode="edit"
                        .label=${this.t('templates_page.field_type_name')}
                        .hint=${this.t('templates_page.field_type_name_hint')}
                        .value=${this.typeDraft.name}
                        ?disabled=${this.savingType}
                        @change=${(e) => this._emitDraftField('name', typeof e.detail.value === 'string' ? e.detail.value : '')}
                    ></platform-field>
                    <platform-field
                        type="enum"
                        mode="edit"
                        .label=${this.t('templates_page.field_parent')}
                        .hint=${this.t('templates_page.field_parent_hint')}
                        .config=${this._parentEnumConfig()}
                        .value=${this.typeDraft.parent_type_id}
                        ?disabled=${this.savingType}
                        @change=${(e) => this._onParentTypeDetailChange(
                            typeof e.detail.value === 'string' ? e.detail.value : '',
                        )}
                    ></platform-field>
                    <div class="field">
                        ${this._fieldLabelWithHint('templates_page.field_icon', 'templates_page.field_icon_hint')}
                        <platform-icon-picker
                            .value=${this.typeDraft.icon}
                            .icons=${this._iconPickerIcons(this.typeDraft.icon)}
                            placeholder=${this.t('templates_page.icon_picker_placeholder')}
                            ?disabled=${this.savingType}
                            @change=${this._onIconPickerChange}
                        ></platform-icon-picker>
                    </div>
                    <div class="field">
                        ${this._fieldLabelWithHint('templates_page.field_color', 'templates_page.field_color_hint')}
                        <platform-palette-color-picker
                            .value=${this.typeDraft.color}
                            allow-clear
                            ?disabled=${this.savingType}
                            @change=${this._onPaletteColorChange}
                        ></platform-palette-color-picker>
                    </div>
                    <platform-field
                        type="number"
                        mode="edit"
                        .label=${this.t('templates_page.field_weight')}
                        .hint=${this.t('templates_page.field_weight_hint')}
                        .value=${this._weightCoefficientNumeric()}
                        ?disabled=${this.savingType}
                        @change=${this._onWeightCoefficientChange}
                    ></platform-field>
                    <div class="field">
                        ${this._fieldLabelWithHint('templates_page.field_flags', 'templates_page.field_flags_hint')}
                        <div class="flags-col">
                            <div class="flag-row">
                                <platform-switch
                                    size="sm"
                                    label=${this.t('templates_page.field_is_event')}
                                    .checked=${this.typeDraft.is_event}
                                    @change=${(e) => this._emitDraftField('is_event', Boolean(e.detail.value))}
                                ></platform-switch>
                                <platform-help-hint
                                    .text=${this.t('templates_page.field_is_event_hint')}
                                    label=${this.t('templates_page.field_hint_button_aria')}
                                ></platform-help-hint>
                            </div>
                            <div class="flag-row">
                                <platform-switch
                                    size="sm"
                                    label=${this.t('templates_page.field_check_duplicates')}
                                    .checked=${this.typeDraft.check_duplicates}
                                    @change=${(e) => this._emitDraftField('check_duplicates', Boolean(e.detail.value))}
                                ></platform-switch>
                                <platform-help-hint
                                    .text=${this.t('templates_page.field_check_duplicates_hint')}
                                    label=${this.t('templates_page.field_hint_button_aria')}
                                ></platform-help-hint>
                            </div>
                            <div class="flag-row">
                                <platform-switch
                                    size="sm"
                                    label=${this.t('templates_page.field_is_context_anchor')}
                                    .checked=${anchorChecked}
                                    ?disabled=${semanticsLocked || this.savingType}
                                    @change=${(e) => this._emitDraftField('is_context_anchor', Boolean(e.detail.value))}
                                ></platform-switch>
                                <platform-help-hint
                                    .text=${this.t('templates_page.field_is_context_anchor_hint')}
                                    label=${this.t('templates_page.field_hint_button_aria')}
                                ></platform-help-hint>
                            </div>
                            <div class="flag-row">
                                <platform-switch
                                    size="sm"
                                    label=${this.t('templates_page.field_is_voice_target')}
                                    .checked=${voiceChecked}
                                    ?disabled=${semanticsLocked || this.savingType}
                                    @change=${(e) => this._emitDraftField('is_voice_target', Boolean(e.detail.value))}
                                ></platform-switch>
                                <platform-help-hint
                                    .text=${this.t('templates_page.field_is_voice_target_hint')}
                                    label=${this.t('templates_page.field_hint_button_aria')}
                                ></platform-help-hint>
                            </div>
                        </div>
                        ${semanticsLocked
                            ? html`<div class="hint">${this.t('templates_page.note_semantics_flags_locked_hint')}</div>`
                            : ''}
                    </div>
                    <platform-field
                        type="text"
                        mode="edit"
                        .label=${this.t('templates_page.field_description')}
                        .hint=${this.t('templates_page.field_description_hint')}
                        .value=${this.typeDraft.description}
                        ?disabled=${this.savingType}
                        @change=${(e) => this._emitDraftField(
                            'description',
                            typeof e.detail.value === 'string' ? e.detail.value : '',
                        )}
                    ></platform-field>
                    <platform-field
                        type="text"
                        mode="edit"
                        .label=${this.t('templates_page.field_prompt')}
                        .hint=${this.t('templates_page.field_prompt_hint')}
                        .value=${this.typeDraft.prompt}
                        ?disabled=${this.savingType}
                        @change=${(e) => this._emitDraftField(
                            'prompt',
                            typeof e.detail.value === 'string' ? e.detail.value : '',
                        )}
                    ></platform-field>
                    ${this.showNamespaces ? html`
                        <div class="field">
                            ${this._fieldLabelWithHint(
                                'templates_page.field_namespaces',
                                'templates_page.field_namespaces_hint',
                            )}
                            ${this.namespaces.length > 0 ? html`
                                <div class="namespace-pills">
                                    ${this.namespaces.map((ns) => {
                                        const list = Array.isArray(this.typeDraft.namespace_ids) ? this.typeDraft.namespace_ids : [];
                                        const checked = list.includes(ns.name);
                                        return html`
                                            <button
                                                type="button"
                                                class="ns-pill ${checked ? 'active' : ''}"
                                                @click=${() => this._onTogglePill(ns.name, !checked)}
                                            >
                                                ${ns.name}
                                            </button>
                                        `;
                                    })}
                                </div>
                            ` : html`<div class="hint">${this.t('templates_page.no_namespaces')}</div>`}
                        </div>
                    ` : ''}
                </div>
                <div class="schema-grid">
                    <div class="schema-section">
                        <div class="schema-section-title-row">
                            <div class="panel-title">${this.t('templates_page.required_fields_title')}</div>
                            <platform-help-hint
                                .text=${this.t('templates_page.required_fields_title_hint')}
                                label=${this.t('templates_page.field_hint_button_aria')}
                            ></platform-help-hint>
                        </div>
                        <div class="hint">${this.t('templates_page.required_fields_hint')}</div>
                        ${schemaReady ? html`
                            <crm-schema-field-builder
                                .rows=${this.typeDraft.required_fields_rows}
                                .schemaOptions=${this.schemaOptions}
                                @rows-changed=${(e) => this._onSchemaRowsChanged('required_fields_rows', e.detail.rows)}
                            ></crm-schema-field-builder>
                        ` : html`<div class="empty">${this.t('templates_page.loading_schema')}</div>`}
                    </div>
                    <div class="schema-section">
                        <div class="schema-section-title-row">
                            <div class="panel-title">${this.t('templates_page.optional_fields_title')}</div>
                            <platform-help-hint
                                .text=${this.t('templates_page.optional_fields_title_hint')}
                                label=${this.t('templates_page.field_hint_button_aria')}
                            ></platform-help-hint>
                        </div>
                        <div class="hint">${this.t('templates_page.optional_fields_hint')}</div>
                        ${schemaReady ? html`
                            <crm-schema-field-builder
                                .rows=${this.typeDraft.optional_fields_rows}
                                .schemaOptions=${this.schemaOptions}
                                @rows-changed=${(e) => this._onSchemaRowsChanged('optional_fields_rows', e.detail.rows)}
                            ></crm-schema-field-builder>
                        ` : html`<div class="empty">${this.t('templates_page.loading_schema')}</div>`}
                    </div>
                </div>
                <details>
                    <summary>${this.t('templates_page.json_preview')}</summary>
                    <div class="grid-2">
                        <div class="field">
                            ${this._fieldLabelWithHint(
                                'templates_page.preview_required',
                                'templates_page.preview_required_hint',
                            )}
                            <pre class="preview">${this._getSchemaPreview('required_fields_rows', this.t('schema_sections.required_fields'))}</pre>
                        </div>
                        <div class="field">
                            ${this._fieldLabelWithHint(
                                'templates_page.preview_optional',
                                'templates_page.preview_optional_hint',
                            )}
                            <pre class="preview">${this._getSchemaPreview('optional_fields_rows', this.t('schema_sections.optional_fields'))}</pre>
                        </div>
                    </div>
                </details>
                <div class="actions-row">
                    <button
                        class="btn btn-primary"
                        type="button"
                        ?disabled=${!schemaReady || this.savingType}
                        @click=${() => this.emit('submit')}
                    >
                        ${this.savingType
                            ? this.t('templates_page.btn_saving')
                            : (editing
                                ? this.t('templates_page.save_type_changes')
                                : this.t('templates_page.save_type'))}
                    </button>
                </div>
            </div>
        `;
    }
}

customElements.define('crm-entity-type-editor', CRMEntityTypeEditor);
