/**
 * CRMTemplatesPage — управление шаблонами пространств CRM (CRUD + типы).
 *
 * Левая колонка — список шаблонов и inline-форма создания нового. Правая —
 * метаданные выбранного шаблона; блок «Типы в шаблоне» и форма типа
 * в одной колонке: при редактировании/создании типа сетка карточек заменяется
 * на `crm-entity-type-editor` (как на `space-detail-page`).
 *
 * Состояние:
 *  - useResource('crm/templates', { autoload: true }) — список + get/create/remove.
 *  - useResource('crm/namespaces', { autoload: true }) — пространства для пилюль типа.
 *  - useOp('crm/template_update') — PUT метаданных выбранного шаблона.
 *  - useOp('crm/template_schema_options') — загрузка опций схемы (silent).
 *  - useOp('crm/template_type_upsert') — upsert типа в шаблоне.
 *  - useOp('crm/template_type_delete') — удаление типа.
 *  - useOp('crm/template_task_board_editor_state') — GET состояния редакторов досок (silent).
 *
 * После CREATE/REMOVE/UPSERT/DELETE — перезагружаем детали выбранного
 * шаблона, чтобы отрисовать актуальный список типов.
 * Стадии досок сохраняются через template_update с body.crm_settings.pipeline_stage_presets.
 */

import { html, css } from 'lit';
import { PlatformPage } from '@platform/lib/base/PlatformPage.js';
import '@platform/lib/components/layout/page-header.js';
import '@platform/lib/components/platform-icon.js';
import '@platform/lib/components/platform-icon-picker.js';
import '@platform/lib/components/platform-breadcrumbs.js';
import '@platform/lib/components/glass-spinner.js';
import '@platform/lib/components/platform-palette-color-picker.js';
import '@platform/lib/components/platform-help-hint.js';
import '@platform/lib/components/fields/platform-field.js';
import { listAvailableUiIcons } from '@platform/lib/utils/file-icons.js';
import { platformConfirm } from '@platform/lib/components/platform-confirm-modal.js';

import '../components/entity-type-editor.js';
import '../components/namespace-note-defaults-fields.js';
import {
    normalizeDefaultNoteVoiceMode,
    parseNoteVoiceDefaultsFromCrmSettings,
} from '../utils/namespace-crm-note-defaults.js';
import {
    normalizeSchemaRows,
    buildSchemaFromRows,
} from '../components/schema-field-builder.js';
import { entityTypeNoteSubtreeLocked } from '../utils/entity-type-note-subtree-lock.js';
import {
    CRM_ENTITY_TYPE_CREATE_MODE_CHOSEN,
    CRM_ENTITY_TYPE_PRESET_PICKER_APPLIED,
} from '../utils/entity-type-create-events.js';
import { buildEntityTypeDraftFromTemplateTypeItem } from '../utils/entity-type-draft-from-preset.js';

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
    is_context_anchor: false,
    is_voice_target: false,
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

const TEMPLATE_UI_ICON_NAMES = Object.freeze(listAvailableUiIcons());

export class CRMTemplatesPage extends PlatformPage {
    static i18nNamespace = 'crm';

    static properties = {
        _selectedTemplateId: { state: true },
        _showCreateForm: { state: true },
        _newDraft: { state: true },
        _typeDraft: { state: true },
        _editingTypeId: { state: true },
        _typeFormOpen: { state: true },
        _metaDraft: { state: true },
        _schemaOptions: { state: true },
        _taskBoardDraft: { state: true },
        _taskBoardSaveBusy: { state: true },
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
            .right-column {
                display: flex;
                flex-direction: column;
                gap: var(--space-3);
                min-width: 0;
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
            .field-label-row {
                display: flex;
                align-items: center;
                gap: var(--space-2);
                flex-wrap: wrap;
            }
            .field-label-row .field-label {
                margin: 0;
            }
            .panel-title-row-hint {
                display: inline-flex;
                align-items: center;
                gap: var(--space-2);
                flex-wrap: wrap;
            }
            .stage-header-row {
                display: grid;
                grid-template-columns: minmax(0, 1fr) minmax(0, 1.2fr) minmax(0, 0.9fr) auto;
                gap: var(--space-2);
                align-items: center;
                margin-bottom: var(--space-1);
            }
            @media (max-width: 720px) {
                .stage-header-row {
                    display: none;
                }
            }
            .stage-head-cell {
                display: flex;
                align-items: center;
                gap: var(--space-1);
                min-width: 0;
                font-size: var(--text-xs);
                font-weight: var(--font-medium);
                color: var(--text-tertiary);
                text-transform: uppercase;
                letter-spacing: 0.04em;
            }
            .stage-head-cell.stage-head-actions {
                justify-content: flex-end;
            }

            .stage-row platform-field {
                min-width: 0;
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

            .panel-title .panel-back {
                flex-shrink: 0;
                padding: var(--space-1);
                min-width: 36px;
                min-height: 36px;
                display: inline-flex;
                align-items: center;
                justify-content: center;
            }

            @media (max-width: 980px) {
                .layout {
                    grid-template-columns: 1fr;
                }
            }

            .center {
                display: flex;
                flex-direction: column;
                align-items: center;
                justify-content: center;
                gap: var(--space-3);
                padding: var(--space-6);
                color: var(--text-tertiary);
            }

            .templates-stack {
                display: flex;
                flex-direction: column;
                gap: var(--space-3);
                min-width: 0;
            }

            .task-board-board {
                display: flex;
                flex-direction: column;
                gap: var(--space-2);
                padding: var(--space-3);
                border: 1px solid var(--crm-stroke);
                border-radius: var(--radius-md);
                background: var(--crm-surface-muted);
            }
            .task-board-board-head {
                display: flex;
                flex-direction: column;
                gap: var(--space-1);
                min-width: 0;
            }
            .task-board-board-head-top {
                display: flex;
                align-items: center;
                justify-content: space-between;
                gap: var(--space-2);
                min-width: 0;
            }
            .task-board-board-title {
                font-weight: 600;
                color: var(--text-primary);
                min-width: 0;
            }
            .task-board-add-stage {
                flex-shrink: 0;
                padding: var(--space-2);
                min-width: 40px;
                min-height: 40px;
            }
            .stage-row {
                display: grid;
                grid-template-columns: minmax(0, 1fr) minmax(0, 1.2fr) minmax(0, 0.9fr) auto;
                gap: var(--space-2);
                align-items: center;
            }
            @media (max-width: 720px) {
                .stage-row {
                    grid-template-columns: 1fr;
                }
            }
            .stage-row-actions {
                display: inline-flex;
                flex-wrap: wrap;
                gap: var(--space-1);
                justify-content: flex-end;
            }
            .stage-color-picker {
                min-width: 0;
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
        this._typeFormOpen = false;
        this._metaDraft = null;
        this._schemaOptions = null;
        this._taskBoardDraft = null;
        this._taskBoardSaveBusy = false;
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
        this._templateTaskBoardEditorStateOp = this.useOp('crm/template_task_board_editor_state');
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

    connectedCallback() {
        super.connectedCallback();
        this._schemaOptionsOp.run(null);
        this.useEvent(this._schemaOptionsOp.op.events.SUCCEEDED, (event) => {
            if (!event.payload || typeof event.payload.result !== 'object') {
                return;
            }
            this._schemaOptions = event.payload.result;
        });
        this.useEvent(this._templateTaskBoardEditorStateOp.op.events.SUCCEEDED, (event) => {
            const r = event.payload.result;
            const boards = r && Array.isArray(r.boards) ? r.boards : [];
            this._taskBoardDraft = boards
                .map((b) => {
                    const board_key = typeof b.board_key === 'string' ? b.board_key : '';
                    const label = typeof b.label === 'string' ? b.label : '';
                    const stagesRaw = Array.isArray(b.stages) ? b.stages : [];
                    const stages = stagesRaw.map((s) => {
                        const id = typeof s.id === 'string' ? s.id : '';
                        const lb = typeof s.label === 'string' ? s.label : '';
                        const color = typeof s.color === 'string' ? s.color : '';
                        return { id, label: lb, color };
                    });
                    return { board_key, label, stages };
                })
                .filter((row) => row.board_key.length > 0);
        });
        this.useEvent(this._templateTaskBoardEditorStateOp.op.events.FAILED, (event) => {
            this._taskBoardDraft = null;
            const msg = event.payload && typeof event.payload.message === 'string' ? event.payload.message : '';
            this.toast('crm:space_detail_page.task_board_load_failed', { type: 'error', vars: { message: msg } });
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
                this._typeFormOpen = false;
                this._taskBoardDraft = null;
                this._taskBoardSaveBusy = false;
            }
            this._deletingTemplate = false;
        });
        this.useEvent(this._templates.resource.events.ITEM_LOADED, (event) => {
            const item = event.payload && event.payload.item;
            if (!item || item.template_id !== this._selectedTemplateId) {
                return;
            }
            const cs =
                item.crm_settings !== undefined
                && item.crm_settings !== null
                && typeof item.crm_settings === 'object'
                    ? item.crm_settings
                    : null;
            const p = parseNoteVoiceDefaultsFromCrmSettings(cs);
            this._metaDraft = {
                name: item.name || '',
                description: item.description || '',
                icon: item.icon || 'folder',
                default_note_voice: p.defaultNoteVoiceMode,
                show_note_voice_ui: p.showNoteVoiceUi,
            };
            this._loadTemplateTaskBoardEditorState();
        });
        this.useEvent(this._updateMetaOp.op.events.SUCCEEDED, () => {
            this._savingMeta = false;
            this._taskBoardSaveBusy = false;
            if (this._selectedTemplateId) {
                this._templates.get(this._selectedTemplateId);
                this._templates.load(null);
                this._loadTemplateTaskBoardEditorState();
            }
        });
        this.useEvent(this._updateMetaOp.op.events.FAILED, () => {
            this._savingMeta = false;
            this._taskBoardSaveBusy = false;
        });
        this.useEvent(this._upsertTypeOp.op.events.SUCCEEDED, () => {
            this._savingType = false;
            this._typeFormOpen = false;
            this._typeDraft = makeTypeDraft();
            this._editingTypeId = '';
            if (this._selectedTemplateId) {
                this._templates.get(this._selectedTemplateId);
                this._loadTemplateTaskBoardEditorState();
            }
        });
        this.useEvent(this._upsertTypeOp.op.events.FAILED, () => {
            this._savingType = false;
        });
        this.useEvent(this._deleteTypeOp.op.events.SUCCEEDED, () => {
            this._typeFormOpen = false;
            this._typeDraft = makeTypeDraft();
            this._editingTypeId = '';
            if (this._selectedTemplateId) {
                this._templates.get(this._selectedTemplateId);
                this._loadTemplateTaskBoardEditorState();
            }
        });
        this.useEvent(CRM_ENTITY_TYPE_CREATE_MODE_CHOSEN, (event) => {
            const p = event.payload;
            if (!p || typeof p !== 'object') {
                throw new Error('CRMTemplatesPage: create_mode_chosen payload required');
            }
            if (p.mode === 'blank') {
                this._openNewTypeForm();
                return;
            }
            if (p.mode === 'from_presets') {
                this.openModal('crm.entity_type_preset_picker');
                return;
            }
            throw new Error('CRMTemplatesPage: create_mode_chosen unknown mode');
        });
        this.useEvent(CRM_ENTITY_TYPE_PRESET_PICKER_APPLIED, (event) => {
            const p = event.payload;
            if (!p || typeof p !== 'object') {
                throw new Error('CRMTemplatesPage: preset_picker_applied payload required');
            }
            const snap = p.type_snapshot;
            if (!snap || typeof snap !== 'object' || typeof snap.type_id !== 'string') {
                throw new Error('CRMTemplatesPage: preset_picker_applied type_snapshot required');
            }
            this._editingTypeId = '';
            this._typeDraft = buildEntityTypeDraftFromTemplateTypeItem(
                snap,
                this._templateDetailTypeCatalogRows(),
                makeTypeDraft,
                { namespaceIds: true },
            );
            this._typeFormOpen = true;
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
        this._typeFormOpen = false;
        this._typeDraft = makeTypeDraft();
        this._editingTypeId = '';
        this._taskBoardDraft = null;
        const cached = this._templates.byId[templateId];
        if (cached && Array.isArray(cached.types)) {
            const cs =
                cached.crm_settings !== undefined
                && cached.crm_settings !== null
                && typeof cached.crm_settings === 'object'
                    ? cached.crm_settings
                    : null;
            const p = parseNoteVoiceDefaultsFromCrmSettings(cs);
            this._metaDraft = {
                name: cached.name || '',
                description: cached.description || '',
                icon: cached.icon || 'folder',
                default_note_voice: p.defaultNoteVoiceMode,
                show_note_voice_ui: p.showNoteVoiceUi,
            };
            this._loadTemplateTaskBoardEditorState();
        } else {
            this._metaDraft = null;
        }
        this._templates.get(templateId);
    }

    _loadTemplateTaskBoardEditorState() {
        if (typeof this._selectedTemplateId !== 'string' || this._selectedTemplateId.length === 0) {
            return;
        }
        this._templateTaskBoardEditorStateOp.run({ template_id: this._selectedTemplateId });
    }

    _taskBoardStageIdValid(raw) {
        if (typeof raw !== 'string') return false;
        return /^[a-z][a-z0-9_]*$/.test(raw.trim());
    }

    _onSaveTemplateTaskBoard() {
        const draft = this._taskBoardDraft;
        if (!Array.isArray(draft) || draft.length === 0) return;
        const presets = {};
        for (const row of draft) {
            const board_key = typeof row.board_key === 'string' ? row.board_key : '';
            if (!board_key) continue;
            const stages = [];
            const seen = new Set();
            for (const st of row.stages) {
                const id = typeof st.id === 'string' ? st.id.trim() : '';
                const label = typeof st.label === 'string' ? st.label.trim() : '';
                if (!id.length || !label.length) continue;
                if (!this._taskBoardStageIdValid(id)) {
                    this.toast('crm:space_detail_page.task_board_err_stage_id', { type: 'error' });
                    return;
                }
                if (seen.has(id)) {
                    this.toast('crm:space_detail_page.task_board_err_duplicate_id', { type: 'error' });
                    return;
                }
                seen.add(id);
                const cell = { id, label };
                const color = typeof st.color === 'string' ? st.color.trim() : '';
                if (color.length > 0) cell.color = color;
                stages.push(cell);
            }
            if (stages.length === 0) {
                this.toast('crm:space_detail_page.task_board_err_stages', { type: 'error' });
                return;
            }
            presets[board_key] = { stages };
        }
        if (Object.keys(presets).length === 0) {
            this.toast('crm:space_detail_page.task_board_err_stages', { type: 'error' });
            return;
        }
        if (!this._selectedTemplateId) {
            throw new Error('CRMTemplatesPage._onSaveTemplateTaskBoard: template not selected');
        }
        this._taskBoardSaveBusy = true;
        this._updateMetaOp.run({
            template_id: this._selectedTemplateId,
            body: { crm_settings: { pipeline_stage_presets: presets } },
        });
    }

    _setTemplateTaskBoardDraft(next) {
        this._taskBoardDraft = next;
    }

    _onTaskBoardStageField(boardIdx, stageIdx, field, value) {
        const draft = this._taskBoardDraft;
        if (!Array.isArray(draft) || !draft[boardIdx] || !draft[boardIdx].stages[stageIdx]) return;
        const next = draft.map((row, bi) => {
            if (bi !== boardIdx) return row;
            return {
                ...row,
                stages: row.stages.map((s, si) => (si === stageIdx ? { ...s, [field]: value } : s)),
            };
        });
        this._setTemplateTaskBoardDraft(next);
    }

    _addTaskBoardStage(boardIdx) {
        const draft = this._taskBoardDraft;
        if (!Array.isArray(draft) || !draft[boardIdx]) return;
        const next = draft.map((row, bi) => {
            if (bi !== boardIdx) return row;
            return { ...row, stages: [...row.stages, { id: '', label: '', color: '' }] };
        });
        this._setTemplateTaskBoardDraft(next);
    }

    _removeTaskBoardStage(boardIdx, stageIdx) {
        const draft = this._taskBoardDraft;
        if (!Array.isArray(draft) || !draft[boardIdx]) return;
        const row = draft[boardIdx];
        if (row.stages.length <= 1) {
            this.toast('crm:space_detail_page.task_board_err_min_stages', { type: 'error' });
            return;
        }
        const next = draft.map((r, bi) => {
            if (bi !== boardIdx) return r;
            return { ...r, stages: r.stages.filter((_, si) => si !== stageIdx) };
        });
        this._setTemplateTaskBoardDraft(next);
    }

    _moveTaskBoardStage(boardIdx, stageIdx, delta) {
        const draft = this._taskBoardDraft;
        if (!Array.isArray(draft) || !draft[boardIdx]) return;
        const stages = draft[boardIdx].stages;
        const j = stageIdx + delta;
        if (j < 0 || j >= stages.length) return;
        const nextStages = stages.slice();
        const t = nextStages[stageIdx];
        nextStages[stageIdx] = nextStages[j];
        nextStages[j] = t;
        const next = draft.map((row, bi) => (bi === boardIdx ? { ...row, stages: nextStages } : row));
        this._setTemplateTaskBoardDraft(next);
    }

    _renderTemplateTaskBoardPanel() {
        if (!this._selectedTemplateId || !this._metaDraft) {
            return '';
        }
        const tbOp = this._templateTaskBoardEditorStateOp;
        const draft = this._taskBoardDraft;
        return html`
            <div class="panel">
                <div class="panel-header">
                    <span class="panel-title panel-title-row-hint">
                        <platform-icon name="layers" size="18"></platform-icon>
                        <span>${this.t('space_detail_page.task_board_section')}</span>
                        <platform-help-hint
                            .text=${this.t('space_detail_page.task_board_section_hint')}
                            label=${this.t('templates_page.field_hint_button_aria')}
                        ></platform-help-hint>
                    </span>
                </div>
                <p class="hint">${this.t('space_detail_page.task_board_hint')}</p>
                <p class="hint">${this.t('templates_page.task_board_template_hint')}</p>
                ${tbOp.busy && !Array.isArray(draft)
                    ? html`<div class="center" style="padding: var(--space-3);"><glass-spinner size="md"></glass-spinner></div>`
                    : ''}
                ${!tbOp.busy && tbOp.error !== null && !Array.isArray(draft)
                    ? html`
                        <p class="hint">${this.t('space_detail_page.task_board_retry_hint', {
                            message:
                                typeof tbOp.error === 'string' && tbOp.error.length !== 0
                                    ? tbOp.error
                                    : '—',
                        })}</p>
                        <div class="actions-row">
                            <button class="btn btn-soft" type="button" @click=${this._loadTemplateTaskBoardEditorState}>
                                ${this.t('space_detail_page.task_board_retry')}
                            </button>
                        </div>
                    `
                    : ''}
                ${Array.isArray(draft) && draft.length === 0
                    ? html`<p class="hint">${this.t('templates_page.task_board_empty')}</p>`
                    : ''}
                ${Array.isArray(draft) && draft.length > 0
                    ? html`
                        ${draft.map((board, bi) => html`
                            <div class="task-board-board">
                                <div class="task-board-board-head">
                                    <div class="task-board-board-head-top">
                                        <div class="task-board-board-title">${board.label}</div>
                                        <button
                                            class="btn btn-soft task-board-add-stage"
                                            type="button"
                                            title=${this.t('space_detail_page.task_board_add_stage')}
                                            aria-label=${this.t('space_detail_page.task_board_add_stage')}
                                            @click=${() => this._addTaskBoardStage(bi)}
                                        >
                                            <platform-icon name="plus" size="18"></platform-icon>
                                        </button>
                                    </div>
                                    <div class="hint mono">${board.board_key}</div>
                                </div>
                                <div class="stage-header-row">
                                    <div class="stage-head-cell">
                                        <span>${this.t('space_detail_page.task_board_col_stage_id_label')}</span>
                                        <platform-help-hint
                                            .text=${this.t('space_detail_page.task_board_col_stage_id_hint')}
                                            label=${this.t('templates_page.field_hint_button_aria')}
                                        ></platform-help-hint>
                                    </div>
                                    <div class="stage-head-cell">
                                        <span>${this.t('space_detail_page.task_board_col_stage_title_label')}</span>
                                        <platform-help-hint
                                            .text=${this.t('space_detail_page.task_board_col_stage_title_hint')}
                                            label=${this.t('templates_page.field_hint_button_aria')}
                                        ></platform-help-hint>
                                    </div>
                                    <div class="stage-head-cell">
                                        <span>${this.t('space_detail_page.task_board_col_color_label')}</span>
                                        <platform-help-hint
                                            .text=${this.t('space_detail_page.task_board_col_color_hint')}
                                            label=${this.t('templates_page.field_hint_button_aria')}
                                        ></platform-help-hint>
                                    </div>
                                    <div class="stage-head-cell stage-head-actions"></div>
                                </div>
                                ${board.stages.map((st, si) => html`
                                    <div class="stage-row">
                                        <platform-field
                                            type="string"
                                            mode="edit"
                                            input-type="text"
                                            .placeholder=${this.t('space_detail_page.task_board_stage_id_ph')}
                                            .value=${st.id}
                                            ?disabled=${this._taskBoardSaveBusy
                                                || this._savingMeta
                                                || this._savingType
                                                || this._deletingTemplate}
                                            @change=${(e) => {
                                                const v = typeof e.detail.value === 'string' ? e.detail.value : '';
                                                this._onTaskBoardStageField(bi, si, 'id', v);
                                            }}
                                        ></platform-field>
                                        <platform-field
                                            type="string"
                                            mode="edit"
                                            input-type="text"
                                            .placeholder=${this.t('space_detail_page.task_board_stage_label_ph')}
                                            .value=${st.label}
                                            ?disabled=${this._taskBoardSaveBusy
                                                || this._savingMeta
                                                || this._savingType
                                                || this._deletingTemplate}
                                            @change=${(e) => {
                                                const v = typeof e.detail.value === 'string' ? e.detail.value : '';
                                                this._onTaskBoardStageField(bi, si, 'label', v);
                                            }}
                                        ></platform-field>
                                        <platform-palette-color-picker
                                            class="stage-color-picker"
                                            allow-clear
                                            .value=${st.color}
                                            ?disabled=${this._taskBoardSaveBusy
                                                || this._savingMeta
                                                || this._savingType
                                                || this._deletingTemplate}
                                            @change=${(e) => {
                                                const v = e.detail && typeof e.detail.value === 'string'
                                                    ? e.detail.value
                                                    : '';
                                                this._onTaskBoardStageField(bi, si, 'color', v);
                                            }}
                                        ></platform-palette-color-picker>
                                        <div class="stage-row-actions">
                                            <button
                                                class="btn btn-soft"
                                                type="button"
                                                ?disabled=${si === 0}
                                                @click=${() => this._moveTaskBoardStage(bi, si, -1)}
                                                title=${this.t('space_detail_page.task_board_move_up')}
                                            >
                                                ${this.t('space_detail_page.task_board_move_up')}
                                            </button>
                                            <button
                                                class="btn btn-soft"
                                                type="button"
                                                ?disabled=${si >= board.stages.length - 1}
                                                @click=${() => this._moveTaskBoardStage(bi, si, 1)}
                                                title=${this.t('space_detail_page.task_board_move_down')}
                                            >
                                                ${this.t('space_detail_page.task_board_move_down')}
                                            </button>
                                            <button
                                                class="btn btn-danger"
                                                type="button"
                                                @click=${() => this._removeTaskBoardStage(bi, si)}
                                            >
                                                ${this.t('space_detail_page.task_board_remove_stage')}
                                            </button>
                                        </div>
                                    </div>
                                `)}
                            </div>
                        `)}
                        <div class="actions-row">
                            <button
                                class="btn btn-primary"
                                type="button"
                                ?disabled=${this._taskBoardSaveBusy
                                    || this._savingMeta
                                    || this._savingType
                                    || this._deletingTemplate}
                                @click=${this._onSaveTemplateTaskBoard}
                            >
                                ${this._taskBoardSaveBusy
                                    ? this.t('space_detail_page.task_board_saving')
                                    : this.t('space_detail_page.task_board_save')}
                            </button>
                        </div>
                    `
                    : ''}
            </div>
        `;
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

    _metaIconPickerIcons(current) {
        const cur = typeof current === 'string' ? current.trim() : '';
        if (cur.length > 0 && !TEMPLATE_UI_ICON_NAMES.includes(cur)) {
            return [cur, ...TEMPLATE_UI_ICON_NAMES];
        }
        return TEMPLATE_UI_ICON_NAMES;
    }

    _onMetaIconChange(event) {
        const v = event && event.detail && event.detail.value;
        this._updateMetaField('icon', typeof v === 'string' ? v : '');
    }

    _onTemplateNoteVoiceFromChild(e) {
        if (!this._metaDraft) {
            return;
        }
        const d = e.detail;
        if (d === undefined || d === null || typeof d !== 'object' || typeof d.value !== 'string') {
            return;
        }
        const v = d.value;
        if (v !== 'none' && v !== 'last' && v !== 'self') {
            return;
        }
        this._metaDraft = { ...this._metaDraft, default_note_voice: v };
    }

    _onTemplateNoteShowUiFromChild(e) {
        if (!this._metaDraft) {
            return;
        }
        const d = e.detail;
        if (d === undefined || d === null || typeof d !== 'object' || typeof d.value !== 'boolean') {
            return;
        }
        this._metaDraft = { ...this._metaDraft, show_note_voice_ui: d.value };
    }

    _onNewTemplateIconChange(event) {
        const v = event && event.detail && event.detail.value;
        this._updateNewDraft('icon', typeof v === 'string' ? v : '');
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
        const voiceMode = normalizeDefaultNoteVoiceMode(this._metaDraft.default_note_voice);
        this._updateMetaOp.run({
            template_id: this._selectedTemplateId,
            body: {
                name,
                description: this._metaDraft.description.trim() || null,
                icon: this._metaDraft.icon.trim() || null,
                crm_settings: {
                    default_note_voice: voiceMode,
                    show_note_voice_ui: this._metaDraft.show_note_voice_ui === true,
                },
            },
        });
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
        this._typeDraft = { ...this._typeDraft, namespace_ids: next };
    }

    _onTypeDraftChanged(event) {
        const next = event && event.detail && event.detail.typeDraft;
        if (!next) {
            return;
        }
        this._typeDraft = next;
    }

    _onSchemaRowsFromEditor(event) {
        const detail = event && event.detail;
        if (!detail
            || (detail.section !== 'required_fields_rows' && detail.section !== 'optional_fields_rows')) {
            return;
        }
        this._setSchemaRows(detail.section, detail.rows);
    }

    _onNamespaceToggledFromEditor(event) {
        const detail = event && event.detail;
        if (!detail || typeof detail.namespaceName !== 'string' || detail.namespaceName.length === 0) {
            return;
        }
        this._toggleTypeNamespace(detail.namespaceName, detail.enabled === true);
    }

    _openNewTypeForm() {
        this._editingTypeId = '';
        this._typeDraft = makeTypeDraft();
        this._typeFormOpen = true;
    }

    _templateDetailTypeCatalogRows() {
        const detail = this._templates.byId[this._selectedTemplateId];
        const types = detail && Array.isArray(detail.types) ? detail.types : [];
        return types.map((row) => ({
            type_id: row.type_id,
            parent_type_id:
                typeof row.parent_type_id === 'string' && row.parent_type_id.length > 0
                    ? row.parent_type_id
                    : '',
        }));
    }

    _editType(item) {
        if (!item || typeof item.type_id !== 'string') {
            throw new Error('CRMTemplatesPage._editType: item.type_id required');
        }
        this._editingTypeId = item.type_id;
        this._typeFormOpen = true;
        const catalogRows = this._templateDetailTypeCatalogRows();
        const parentId = typeof item.parent_type_id === 'string' ? item.parent_type_id : '';
        const noteLocked = entityTypeNoteSubtreeLocked(
            { type_id: item.type_id, parent_type_id: parentId },
            catalogRows,
        );
        this._typeDraft = {
            type_id: item.type_id,
            name: item.name || '',
            description: item.description || '',
            prompt: item.prompt || '',
            required_fields_rows: normalizeSchemaRows(item.required_fields && typeof item.required_fields === 'object' ? item.required_fields : {}),
            optional_fields_rows: normalizeSchemaRows(item.optional_fields && typeof item.optional_fields === 'object' ? item.optional_fields : {}),
            namespace_ids: Array.isArray(item.namespace_ids) ? [...item.namespace_ids] : [],
            parent_type_id: parentId,
            icon: item.icon || '',
            color: item.color || '',
            is_event: item.is_event === true,
            check_duplicates: item.check_duplicates !== false,
            is_context_anchor: noteLocked ? false : item.is_context_anchor === true,
            is_voice_target: noteLocked ? false : item.is_voice_target === true,
            weight_coefficient: String(item.weight_coefficient === undefined ? 1 : item.weight_coefficient),
        };
    }

    _resetTypeDraft() {
        this._typeFormOpen = false;
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
        const noteLocked = entityTypeNoteSubtreeLocked(this._typeDraft, this._templateDetailTypeCatalogRows());
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
                is_context_anchor: noteLocked ? false : this._typeDraft.is_context_anchor === true,
                is_voice_target: noteLocked ? false : this._typeDraft.is_voice_target === true,
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
        return html`
            <div class="breadcrumbs-wrap">
                <platform-breadcrumbs></platform-breadcrumbs>
            </div>
            <page-header
                title=${this.t('templates_page.title')}
                subtitle=${this.t('templates_page.subtitle')}
            ></page-header>
            <div class="scroll">
                <div class="templates-stack">
                    <div class="layout">
                        ${this._renderLeftPanel(templates)}
                        ${this._renderRightPanel(selectedDetail, types)}
                    </div>
                    ${this._renderTemplateTaskBoardPanel()}
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
                <platform-field
                    type="string"
                    mode="edit"
                    .label=${this.t('templates_page.label_template_id')}
                    .hint=${this.t('templates_page.label_template_id_hint')}
                    .placeholder=${this.t('templates_page.ph_template_id')}
                    .value=${this._newDraft.template_id}
                    ?disabled=${this._creatingTemplate}
                    @change=${(e) => this._updateNewDraft(
                        'template_id',
                        typeof e.detail.value === 'string' ? e.detail.value : '',
                    )}
                ></platform-field>
                <platform-field
                    type="string"
                    mode="edit"
                    .label=${this.t('templates_page.label_name')}
                    .hint=${this.t('templates_page.label_name_hint')}
                    .placeholder=${this.t('templates_page.ph_template_name')}
                    .value=${this._newDraft.name}
                    ?disabled=${this._creatingTemplate}
                    @change=${(e) => this._updateNewDraft(
                        'name',
                        typeof e.detail.value === 'string' ? e.detail.value : '',
                    )}
                ></platform-field>
                <platform-field
                    type="text"
                    mode="edit"
                    .label=${this.t('templates_page.label_description')}
                    .hint=${this.t('templates_page.label_description_hint')}
                    .placeholder=${this.t('templates_page.ph_template_description')}
                    .value=${this._newDraft.description}
                    ?disabled=${this._creatingTemplate}
                    @change=${(e) => this._updateNewDraft(
                        'description',
                        typeof e.detail.value === 'string' ? e.detail.value : '',
                    )}
                ></platform-field>
                    <div class="field">
                        ${this._fieldLabelWithHint(
                            'templates_page.label_icon',
                            'templates_page.label_icon_hint',
                        )}
                        <platform-icon-picker
                            .value=${this._newDraft.icon}
                            .icons=${this._metaIconPickerIcons(this._newDraft.icon)}
                            placeholder=${this.t('templates_page.icon_picker_placeholder')}
                            ?disabled=${this._creatingTemplate}
                            @change=${this._onNewTemplateIconChange}
                        ></platform-icon-picker>
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

    _renderRightPanel(detail, types) {
        if (!this._selectedTemplateId) {
            return html`
                <div class="right-column">
                    <div class="panel">
                        <div class="empty">${this.t('templates_page.no_template_selected')}</div>
                    </div>
                </div>
            `;
        }
        if (!detail || !this._metaDraft) {
            return html`
                <div class="right-column">
                    <div class="panel">
                        <div class="empty">${this.t('templates_page.loading_detail')}</div>
                    </div>
                </div>
            `;
        }
        return html`
            <div class="right-column">
                ${this._renderMetaPanel(detail)}
                ${this._typeFormOpen
                    ? this._renderTypeFormPanel()
                    : this._renderTypesListPanel(types)}
            </div>
        `;
    }

    _renderMetaPanel(detail) {
        return html`
            <div class="panel">
                <div class="panel-header">
                    <span class="panel-title panel-title-row-hint">
                        <platform-icon name="edit" size="18"></platform-icon>
                        <span>${this.t('templates_page.meta_section')}</span>
                        <platform-help-hint
                            .text=${this.t('templates_page.meta_section_hint')}
                            label=${this.t('templates_page.field_hint_button_aria')}
                        ></platform-help-hint>
                    </span>
                    <span class="chip mono">${detail.template_id}</span>
                </div>
                <div class="grid-2">
                    <platform-field
                        type="string"
                        mode="edit"
                        .label=${this.t('templates_page.label_name')}
                        .hint=${this.t('templates_page.label_name_hint')}
                        .value=${this._metaDraft.name}
                        ?disabled=${this._savingMeta || this._deletingTemplate}
                        @change=${(e) => this._updateMetaField(
                            'name',
                            typeof e.detail.value === 'string' ? e.detail.value : '',
                        )}
                    ></platform-field>
                    <div class="field">
                        ${this._fieldLabelWithHint(
                            'templates_page.label_icon',
                            'templates_page.label_icon_hint',
                        )}
                        <platform-icon-picker
                            .value=${this._metaDraft.icon}
                            .icons=${this._metaIconPickerIcons(this._metaDraft.icon)}
                            placeholder=${this.t('templates_page.icon_picker_placeholder')}
                            ?disabled=${this._savingMeta || this._deletingTemplate}
                            @change=${this._onMetaIconChange}
                        ></platform-icon-picker>
                    </div>
                </div>
                <platform-field
                    type="text"
                    mode="edit"
                    .label=${this.t('templates_page.label_description')}
                    .hint=${this.t('templates_page.label_description_hint')}
                    .value=${this._metaDraft.description}
                    ?disabled=${this._savingMeta || this._deletingTemplate}
                    @change=${(e) => this._updateMetaField(
                        'description',
                        typeof e.detail.value === 'string' ? e.detail.value : '',
                    )}
                ></platform-field>
                <crm-namespace-note-defaults-fields
                    .defaultNoteVoiceMode=${normalizeDefaultNoteVoiceMode(this._metaDraft.default_note_voice)}
                    .showNoteVoiceUi=${this._metaDraft.show_note_voice_ui !== false}
                    ?disabled=${this._savingMeta || this._deletingTemplate}
                    @default-note-voice-change=${this._onTemplateNoteVoiceFromChild}
                    @show-note-voice-ui-change=${this._onTemplateNoteShowUiFromChild}
                ></crm-namespace-note-defaults-fields>
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
                    <span class="actions-row" style="flex-wrap: nowrap; align-items: center;">
                        <span class="chip">${this.t('templates_page.types_count', { count: String(types.length) })}</span>
                        <button
                            class="btn btn-soft"
                            type="button"
                            @click=${() => this.openModal('crm.entity_type_create_mode')}
                        >
                            ${this.t('templates_page.action_new_type')}
                        </button>
                    </span>
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

    _renderTypeFormPanel() {
        const namespaces = Array.isArray(this._namespaces.items) ? this._namespaces.items : [];
        return html`
            <div class="panel">
                <div class="panel-header">
                    <span class="panel-title">
                        <button
                            class="btn btn-soft panel-back"
                            type="button"
                            title=${this.t('templates_page.back_to_types')}
                            aria-label=${this.t('templates_page.back_to_types')}
                            @click=${this._resetTypeDraft}
                        >
                            <platform-icon name="chevron-left" size="18"></platform-icon>
                        </button>
                        <platform-icon name="list" size="18"></platform-icon>
                        ${this.t('templates_page.types_section')}
                    </span>
                    <span class="actions-row" style="flex-wrap: nowrap; align-items: center;">
                        <button
                            class="btn btn-soft"
                            type="button"
                            @click=${this._resetTypeDraft}
                        >
                            ${this.t('templates_page.btn_cancel')}
                        </button>
                    </span>
                </div>
                <crm-entity-type-editor
                    .typeDraft=${this._typeDraft}
                    .schemaOptions=${this._schemaOptions}
                    .namespaces=${namespaces}
                    .entityTypeCatalogRows=${this._templateDetailTypeCatalogRows()}
                    .parentTypeOptions=${this._getParentTypeOptions()}
                    editingTypeId=${this._editingTypeId}
                    ?savingType=${this._savingType}
                    ?showNamespaces=${true}
                    .compactChrome=${true}
                    @draft-changed=${this._onTypeDraftChanged}
                    @schema-rows-changed=${this._onSchemaRowsFromEditor}
                    @namespace-toggled=${this._onNamespaceToggledFromEditor}
                    @cancel=${this._resetTypeDraft}
                    @submit=${this._onUpsertType}
                ></crm-entity-type-editor>
            </div>
        `;
    }
}

customElements.define('crm-templates-page', CRMTemplatesPage);
