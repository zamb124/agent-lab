/**
 * CRMTemplatesPage — управление шаблонами пространств CRM (CRUD + типы).
 *
 * Левая колонка — список шаблонов и inline-форма создания нового. Правая —
 * метаданные выбранного шаблона, его типы сущностей и форма upsert/edit
 * типа со встроенным `crm-schema-field-builder` для секций
 * `required_fields` и `optional_fields`.
 *
 * Состояние:
 *  - useResource('crm/templates', { autoload: true }) — список + get/create/remove.
 *  - useResource('crm/namespaces', { autoload: true }) — пространства для пилюль типа.
 *  - useOp('crm/template_update') — PUT метаданных выбранного шаблона.
 *  - useOp('crm/template_schema_options') — загрузка опций схемы (silent).
 *  - useOp('crm/template_type_upsert') — upsert типа в шаблоне.
 *  - useOp('crm/template_type_delete') — удаление типа.
 *
 * После CREATE/REMOVE/UPSERT/DELETE — перезагружаем детали выбранного
 * шаблона, чтобы отрисовать актуальный список типов.
 */

import { html, css } from 'lit';
import { PlatformPage } from '@platform/lib/base/PlatformPage.js';
import '@platform/lib/components/layout/page-header.js';
import '@platform/lib/components/platform-icon.js';
import '@platform/lib/components/platform-switch.js';
import '@platform/lib/components/platform-breadcrumbs.js';
import { platformConfirm } from '@platform/lib/components/platform-confirm-modal.js';

import '../components/schema-field-builder.js';
import {
    normalizeSchemaRows,
    buildSchemaFromRows,
} from '../components/schema-field-builder.js';

const DEFAULT_TYPE_DRAFT = Object.freeze({
    type_id: '',
    name: '',
    description: '',
    prompt: '',
    required_fields_rows: Object.freeze([]),
    optional_fields_rows: Object.freeze([]),
    namespace_ids: Object.freeze([]),
    parent_type_id: '',
    icon: '',
    color: '',
    is_event: false,
    check_duplicates: true,
    weight_coefficient: '1.0',
});

function makeTypeDraft(overrides = {}) {
    return {
        ...DEFAULT_TYPE_DRAFT,
        required_fields_rows: [],
        optional_fields_rows: [],
        namespace_ids: [],
        ...overrides,
    };
}

const DEFAULT_NEW_TEMPLATE_DRAFT = Object.freeze({
    template_id: '',
    name: '',
    description: '',
    icon: 'folder',
});

export class CRMTemplatesPage extends PlatformPage {
    static i18nNamespace = 'crm';

    static properties = {
        _selectedTemplateId: { state: true },
        _showCreateForm: { state: true },
        _newDraft: { state: true },
        _typeDraft: { state: true },
        _editingTypeId: { state: true },
        _metaDraft: { state: true },
        _schemaOptions: { state: true },
    };

    static styles = [
        PlatformPage.styles,
        css`
            :host {
                display: flex;
                flex-direction: column;
                width: 100%;
                height: 100%;
                min-height: 0;
                overflow: hidden;
            }

            .scroll {
                flex: 1;
                min-height: 0;
                overflow-y: auto;
                overflow-x: hidden;
                padding: var(--space-2);
            }

            .breadcrumbs-wrap {
                flex-shrink: 0;
                padding: var(--space-2) var(--space-2) 0;
            }

            .layout {
                display: grid;
                gap: var(--space-3);
                grid-template-columns: minmax(280px, 360px) minmax(0, 1fr);
                align-items: start;
            }

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
                color: var(--text-primary);
                font-size: var(--text-base);
                font-weight: var(--font-semibold);
            }

            .panel-subtitle {
                color: var(--text-secondary);
                font-size: var(--text-sm);
            }

            .templates-list {
                display: flex;
                flex-direction: column;
                gap: var(--space-2);
            }

            .tpl-card {
                border: 1px solid var(--glass-border-subtle);
                border-radius: var(--radius-lg);
                background: var(--glass-solid-medium);
                padding: var(--space-3);
                cursor: pointer;
                transition:
                    border-color var(--duration-fast),
                    background var(--duration-fast),
                    transform var(--duration-fast);
                font: inherit;
                color: inherit;
                text-align: left;
            }

            .tpl-card:hover {
                border-color: var(--accent);
                transform: translateY(-1px);
            }

            .tpl-card.active {
                border-color: var(--accent);
                background: rgba(59, 130, 246, 0.12);
            }

            .tpl-leading {
                display: flex;
                align-items: center;
                gap: var(--space-2);
                margin-bottom: var(--space-1);
            }

            .tpl-name {
                color: var(--text-primary);
                font-size: var(--text-sm);
                font-weight: var(--font-semibold);
            }

            .tpl-desc {
                color: var(--text-secondary);
                font-size: var(--text-sm);
                line-height: 1.4;
                margin-bottom: var(--space-2);
            }

            .tpl-meta {
                display: flex;
                align-items: center;
                justify-content: space-between;
                gap: var(--space-2);
            }

            .chip {
                display: inline-flex;
                align-items: center;
                gap: var(--space-1);
                border: 1px solid var(--glass-border-subtle);
                border-radius: var(--radius-full);
                padding: 2px var(--space-2);
                color: var(--text-secondary);
                background: var(--glass-solid-medium);
                font-size: var(--text-xs);
            }

            .mono {
                font-family: var(--font-mono, ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace);
            }

            .empty {
                color: var(--text-tertiary);
                font-size: var(--text-sm);
                padding: var(--space-3);
                text-align: center;
            }

            .field {
                display: flex;
                flex-direction: column;
                gap: var(--space-2);
            }

            .field-label {
                color: var(--text-secondary);
                font-size: var(--text-sm);
                font-weight: var(--font-medium);
            }

            .input,
            .select,
            .textarea {
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

            .textarea {
                min-height: 88px;
                resize: vertical;
            }

            .input:focus,
            .select:focus,
            .textarea:focus {
                outline: none;
                border-color: var(--accent);
                box-shadow: 0 0 0 1px var(--accent);
            }

            .icon-row {
                display: grid;
                grid-template-columns: 40px minmax(0, 1fr);
                gap: var(--space-2);
                align-items: center;
            }

            .icon-preview {
                width: 36px;
                height: 36px;
                border-radius: var(--radius-md);
                border: 1px solid var(--glass-border-subtle);
                background: var(--glass-solid-medium);
                display: flex;
                align-items: center;
                justify-content: center;
                color: var(--text-secondary);
            }

            .grid-2 {
                display: grid;
                gap: var(--space-3);
                grid-template-columns: repeat(auto-fit, minmax(min(100%, 220px), 1fr));
            }

            .actions-row {
                display: flex;
                gap: var(--space-2);
                flex-wrap: wrap;
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

            .btn:disabled {
                opacity: 0.5;
                cursor: not-allowed;
            }

            .btn-primary {
                background: var(--accent);
                color: var(--platform-btn-primary-text, white);
                border-color: var(--accent);
            }

            .btn-primary:hover:not(:disabled) {
                filter: brightness(1.1);
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

            .types-grid {
                display: grid;
                gap: var(--space-2);
                grid-template-columns: repeat(auto-fit, minmax(min(100%, 260px), 1fr));
            }

            .type-card {
                border: 1px solid var(--glass-border-subtle);
                border-radius: var(--radius-md);
                background: var(--glass-solid-medium);
                padding: var(--space-3);
                display: flex;
                flex-direction: column;
                gap: var(--space-2);
            }

            .type-title {
                display: flex;
                align-items: center;
                gap: var(--space-2);
                color: var(--text-primary);
                font-size: var(--text-sm);
                font-weight: var(--font-semibold);
            }

            .hint {
                color: var(--text-tertiary);
                font-size: var(--text-xs);
                line-height: 1.4;
            }

            .chips {
                display: flex;
                flex-wrap: wrap;
                gap: var(--space-1);
            }

            .schema-grid {
                display: grid;
                gap: var(--space-3);
                grid-template-columns: 1fr 1fr;
            }

            .schema-section {
                border: 1px solid var(--glass-border-subtle);
                border-radius: var(--radius-md);
                background: var(--glass-solid-medium);
                padding: var(--space-3);
                display: flex;
                flex-direction: column;
                gap: var(--space-2);
            }

            .namespace-pills {
                display: flex;
                gap: var(--space-2);
                flex-wrap: wrap;
            }

            .ns-pill {
                display: inline-flex;
                align-items: center;
                gap: var(--space-2);
                border: 1px solid var(--glass-border-subtle);
                border-radius: var(--radius-full);
                background: var(--glass-solid-medium);
                color: var(--text-primary);
                padding: 4px var(--space-2);
                font-size: var(--text-xs);
                cursor: pointer;
                font: inherit;
            }

            .ns-pill.active {
                border-color: var(--accent);
                background: rgba(59, 130, 246, 0.18);
            }

            details {
                border: 1px solid var(--glass-border-subtle);
                border-radius: var(--radius-md);
                background: var(--glass-solid-medium);
                padding: var(--space-3);
            }

            details > summary {
                cursor: pointer;
                color: var(--text-primary);
                font-size: var(--text-sm);
                font-weight: var(--font-semibold);
                margin-bottom: var(--space-2);
            }

            .preview {
                border: 1px solid var(--glass-border-subtle);
                border-radius: var(--radius-md);
                background: var(--glass-solid-subtle);
                color: var(--text-secondary);
                font-size: var(--text-xs);
                padding: var(--space-2);
                max-height: 200px;
                overflow: auto;
                white-space: pre-wrap;
                word-break: break-word;
                font-family: var(--font-mono, ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace);
            }

            .flags-row {
                display: flex;
                gap: var(--space-3);
                flex-wrap: wrap;
            }

            @media (max-width: 980px) {
                .layout {
                    grid-template-columns: 1fr;
                }

                .schema-grid {
                    grid-template-columns: 1fr;
                }
            }
        `,
    ];

    constructor() {
        super();
        this._selectedTemplateId = '';
        this._showCreateForm = false;
        this._newDraft = { ...DEFAULT_NEW_TEMPLATE_DRAFT };
        this._typeDraft = makeTypeDraft();
        this._editingTypeId = '';
        this._metaDraft = null;
        this._schemaOptions = null;
        this._creatingTemplate = false;
        this._savingMeta = false;
        this._savingType = false;
        this._deletingTemplate = false;
        this._templates = this.useResource('crm/templates', { autoload: true });
        this._namespaces = this.useResource('crm/namespaces', { autoload: true });
        this._updateMetaOp = this.useOp('crm/template_update');
        this._schemaOptionsOp = this.useOp('crm/template_schema_options');
        this._upsertTypeOp = this.useOp('crm/template_type_upsert');
        this._deleteTypeOp = this.useOp('crm/template_type_delete');
    }

    connectedCallback() {
        super.connectedCallback();
        this._schemaOptionsOp.run(null);
        this.useEvent(this._schemaOptionsOp.op.events.SUCCEEDED, (event) => {
            if (!event.payload || typeof event.payload.result !== 'object') {
                return;
            }
            this._schemaOptions = event.payload.result;
        });
        this.useEvent(this._templates.resource.events.LIST_LOADED, () => {
            this._maybeAutoSelect();
        });
        this.useEvent(this._templates.resource.events.CREATED, (event) => {
            const item = event.payload && event.payload.item;
            if (!item || typeof item.template_id !== 'string') {
                return;
            }
            this._creatingTemplate = false;
            this._showCreateForm = false;
            this._newDraft = { ...DEFAULT_NEW_TEMPLATE_DRAFT };
            this._selectTemplate(item.template_id);
        });
        this.useEvent(this._templates.resource.events.CREATE_FAILED, () => {
            this._creatingTemplate = false;
        });
        this.useEvent(this._templates.resource.events.REMOVED, (event) => {
            const removedId = event.payload && event.payload.template_id;
            if (removedId === this._selectedTemplateId) {
                this._selectedTemplateId = '';
                this._metaDraft = null;
                this._typeDraft = makeTypeDraft();
                this._editingTypeId = '';
            }
            this._deletingTemplate = false;
        });
        this.useEvent(this._templates.resource.events.ITEM_LOADED, (event) => {
            const item = event.payload && event.payload.item;
            if (!item || item.template_id !== this._selectedTemplateId) {
                return;
            }
            this._metaDraft = {
                name: item.name || '',
                description: item.description || '',
                icon: item.icon || 'folder',
            };
        });
        this.useEvent(this._updateMetaOp.op.events.SUCCEEDED, () => {
            this._savingMeta = false;
            if (this._selectedTemplateId) {
                this._templates.get(this._selectedTemplateId);
                this._templates.load(null);
            }
        });
        this.useEvent(this._updateMetaOp.op.events.FAILED, () => {
            this._savingMeta = false;
        });
        this.useEvent(this._upsertTypeOp.op.events.SUCCEEDED, () => {
            this._savingType = false;
            this._typeDraft = makeTypeDraft();
            this._editingTypeId = '';
            if (this._selectedTemplateId) {
                this._templates.get(this._selectedTemplateId);
            }
        });
        this.useEvent(this._upsertTypeOp.op.events.FAILED, () => {
            this._savingType = false;
        });
        this.useEvent(this._deleteTypeOp.op.events.SUCCEEDED, () => {
            if (this._selectedTemplateId) {
                this._templates.get(this._selectedTemplateId);
            }
        });
    }

    _maybeAutoSelect() {
        const list = this._templates.items;
        if (list.length === 0) {
            this._selectedTemplateId = '';
            return;
        }
        if (!this._selectedTemplateId || !list.some((t) => t.template_id === this._selectedTemplateId)) {
            this._selectTemplate(list[0].template_id);
        }
    }

    _selectTemplate(templateId) {
        if (typeof templateId !== 'string' || templateId.length === 0) {
            throw new Error('CRMTemplatesPage._selectTemplate: templateId required');
        }
        this._selectedTemplateId = templateId;
        this._typeDraft = makeTypeDraft();
        this._editingTypeId = '';
        const cached = this._templates.byId[templateId];
        if (cached && Array.isArray(cached.types)) {
            this._metaDraft = {
                name: cached.name || '',
                description: cached.description || '',
                icon: cached.icon || 'folder',
            };
        } else {
            this._metaDraft = null;
        }
        this._templates.get(templateId);
    }

    _resolveIcon(value) {
        const trimmed = typeof value === 'string' ? value.trim() : '';
        return trimmed.length > 0 ? trimmed : 'folder';
    }

    _toggleCreateForm() {
        this._showCreateForm = !this._showCreateForm;
        if (!this._showCreateForm) {
            this._newDraft = { ...DEFAULT_NEW_TEMPLATE_DRAFT };
        }
    }

    _updateNewDraft(field, value) {
        this._newDraft = { ...this._newDraft, [field]: value };
    }

    _onCreateSubmit(event) {
        event.preventDefault();
        const templateId = this._newDraft.template_id.trim();
        const name = this._newDraft.name.trim();
        if (templateId.length === 0 || name.length === 0) {
            this.toast('templates_page.err_id_name_required', { type: 'error' });
            return;
        }
        this._creatingTemplate = true;
        this._templates.create({
            template_id: templateId,
            name,
            description: this._newDraft.description.trim() || null,
            icon: this._newDraft.icon.trim() || null,
        });
    }

    async _onDeleteTemplate() {
        if (!this._selectedTemplateId || !this._metaDraft) {
            throw new Error('CRMTemplatesPage._onDeleteTemplate: template not selected');
        }
        const confirmed = await platformConfirm(
            this.t('templates_page.confirm_delete_template_msg', {
                name: this._metaDraft.name || this._selectedTemplateId,
            }),
            {
                title: this.t('templates_page.confirm_delete_template_title'),
                variant: 'danger',
                confirmText: this.t('templates_page.delete_template'),
                cancelText: this.t('templates_page.btn_cancel'),
            },
        );
        if (!confirmed) {
            return;
        }
        this._deletingTemplate = true;
        this._templates.remove(this._selectedTemplateId);
    }

    _updateMetaField(field, value) {
        if (!this._metaDraft) {
            throw new Error('CRMTemplatesPage._updateMetaField: meta draft not initialized');
        }
        this._metaDraft = { ...this._metaDraft, [field]: value };
    }

    _onSaveMeta() {
        if (!this._selectedTemplateId || !this._metaDraft) {
            throw new Error('CRMTemplatesPage._onSaveMeta: template not selected');
        }
        const name = this._metaDraft.name.trim();
        if (name.length === 0) {
            this.toast('templates_page.err_name_required', { type: 'error' });
            return;
        }
        this._savingMeta = true;
        this._updateMetaOp.run({
            template_id: this._selectedTemplateId,
            body: {
                name,
                description: this._metaDraft.description.trim() || null,
                icon: this._metaDraft.icon.trim() || null,
            },
        });
    }

    _updateTypeDraft(field, value) {
        this._typeDraft = { ...this._typeDraft, [field]: value };
    }

    _setSchemaRows(section, rows) {
        if (section !== 'required_fields_rows' && section !== 'optional_fields_rows') {
            throw new Error(`CRMTemplatesPage._setSchemaRows: unknown section "${section}"`);
        }
        this._typeDraft = { ...this._typeDraft, [section]: rows };
    }

    _toggleTypeNamespace(namespaceName, enabled) {
        if (typeof namespaceName !== 'string' || namespaceName.length === 0) {
            throw new Error('CRMTemplatesPage._toggleTypeNamespace: namespaceName required');
        }
        const current = Array.isArray(this._typeDraft.namespace_ids)
            ? this._typeDraft.namespace_ids
            : [];
        const next = enabled
            ? [...new Set([...current, namespaceName])]
            : current.filter((item) => item !== namespaceName);
        this._updateTypeDraft('namespace_ids', next);
    }

    _editType(item) {
        if (!item || typeof item.type_id !== 'string') {
            throw new Error('CRMTemplatesPage._editType: item.type_id required');
        }
        this._editingTypeId = item.type_id;
        this._typeDraft = {
            type_id: item.type_id,
            name: item.name || '',
            description: item.description || '',
            prompt: item.prompt || '',
            required_fields_rows: normalizeSchemaRows(item.required_fields && typeof item.required_fields === 'object' ? item.required_fields : {}),
            optional_fields_rows: normalizeSchemaRows(item.optional_fields && typeof item.optional_fields === 'object' ? item.optional_fields : {}),
            namespace_ids: Array.isArray(item.namespace_ids) ? [...item.namespace_ids] : [],
            parent_type_id: item.parent_type_id || '',
            icon: item.icon || '',
            color: item.color || '',
            is_event: item.is_event === true,
            check_duplicates: item.check_duplicates !== false,
            weight_coefficient: String(item.weight_coefficient === undefined ? 1 : item.weight_coefficient),
        };
    }

    _resetTypeDraft() {
        this._typeDraft = makeTypeDraft();
        this._editingTypeId = '';
    }

    _getParentTypeOptions() {
        const detail = this._templates.byId[this._selectedTemplateId];
        const fromTemplate = detail && Array.isArray(detail.types)
            ? detail.types
                .map((item) => item.type_id)
                .filter((item) => typeof item === 'string' && item.length > 0)
            : [];
        return [...new Set(['note', 'task', ...fromTemplate])];
    }

    _getSchemaPreview(sectionKey, sectionLabel) {
        try {
            const rows = Array.isArray(this._typeDraft[sectionKey]) ? this._typeDraft[sectionKey] : [];
            const schema = buildSchemaFromRows(rows, sectionLabel, this._schemaOptions, (k, v) => this.t(k, v));
            return JSON.stringify(schema, null, 2);
        } catch (error) {
            const msg = error instanceof Error ? error.message : String(error);
            return this.t('errors.preview_prefix', { message: msg });
        }
    }

    _onUpsertType() {
        if (!this._selectedTemplateId) {
            throw new Error('CRMTemplatesPage._onUpsertType: template not selected');
        }
        if (!this._schemaOptions) {
            this.toast('templates_page.err_schema_not_loaded', { type: 'error' });
            return;
        }
        const typeId = this._typeDraft.type_id.trim();
        const name = this._typeDraft.name.trim();
        if (typeId.length === 0 || name.length === 0) {
            this.toast('templates_page.err_type_id_name_required', { type: 'error' });
            return;
        }
        const requiredFields = buildSchemaFromRows(
            this._typeDraft.required_fields_rows,
            this.t('schema_sections.required_fields'),
            this._schemaOptions,
            (k, v) => this.t(k, v),
        );
        const optionalFields = buildSchemaFromRows(
            this._typeDraft.optional_fields_rows,
            this.t('schema_sections.optional_fields'),
            this._schemaOptions,
            (k, v) => this.t(k, v),
        );
        for (const key of Object.keys(requiredFields)) {
            if (Object.prototype.hasOwnProperty.call(optionalFields, key)) {
                throw new Error(this.t('errors.key_both_sections', { key }));
            }
        }
        const namespaceIds = Array.isArray(this._typeDraft.namespace_ids)
            ? this._typeDraft.namespace_ids
            : [];
        const normalizedNamespaceIds = namespaceIds
            .map((item) => (typeof item === 'string' ? item.trim() : ''))
            .filter((item) => item.length > 0);
        this._savingType = true;
        this._upsertTypeOp.run({
            template_id: this._selectedTemplateId,
            body: {
                type_id: typeId,
                parent_type_id: this._typeDraft.parent_type_id.trim() || null,
                name,
                description: this._typeDraft.description.trim() || null,
                prompt: this._typeDraft.prompt.trim() || null,
                required_fields: requiredFields,
                optional_fields: optionalFields,
                namespace_ids: [...new Set(normalizedNamespaceIds)],
                icon: this._typeDraft.icon.trim() || null,
                color: this._typeDraft.color.trim() || null,
                is_event: this._typeDraft.is_event === true,
                check_duplicates: this._typeDraft.check_duplicates !== false,
                weight_coefficient: Number.parseFloat(this._typeDraft.weight_coefficient || '1') || 1,
            },
        });
    }

    async _onDeleteType(typeId) {
        if (!this._selectedTemplateId) {
            throw new Error('CRMTemplatesPage._onDeleteType: template not selected');
        }
        if (typeof typeId !== 'string' || typeId.length === 0) {
            throw new Error('CRMTemplatesPage._onDeleteType: typeId required');
        }
        const confirmed = await platformConfirm(
            this.t('templates_page.confirm_delete_type_msg', { type_id: typeId }),
            {
                title: this.t('templates_page.confirm_delete_type_title'),
                variant: 'danger',
                confirmText: this.t('templates_page.delete_type'),
                cancelText: this.t('templates_page.btn_cancel'),
            },
        );
        if (!confirmed) {
            return;
        }
        this._deleteTypeOp.run({
            template_id: this._selectedTemplateId,
            type_id: typeId,
        });
    }

    render() {
        const templates = this._templates.items;
        const selectedDetail = this._selectedTemplateId
            ? this._templates.byId[this._selectedTemplateId]
            : null;
        const types = selectedDetail && Array.isArray(selectedDetail.types) ? selectedDetail.types : [];
        const schemaReady = this._schemaOptions && Array.isArray(this._schemaOptions.field_types);
        return html`
            <div class="breadcrumbs-wrap">
                <platform-breadcrumbs></platform-breadcrumbs>
            </div>
            <page-header
                title=${this.t('templates_page.title')}
                subtitle=${this.t('templates_page.subtitle')}
            ></page-header>
            <div class="scroll">
                <div class="layout">
                    ${this._renderLeftPanel(templates)}
                    ${this._renderRightPanel(selectedDetail, types, schemaReady)}
                </div>
            </div>
        `;
    }

    _renderLeftPanel(templates) {
        return html`
            <div class="panel">
                <div class="panel-header">
                    <span class="panel-title">
                        <platform-icon name="folder" size="18"></platform-icon>
                        ${this.t('templates_page.section_templates')}
                    </span>
                    <button
                        class="btn ${this._showCreateForm ? 'btn-soft' : 'btn-primary'}"
                        type="button"
                        ?disabled=${this._creatingTemplate}
                        @click=${this._toggleCreateForm}
                    >
                        ${this._showCreateForm
                            ? this.t('templates_page.btn_cancel')
                            : this.t('templates_page.create_btn')}
                    </button>
                </div>
                ${this._showCreateForm ? this._renderCreateForm() : ''}
                ${templates.length > 0 ? html`
                    <div class="templates-list">
                        ${templates.map((tpl) => this._renderTemplateCard(tpl))}
                    </div>
                ` : html`<div class="empty">${this.t('templates_page.empty')}</div>`}
            </div>
        `;
    }

    _renderCreateForm() {
        return html`
            <form @submit=${this._onCreateSubmit} class="panel" style="background: var(--glass-solid-medium);">
                <div class="field">
                    <label class="field-label">${this.t('templates_page.label_template_id')}</label>
                    <input
                        class="input mono"
                        .value=${this._newDraft.template_id}
                        placeholder=${this.t('templates_page.ph_template_id')}
                        ?disabled=${this._creatingTemplate}
                        @input=${(e) => this._updateNewDraft('template_id', e.target.value)}
                    />
                </div>
                <div class="field">
                    <label class="field-label">${this.t('templates_page.label_name')}</label>
                    <input
                        class="input"
                        .value=${this._newDraft.name}
                        placeholder=${this.t('templates_page.ph_template_name')}
                        ?disabled=${this._creatingTemplate}
                        @input=${(e) => this._updateNewDraft('name', e.target.value)}
                    />
                </div>
                <div class="field">
                    <label class="field-label">${this.t('templates_page.label_description')}</label>
                    <textarea
                        class="textarea"
                        .value=${this._newDraft.description}
                        placeholder=${this.t('templates_page.ph_template_description')}
                        ?disabled=${this._creatingTemplate}
                        @input=${(e) => this._updateNewDraft('description', e.target.value)}
                    ></textarea>
                </div>
                <div class="field">
                    <label class="field-label">${this.t('templates_page.label_icon')}</label>
                    <div class="icon-row">
                        <div class="icon-preview">
                            <platform-icon name=${this._resolveIcon(this._newDraft.icon)} size="18"></platform-icon>
                        </div>
                        <input
                            class="input mono"
                            .value=${this._newDraft.icon}
                            placeholder=${this.t('templates_page.ph_icon')}
                            ?disabled=${this._creatingTemplate}
                            @input=${(e) => this._updateNewDraft('icon', e.target.value)}
                        />
                    </div>
                </div>
                <div class="actions-row">
                    <button
                        type="submit"
                        class="btn btn-primary"
                        ?disabled=${this._creatingTemplate
                            || this._newDraft.template_id.trim().length === 0
                            || this._newDraft.name.trim().length === 0}
                    >
                        ${this._creatingTemplate
                            ? this.t('templates_page.btn_creating')
                            : this.t('templates_page.btn_create')}
                    </button>
                </div>
            </form>
        `;
    }

    _renderTemplateCard(tpl) {
        const active = tpl.template_id === this._selectedTemplateId;
        const typesCount = Array.isArray(tpl.entity_type_ids)
            ? tpl.entity_type_ids.length
            : Array.isArray(tpl.types) ? tpl.types.length : 0;
        return html`
            <button
                type="button"
                class="tpl-card ${active ? 'active' : ''}"
                @click=${() => this._selectTemplate(tpl.template_id)}
            >
                <div class="tpl-leading">
                    <platform-icon name=${this._resolveIcon(tpl.icon)} size="18"></platform-icon>
                    <span class="tpl-name">${tpl.name}</span>
                </div>
                ${tpl.description
                    ? html`<div class="tpl-desc">${tpl.description}</div>`
                    : ''}
                <div class="tpl-meta">
                    <span class="chip mono">${tpl.template_id}</span>
                    <span class="chip">${this.t('templates_page.types_count', { count: String(typesCount) })}</span>
                </div>
            </button>
        `;
    }

    _renderRightPanel(detail, types, schemaReady) {
        if (!this._selectedTemplateId) {
            return html`
                <div class="panel">
                    <div class="empty">${this.t('templates_page.no_template_selected')}</div>
                </div>
            `;
        }
        if (!detail || !this._metaDraft) {
            return html`
                <div class="panel">
                    <div class="empty">${this.t('templates_page.loading_detail')}</div>
                </div>
            `;
        }
        return html`
            ${this._renderMetaPanel(detail)}
            ${this._renderTypesListPanel(types)}
            ${this._renderTypeFormPanel(schemaReady)}
        `;
    }

    _renderMetaPanel(detail) {
        return html`
            <div class="panel">
                <div class="panel-header">
                    <span class="panel-title">
                        <platform-icon name="edit" size="18"></platform-icon>
                        ${this.t('templates_page.meta_section')}
                    </span>
                    <span class="chip mono">${detail.template_id}</span>
                </div>
                <div class="grid-2">
                    <div class="field">
                        <label class="field-label">${this.t('templates_page.label_name')}</label>
                        <input
                            class="input"
                            .value=${this._metaDraft.name}
                            ?disabled=${this._savingMeta || this._deletingTemplate}
                            @input=${(e) => this._updateMetaField('name', e.target.value)}
                        />
                    </div>
                    <div class="field">
                        <label class="field-label">${this.t('templates_page.label_icon')}</label>
                        <div class="icon-row">
                            <div class="icon-preview">
                                <platform-icon name=${this._resolveIcon(this._metaDraft.icon)} size="18"></platform-icon>
                            </div>
                            <input
                                class="input mono"
                                .value=${this._metaDraft.icon}
                                placeholder=${this.t('templates_page.ph_icon')}
                                ?disabled=${this._savingMeta || this._deletingTemplate}
                                @input=${(e) => this._updateMetaField('icon', e.target.value)}
                            />
                        </div>
                    </div>
                </div>
                <div class="field">
                    <label class="field-label">${this.t('templates_page.label_description')}</label>
                    <textarea
                        class="textarea"
                        .value=${this._metaDraft.description}
                        ?disabled=${this._savingMeta || this._deletingTemplate}
                        @input=${(e) => this._updateMetaField('description', e.target.value)}
                    ></textarea>
                </div>
                <div class="actions-row">
                    <button
                        class="btn btn-primary"
                        type="button"
                        ?disabled=${this._savingMeta || this._deletingTemplate}
                        @click=${this._onSaveMeta}
                    >
                        ${this._savingMeta
                            ? this.t('templates_page.btn_saving')
                            : this.t('templates_page.save_meta')}
                    </button>
                    <button
                        class="btn btn-danger"
                        type="button"
                        ?disabled=${this._savingMeta || this._deletingTemplate}
                        @click=${this._onDeleteTemplate}
                    >
                        ${this.t('templates_page.delete_template')}
                    </button>
                </div>
            </div>
        `;
    }

    _renderTypesListPanel(types) {
        return html`
            <div class="panel">
                <div class="panel-header">
                    <span class="panel-title">
                        <platform-icon name="list" size="18"></platform-icon>
                        ${this.t('templates_page.types_section')}
                    </span>
                    <span class="chip">${this.t('templates_page.types_count', { count: String(types.length) })}</span>
                </div>
                ${types.length > 0 ? html`
                    <div class="types-grid">
                        ${types.map((item) => this._renderTypeCard(item))}
                    </div>
                ` : html`<div class="empty">${this.t('templates_page.no_types')}</div>`}
            </div>
        `;
    }

    _renderTypeCard(item) {
        const namespaceIds = Array.isArray(item.namespace_ids) ? item.namespace_ids : [];
        return html`
            <div class="type-card">
                <div class="type-title">
                    <platform-icon name=${this._resolveIcon(item.icon)} size="16"></platform-icon>
                    <span>${item.name}</span>
                </div>
                <div class="hint mono">${item.type_id}</div>
                ${item.description
                    ? html`<div class="hint">${item.description}</div>`
                    : html`<div class="hint">${this.t('templates_page.no_description')}</div>`}
                ${namespaceIds.length > 0 ? html`
                    <div class="chips">
                        ${namespaceIds.map((nsId) => html`<span class="chip mono">${nsId}</span>`)}
                    </div>
                ` : ''}
                <div class="actions-row">
                    <button
                        class="btn btn-soft"
                        type="button"
                        @click=${() => this._editType(item)}
                    >
                        ${this.t('templates_page.edit_type')}
                    </button>
                    <button
                        class="btn btn-danger"
                        type="button"
                        @click=${() => this._onDeleteType(item.type_id)}
                    >
                        ${this.t('templates_page.delete_type')}
                    </button>
                </div>
            </div>
        `;
    }

    _renderTypeFormPanel(schemaReady) {
        const namespaces = this._namespaces.items;
        const editing = this._editingTypeId.length > 0;
        return html`
            <div class="panel">
                <div class="panel-header">
                    <span class="panel-title">
                        <platform-icon name="plus" size="18"></platform-icon>
                        ${editing
                            ? this.t('templates_page.type_form_edit_title', { type_id: this._editingTypeId })
                            : this.t('templates_page.type_form_create_title')}
                    </span>
                    ${editing ? html`
                        <button
                            class="btn btn-soft"
                            type="button"
                            @click=${this._resetTypeDraft}
                        >
                            ${this.t('templates_page.btn_cancel')}
                        </button>
                    ` : ''}
                </div>
                ${!schemaReady ? html`<div class="empty">${this.t('templates_page.loading_schema')}</div>` : ''}
                <div class="grid-2">
                    <div class="field">
                        <label class="field-label">${this.t('templates_page.field_type_id')}</label>
                        <input
                            class="input mono"
                            .value=${this._typeDraft.type_id}
                            ?disabled=${editing}
                            @input=${(e) => this._updateTypeDraft('type_id', e.target.value)}
                        />
                    </div>
                    <div class="field">
                        <label class="field-label">${this.t('templates_page.field_type_name')}</label>
                        <input
                            class="input"
                            .value=${this._typeDraft.name}
                            @input=${(e) => this._updateTypeDraft('name', e.target.value)}
                        />
                    </div>
                    <div class="field">
                        <label class="field-label">${this.t('templates_page.field_parent')}</label>
                        <select
                            class="select mono"
                            .value=${this._typeDraft.parent_type_id}
                            @change=${(e) => this._updateTypeDraft('parent_type_id', e.target.value)}
                        >
                            <option value="">${this.t('templates_page.field_parent_none')}</option>
                            ${this._getParentTypeOptions().map((typeId) => html`
                                <option value=${typeId} ?selected=${typeId === this._typeDraft.parent_type_id}>${typeId}</option>
                            `)}
                        </select>
                    </div>
                    <div class="field">
                        <label class="field-label">${this.t('templates_page.field_icon')}</label>
                        <div class="icon-row">
                            <div class="icon-preview">
                                <platform-icon name=${this._resolveIcon(this._typeDraft.icon)} size="18"></platform-icon>
                            </div>
                            <input
                                class="input mono"
                                .value=${this._typeDraft.icon}
                                placeholder=${this.t('templates_page.ph_icon')}
                                @input=${(e) => this._updateTypeDraft('icon', e.target.value)}
                            />
                        </div>
                    </div>
                    <div class="field">
                        <label class="field-label">${this.t('templates_page.field_color')}</label>
                        <input
                            class="input"
                            .value=${this._typeDraft.color}
                            placeholder=${this.t('templates_page.ph_color')}
                            @input=${(e) => this._updateTypeDraft('color', e.target.value)}
                        />
                    </div>
                    <div class="field">
                        <label class="field-label">${this.t('templates_page.field_weight')}</label>
                        <input
                            type="number"
                            step="0.1"
                            min="0"
                            class="input mono"
                            .value=${this._typeDraft.weight_coefficient}
                            @input=${(e) => this._updateTypeDraft('weight_coefficient', e.target.value)}
                        />
                    </div>
                    <div class="field">
                        <label class="field-label">${this.t('templates_page.field_flags')}</label>
                        <div class="flags-row">
                            <platform-switch
                                size="sm"
                                label=${this.t('templates_page.field_is_event')}
                                .checked=${this._typeDraft.is_event}
                                @change=${(e) => this._updateTypeDraft('is_event', Boolean(e.detail.value))}
                            ></platform-switch>
                            <platform-switch
                                size="sm"
                                label=${this.t('templates_page.field_check_duplicates')}
                                .checked=${this._typeDraft.check_duplicates}
                                @change=${(e) => this._updateTypeDraft('check_duplicates', Boolean(e.detail.value))}
                            ></platform-switch>
                        </div>
                    </div>
                    <div class="field">
                        <label class="field-label">${this.t('templates_page.field_description')}</label>
                        <textarea
                            class="textarea"
                            .value=${this._typeDraft.description}
                            @input=${(e) => this._updateTypeDraft('description', e.target.value)}
                        ></textarea>
                    </div>
                    <div class="field">
                        <label class="field-label">${this.t('templates_page.field_prompt')}</label>
                        <textarea
                            class="textarea"
                            .value=${this._typeDraft.prompt}
                            @input=${(e) => this._updateTypeDraft('prompt', e.target.value)}
                        ></textarea>
                    </div>
                    <div class="field">
                        <label class="field-label">${this.t('templates_page.field_namespaces')}</label>
                        ${namespaces.length > 0 ? html`
                            <div class="namespace-pills">
                                ${namespaces.map((ns) => {
                                    const checked = this._typeDraft.namespace_ids.includes(ns.name);
                                    return html`
                                        <button
                                            type="button"
                                            class="ns-pill ${checked ? 'active' : ''}"
                                            @click=${() => this._toggleTypeNamespace(ns.name, !checked)}
                                        >
                                            ${ns.name}
                                        </button>
                                    `;
                                })}
                            </div>
                        ` : html`<div class="hint">${this.t('templates_page.no_namespaces')}</div>`}
                    </div>
                </div>
                <div class="schema-grid">
                    ${this._renderSchemaSection('required_fields_rows', schemaReady,
                        this.t('templates_page.required_fields_title'),
                        this.t('templates_page.required_fields_hint'))}
                    ${this._renderSchemaSection('optional_fields_rows', schemaReady,
                        this.t('templates_page.optional_fields_title'),
                        this.t('templates_page.optional_fields_hint'))}
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
                        ?disabled=${!schemaReady || this._savingType}
                        @click=${this._onUpsertType}
                    >
                        ${this._savingType
                            ? this.t('templates_page.btn_saving')
                            : (editing
                                ? this.t('templates_page.save_type_changes')
                                : this.t('templates_page.save_type'))}
                    </button>
                </div>
            </div>
        `;
    }

    _renderSchemaSection(sectionKey, schemaReady, title, hint) {
        return html`
            <div class="schema-section">
                <div class="panel-title">${title}</div>
                <div class="hint">${hint}</div>
                ${schemaReady ? html`
                    <crm-schema-field-builder
                        .rows=${this._typeDraft[sectionKey]}
                        .schemaOptions=${this._schemaOptions}
                        @rows-changed=${(e) => this._setSchemaRows(sectionKey, e.detail.rows)}
                    ></crm-schema-field-builder>
                ` : html`<div class="empty">${this.t('templates_page.loading_schema')}</div>`}
            </div>
        `;
    }
}

customElements.define('crm-templates-page', CRMTemplatesPage);
