/**
 * crm-entity-type-editor — общий редактор типа сущности.
 *
 * Используется и в `templates-page` (тип внутри шаблона), и в
 * `space-detail-page` (тип компании, привязанный к namespace).
 *
 * Props:
 *   - typeDraft: { type_id, name, description, prompt, parent_type_id, icon,
 *                  color, is_event, check_duplicates, weight_coefficient,
 *                  required_fields_rows, optional_fields_rows, namespace_ids }
 *   - schemaOptions: { field_types[], enum_sets[], operators[], ... }
 *   - namespaces: list[{ name, description? }]
 *   - parentTypeOptions: string[]
 *   - editingTypeId: string ('' если создаём новый)
 *   - savingType: boolean
 *   - showNamespaces: boolean (true для templates-page; false для space-detail
 *                     где namespace задан контекстом и редактируется одним
 *                     toggle снаружи)
 *   - compactChrome: boolean — без внешней .panel и без верхнего panel-header
 *     (шапка рисует родитель, напр. `space-detail-page`).
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
import './schema-field-builder.js';
import { buildSchemaFromRows } from './schema-field-builder.js';

export class CRMEntityTypeEditor extends PlatformElement {
    static i18nNamespace = 'crm';

    static properties = {
        typeDraft: { attribute: false },
        schemaOptions: { attribute: false },
        namespaces: { attribute: false },
        parentTypeOptions: { attribute: false },
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

            .input, .select, .textarea {
                width: 100%;
                box-sizing: border-box;
                padding: var(--space-2) var(--space-3);
                border: 1px solid var(--crm-stroke);
                border-radius: var(--radius-md);
                background: var(--crm-surface);
                color: var(--text-primary);
                font-size: var(--text-sm);
            }
            .input.mono, .select.mono { font-family: var(--font-mono); }
            .textarea { min-height: 76px; resize: vertical; }
            .icon-row {
                display: flex;
                align-items: center;
                gap: var(--space-2);
            }
            .icon-preview {
                width: 36px;
                height: 36px;
                display: inline-flex;
                align-items: center;
                justify-content: center;
                border-radius: var(--radius-md);
                background: var(--glass-tint-medium);
            }
            .flags-row {
                display: flex;
                flex-wrap: wrap;
                gap: var(--space-3);
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
        this.editingTypeId = '';
        this.savingType = false;
        this.showNamespaces = true;
    }

    _emitDraftField(field, value) {
        const next = { ...this.typeDraft, [field]: value };
        this.emit('draft-changed', { typeDraft: next });
    }

    _onSchemaRowsChanged(section, rows) {
        this.emit('schema-rows-changed', { section, rows });
    }

    _onTogglePill(name, enabled) {
        this.emit('namespace-toggled', { namespaceName: name, enabled });
    }

    _resolveIcon(value) {
        const trimmed = typeof value === 'string' ? value.trim() : '';
        return trimmed.length > 0 ? trimmed : 'folder';
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
                    <div class="field">
                        <label class="field-label">${this.t('templates_page.field_type_id')}</label>
                        <input
                            class="input mono"
                            .value=${this.typeDraft.type_id}
                            ?disabled=${editing}
                            @input=${(e) => this._emitDraftField('type_id', e.target.value)}
                        />
                    </div>
                    <div class="field">
                        <label class="field-label">${this.t('templates_page.field_type_name')}</label>
                        <input
                            class="input"
                            .value=${this.typeDraft.name}
                            @input=${(e) => this._emitDraftField('name', e.target.value)}
                        />
                    </div>
                    <div class="field">
                        <label class="field-label">${this.t('templates_page.field_parent')}</label>
                        <select
                            class="select mono"
                            .value=${this.typeDraft.parent_type_id}
                            @change=${(e) => this._emitDraftField('parent_type_id', e.target.value)}
                        >
                            <option value="">${this.t('templates_page.field_parent_none')}</option>
                            ${this.parentTypeOptions.map((typeId) => html`
                                <option value=${typeId} ?selected=${typeId === this.typeDraft.parent_type_id}>${typeId}</option>
                            `)}
                        </select>
                    </div>
                    <div class="field">
                        <label class="field-label">${this.t('templates_page.field_icon')}</label>
                        <div class="icon-row">
                            <div class="icon-preview">
                                <platform-icon name=${this._resolveIcon(this.typeDraft.icon)} size="18"></platform-icon>
                            </div>
                            <input
                                class="input mono"
                                .value=${this.typeDraft.icon}
                                placeholder=${this.t('templates_page.ph_icon')}
                                @input=${(e) => this._emitDraftField('icon', e.target.value)}
                            />
                        </div>
                    </div>
                    <div class="field">
                        <label class="field-label">${this.t('templates_page.field_color')}</label>
                        <input
                            class="input"
                            .value=${this.typeDraft.color}
                            placeholder=${this.t('templates_page.ph_color')}
                            @input=${(e) => this._emitDraftField('color', e.target.value)}
                        />
                    </div>
                    <div class="field">
                        <label class="field-label">${this.t('templates_page.field_weight')}</label>
                        <input
                            type="number"
                            step="0.1"
                            min="0"
                            class="input mono"
                            .value=${this.typeDraft.weight_coefficient}
                            @input=${(e) => this._emitDraftField('weight_coefficient', e.target.value)}
                        />
                    </div>
                    <div class="field">
                        <label class="field-label">${this.t('templates_page.field_flags')}</label>
                        <div class="flags-row">
                            <platform-switch
                                size="sm"
                                label=${this.t('templates_page.field_is_event')}
                                .checked=${this.typeDraft.is_event}
                                @change=${(e) => this._emitDraftField('is_event', Boolean(e.detail.value))}
                            ></platform-switch>
                            <platform-switch
                                size="sm"
                                label=${this.t('templates_page.field_check_duplicates')}
                                .checked=${this.typeDraft.check_duplicates}
                                @change=${(e) => this._emitDraftField('check_duplicates', Boolean(e.detail.value))}
                            ></platform-switch>
                        </div>
                    </div>
                    <div class="field">
                        <label class="field-label">${this.t('templates_page.field_description')}</label>
                        <textarea
                            class="textarea"
                            .value=${this.typeDraft.description}
                            @input=${(e) => this._emitDraftField('description', e.target.value)}
                        ></textarea>
                    </div>
                    <div class="field">
                        <label class="field-label">${this.t('templates_page.field_prompt')}</label>
                        <textarea
                            class="textarea"
                            .value=${this.typeDraft.prompt}
                            @input=${(e) => this._emitDraftField('prompt', e.target.value)}
                        ></textarea>
                    </div>
                    ${this.showNamespaces ? html`
                        <div class="field">
                            <label class="field-label">${this.t('templates_page.field_namespaces')}</label>
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
                        <div class="panel-title">${this.t('templates_page.required_fields_title')}</div>
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
                        <div class="panel-title">${this.t('templates_page.optional_fields_title')}</div>
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
                            <label class="field-label">${this.t('templates_page.preview_required')}</label>
                            <pre class="preview">${this._getSchemaPreview('required_fields_rows', this.t('schema_sections.required_fields'))}</pre>
                        </div>
                        <div class="field">
                            <label class="field-label">${this.t('templates_page.preview_optional')}</label>
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
