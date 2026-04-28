/**
 * CRMSpaceDetailPage — настройки конкретного namespace.
 *
 * Маршрут: `/crm/spaces/:itemId` (parent: `spaces`).
 *
 * UX-аналог `templates-page`, но работает с **instance** namespace и его
 * привязанными типами. Типы — общекомпанийные (`crm/entity_types`),
 * к namespace они привязаны через `entityType.namespace_ids`.
 *
 * Источники данных:
 *   - useResource('crm/namespaces')         — метаданные namespace (описание и др.).
 *   - useOp('crm/namespace_editability')    — статистика, locked_type_ids и
 *     current_allowed_type_ids (канон для карточек и счётчика «разрешено»).
 *   - useResource('crm/entity_types', { autoload: true }) — все типы компании.
 *   - useOp('crm/entity_type_update')       — PUT /entity-types/{id}.
 *   - useOp('crm/template_schema_options')  — опции SchemaFieldBuilder
 *                                             (общие для шаблонов и типов).
 *   - useOp('crm/namespace_update')         — body.allowed_type_ids: сервис синхронизирует
 *     entity_type.namespace_ids; после успеха перезапускается editability.
 *
 * Поток:
 *   - На load: get(namespace), editability(namespace), load entity_types.
 *   - _allowedTypeIds заполняется из ответа editability (current_allowed_type_ids).
 *   - Toggle типа: добавить/удалить из allowed_type_ids → namespace_update.
 *   - Стадии канбана задач: панель под сеткой «метаданные + типы», на всю ширину.
 *   - Edit / create типа: <crm-entity-type-editor> в той же правой колонке вместо
 *     сетки карточек; кнопка «назад» возвращает к сетке.
 *   - Create нового типа: entityTypesResource.create + после CREATED —
 *     если ещё не в allowed → namespace_update с расширенным списком.
 */

import { html, css } from 'lit';
import { PlatformPage } from '@platform/lib/base/PlatformPage.js';
import '@platform/lib/components/layout/page-header.js';
import '@platform/lib/components/glass-spinner.js';
import '@platform/lib/components/platform-breadcrumbs.js';
import '@platform/lib/components/platform-icon.js';
import '@platform/lib/components/platform-button.js';
import '@platform/lib/components/platform-palette-color-picker.js';
import { platformConfirm } from '@platform/lib/components/platform-confirm-modal.js';

import '../components/entity-type-editor.js';
import '../components/namespace-note-defaults-fields.js';
import {
    normalizeDefaultNoteVoiceMode,
    parseNoteVoiceDefaultsFromCrmSettings,
} from '../utils/namespace-crm-note-defaults.js';
import {
    buildDefaultSidebarNav,
    sidebarNavTreeToApiPayload,
} from '../utils/build-default-sidebar-nav.js';
import {
    normalizeSchemaRows,
    buildSchemaFromRows,
} from '../components/schema-field-builder.js';
import { entityTypeNoteSubtreeLocked } from '../utils/entity-type-note-subtree-lock.js';

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

export class CRMSpaceDetailPage extends PlatformPage {
    static i18nNamespace = 'crm';

    static properties = {
        itemId: { type: String },
        _description: { state: true },
        _defaultNoteVoiceMode: { state: true },
        _showNoteVoiceUi: { state: true },
        _allowedTypeIds: { state: true },
        _typeDraft: { state: true },
        _editingTypeId: { state: true },
        _typeFormOpen: { state: true },
        _schemaOptions: { state: true },
        _savingMeta: { state: true },
        _savingAllowed: { state: true },
        _savingType: { state: true },
        _creatingType: { state: true },
        _sidebarMenuBusy: { state: true },
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
            .breadcrumbs-wrap {
                flex-shrink: 0;
                padding: 0 var(--space-4);
                margin-top: var(--space-2);
                margin-bottom: var(--space-2);
            }
            .header-wrap { flex-shrink: 0; padding: 0 var(--space-4); }
            .scroll {
                flex: 1;
                min-height: 0;
                overflow-y: auto;
                padding: var(--space-2) var(--space-4) var(--space-4);
            }
            .space-detail-stack {
                display: flex;
                flex-direction: column;
                gap: var(--space-3);
                min-width: 0;
            }
            .layout {
                display: grid;
                gap: var(--space-3);
                grid-template-columns: minmax(280px, 360px) minmax(0, 1fr);
                align-items: start;
            }
            @media (max-width: 980px) { .layout { grid-template-columns: 1fr; } }

            .space-detail-left-col {
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
                font-weight: 600;
                color: var(--text-primary);
            }
            .field { display: grid; gap: var(--space-1); }
            .field-label {
                font-size: var(--text-xs);
                color: var(--text-tertiary);
                text-transform: uppercase;
                letter-spacing: 0.04em;
            }
            .input, .textarea {
                width: 100%;
                box-sizing: border-box;
                padding: var(--space-2) var(--space-3);
                border: 1px solid var(--crm-stroke);
                border-radius: var(--radius-md);
                background: var(--crm-surface);
                color: var(--text-primary);
                font-size: var(--text-sm);
            }
            .textarea { min-height: 76px; resize: vertical; }

            .meta {
                display: grid;
                gap: var(--space-2);
                padding: var(--space-3);
                border: 1px solid var(--crm-stroke);
                border-radius: var(--radius-md);
                background: var(--crm-surface-muted);
            }
            .meta-row {
                display: flex;
                justify-content: space-between;
                align-items: center;
                gap: var(--space-2);
                font-size: var(--text-xs);
                color: var(--text-secondary);
            }
            .meta-row strong { color: var(--text-primary); font-weight: 600; }

            .types-grid {
                display: grid;
                gap: var(--space-2);
                grid-template-columns: repeat(auto-fit, minmax(min(100%, 260px), 1fr));
            }
            .type-card {
                display: grid;
                gap: var(--space-1);
                padding: var(--space-3);
                border: 1px solid var(--crm-stroke);
                border-radius: var(--radius-md);
                background: var(--crm-surface);
                min-width: 0;
            }
            .type-card.locked { background: var(--glass-tint-subtle); }
            .type-card.allowed { border-color: var(--accent); }
            .type-title {
                display: flex;
                align-items: center;
                gap: var(--space-2);
                font-weight: 600;
                color: var(--text-primary);
            }
            .hint { color: var(--text-tertiary); font-size: var(--text-xs); }
            .hint.mono { font-family: var(--font-mono); }

            .actions-row {
                display: flex;
                flex-wrap: wrap;
                gap: var(--space-2);
            }
            .btn {
                display: inline-flex;
                align-items: center;
                gap: 6px;
                padding: var(--space-2) var(--space-3);
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
            .btn-danger {
                background: transparent;
                color: var(--color-danger, #ef4444);
                border-color: var(--color-danger, #ef4444);
            }
            .btn-danger:hover:not(:disabled) {
                background: var(--color-danger, #ef4444);
                color: white;
            }
            .btn:disabled { opacity: 0.5; cursor: not-allowed; }

            .center {
                display: flex;
                flex-direction: column;
                align-items: center;
                justify-content: center;
                gap: var(--space-3);
                padding: var(--space-6);
                color: var(--text-tertiary);
            }

            .empty {
                padding: var(--space-3);
                text-align: center;
                color: var(--text-tertiary);
                font-size: var(--text-sm);
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
        this.itemId = '';
        this._description = '';
        this._defaultNoteVoiceMode = 'self';
        this._showNoteVoiceUi = true;
        this._allowedTypeIds = [];
        this._typeDraft = makeTypeDraft();
        this._editingTypeId = '';
        this._typeFormOpen = false;
        this._schemaOptions = null;
        this._savingMeta = false;
        this._savingAllowed = false;
        this._savingType = false;
        this._creatingType = false;
        this._sidebarMenuBusy = false;
        this._taskBoardDraft = null;
        this._taskBoardSaveBusy = false;
        this._lastRequestedId = '';

        this._namespaces = this.useResource('crm/namespaces');
        this._editabilityOp = this.useOp('crm/namespace_editability');
        this._namespaceUpdateOp = this.useOp('crm/namespace_update');
        this._taskBoardEditorStateOp = this.useOp('crm/task_board_editor_state');
        this._entityTypes = this.useResource('crm/entity_types', { autoload: true });
        this._entityTypeUpdateOp = this.useOp('crm/entity_type_update');
        this._schemaOptionsOp = this.useOp('crm/template_schema_options');
    }

    connectedCallback() {
        super.connectedCallback();
        this._schemaOptionsOp.run(null);
        this.useEvent(this._schemaOptionsOp.op.events.SUCCEEDED, (event) => {
            const result = event && event.payload && event.payload.result;
            if (!result || typeof result !== 'object') return;
            this._schemaOptions = result;
        });
        this.useEvent(this._namespaces.resource.events.ITEM_LOADED, (event) => {
            const item = event && event.payload && event.payload.item;
            if (!item || item.name !== this.itemId) return;
            this._hydrateFromNamespace(item);
        });
        this.useEvent(this._namespaces.resource.events.LIST_LOADED, () => {
            const item = this._namespaces.byId[this.itemId];
            if (item !== undefined) this._hydrateFromNamespace(item);
        });
        this.useEvent(this._editabilityOp.op.events.SUCCEEDED, (event) => {
            const result = event && event.payload && event.payload.result;
            if (!result || typeof result !== 'object') return;
            if (result.namespace !== this.itemId) return;
            const ids = result.current_allowed_type_ids;
            if (!Array.isArray(ids)) {
                throw new Error('namespace_editability: current_allowed_type_ids must be an array');
            }
            this._allowedTypeIds = ids.filter((id) => typeof id === 'string' && id.length > 0);
            this._loadTaskBoardEditorState();
        });
        this.useEvent(this._taskBoardEditorStateOp.op.events.SUCCEEDED, (event) => {
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
        this.useEvent(this._taskBoardEditorStateOp.op.events.FAILED, (event) => {
            this._taskBoardDraft = null;
            const msg = event.payload && typeof event.payload.message === 'string' ? event.payload.message : '';
            this.toast('crm:space_detail_page.task_board_load_failed', { type: 'error', vars: { message: msg } });
        });
        this.useEvent(this._namespaceUpdateOp.op.events.SUCCEEDED, (event) => {
            this._savingMeta = false;
            this._savingAllowed = false;
            this._sidebarMenuBusy = false;
            this._taskBoardSaveBusy = false;
            const result = event && event.payload && event.payload.result;
            if (result && result.name === this.itemId) {
                this._hydrateFromNamespace(result);
            }
            this._namespaces.load();
            this._editabilityOp.run({ name: this.itemId });
            this._loadTaskBoardEditorState();
        });
        this.useEvent(this._namespaceUpdateOp.op.events.FAILED, () => {
            this._savingMeta = false;
            this._savingAllowed = false;
            this._sidebarMenuBusy = false;
            this._taskBoardSaveBusy = false;
        });
        this.useEvent(this._entityTypeUpdateOp.op.events.SUCCEEDED, () => {
            this._savingType = false;
            this._typeFormOpen = false;
            this._typeDraft = makeTypeDraft();
            this._editingTypeId = '';
            this._entityTypes.load(null);
        });
        this.useEvent(this._entityTypeUpdateOp.op.events.FAILED, () => {
            this._savingType = false;
        });
        this.useEvent(this._entityTypes.resource.events.CREATED, (event) => {
            this._creatingType = false;
            this._typeFormOpen = false;
            this._typeDraft = makeTypeDraft();
            this._editingTypeId = '';
            const item = event && event.payload && event.payload.item;
            if (!item || typeof item.type_id !== 'string') return;
            const next = this._allowedTypeIds.includes(item.type_id)
                ? this._allowedTypeIds
                : [...this._allowedTypeIds, item.type_id];
            this._allowedTypeIds = next;
            this._namespaceUpdateOp.run({
                name: this.itemId,
                body: { allowed_type_ids: next },
            });
        });
        this.useEvent(this._entityTypes.resource.events.CREATE_FAILED, () => {
            this._creatingType = false;
        });
    }

    willUpdate(changed) {
        if (changed.has('itemId')) {
            if (
                typeof this.itemId === 'string'
                && this.itemId.length > 0
                && this._lastRequestedId.length > 0
                && this._lastRequestedId !== this.itemId
            ) {
                this._typeFormOpen = false;
                this._typeDraft = makeTypeDraft();
                this._editingTypeId = '';
            }
        }
        if (!changed.has('itemId')) return;
        if (typeof this.itemId !== 'string' || this.itemId.length === 0) return;
        if (this._lastRequestedId === this.itemId) return;
        this._lastRequestedId = this.itemId;
        this._allowedTypeIds = [];
        this._taskBoardDraft = null;
        this._namespaces.get(this.itemId);
        this._editabilityOp.run({ name: this.itemId });
    }

    _namespace() {
        const item = this._namespaces.byId[this.itemId];
        return item === undefined ? null : item;
    }

    _hydrateFromNamespace(item) {
        this._description = typeof item.description === 'string' ? item.description : '';
        const cs =
            item.crm_settings !== undefined
            && item.crm_settings !== null
            && typeof item.crm_settings === 'object'
                ? item.crm_settings
                : null;
        const parsed = parseNoteVoiceDefaultsFromCrmSettings(cs);
        this._defaultNoteVoiceMode = parsed.defaultNoteVoiceMode;
        this._showNoteVoiceUi = parsed.showNoteVoiceUi;
    }

    _loadTaskBoardEditorState() {
        if (typeof this.itemId !== 'string' || this.itemId.length === 0) return;
        this._taskBoardEditorStateOp.run({ namespace_name: this.itemId });
    }

    _taskBoardStageIdValid(raw) {
        if (typeof raw !== 'string') return false;
        return /^[a-z][a-z0-9_]*$/.test(raw.trim());
    }

    _onSaveTaskBoard() {
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
        this._taskBoardSaveBusy = true;
        this._namespaceUpdateOp.run({
            name: this.itemId,
            body: { crm_settings: { pipeline_stage_presets: presets } },
        });
    }

    _setTaskBoardDraft(next) {
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
        this._setTaskBoardDraft(next);
    }

    _addTaskBoardStage(boardIdx) {
        const draft = this._taskBoardDraft;
        if (!Array.isArray(draft) || !draft[boardIdx]) return;
        const next = draft.map((row, bi) => {
            if (bi !== boardIdx) return row;
            return { ...row, stages: [...row.stages, { id: '', label: '', color: '' }] };
        });
        this._setTaskBoardDraft(next);
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
        this._setTaskBoardDraft(next);
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
        this._setTaskBoardDraft(next);
    }

    _onDescriptionInput(e) { this._description = e.target.value; }

    _onNoteDefaultVoiceFromChild(e) {
        const d = e.detail;
        if (d === undefined || d === null || typeof d !== 'object' || typeof d.value !== 'string') {
            return;
        }
        const v = d.value;
        if (v === 'none' || v === 'last' || v === 'self') {
            this._defaultNoteVoiceMode = v;
        }
    }

    _onNoteVoiceShowUiFromChild(e) {
        const d = e.detail;
        if (d === undefined || d === null || typeof d !== 'object' || typeof d.value !== 'boolean') {
            return;
        }
        this._showNoteVoiceUi = d.value;
    }

    _onSaveMeta() {
        this._savingMeta = true;
        this._namespaceUpdateOp.run({
            name: this.itemId,
            body: {
                description: this._description.trim().length > 0 ? this._description.trim() : null,
                crm_settings: {
                    default_note_voice: normalizeDefaultNoteVoiceMode(this._defaultNoteVoiceMode),
                    show_note_voice_ui: this._showNoteVoiceUi === true,
                },
            },
        });
    }

    _onSidebarNavReset() {
        this._sidebarMenuBusy = true;
        this._namespaceUpdateOp.run({
            name: this.itemId,
            body: { crm_settings: { sidebar_navigation: null } },
        });
    }

    _onSidebarNavSnapshot() {
        const items = Array.isArray(this._entityTypes.items) ? this._entityTypes.items : [];
        const tree = buildDefaultSidebarNav({
            allowedTypeIds: this._allowedTypeIds,
            entityTypes: items,
            labels: {
                groupNotes: this.t('sidebar.nav_group_notes'),
                groupTasks: this.t('sidebar.nav_group_tasks'),
                groupEntities: this.t('sidebar.nav_group_entities'),
                allNotes: this.t('sidebar.nav_all_notes'),
                allTasks: this.t('sidebar.nav_all_tasks'),
                allEntities: this.t('sidebar.nav_all_entities'),
                graph: this.t('sidebar.nav.graph'),
            },
        });
        const payload = sidebarNavTreeToApiPayload(tree);
        this._sidebarMenuBusy = true;
        this._namespaceUpdateOp.run({
            name: this.itemId,
            body: { crm_settings: { sidebar_navigation: payload } },
        });
    }

    _onToggleType(typeId, allowed) {
        if (typeof typeId !== 'string' || typeId.length === 0) return;
        const next = allowed
            ? [...new Set([...this._allowedTypeIds, typeId])]
            : this._allowedTypeIds.filter((id) => id !== typeId);
        this._allowedTypeIds = next;
        this._savingAllowed = true;
        this._namespaceUpdateOp.run({
            name: this.itemId,
            body: { allowed_type_ids: next },
        });
    }

    _openNewTypeForm() {
        this._editingTypeId = '';
        this._typeDraft = makeTypeDraft();
        this._typeFormOpen = true;
    }

    _spaceEntityTypeCatalogRows() {
        const items = Array.isArray(this._entityTypes.items) ? this._entityTypes.items : [];
        return items.map((row) => ({
            type_id: row.type_id,
            parent_type_id:
                typeof row.parent_type_id === 'string' && row.parent_type_id.length > 0
                    ? row.parent_type_id
                    : '',
        }));
    }

    _editType(item) {
        if (!item || typeof item.type_id !== 'string') {
            throw new Error('CRMSpaceDetailPage._editType: item.type_id required');
        }
        this._editingTypeId = item.type_id;
        this._typeFormOpen = true;
        const catalogRows = this._spaceEntityTypeCatalogRows();
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

    _onResetTypeDraft() {
        this._typeFormOpen = false;
        this._typeDraft = makeTypeDraft();
        this._editingTypeId = '';
    }

    _onTypeDraftChanged(event) {
        const next = event && event.detail && event.detail.typeDraft;
        if (!next) return;
        this._typeDraft = next;
    }

    _onSchemaRowsChanged(event) {
        const detail = event && event.detail;
        if (!detail || (detail.section !== 'required_fields_rows' && detail.section !== 'optional_fields_rows')) return;
        this._typeDraft = { ...this._typeDraft, [detail.section]: detail.rows };
    }

    _onSubmitType() {
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
        const noteLocked = entityTypeNoteSubtreeLocked(this._typeDraft, this._spaceEntityTypeCatalogRows());
        const body = {
            parent_type_id: this._typeDraft.parent_type_id.trim() || null,
            name,
            description: this._typeDraft.description.trim() || null,
            prompt: this._typeDraft.prompt.trim() || null,
            required_fields: requiredFields,
            optional_fields: optionalFields,
            icon: this._typeDraft.icon.trim() || null,
            color: this._typeDraft.color.trim() || null,
            is_event: this._typeDraft.is_event === true,
            check_duplicates: this._typeDraft.check_duplicates !== false,
            is_context_anchor: noteLocked ? false : this._typeDraft.is_context_anchor === true,
            is_voice_target: noteLocked ? false : this._typeDraft.is_voice_target === true,
            weight_coefficient: Number.parseFloat(this._typeDraft.weight_coefficient || '1') || 1,
        };
        if (this._editingTypeId.length > 0) {
            this._savingType = true;
            this._entityTypeUpdateOp.run({ type_id: this._editingTypeId, body });
            return;
        }
        this._creatingType = true;
        this._entityTypes.create({ type_id: typeId, ...body });
    }

    async _onDeleteEntity(typeId) {
        if (typeof typeId !== 'string' || typeId.length === 0) return;
        const confirmed = await platformConfirm(
            this.t('templates_page.confirm_delete_type_msg', { type_id: typeId }),
            {
                title: this.t('templates_page.confirm_delete_type_title'),
                variant: 'danger',
                confirmText: this.t('templates_page.delete_type'),
                cancelText: this.t('templates_page.btn_cancel'),
            },
        );
        if (!confirmed) return;
        this._onToggleType(typeId, false);
    }

    _getParentTypeOptions() {
        const items = Array.isArray(this._entityTypes.items) ? this._entityTypes.items : [];
        const ids = items
            .map((item) => (typeof item.type_id === 'string' ? item.type_id : null))
            .filter((id) => typeof id === 'string' && id.length > 0);
        return [...new Set(['note', 'task', ...ids])];
    }

    _typeIsLocked(typeId) {
        const result = this._editabilityOp.lastResult;
        if (!result || !Array.isArray(result.locked_type_ids)) return false;
        return result.locked_type_ids.includes(typeId);
    }

    render() {
        if (typeof this.itemId !== 'string' || this.itemId.length === 0) {
            return html`
                <div class="center">
                    <platform-icon name="info" size="32"></platform-icon>
                    <p>${this.t('space_detail_page.no_id')}</p>
                </div>
            `;
        }
        const ns = this._namespace();
        if (ns === null) {
            return html`<div class="center"><glass-spinner size="lg"></glass-spinner></div>`;
        }

        return html`
            <div class="breadcrumbs-wrap">
                <platform-breadcrumbs current-label=${ns.name}></platform-breadcrumbs>
            </div>
            <div class="header-wrap">
                <page-header
                    title=${ns.name}
                    subtitle=${this.t('space_detail_page.subtitle')}
                >
                    <platform-button
                        slot="actions"
                        variant="secondary"
                        type="button"
                        @click=${() => this.navigate('space_integrations', { itemId: this.itemId })}
                    >
                        <platform-icon name="integration" size="18"></platform-icon>
                        ${this.t('space_detail_page.link_integrations')}
                    </platform-button>
                </page-header>
            </div>
            <div class="scroll">
                <div class="space-detail-stack">
                    <div class="layout">
                        <div class="space-detail-left-col">
                            ${this._renderLeftPanel(ns)}
                            ${this._renderSidebarMenuPanel(ns)}
                        </div>
                        ${this._renderRightPanel()}
                    </div>
                    ${this._renderTaskBoardPanel()}
                </div>
            </div>
        `;
    }

    _renderLeftPanel(ns) {
        const editability = this._editabilityOp.lastResult;
        return html`
            <div class="panel">
                <div class="panel-header">
                    <span class="panel-title">
                        <platform-icon name="folder" size="18"></platform-icon>
                        ${this.t('space_detail_page.meta_section')}
                    </span>
                </div>

                <div class="field">
                    <label class="field-label">${this.t('namespace_modal.label_name')}</label>
                    <div class="hint mono">${ns.name}</div>
                </div>

                <div class="field">
                    <label class="field-label">${this.t('namespace_modal.label_description')}</label>
                    <textarea
                        class="textarea"
                        placeholder=${this.t('namespace_modal.description_placeholder')}
                        .value=${this._description}
                        @input=${this._onDescriptionInput}
                    ></textarea>
                </div>

                <crm-namespace-note-defaults-fields
                    .defaultNoteVoiceMode=${this._defaultNoteVoiceMode}
                    .showNoteVoiceUi=${this._showNoteVoiceUi}
                    ?disabled=${this._savingMeta}
                    @default-note-voice-change=${this._onNoteDefaultVoiceFromChild}
                    @show-note-voice-ui-change=${this._onNoteVoiceShowUiFromChild}
                ></crm-namespace-note-defaults-fields>

                <div class="actions-row">
                    <button
                        class="btn btn-primary"
                        type="button"
                        ?disabled=${this._savingMeta}
                        @click=${this._onSaveMeta}
                    >
                        ${this._savingMeta
                            ? this.t('namespace_modal.action_saving')
                            : this.t('namespace_modal.action_save')}
                    </button>
                </div>

                ${editability !== null ? html`
                    <div class="meta">
                        <div class="meta-row">
                            <span>${this.t('namespace_modal.entity_count')}</span>
                            <strong>${editability.entity_count}</strong>
                        </div>
                        <div class="meta-row">
                            <span>${this.t('namespace_modal.used_types')}</span>
                            <strong>${Array.isArray(editability.used_type_ids) ? editability.used_type_ids.length : 0}</strong>
                        </div>
                        <div class="meta-row">
                            <span>${this.t('namespace_modal.can_update_types')}</span>
                            <strong>${editability.can_update_allowed_types
                                ? this.t('namespace_modal.yes')
                                : this.t('namespace_modal.no')}</strong>
                        </div>
                    </div>
                ` : ''}
            </div>
        `;
    }

    _renderSidebarMenuPanel(ns) {
        const crm = ns && ns.crm_settings && typeof ns.crm_settings === 'object' ? ns.crm_settings : null;
        const custom = crm !== null
            && Array.isArray(crm.sidebar_navigation)
            && crm.sidebar_navigation.length > 0;
        const modeHint = custom
            ? this.t('space_detail_page.sidebar_menu_mode_custom')
            : this.t('space_detail_page.sidebar_menu_mode_derived');
        return html`
            <div class="panel">
                <div class="panel-header">
                    <span class="panel-title">
                        <platform-icon name="menu" size="18"></platform-icon>
                        ${this.t('space_detail_page.sidebar_menu_section')}
                    </span>
                </div>
                <p class="hint">${this.t('space_detail_page.sidebar_menu_hint')}</p>
                <p class="hint mono">${modeHint}</p>
                <div class="actions-row">
                    <button
                        class="btn btn-soft"
                        type="button"
                        ?disabled=${this._sidebarMenuBusy}
                        @click=${this._onSidebarNavSnapshot}
                    >
                        ${this.t('space_detail_page.sidebar_menu_snapshot')}
                    </button>
                    <button
                        class="btn btn-danger"
                        type="button"
                        ?disabled=${this._sidebarMenuBusy || !custom}
                        @click=${this._onSidebarNavReset}
                    >
                        ${this.t('space_detail_page.sidebar_menu_reset')}
                    </button>
                </div>
            </div>
        `;
    }

    _renderTaskBoardPanel() {
        const ed = this._editabilityOp.lastResult;
        if (!ed || typeof ed.namespace !== 'string' || ed.namespace !== this.itemId) {
            return html`
                <div class="panel">
                    <div class="panel-header">
                        <span class="panel-title">
                            <platform-icon name="layers" size="18"></platform-icon>
                            ${this.t('space_detail_page.task_board_section')}
                        </span>
                    </div>
                    <div class="center" style="padding: var(--space-3);">
                        <glass-spinner size="md"></glass-spinner>
                    </div>
                </div>
            `;
        }
        const tbOp = this._taskBoardEditorStateOp;
        const draft = this._taskBoardDraft;
        return html`
            <div class="panel">
                <div class="panel-header">
                    <span class="panel-title">
                        <platform-icon name="layers" size="18"></platform-icon>
                        ${this.t('space_detail_page.task_board_section')}
                    </span>
                </div>
                <p class="hint">${this.t('space_detail_page.task_board_hint')}</p>
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
                            <button class="btn btn-soft" type="button" @click=${this._loadTaskBoardEditorState}>
                                ${this.t('space_detail_page.task_board_retry')}
                            </button>
                        </div>
                    `
                    : ''}
                ${Array.isArray(draft) && draft.length === 0
                    ? html`<p class="hint">${this.t('space_detail_page.task_board_empty')}</p>`
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
                                ${board.stages.map((st, si) => html`
                                    <div class="stage-row">
                                        <input
                                            class="input"
                                            type="text"
                                            autocomplete="off"
                                            spellcheck="false"
                                            placeholder=${this.t('space_detail_page.task_board_stage_id_ph')}
                                            .value=${st.id}
                                            @input=${(e) => this._onTaskBoardStageField(bi, si, 'id', e.target.value)}
                                        />
                                        <input
                                            class="input"
                                            type="text"
                                            autocomplete="off"
                                            placeholder=${this.t('space_detail_page.task_board_stage_label_ph')}
                                            .value=${st.label}
                                            @input=${(e) => this._onTaskBoardStageField(bi, si, 'label', e.target.value)}
                                        />
                                        <platform-palette-color-picker
                                            class="stage-color-picker"
                                            allow-clear
                                            .value=${st.color}
                                            ?disabled=${this._taskBoardSaveBusy
                                                || this._savingMeta
                                                || this._savingAllowed
                                                || this._sidebarMenuBusy}
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
                                    || this._savingAllowed
                                    || this._sidebarMenuBusy}
                                @click=${this._onSaveTaskBoard}
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

    _renderRightPanel() {
        const items = Array.isArray(this._entityTypes.items) ? this._entityTypes.items : [];
        if (this._typeFormOpen) {
            return this._renderTypeFormPanel();
        }
        return this._renderTypesListPanel(items);
    }

    _renderTypesListPanel(allTypes) {
        return html`
            <div class="panel">
                <div class="panel-header">
                    <span class="panel-title">
                        <platform-icon name="list" size="18"></platform-icon>
                        ${this.t('space_detail_page.types_section')}
                    </span>
                    <span class="actions-row" style="flex-wrap: nowrap; align-items: center;">
                        <span class="hint">
                            ${this.t('space_detail_page.allowed_count', {
                                allowed: String(this._allowedTypeIds.length),
                                total: String(allTypes.length),
                            })}
                        </span>
                        <button
                            class="btn btn-soft"
                            type="button"
                            @click=${this._openNewTypeForm}
                        >
                            ${this.t('space_detail_page.action_new_type')}
                        </button>
                    </span>
                </div>
                ${allTypes.length === 0
                    ? html`<div class="empty">${this.t('space_detail_page.no_types')}</div>`
                    : html`
                        <div class="types-grid">
                            ${allTypes.map((item) => this._renderTypeCard(item))}
                        </div>
                    `}
            </div>
        `;
    }

    _renderTypeCard(item) {
        const allowed = this._allowedTypeIds.includes(item.type_id);
        const locked = this._typeIsLocked(item.type_id);
        const classes = ['type-card'];
        if (allowed) classes.push('allowed');
        if (locked) classes.push('locked');
        return html`
            <div class=${classes.join(' ')}>
                <div class="type-title">
                    <platform-icon name=${typeof item.icon === 'string' && item.icon.length > 0 ? item.icon : 'circle'} size="16"></platform-icon>
                    <span>${item.name}</span>
                </div>
                <div class="hint mono">${item.type_id}</div>
                ${item.description ? html`<div class="hint">${item.description}</div>` : ''}
                <div class="actions-row">
                    <button
                        class="btn ${allowed ? 'btn-soft' : 'btn-primary'}"
                        type="button"
                        ?disabled=${this._savingAllowed || (locked && allowed)}
                        @click=${() => this._onToggleType(item.type_id, !allowed)}
                    >
                        ${allowed
                            ? this.t('space_detail_page.action_disallow')
                            : this.t('space_detail_page.action_allow')}
                    </button>
                    <button
                        class="btn btn-soft"
                        type="button"
                        @click=${() => this._editType(item)}
                    >
                        ${this.t('templates_page.edit_type')}
                    </button>
                    ${allowed && !locked ? html`
                        <button
                            class="btn btn-danger"
                            type="button"
                            @click=${() => this._onDeleteEntity(item.type_id)}
                        >
                            ${this.t('space_detail_page.action_remove')}
                        </button>
                    ` : ''}
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
                            title=${this.t('space_detail_page.back_to_types')}
                            aria-label=${this.t('space_detail_page.back_to_types')}
                            @click=${this._onResetTypeDraft}
                        >
                            <platform-icon name="chevron-left" size="18"></platform-icon>
                        </button>
                        <platform-icon name="list" size="18"></platform-icon>
                        ${this.t('space_detail_page.types_section')}
                    </span>
                    <span class="actions-row" style="flex-wrap: nowrap; align-items: center;">
                        <button
                            class="btn btn-soft"
                            type="button"
                            @click=${this._onResetTypeDraft}
                        >
                            ${this.t('templates_page.btn_cancel')}
                        </button>
                    </span>
                </div>
                <crm-entity-type-editor
                    .typeDraft=${this._typeDraft}
                    .schemaOptions=${this._schemaOptions}
                    .namespaces=${namespaces}
                    .entityTypeCatalogRows=${this._spaceEntityTypeCatalogRows()}
                    .parentTypeOptions=${this._getParentTypeOptions()}
                    editingTypeId=${this._editingTypeId}
                    ?savingType=${this._savingType || this._creatingType}
                    ?showNamespaces=${false}
                    .compactChrome=${true}
                    @draft-changed=${this._onTypeDraftChanged}
                    @schema-rows-changed=${this._onSchemaRowsChanged}
                    @cancel=${this._onResetTypeDraft}
                    @submit=${this._onSubmitType}
                ></crm-entity-type-editor>
            </div>
        `;
    }
}

customElements.define('crm-space-detail-page', CRMSpaceDetailPage);
