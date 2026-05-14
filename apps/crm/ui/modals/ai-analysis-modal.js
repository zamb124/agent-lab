/**
 * CRMAiAnalysisModal — модалка AI-анализа заметки.
 *
 * Props:
 *   - noteId: string — обязательный, id заметки.
 *
 * Поток:
 *   1. На open подгружаем заметку через `entitiesResource.get(noteId)`.
 *      Из `entity.attributes.ai_analysis_draft` достаём текущий черновик
 *      (note + entities + relationships + draft_version).
 *   2. Подписка на WS `crm/note/updated` для noteId — перезагрузка entity
 *      (когда воркер докинул свежий draft или применил его).
 *   3. Действия:
 *      - «Запустить анализ» — `noteAnalyzeStartOp.run({ note_id, mode: 'analyze' })`.
 *      - «Применить» — `noteAnalyzeStartOp.run({ note_id, mode: 'apply' })`.
 *      - per-row «удалить» — кладём draft_entity_id / draft_relationship_id
 *        в локальные _pendingRemoveEntityIds / _pendingRemoveRelIds; локально
 *        добавленные строки до сохранения убираются из _pendingAddEntities /
 *        _pendingAddRelationships.
 *      - «Сохранить изменения» — `noteAnalysisDraftSaveOp.run({ note_id, draft })`,
 *        где draft.expected_version берётся из текущего draft; patch_entities —
 *        правки атрибутов, entity_type и entity_subtype; add_entities /
 *        add_relationships — новые строки черновика до первого сохранения.
 *      - Ошибка применения черновика — `ai_analysis_last_error` +
 *        `ai_analysis_apply_failures`; баннер в модалке; AI-починка —
 *        `noteAnalysisDraftRepairOp` (TaskIQ + flow ветка `draft_repair`); сброс ошибки
 *        через `noteAnalysisErrorDismissOp`; удалить черновик — noteAnalysisDraftDiscardOp.
 *      - «Запустить заново» — повторный analyze поверх той же заметки.
 *   4. Render — двухколоночный layout: левая колонка summary + предложенные задачи
 *      (быстрое редактирование текста, отметка выполнения, Enter-добавление); правая —
 *      suggested entities/relationships.
 */

import { html, css, nothing } from 'lit';
import { PlatformModal } from '@platform/lib/components/glass-modal.js';
import { registerModalKind } from '@platform/lib/utils/modal-registry.js';
import '@platform/lib/components/platform-icon.js';
import '@platform/lib/components/glass-spinner.js';
import '@platform/lib/components/fields/platform-field.js';
import { platformConfirm } from '@platform/lib/components/platform-confirm-modal.js';

const ENTITIES_NAME = 'crm/entities';
const ENTITY_TYPES_NAME = 'crm/entity_types';
const REL_TYPES_NAME = 'crm/relationship_types';
const ANALYZE_OP = 'crm/note_analyze_start';
const DRAFT_SAVE_OP = 'crm/note_analysis_draft_save';
const DRAFT_DISCARD_OP = 'crm/note_analysis_draft_discard';
const APPLY_ERROR_DISMISS_OP = 'crm/note_analysis_error_dismiss';
const DRAFT_REPAIR_OP = 'crm/note_analysis_draft_repair';

const TASK_TYPE = 'task';
/** Только черновик AI: при apply не попадает в attributes сущности в БД. */
const DRAFT_TASK_COMPLETED_ATTR = 'platform_ai_draft_task_completed';
const CUSTOM_ATTR_FIELD_TYPES = Object.freeze([
    'string',
    'text',
    'number',
    'integer',
    'boolean',
    'date',
    'datetime',
    'enum',
    'array',
    'object',
]);

function _isObject(value) {
    return typeof value === 'object' && value !== null;
}

function _readDraft(entity) {
    if (entity === null) return null;
    const attrs = entity.attributes;
    if (!_isObject(attrs)) return null;
    const draft = attrs.ai_analysis_draft;
    if (!_isObject(draft)) return null;
    if (typeof draft.draft_version !== 'number') return null;
    return draft;
}

function _readApplyFailures(entity) {
    if (entity === null) return [];
    const attrs = entity.attributes;
    if (!_isObject(attrs)) return [];
    const raw = attrs.ai_analysis_apply_failures;
    if (!Array.isArray(raw)) return [];
    return raw.filter((x) => _isObject(x) && typeof x.draft_entity_id === 'string');
}

function _analysisLastErrorText(entity) {
    if (entity === null) return '';
    const attrs = entity.attributes;
    if (!_isObject(attrs)) return '';
    const msg = attrs.ai_analysis_last_error;
    return typeof msg === 'string' && msg.trim().length > 0 ? msg.trim() : '';
}

function _isApplied(entity) {
    if (entity === null) return false;
    const attrs = entity.attributes;
    if (!_isObject(attrs)) return false;
    return typeof attrs.ai_analysis_applied_at === 'string'
        && attrs.ai_analysis_applied_at.length > 0
        && _readDraft(entity) === null;
}

export class CRMAiAnalysisModal extends PlatformModal {
    static modalKind = 'crm.ai_analysis';
    static i18nNamespace = 'crm';

    static properties = {
        ...PlatformModal.properties,
        noteId: { type: String },
        _pendingRemoveEntityIds: { state: true },
        _pendingRemoveRelIds: { state: true },
        _attrsExpandedIds: { state: true },
        _saveError: { state: true },
        _pendingAttrPatches: { state: true },
        _attrValidationErrorsById: { state: true },
        _attrAddUiById: { state: true },
        _customAttrTypesById: { state: true },
        _pendingKindPatches: { state: true },
        _kindUiById: { state: true },
        _entityTypesNs: { state: true },
        _pendingAddEntities: { state: true },
        _pendingAddRelationships: { state: true },
        _newEntityType: { state: true },
        _newEntitySubtype: { state: true },
        _newEntityName: { state: true },
        _newRelSource: { state: true },
        _newRelTarget: { state: true },
        _newRelType: { state: true },
        _pendingNamePatches: { state: true },
        _newTaskTitle: { state: true },
        _showDraftEntityComposer: { state: true },
        _showDraftRelComposer: { state: true },
    };

    static styles = [
        ...PlatformModal.styles,
        css`
            :host { --modal-max-width: 1240px; }

            .modal-title-gradient {
                background: var(--crm-main-gradient);
                -webkit-background-clip: text;
                background-clip: text;
                color: transparent;
                font-weight: 700;
            }

            .body {
                display: grid;
                grid-template-columns: 1fr 1fr;
                gap: var(--space-4);
                min-height: 480px;
            }

            .apply-error-banner {
                grid-column: 1 / -1;
                display: flex;
                align-items: flex-start;
                gap: var(--space-3);
                padding: var(--space-3);
                border: 1px solid var(--error);
                border-radius: var(--radius-md);
                background: color-mix(in srgb, var(--error) 12%, transparent);
                color: var(--text-primary);
                font-size: var(--text-sm);
            }
            .apply-error-banner .apply-error-body {
                flex: 1;
                min-width: 0;
                display: grid;
                gap: var(--space-2);
            }
            .apply-error-banner .apply-error-title {
                font-weight: 700;
                color: var(--error);
            }
            .apply-error-banner .apply-error-detail {
                margin: 0;
                padding-left: var(--space-4);
                color: var(--text-secondary);
                font-size: var(--text-xs);
                white-space: pre-wrap;
            }
            .apply-error-banner .icon-btn {
                flex-shrink: 0;
            }
            .apply-error-banner .apply-error-actions {
                display: inline-flex;
                align-items: center;
                gap: 4px;
                flex-shrink: 0;
            }

            .item-row.has-apply-error {
                border-color: color-mix(in srgb, var(--error) 55%, var(--crm-stroke));
            }

            .draft-kind-fields {
                margin-top: var(--space-2);
                display: grid;
                grid-template-columns: minmax(0, 1fr);
                gap: var(--space-3);
                min-width: 0;
                width: 100%;
            }
            .draft-kind-fields platform-field {
                width: 100%;
                min-width: 0;
            }

            .attr-fields-editor {
                margin-top: var(--space-2);
                display: grid;
                grid-template-columns: minmax(0, 1fr);
                gap: var(--space-2);
                min-width: 0;
                width: 100%;
            }

            .attr-field-row {
                display: grid;
                grid-template-columns: minmax(0, 1fr);
                gap: var(--space-1);
                min-width: 0;
                width: 100%;
            }
            .attr-field-row.with-action {
                grid-template-columns: minmax(0, 1fr) auto;
                align-items: start;
            }
            .attr-field-row platform-field {
                width: 100%;
                min-width: 0;
            }
            .attr-field-row .icon-btn {
                margin-top: 6px;
            }
            .attr-field-main {
                display: grid;
                gap: var(--space-1);
                min-width: 0;
                width: 100%;
            }
            .attr-field-main.is-required {
                position: relative;
            }
            .attr-required-mark {
                position: absolute;
                top: 8px;
                right: 10px;
                z-index: 1;
                display: inline-flex;
                align-items: center;
                justify-content: center;
                width: 18px;
                height: 18px;
                border-radius: var(--radius-full);
                border: 1px solid color-mix(in srgb, var(--error) 35%, transparent);
                background: color-mix(in srgb, var(--error) 10%, var(--crm-surface));
                color: var(--error);
                font-size: var(--text-sm);
                font-weight: 800;
                line-height: 1;
                pointer-events: none;
            }

            .attr-field-error {
                margin: 0;
                color: var(--error);
                font-size: var(--text-xs);
            }

            .attr-schema-empty {
                color: var(--text-tertiary);
                font-size: var(--text-xs);
                padding: var(--space-2) var(--space-3);
                border: 1px dashed var(--crm-stroke);
                border-radius: var(--radius-md);
                background: var(--crm-surface-muted);
            }

            .attr-add-composer {
                display: grid;
                grid-template-columns: minmax(0, 1fr);
                gap: var(--space-2);
                min-width: 0;
                width: 100%;
                margin-top: var(--space-1);
                padding-top: var(--space-2);
                border-top: 1px dashed var(--crm-stroke);
            }
            .attr-add-composer-title {
                color: var(--text-primary);
                font-size: var(--text-sm);
                font-weight: 600;
            }
            .attr-add-composer-grid {
                display: grid;
                grid-template-columns: minmax(0, 1fr) minmax(120px, 160px);
                gap: var(--space-2);
                min-width: 0;
            }
            .attr-add-composer platform-field {
                width: 100%;
                min-width: 0;
            }
            .attr-add-composer-actions {
                display: flex;
                align-items: center;
                justify-content: flex-end;
                gap: var(--space-2);
                flex-wrap: wrap;
            }

            .btn-inline {
                justify-self: start;
                padding: var(--space-1) var(--space-3);
                border-radius: var(--radius-sm);
                font-size: var(--text-xs);
                font-weight: 500;
                cursor: pointer;
                border: 1px solid var(--crm-stroke);
                background: var(--crm-surface-muted);
                color: var(--text-secondary);
            }
            .btn-inline:hover:not(:disabled) {
                color: var(--text-primary);
                background: var(--crm-surface);
            }

            .modal-header-actions {
                display: inline-flex;
                align-items: center;
                gap: 4px;
            }

            .column {
                display: flex;
                flex-direction: column;
                gap: var(--space-3);
                min-height: 0;
            }

            .block {
                border: 1px solid var(--crm-stroke);
                border-radius: var(--radius-xl);
                background: var(--crm-surface-muted);
                padding: var(--space-4);
            }

            .block.summary {
                background: var(--crm-selected-bg);
                border-color: var(--crm-selected-stroke);
            }

            .block-title-row {
                display: flex;
                align-items: center;
                justify-content: space-between;
                gap: var(--space-2);
                width: 100%;
                margin-bottom: var(--space-3);
            }
            .block-title-row .block-title {
                margin: 0;
                flex: 1;
                min-width: 0;
            }

            .block-title {
                margin: 0 0 var(--space-3) 0;
                display: inline-flex;
                align-items: center;
                gap: var(--space-2);
                font-size: var(--text-lg);
                font-weight: 700;
                color: var(--text-primary);
            }

            .block-title-row + .hint,
            .block-title-row + .items-list,
            .block-title-row + .tasks-quick-list {
                margin-top: 0;
            }

            .block-title platform-icon {
                color: var(--accent);
            }

            .summary-text {
                margin: 0;
                color: var(--text-primary);
                line-height: 1.45;
                font-size: var(--text-sm);
                white-space: pre-wrap;
            }

            .empty-state {
                display: flex;
                flex-direction: column;
                align-items: center;
                gap: var(--space-3);
                padding: var(--space-6);
                text-align: center;
                color: var(--text-tertiary);
            }
            .empty-state .hint { font-size: var(--text-sm); }

            .loading-state {
                display: flex;
                flex-direction: column;
                align-items: center;
                gap: var(--space-3);
                padding: var(--space-6);
            }

            .applied-banner {
                display: flex;
                align-items: center;
                gap: var(--space-2);
                padding: var(--space-3);
                background: var(--crm-selected-bg);
                border: 1px solid var(--crm-selected-stroke);
                border-radius: var(--radius-md);
                color: var(--text-secondary);
                font-size: var(--text-sm);
            }

            .items-list {
                display: flex;
                flex-direction: column;
                gap: var(--space-2);
                max-height: 360px;
                overflow-y: auto;
            }
            .items-list.entities-list {
                max-height: none;
                overflow: visible;
                position: relative;
                z-index: 2;
            }

            .item-row {
                display: grid;
                grid-template-columns: auto 1fr auto;
                align-items: start;
                gap: var(--space-2);
                padding: var(--space-2) var(--space-3);
                background: var(--crm-surface);
                border: 1px solid var(--crm-stroke);
                border-radius: var(--radius-md);
            }
            .item-row.removed {
                opacity: 0.45;
                text-decoration: line-through;
            }
            .item-row .icon {
                width: 28px;
                height: 28px;
                display: inline-flex;
                align-items: center;
                justify-content: center;
                background: var(--crm-selected-bg);
                color: var(--accent);
                border-radius: var(--radius-sm);
            }
            .item-row .meta {
                display: grid;
                grid-template-columns: minmax(0, 1fr);
                gap: 2px;
                min-width: 0;
                width: 100%;
            }
            .item-row .entity-expanded {
                grid-column: 2 / -1;
                display: grid;
                grid-template-columns: minmax(0, 1fr);
                gap: var(--space-2);
                min-width: 0;
                width: 100%;
            }
            .item-row .name {
                font-weight: 500;
                color: var(--text-primary);
                font-size: var(--text-sm);
                overflow: hidden;
                text-overflow: ellipsis;
                white-space: nowrap;
            }
            .item-row .sub {
                font-size: var(--text-xs);
                color: var(--text-tertiary);
            }
            .item-row .actions {
                display: inline-flex;
                gap: 4px;
                align-items: center;
            }
            .icon-btn {
                width: 24px;
                height: 24px;
                display: inline-flex;
                align-items: center;
                justify-content: center;
                background: transparent;
                border: none;
                color: var(--text-tertiary);
                cursor: pointer;
                border-radius: var(--radius-sm);
            }
            .icon-btn:hover { background: var(--crm-surface-muted); color: var(--text-primary); }

            .badge {
                display: inline-flex;
                align-items: center;
                gap: 4px;
                padding: 2px 8px;
                font-size: var(--text-xs);
                border-radius: var(--radius-full);
                background: var(--crm-selected-bg);
                color: var(--text-secondary);
                white-space: nowrap;
            }
            .badge.dedup-existing { background: rgba(250, 209, 122, 0.34); color: var(--text-primary); }
            .badge.dedup-new { background: rgba(142, 155, 247, 0.34); color: var(--text-primary); }

            .attrs-preview {
                margin-top: var(--space-2);
                padding: var(--space-2);
                background: var(--crm-surface-muted);
                border-radius: var(--radius-sm);
                font-family: var(--font-mono);
                font-size: var(--text-xs);
                color: var(--text-tertiary);
                white-space: pre-wrap;
                max-height: 160px;
                overflow-y: auto;
            }

            .footer-actions {
                display: flex;
                gap: var(--space-2);
                justify-content: space-between;
                align-items: center;
                width: 100%;
            }
            .footer-actions .left,
            .footer-actions .right {
                display: flex;
                gap: var(--space-2);
                align-items: center;
            }
            .submit-error {
                color: var(--error);
                font-size: var(--text-sm);
            }

            .btn {
                padding: var(--space-2) var(--space-4);
                border-radius: var(--radius-md);
                font-size: var(--text-sm);
                font-weight: 500;
                cursor: pointer;
                border: 1px solid transparent;
                background: var(--crm-surface);
                border-color: var(--crm-stroke);
                color: var(--text-secondary);
            }
            .btn:hover:not(:disabled) {
                background: var(--crm-surface-muted);
                color: var(--text-primary);
            }
            .btn-primary {
                background: var(--crm-main-gradient);
                border-color: transparent;
                color: white;
                font-weight: 600;
            }
            .btn-primary:hover:not(:disabled) { filter: brightness(1.08); }
            .btn:disabled { opacity: 0.5; cursor: not-allowed; }

            .draft-composer {
                margin-top: var(--space-3);
                padding-top: var(--space-3);
                border-top: 1px dashed var(--crm-stroke);
                display: grid;
                gap: var(--space-3);
                min-width: 0;
            }
            .draft-composer-actions {
                display: flex;
                gap: var(--space-2);
                justify-content: flex-end;
                flex-wrap: wrap;
            }

            .tasks-quick-list {
                display: flex;
                flex-direction: column;
                gap: var(--space-2);
                max-height: 280px;
                overflow-y: auto;
                margin-bottom: var(--space-3);
            }

            .task-quick-row {
                display: grid;
                grid-template-columns: auto 1fr auto;
                align-items: center;
                gap: var(--space-2);
                padding: var(--space-2) var(--space-3);
                background: var(--crm-surface);
                border: 1px solid var(--crm-stroke);
                border-radius: var(--radius-md);
                min-width: 0;
            }
            .task-quick-row.task-done .task-title-input {
                text-decoration: line-through;
                color: var(--text-tertiary);
            }
            .task-quick-row.has-apply-error {
                border-color: color-mix(in srgb, var(--error) 55%, var(--crm-stroke));
            }
            .task-quick-row.removed {
                opacity: 0.45;
            }
            .task-done-checkbox {
                width: 18px;
                height: 18px;
                flex-shrink: 0;
                accent-color: var(--accent);
                cursor: pointer;
            }
            .task-title-input {
                width: 100%;
                min-width: 0;
                box-sizing: border-box;
                padding: var(--space-1) var(--space-2);
                border: none;
                border-radius: var(--radius-sm);
                background: transparent;
                color: var(--text-primary);
                font-size: var(--text-sm);
                font-family: inherit;
            }
            .task-title-input:focus {
                outline: 1px solid var(--crm-stroke);
                background: var(--crm-surface-muted);
            }
            .task-quick-meta {
                display: flex;
                flex-direction: column;
                align-items: stretch;
                gap: var(--space-1);
                min-width: 0;
            }
            .tasks-quick-add-wrap {
                display: flex;
                align-items: center;
                gap: var(--space-2);
                padding: var(--space-2) var(--space-3);
                border-radius: var(--radius-lg);
                border: 1px solid var(--crm-stroke);
                background: var(--crm-surface);
            }
            .tasks-quick-add-wrap platform-icon {
                flex-shrink: 0;
                color: var(--accent);
            }
            .tasks-quick-add-input {
                flex: 1;
                min-width: 0;
                border: none;
                background: transparent;
                color: var(--text-primary);
                font-size: var(--text-sm);
                font-family: inherit;
            }
            .tasks-quick-add-input:focus {
                outline: none;
            }
            .tasks-quick-add-input::placeholder {
                color: var(--text-tertiary);
            }

            @media (max-width: 1024px) {
                .body { grid-template-columns: 1fr; }
                .attr-add-composer-grid { grid-template-columns: minmax(0, 1fr); }
            }
        `,
    ];

    constructor() {
        super();
        this.size = 'xl';
        this.noteId = '';
        this._pendingRemoveEntityIds = [];
        this._pendingRemoveRelIds = [];
        this._attrsExpandedIds = [];
        this._saveError = '';
        this._pendingAttrPatches = {};
        this._attrValidationErrorsById = {};
        this._attrAddUiById = {};
        this._customAttrTypesById = {};
        this._pendingKindPatches = {};
        this._kindUiById = {};
        this._entityTypesNs = '';
        this._pendingAddEntities = [];
        this._pendingAddRelationships = [];
        this._newEntityType = '';
        this._newEntitySubtype = '';
        this._newEntityName = '';
        this._newRelSource = '';
        this._newRelTarget = '';
        this._newRelType = '';
        this._pendingNamePatches = {};
        this._newTaskTitle = '';
        this._showDraftEntityComposer = false;
        this._showDraftRelComposer = false;
        this._draftRepairPending = false;

        this._entities = this.useResource(ENTITIES_NAME);
        this._entityTypes = this.useResource(ENTITY_TYPES_NAME, { autoload: false });
        this._relationshipTypes = this.useResource(REL_TYPES_NAME, { autoload: true });
        this._analyzeOp = this.useOp(ANALYZE_OP);
        this._draftSaveOp = this.useOp(DRAFT_SAVE_OP);
        this._draftDiscardOp = this.useOp(DRAFT_DISCARD_OP);
        this._applyErrorDismissOp = this.useOp(APPLY_ERROR_DISMISS_OP);
        this._draftRepairOp = this.useOp(DRAFT_REPAIR_OP);
    }

    connectedCallback() {
        super.connectedCallback();
        if (typeof this.noteId !== 'string' || this.noteId.length === 0) {
            throw new Error('CRMAiAnalysisModal: prop "noteId" required');
        }

        this._entities.get(this.noteId);

        this.useEvent('crm/note/updated', (event) => {
            const payload = event && event.payload;
            if (!_isObject(payload)) return;
            if (payload.note_id !== this.noteId && payload.entity_id !== this.noteId) return;
            const dr = payload.draft_repair;
            if (_isObject(dr) && (dr.phase === 'complete' || dr.phase === 'failed')) {
                this._draftRepairPending = false;
            }
            this._entities.get(this.noteId);
        });

        this.useEvent(this._draftRepairOp.op.events.SUCCEEDED, () => {
            this._draftRepairPending = true;
        });
        this.useEvent(this._draftRepairOp.op.events.FAILED, () => {
            this._draftRepairPending = false;
        });

        this.useEvent(this._draftSaveOp.op.events.SUCCEEDED, () => {
            this._pendingRemoveEntityIds = [];
            this._pendingRemoveRelIds = [];
            this._pendingAttrPatches = {};
            this._pendingKindPatches = {};
            this._kindUiById = {};
            this._attrValidationErrorsById = {};
            this._attrAddUiById = {};
            this._customAttrTypesById = {};
            this._pendingAddEntities = [];
            this._pendingAddRelationships = [];
            this._newEntityType = '';
            this._newEntitySubtype = '';
            this._newEntityName = '';
            this._newRelSource = '';
            this._newRelTarget = '';
            this._newRelType = '';
            this._pendingNamePatches = {};
            this._newTaskTitle = '';
            this._showDraftEntityComposer = false;
            this._showDraftRelComposer = false;
            this._saveError = '';
            this._entities.get(this.noteId);
        });
        this.useEvent(this._draftSaveOp.op.events.FAILED, (event) => {
            const payload = event && event.payload;
            const message = _isObject(payload) && typeof payload.message === 'string'
                ? payload.message
                : this.t('ai_analysis_modal.err_save');
            this._saveError = message;
        });
        this.useEvent(this._draftDiscardOp.op.events.SUCCEEDED, () => {
            this._pendingRemoveEntityIds = [];
            this._pendingRemoveRelIds = [];
            this._pendingAttrPatches = {};
            this._pendingKindPatches = {};
            this._kindUiById = {};
            this._attrValidationErrorsById = {};
            this._attrAddUiById = {};
            this._customAttrTypesById = {};
            this._pendingAddEntities = [];
            this._pendingAddRelationships = [];
            this._newEntityType = '';
            this._newEntitySubtype = '';
            this._newEntityName = '';
            this._newRelSource = '';
            this._newRelTarget = '';
            this._newRelType = '';
            this._pendingNamePatches = {};
            this._newTaskTitle = '';
            this._showDraftEntityComposer = false;
            this._showDraftRelComposer = false;
            this._attrsExpandedIds = [];
            this._saveError = '';
            this._entities.get(this.noteId);
        });
        this.useEvent(this._applyErrorDismissOp.op.events.SUCCEEDED, () => {
            this._entities.get(this.noteId);
        });
    }

    updated(changed) {
        super.updated(changed);
        const ent = this._entity();
        const rawNs = ent && typeof ent.namespace === 'string' ? ent.namespace.trim() : '';
        if (rawNs.length === 0) {
            return;
        }
        if (this._entityTypesNs !== rawNs) {
            this._entityTypesNs = rawNs;
            this._entityTypes.load({ namespace: rawNs });
        }
    }

    _entity() {
        const item = this._entities.byId[this.noteId];
        return item === undefined ? null : item;
    }

    _draft() {
        return _readDraft(this._entity());
    }

    _isPendingRemoveEntity(draftEntityId) {
        return this._pendingRemoveEntityIds.indexOf(draftEntityId) !== -1;
    }

    _isPendingRemoveRel(draftRelId) {
        return this._pendingRemoveRelIds.indexOf(draftRelId) !== -1;
    }

    _draftEntityRow(draft, draftEntityId) {
        const draftEntities = Array.isArray(draft.entities) ? draft.entities : [];
        const byId = draftEntities.find((e) => e && e.draft_entity_id === draftEntityId);
        if (_isObject(byId)) {
            return byId;
        }
        const byName = draftEntities.find((e) => e && e.name === draftEntityId);
        if (_isObject(byName)) {
            return byName;
        }
        const pending = this._pendingAddEntities.find((e) => e && e.draft_entity_id === draftEntityId);
        return _isObject(pending) ? pending : null;
    }

    _newDraftUuid() {
        if (typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function') {
            return crypto.randomUUID();
        }
        if (typeof crypto !== 'undefined' && typeof crypto.getRandomValues === 'function') {
            const bytes = new Uint8Array(16);
            crypto.getRandomValues(bytes);
            bytes[6] = (bytes[6] & 0x0f) | 0x40;
            bytes[8] = (bytes[8] & 0x3f) | 0x80;
            const hex = [...bytes].map((b) => b.toString(16).padStart(2, '0')).join('');
            return `${hex.slice(0, 8)}-${hex.slice(8, 12)}-${hex.slice(12, 16)}-${hex.slice(16, 20)}-${hex.slice(20)}`;
        }
        throw new Error('CRMAiAnalysisModal: Web Crypto API unavailable for draft ids');
    }

    _isPendingLocalRelationship(draftRelId) {
        return this._pendingAddRelationships.some((r) => r && r.draft_relationship_id === draftRelId);
    }

    _cleanupDraftRowSideState(draftEntityId) {
        if (draftEntityId in this._pendingKindPatches) {
            const nk = { ...this._pendingKindPatches };
            delete nk[draftEntityId];
            this._pendingKindPatches = nk;
        }
        if (draftEntityId in this._pendingAttrPatches) {
            const na = { ...this._pendingAttrPatches };
            delete na[draftEntityId];
            this._pendingAttrPatches = na;
        }
        if (draftEntityId in this._kindUiById) {
            const ku = { ...this._kindUiById };
            delete ku[draftEntityId];
            this._kindUiById = ku;
        }
        if (draftEntityId in this._attrValidationErrorsById) {
            const ve = { ...this._attrValidationErrorsById };
            delete ve[draftEntityId];
            this._attrValidationErrorsById = ve;
        }
        if (draftEntityId in this._attrAddUiById) {
            const au = { ...this._attrAddUiById };
            delete au[draftEntityId];
            this._attrAddUiById = au;
        }
        if (draftEntityId in this._customAttrTypesById) {
            const ct = { ...this._customAttrTypesById };
            delete ct[draftEntityId];
            this._customAttrTypesById = ct;
        }
        if (draftEntityId in this._pendingNamePatches) {
            const nm = { ...this._pendingNamePatches };
            delete nm[draftEntityId];
            this._pendingNamePatches = nm;
        }
        this._attrsExpandedIds = this._attrsExpandedIds.filter((id) => id !== draftEntityId);
    }

    _onEntityRowRemoveClick(draftEntityId, draft) {
        const pendingIdx = this._pendingAddEntities.findIndex((e) => e && e.draft_entity_id === draftEntityId);
        if (pendingIdx !== -1) {
            this._pendingAddEntities = this._pendingAddEntities.filter((e) => e.draft_entity_id !== draftEntityId);
            this._pendingAddRelationships = this._pendingAddRelationships.filter(
                (r) => r.source_draft_entity_id !== draftEntityId && r.target_draft_entity_id !== draftEntityId,
            );
            this._cleanupDraftRowSideState(draftEntityId);
            return;
        }
        this._toggleRemoveEntity(draftEntityId);
    }

    _mergeNonTaskDraftEntities(draft) {
        const draftEntities = Array.isArray(draft.entities) ? draft.entities : [];
        const server = draftEntities.filter((e) => e.entity_type !== TASK_TYPE);
        const pendingNonTask = this._pendingAddEntities.filter((e) => _isObject(e) && e.entity_type !== TASK_TYPE);
        return [...server, ...pendingNonTask];
    }

    _mergeDraftRelationships(draft) {
        const server = Array.isArray(draft.relationships) ? draft.relationships : [];
        return [...server, ...this._pendingAddRelationships];
    }

    _draftEndpointEnumValues(draft) {
        const values = [];
        const merged = [...(Array.isArray(draft.entities) ? draft.entities : []), ...this._pendingAddEntities];
        for (const e of merged) {
            if (!_isObject(e) || typeof e.draft_entity_id !== 'string' || e.draft_entity_id.length === 0) {
                continue;
            }
            const nm = typeof e.name === 'string' && e.name.length > 0 ? e.name : e.draft_entity_id.slice(0, 8);
            const et = typeof e.entity_type === 'string' ? e.entity_type : '';
            values.push({
                value: e.draft_entity_id,
                label: et.length > 0 ? `${nm} (${et})` : nm,
            });
        }
        if (_isObject(draft.note) && typeof draft.note.draft_entity_id === 'string' && draft.note.draft_entity_id.length > 0) {
            values.push({
                value: draft.note.draft_entity_id,
                label: this.t('ai_analysis_modal.endpoint_note_summary'),
            });
        }
        const known = draft.known_entity_id_map;
        if (_isObject(known)) {
            for (const did of Object.keys(known)) {
                if (typeof did !== 'string' || did.length === 0) {
                    continue;
                }
                values.push({
                    value: did,
                    label: this.t('ai_analysis_modal.endpoint_known_entity', {
                        id: did.length > 8 ? `${did.slice(0, 8)}…` : did,
                    }),
                });
            }
        }
        values.sort((a, b) => a.label.localeCompare(b.label));
        return [{ value: '', label: this.t('ai_analysis_modal.rel_endpoint_pick') }, ...values];
    }

    _relationshipTypeEnumConfigForDraft() {
        const types = Array.isArray(this._relationshipTypes.items) ? this._relationshipTypes.items : [];
        const values = [{ value: '', label: this.t('ai_analysis_modal.rel_type_pick') }];
        for (const rt of types) {
            if (!rt || typeof rt.type_id !== 'string' || rt.type_id.length === 0) {
                continue;
            }
            const nm = typeof rt.name === 'string' && rt.name.length > 0 ? rt.name : rt.type_id;
            values.push({ value: rt.type_id, label: nm });
        }
        return { values };
    }

    _entityTypeRowByTypeId(typeId) {
        if (typeof typeId !== 'string' || typeId.length === 0) {
            return null;
        }
        const items = Array.isArray(this._entityTypes.items) ? this._entityTypes.items : [];
        for (const item of items) {
            if (_isObject(item) && item.type_id === typeId) {
                return item;
            }
        }
        return null;
    }

    _schemaTypeIdForDraftRow(item, draftEntityId) {
        const subtype = this._effectiveEntitySubtypeFromItem(item, draftEntityId);
        if (subtype.length > 0) {
            return subtype;
        }
        return this._effectiveEntityTypeFromItem(item, draftEntityId);
    }

    _schemaTypeForDraftRow(item, draftEntityId) {
        return this._entityTypeRowByTypeId(this._schemaTypeIdForDraftRow(item, draftEntityId));
    }

    _attributesSchema(type) {
        const required = type && _isObject(type.required_fields) ? type.required_fields : {};
        const optional = type && _isObject(type.optional_fields) ? type.optional_fields : {};
        const out = [];
        for (const [key, def] of Object.entries(required)) {
            out.push({ key, def, required: true });
        }
        for (const [key, def] of Object.entries(optional)) {
            if (key in required) {
                continue;
            }
            out.push({ key, def, required: false });
        }
        return out;
    }

    _fieldType(def, key) {
        if (typeof key === 'string' && key === 'external_refs') {
            return 'external_refs';
        }
        if (!_isObject(def)) {
            return 'string';
        }
        const t = typeof def.type === 'string' ? def.type.trim() : '';
        return t.length === 0 ? 'string' : t;
    }

    _inferAttrFieldType(key, value) {
        if (typeof key === 'string' && key === 'external_refs') {
            return 'external_refs';
        }
        if (Array.isArray(value)) {
            return 'array';
        }
        if (_isObject(value)) {
            return 'object';
        }
        if (typeof value === 'number') {
            return Number.isInteger(value) ? 'integer' : 'number';
        }
        if (typeof value === 'boolean') {
            return 'boolean';
        }
        return 'string';
    }

    _fieldLabel(key, def) {
        if (_isObject(def) && typeof def.label === 'string' && def.label.length > 0) {
            return def.label;
        }
        return key;
    }

    _fieldConfig(def) {
        if (!_isObject(def)) {
            return {};
        }
        const config = {};
        if (Array.isArray(def.values)) {
            config.values = def.values;
        }
        if (Array.isArray(def.allowed_values)) {
            config.allowed_values = def.allowed_values;
        }
        if (def.preserve_case === true) {
            config.preserve_case = true;
        }
        return config;
    }

    _attrFieldTypeEnumConfig() {
        return {
            values: [
                { value: 'string', label: this.t('ai_analysis_modal.attr_type_string') },
                { value: 'text', label: this.t('ai_analysis_modal.attr_type_text') },
                { value: 'number', label: this.t('ai_analysis_modal.attr_type_number') },
                { value: 'integer', label: this.t('ai_analysis_modal.attr_type_integer') },
                { value: 'boolean', label: this.t('ai_analysis_modal.attr_type_boolean') },
                { value: 'date', label: this.t('ai_analysis_modal.attr_type_date') },
                { value: 'datetime', label: this.t('ai_analysis_modal.attr_type_datetime') },
                { value: 'enum', label: this.t('ai_analysis_modal.attr_type_enum') },
                { value: 'array', label: this.t('ai_analysis_modal.attr_type_array') },
                { value: 'object', label: this.t('ai_analysis_modal.attr_type_object') },
            ],
        };
    }

    _customAttrDefaultValue(type) {
        if (type === 'boolean') {
            return false;
        }
        if (type === 'array') {
            return [];
        }
        if (type === 'object') {
            return {};
        }
        if (type === 'number' || type === 'integer') {
            return null;
        }
        return '';
    }

    _customAttrEditorType(type) {
        return type === 'enum' ? 'string' : type;
    }

    _customAttrConfig(type) {
        if (type === 'array') {
            return { preserve_case: true };
        }
        return {};
    }

    _normalizeCustomAttrValue(type, value) {
        if (type === 'boolean') {
            return value === true;
        }
        if (type === 'array') {
            return Array.isArray(value) ? value : [];
        }
        if (type === 'object') {
            return _isObject(value) && !Array.isArray(value) ? value : {};
        }
        if (type === 'number' || type === 'integer') {
            return typeof value === 'number' && Number.isFinite(value) ? value : null;
        }
        return value === null || value === undefined ? '' : String(value);
    }

    _attrAddUi(draftEntityId) {
        const ui = this._attrAddUiById[draftEntityId];
        if (_isObject(ui)) {
            return {
                key: typeof ui.key === 'string' ? ui.key : '',
                type: CUSTOM_ATTR_FIELD_TYPES.includes(ui.type) ? ui.type : 'string',
                value: ui.value === undefined ? '' : ui.value,
                error: typeof ui.error === 'string' ? ui.error : '',
            };
        }
        return { key: '', type: 'string', value: '', error: '' };
    }

    _patchAttrAddUi(draftEntityId, patch) {
        const prev = this._attrAddUi(draftEntityId);
        this._attrAddUiById = {
            ...this._attrAddUiById,
            [draftEntityId]: { ...prev, ...patch },
        };
    }

    _closeAttrAddUi(draftEntityId) {
        if (!(draftEntityId in this._attrAddUiById)) {
            return;
        }
        const next = { ...this._attrAddUiById };
        delete next[draftEntityId];
        this._attrAddUiById = next;
    }

    _setCustomAttrType(draftEntityId, key, type) {
        const row = _isObject(this._customAttrTypesById[draftEntityId])
            ? this._customAttrTypesById[draftEntityId]
            : {};
        this._customAttrTypesById = {
            ...this._customAttrTypesById,
            [draftEntityId]: {
                ...row,
                [key]: type,
            },
        };
    }

    _deleteCustomAttrType(draftEntityId, key) {
        const row = this._customAttrTypesById[draftEntityId];
        if (!_isObject(row) || !(key in row)) {
            return;
        }
        const nextRow = { ...row };
        delete nextRow[key];
        const next = { ...this._customAttrTypesById };
        if (Object.keys(nextRow).length === 0) {
            delete next[draftEntityId];
        } else {
            next[draftEntityId] = nextRow;
        }
        this._customAttrTypesById = next;
    }

    _effectiveAttrsForDraftRow(draftEntityId, item) {
        if (draftEntityId in this._pendingAttrPatches) {
            const pending = this._pendingAttrPatches[draftEntityId];
            return _isObject(pending) && !Array.isArray(pending) ? pending : {};
        }
        const attrs = _isObject(item.attributes) && !Array.isArray(item.attributes) ? item.attributes : {};
        return attrs;
    }

    _shouldDropAttrValue(value) {
        return value === null
            || value === undefined
            || (typeof value === 'string' && value.trim().length === 0);
    }

    _onAttrFieldChange(draftEntityId, item, key, event) {
        if (key === 'external_refs') {
            return;
        }
        const value = event && event.detail ? event.detail.value : null;
        const base = this._effectiveAttrsForDraftRow(draftEntityId, item);
        const next = { ...base };
        if (this._shouldDropAttrValue(value)) {
            delete next[key];
        } else {
            next[key] = value;
        }
        this._pendingAttrPatches = {
            ...this._pendingAttrPatches,
            [draftEntityId]: next,
        };
        this._clearAttrValidationError(draftEntityId, key);
    }

    _toggleAttrAdd(draftEntityId, item) {
        if (draftEntityId in this._attrAddUiById) {
            this._closeAttrAddUi(draftEntityId);
            return;
        }
        this._ensureKindUi(draftEntityId, item);
        if (this._attrsExpandedIds.indexOf(draftEntityId) === -1) {
            this._attrsExpandedIds = [...this._attrsExpandedIds, draftEntityId];
        }
        this._attrAddUiById = {
            ...this._attrAddUiById,
            [draftEntityId]: { key: '', type: 'string', value: '', error: '' },
        };
    }

    _onAttrAddKeyChange(draftEntityId, detail) {
        const value = detail && detail.value !== undefined && detail.value !== null
            ? String(detail.value)
            : '';
        this._patchAttrAddUi(draftEntityId, { key: value, error: '' });
    }

    _onAttrAddTypeChange(draftEntityId, detail) {
        const value = detail && typeof detail.value === 'string' ? detail.value : 'string';
        const type = CUSTOM_ATTR_FIELD_TYPES.includes(value) ? value : 'string';
        this._patchAttrAddUi(draftEntityId, {
            type,
            value: this._customAttrDefaultValue(type),
            error: '',
        });
    }

    _onAttrAddValueChange(draftEntityId, detail) {
        const value = detail && detail.value !== undefined ? detail.value : null;
        this._patchAttrAddUi(draftEntityId, { value, error: '' });
    }

    _onAddCustomAttr(draftEntityId, item) {
        const ui = this._attrAddUi(draftEntityId);
        const key = ui.key.trim();
        if (key.length === 0) {
            this._patchAttrAddUi(draftEntityId, {
                error: this.t('ai_analysis_modal.attr_add_err_key_required'),
            });
            return;
        }
        if (key === 'external_refs') {
            this._patchAttrAddUi(draftEntityId, {
                error: this.t('ai_analysis_modal.attr_add_err_reserved'),
            });
            return;
        }
        const type = CUSTOM_ATTR_FIELD_TYPES.includes(ui.type) ? ui.type : 'string';
        const schema = this._attributesSchema(this._schemaTypeForDraftRow(item, draftEntityId));
        const schemaHasKey = schema.some((row) => row.key === key);
        const attrs = this._effectiveAttrsForDraftRow(draftEntityId, item);
        if (schemaHasKey || Object.prototype.hasOwnProperty.call(attrs, key)) {
            this._patchAttrAddUi(draftEntityId, {
                error: this.t('ai_analysis_modal.attr_add_err_duplicate'),
            });
            return;
        }
        const next = {
            ...attrs,
            [key]: this._normalizeCustomAttrValue(type, ui.value),
        };
        this._pendingAttrPatches = {
            ...this._pendingAttrPatches,
            [draftEntityId]: next,
        };
        this._setCustomAttrType(draftEntityId, key, type);
        this._closeAttrAddUi(draftEntityId);
    }

    _removeAttrField(draftEntityId, item, key) {
        if (key === 'external_refs') {
            return;
        }
        const attrs = this._effectiveAttrsForDraftRow(draftEntityId, item);
        if (!Object.prototype.hasOwnProperty.call(attrs, key)) {
            return;
        }
        const nextAttrs = { ...attrs };
        delete nextAttrs[key];
        this._pendingAttrPatches = {
            ...this._pendingAttrPatches,
            [draftEntityId]: nextAttrs,
        };
        this._clearAttrValidationError(draftEntityId, key);
        this._deleteCustomAttrType(draftEntityId, key);
    }

    _clearAttrValidationError(draftEntityId, key) {
        const byId = this._attrValidationErrorsById;
        const row = byId[draftEntityId];
        if (!_isObject(row) || !(key in row)) {
            return;
        }
        const nextRow = { ...row };
        delete nextRow[key];
        const next = { ...byId };
        if (Object.keys(nextRow).length === 0) {
            delete next[draftEntityId];
        } else {
            next[draftEntityId] = nextRow;
        }
        this._attrValidationErrorsById = next;
    }

    _clearAttrValidationErrorsForRow(draftEntityId) {
        if (!(draftEntityId in this._attrValidationErrorsById)) {
            return;
        }
        const next = { ...this._attrValidationErrorsById };
        delete next[draftEntityId];
        this._attrValidationErrorsById = next;
    }

    _requiredAttrMissing(value) {
        return value === undefined
            || value === null
            || (typeof value === 'string' && value.trim().length === 0);
    }

    _numericStringIsValid(value, integer) {
        if (typeof value !== 'string') {
            return false;
        }
        const trimmed = value.trim();
        if (trimmed.length === 0) {
            return false;
        }
        const parsed = Number(trimmed.replace(',', '.'));
        if (!Number.isFinite(parsed)) {
            return false;
        }
        return integer ? Number.isInteger(parsed) : true;
    }

    _attrTypeInvalid(value, fieldType) {
        if (value === undefined || value === null || (typeof value === 'string' && value.trim().length === 0)) {
            return false;
        }
        if (fieldType === 'string' || fieldType === 'text' || fieldType === 'enum' || fieldType === 'date' || fieldType === 'datetime') {
            return typeof value !== 'string';
        }
        if (fieldType === 'integer') {
            if (typeof value === 'number') {
                return !Number.isInteger(value);
            }
            return !this._numericStringIsValid(value, true);
        }
        if (fieldType === 'number') {
            if (typeof value === 'number') {
                return !Number.isFinite(value);
            }
            return !this._numericStringIsValid(value, false);
        }
        if (fieldType === 'boolean') {
            return typeof value !== 'boolean';
        }
        if (fieldType === 'array') {
            return !Array.isArray(value);
        }
        if (fieldType === 'object' || fieldType === 'external_refs') {
            return !_isObject(value) || Array.isArray(value);
        }
        return false;
    }

    _validateDraftAttributeRows(draft) {
        const server = Array.isArray(draft.entities) ? draft.entities : [];
        const rows = [...server, ...this._pendingAddEntities];
        const nextErrors = {};
        const expanded = new Set(this._attrsExpandedIds);

        for (const item of rows) {
            if (!_isObject(item) || item.entity_type === TASK_TYPE) {
                continue;
            }
            const draftEntityId = typeof item.draft_entity_id === 'string' && item.draft_entity_id.length > 0
                ? item.draft_entity_id
                : item.name;
            if (typeof draftEntityId !== 'string' || draftEntityId.length === 0) {
                continue;
            }
            if (this._isPendingRemoveEntity(draftEntityId)) {
                continue;
            }
            const type = this._schemaTypeForDraftRow(item, draftEntityId);
            const schema = this._attributesSchema(type);
            if (schema.length === 0) {
                continue;
            }
            const attrs = this._effectiveAttrsForDraftRow(draftEntityId, item);
            const rowErrors = {};
            for (const { key, def, required } of schema) {
                const fieldType = this._fieldType(def, key);
                const value = Object.prototype.hasOwnProperty.call(attrs, key) ? attrs[key] : undefined;
                if (required && this._requiredAttrMissing(value)) {
                    rowErrors[key] = this.t('ai_analysis_modal.attr_field_required');
                    continue;
                }
                if (this._attrTypeInvalid(value, fieldType)) {
                    rowErrors[key] = this.t('ai_analysis_modal.attr_field_type_invalid', { type: fieldType });
                }
            }
            if (Object.keys(rowErrors).length > 0) {
                nextErrors[draftEntityId] = rowErrors;
                expanded.add(draftEntityId);
            }
        }

        this._attrValidationErrorsById = nextErrors;
        if (Object.keys(nextErrors).length === 0) {
            return true;
        }
        this._attrsExpandedIds = Array.from(expanded);
        this._saveError = this.t('ai_analysis_modal.attr_required_save_error');
        this.toast('ai_analysis_modal.attr_required_save_error', { type: 'error' });
        return false;
    }

    _onNewEntityTypeChange(detail) {
        const raw = detail && typeof detail.value === 'string' ? detail.value : '';
        const subOpts = this._subtypeEnumOptions(raw).filter((o) => o.value !== '');
        let nextSub = typeof this._newEntitySubtype === 'string' ? this._newEntitySubtype : '';
        if (nextSub.length > 0 && subOpts.every((o) => o.value !== nextSub)) {
            nextSub = '';
        }
        this._newEntityType = raw;
        this._newEntitySubtype = nextSub;
    }

    _onAddDraftEntity() {
        const entityType = typeof this._newEntityType === 'string' ? this._newEntityType.trim() : '';
        const name = typeof this._newEntityName === 'string' ? this._newEntityName.trim() : '';
        const sub = typeof this._newEntitySubtype === 'string' ? this._newEntitySubtype.trim() : '';
        if (!entityType.length || !name.length) {
            this.toast('ai_analysis_modal.err_add_entity_required', { type: 'error' });
            return;
        }
        const row = {
            draft_entity_id: this._newDraftUuid(),
            entity_type: entityType,
            name,
            attributes: {},
        };
        if (sub.length > 0) {
            row.entity_subtype = sub;
        }
        this._pendingAddEntities = [...this._pendingAddEntities, row];
        this._newEntityType = '';
        this._newEntitySubtype = '';
        this._newEntityName = '';
        this._showDraftEntityComposer = false;
    }

    _onAddDraftRelationship(draft) {
        const source = typeof this._newRelSource === 'string' ? this._newRelSource.trim() : '';
        const target = typeof this._newRelTarget === 'string' ? this._newRelTarget.trim() : '';
        const relType = typeof this._newRelType === 'string' ? this._newRelType.trim() : '';
        if (!source.length || !target.length || !relType.length) {
            this.toast('ai_analysis_modal.err_add_rel_required', { type: 'error' });
            return;
        }
        if (source === target) {
            this.toast('ai_analysis_modal.err_add_rel_same_endpoints', { type: 'error' });
            return;
        }
        const endpoints = new Set(
            this._draftEndpointEnumValues(draft).filter((o) => o.value.length > 0).map((o) => o.value),
        );
        if (!endpoints.has(source) || !endpoints.has(target)) {
            this.toast('ai_analysis_modal.err_add_rel_bad_endpoint', { type: 'error' });
            return;
        }
        const row = {
            draft_relationship_id: this._newDraftUuid(),
            source_draft_entity_id: source,
            target_draft_entity_id: target,
            relationship_type: relType,
            weight: 1,
            confidence: 1,
        };
        this._pendingAddRelationships = [...this._pendingAddRelationships, row];
        this._newRelSource = '';
        this._newRelTarget = '';
        this._newRelType = '';
        this._showDraftRelComposer = false;
    }

    _onRelRowRemoveClick(draftRelId) {
        if (this._isPendingLocalRelationship(draftRelId)) {
            this._pendingAddRelationships = this._pendingAddRelationships.filter(
                (r) => r.draft_relationship_id !== draftRelId,
            );
            return;
        }
        this._toggleRemoveRel(draftRelId);
    }

    _effectiveEntityTypeFromItem(item, draftEntityId) {
        const k = this._pendingKindPatches[draftEntityId];
        if (k && k.entity_type !== undefined) {
            return typeof k.entity_type === 'string' ? k.entity_type : '';
        }
        return typeof item.entity_type === 'string' ? item.entity_type : '';
    }

    _effectiveEntitySubtypeFromItem(item, draftEntityId) {
        const k = this._pendingKindPatches[draftEntityId];
        if (k && k.entity_subtype !== undefined) {
            const s = k.entity_subtype;
            return s !== null && s !== undefined ? String(s) : '';
        }
        if (item.entity_subtype != null && item.entity_subtype !== undefined) {
            return String(item.entity_subtype);
        }
        return '';
    }

    _entitySubtitleDraft(item, draftEntityId) {
        const parts = [];
        const et = this._effectiveEntityTypeFromItem(item, draftEntityId);
        const es = this._effectiveEntitySubtypeFromItem(item, draftEntityId);
        if (et.length > 0) parts.push(et);
        if (es.length > 0) parts.push(es);
        if (parts.length === 0) return this.t('ai_analysis_modal.object_fallback');
        return parts.join(' · ');
    }

    _allTypeEnumOptions() {
        const items = Array.isArray(this._entityTypes.items) ? this._entityTypes.items : [];
        const out = [];
        for (const it of items) {
            if (!_isObject(it) || typeof it.type_id !== 'string' || it.type_id.length === 0) {
                continue;
            }
            const label = typeof it.label === 'string' && it.label.length > 0 ? it.label : it.type_id;
            out.push({ value: it.type_id, label });
        }
        out.sort((a, b) => a.label.localeCompare(b.label));
        return out;
    }

    _subtypeEnumOptions(parentTypeId) {
        const blank = {
            value: '',
            label: this.t('ai_analysis_modal.kind_subtype_blank'),
        };
        if (typeof parentTypeId !== 'string' || parentTypeId.length === 0) {
            return [blank];
        }
        const items = Array.isArray(this._entityTypes.items) ? this._entityTypes.items : [];
        const opts = [blank];
        for (const it of items) {
            if (!_isObject(it) || typeof it.type_id !== 'string' || it.type_id.length === 0) {
                continue;
            }
            if (it.type_id === parentTypeId) {
                continue;
            }
            const pid = it.parent_type_id != null && typeof it.parent_type_id === 'string'
                ? it.parent_type_id
                : null;
            if (pid !== parentTypeId) {
                continue;
            }
            const label = typeof it.label === 'string' && it.label.length > 0 ? it.label : it.type_id;
            opts.push({ value: it.type_id, label });
        }
        opts.sort((a, b) => {
            if (a.value === '') return -1;
            if (b.value === '') return 1;
            return a.label.localeCompare(b.label);
        });
        return opts;
    }

    _ensureKindUi(draftEntityId, item) {
        if (draftEntityId in this._kindUiById) {
            return;
        }
        const ot = typeof item.entity_type === 'string' ? item.entity_type : '';
        let os = item.entity_subtype != null ? String(item.entity_subtype) : '';
        const allowedSubs = this._subtypeEnumOptions(ot).filter((o) => o.value !== '');
        if (allowedSubs.length === 0) {
            os = '';
        } else if (os.length > 0 && allowedSubs.every((o) => o.value !== os)) {
            os = '';
        }
        this._kindUiById = {
            ...this._kindUiById,
            [draftEntityId]: { entity_type: ot, entity_subtype: os },
        };
        this._syncPendingKindFromUi(draftEntityId, item);
    }

    _syncPendingKindFromUi(draftEntityId, item) {
        const ui = this._kindUiById[draftEntityId];
        if (!ui || !_isObject(ui)) {
            return;
        }
        const origType = typeof item.entity_type === 'string' ? item.entity_type : '';
        const origSub = item.entity_subtype != null ? String(item.entity_subtype) : '';
        const uiType = typeof ui.entity_type === 'string' ? ui.entity_type : '';
        const uiSub = typeof ui.entity_subtype === 'string' ? ui.entity_subtype : '';
        const patch = {};
        if (uiType !== origType) {
            patch.entity_type = uiType;
        }
        if (uiSub !== origSub) {
            patch.entity_subtype = uiSub;
        }
        if (Object.keys(patch).length === 0) {
            if (draftEntityId in this._pendingKindPatches) {
                const next = { ...this._pendingKindPatches };
                delete next[draftEntityId];
                this._pendingKindPatches = next;
            }
            return;
        }
        this._pendingKindPatches = {
            ...this._pendingKindPatches,
            [draftEntityId]: patch,
        };
    }

    _onDraftEntityTypeChange(draftEntityId, item, detail) {
        const raw = detail && typeof detail.value === 'string' ? detail.value : '';
        const prev = this._kindUiById[draftEntityId];
        const prevSub = prev && typeof prev.entity_subtype === 'string' ? prev.entity_subtype : '';
        const subOpts = this._subtypeEnumOptions(raw).filter((o) => o.value !== '');
        let nextSub = prevSub;
        if (nextSub.length > 0 && subOpts.every((o) => o.value !== nextSub)) {
            nextSub = '';
        }
        this._kindUiById = {
            ...this._kindUiById,
            [draftEntityId]: { entity_type: raw, entity_subtype: nextSub },
        };
        this._clearAttrValidationErrorsForRow(draftEntityId);
        this._syncPendingKindFromUi(draftEntityId, item);
    }

    _onDraftEntitySubtypeChange(draftEntityId, item, detail) {
        const raw = detail && typeof detail.value === 'string' ? detail.value : '';
        const prev = this._kindUiById[draftEntityId];
        const prevType = prev && typeof prev.entity_type === 'string' ? prev.entity_type : '';
        this._kindUiById = {
            ...this._kindUiById,
            [draftEntityId]: { entity_type: prevType, entity_subtype: raw },
        };
        this._clearAttrValidationErrorsForRow(draftEntityId);
        this._syncPendingKindFromUi(draftEntityId, item);
    }

    _toggleRemoveEntity(draftEntityId) {
        if (this._isPendingRemoveEntity(draftEntityId)) {
            this._pendingRemoveEntityIds = this._pendingRemoveEntityIds.filter((id) => id !== draftEntityId);
        } else {
            this._pendingRemoveEntityIds = [...this._pendingRemoveEntityIds, draftEntityId];
        }
    }

    _toggleRemoveRel(draftRelId) {
        if (this._isPendingRemoveRel(draftRelId)) {
            this._pendingRemoveRelIds = this._pendingRemoveRelIds.filter((id) => id !== draftRelId);
        } else {
            this._pendingRemoveRelIds = [...this._pendingRemoveRelIds, draftRelId];
        }
    }

    _toggleAttrs(draftEntityId, draft) {
        const idx = this._attrsExpandedIds.indexOf(draftEntityId);
        if (idx !== -1) {
            this._attrsExpandedIds = this._attrsExpandedIds.filter((id) => id !== draftEntityId);
            return;
        }
        const item = this._draftEntityRow(draft, draftEntityId);
        if (!_isObject(item)) {
            throw new Error('CRMAiAnalysisModal: draft entity row not found');
        }
        this._ensureKindUi(draftEntityId, item);
        this._attrsExpandedIds = [...this._attrsExpandedIds, draftEntityId];
    }

    _hasPendingChanges() {
        return this._pendingRemoveEntityIds.length > 0
            || this._pendingRemoveRelIds.length > 0
            || Object.keys(this._pendingAttrPatches).length > 0
            || Object.keys(this._pendingKindPatches).length > 0
            || Object.keys(this._pendingNamePatches).length > 0
            || this._pendingAddEntities.length > 0
            || this._pendingAddRelationships.length > 0;
    }

    _serializePendingAddEntitiesForPatch() {
        return this._pendingAddEntities.map((e) => {
            if (!_isObject(e) || typeof e.draft_entity_id !== 'string' || e.draft_entity_id.length === 0) {
                throw new Error('CRMAiAnalysisModal: invalid pending add entity');
            }
            const entityType = typeof e.entity_type === 'string' ? e.entity_type : '';
            const name = typeof e.name === 'string' ? e.name : '';
            const row = {
                draft_entity_id: e.draft_entity_id,
                entity_type: entityType,
                name,
                attributes: _isObject(e.attributes) ? e.attributes : {},
            };
            const sub = e.entity_subtype != null ? String(e.entity_subtype).trim() : '';
            if (sub.length > 0) {
                row.entity_subtype = sub;
            }
            return row;
        });
    }

    _serializePendingAddRelationshipsForPatch() {
        return this._pendingAddRelationships.map((r) => {
            if (!_isObject(r) || typeof r.draft_relationship_id !== 'string' || r.draft_relationship_id.length === 0) {
                throw new Error('CRMAiAnalysisModal: invalid pending add relationship');
            }
            return {
                draft_relationship_id: r.draft_relationship_id,
                source_draft_entity_id: r.source_draft_entity_id,
                target_draft_entity_id: r.target_draft_entity_id,
                relationship_type: r.relationship_type,
                weight: typeof r.weight === 'number' ? r.weight : 1,
                confidence: typeof r.confidence === 'number' ? r.confidence : 1,
            };
        });
    }

    _buildDraftMutationPayload() {
        const draft = this._draft();
        if (draft === null) {
            return null;
        }
        const ids = new Set([
            ...Object.keys(this._pendingAttrPatches),
            ...Object.keys(this._pendingKindPatches),
            ...Object.keys(this._pendingNamePatches),
        ]);
        const patch_entities = [];
        for (const draft_entity_id of ids) {
            const row = { draft_entity_id };
            if (draft_entity_id in this._pendingAttrPatches) {
                row.attributes = this._pendingAttrPatches[draft_entity_id];
            }
            const kind = this._pendingKindPatches[draft_entity_id];
            if (kind && _isObject(kind)) {
                if (kind.entity_type !== undefined) {
                    row.entity_type = kind.entity_type;
                }
                if (kind.entity_subtype !== undefined) {
                    row.entity_subtype = kind.entity_subtype;
                }
            }
            if (draft_entity_id in this._pendingNamePatches) {
                row.name = this._pendingNamePatches[draft_entity_id];
            }
            patch_entities.push(row);
        }
        const payload = {
            expected_version: draft.draft_version,
            remove_entity_draft_ids: this._pendingRemoveEntityIds,
            remove_relationship_draft_ids: this._pendingRemoveRelIds,
            patch_entities,
        };
        const addEntities = this._serializePendingAddEntitiesForPatch();
        const addRels = this._serializePendingAddRelationshipsForPatch();
        if (addEntities.length > 0) {
            payload.add_entities = addEntities;
        }
        if (addRels.length > 0) {
            payload.add_relationships = addRels;
        }
        return payload;
    }

    _failureMessageForDraft(entity, draftEntityId) {
        const failures = _readApplyFailures(entity);
        const hit = failures.find((x) => x.draft_entity_id === draftEntityId);
        if (!hit || typeof hit.message !== 'string') {
            return '';
        }
        const msg = hit.message.trim();
        return msg.length > 0 ? msg : '';
    }

    async _onDiscardDraft() {
        const confirmed = await platformConfirm(
            this.t('ai_analysis_modal.discard_draft_confirm'),
            {
                title: this.t('ai_analysis_modal.discard_draft_title'),
                confirmText: this.t('ai_analysis_modal.discard_draft_confirm_btn'),
                cancelText: this.t('ai_analysis_modal.discard_draft_cancel'),
                confirmVariant: 'danger',
            },
        );
        if (!confirmed) {
            return;
        }
        this._draftDiscardOp.run({ note_id: this.noteId });
    }

    _onDismissApplyError() {
        this._applyErrorDismissOp.run({ note_id: this.noteId });
    }

    _onRepairDraftAi() {
        this._draftRepairOp.run({ note_id: this.noteId });
    }

    _onAnalyze() {
        const entity = this._entity();
        if (entity === null) return;
        this._analyzeOp.run({
            note_id: this.noteId,
            mode: 'analyze',
        });
    }

    _onApply() {
        const draft = this._draft();
        if (draft === null) return;
        if (!this._validateDraftAttributeRows(draft)) {
            return;
        }
        if (this._hasPendingChanges()) {
            const body = this._buildDraftMutationPayload();
            if (body === null) {
                throw new Error('CRMAiAnalysisModal: draft mutation payload expected');
            }
            this._draftSaveOp.run({
                note_id: this.noteId,
                draft: body,
            });
            return;
        }
        this._analyzeOp.run({
            note_id: this.noteId,
            mode: 'apply',
        });
    }

    _onSavePending() {
        const draft = this._draft();
        if (draft === null) return;
        if (!this._hasPendingChanges()) return;
        if (!this._validateDraftAttributeRows(draft)) {
            return;
        }
        const body = this._buildDraftMutationPayload();
        if (body === null) {
            throw new Error('CRMAiAnalysisModal: draft mutation payload expected');
        }
        this._draftSaveOp.run({
            note_id: this.noteId,
            draft: body,
        });
    }

    renderHeader() {
        const hasDraft = this._draft() !== null;
        return html`
            <span style="display:flex;align-items:center;justify-content:space-between;width:100%;gap:12px;min-width:0;">
                <span style="display:inline-flex;align-items:center;gap:8px;min-width:0;">
                    <platform-icon name="sparkle" size="18" style="color: var(--accent);"></platform-icon>
                    <span class="modal-title-gradient">${this.t('ai_analysis_modal.header_title')}</span>
                </span>
                ${hasDraft
                    ? html`
                        <span class="modal-header-actions">
                            <button
                                type="button"
                                class="icon-btn"
                                title=${this.t('ai_analysis_modal.discard_draft_tooltip')}
                                ?disabled=${this._draftDiscardOp.busy || this._draftSaveOp.busy || this._analyzeOp.busy}
                                @click=${() => this._onDiscardDraft()}
                            >
                                <platform-icon name="trash" size="16"></platform-icon>
                            </button>
                        </span>
                    `
                    : nothing}
            </span>
        `;
    }

    renderBody() {
        const entity = this._entity();
        if (entity === null) {
            return html`
                <div class="loading-state">
                    <glass-spinner></glass-spinner>
                    <span>${this.t('ai_analysis_modal.loading_1')}</span>
                </div>
            `;
        }

        const draft = _readDraft(entity);
        if (draft === null) {
            return this._renderEmptyState(entity);
        }

        return html`
            <div class="body">
                ${this._renderApplyErrorBanner(entity)}
                ${this._renderLeftColumn(entity, draft)}
                ${this._renderRightColumn(entity, draft)}
            </div>
        `;
    }

    _renderApplyErrorBanner(entity) {
        const summary = _analysisLastErrorText(entity);
        const failures = _readApplyFailures(entity);
        if (!summary && failures.length === 0) {
            return nothing;
        }
        const busy = this._applyErrorDismissOp.busy;
        const repairBusy = this._draftRepairOp.busy || this._draftRepairPending;
        const repairDisabled = busy || repairBusy;
        return html`
            <div class="apply-error-banner">
                <platform-icon name="alert-triangle" size="20" style="color: var(--error); flex-shrink: 0;"></platform-icon>
                <div class="apply-error-body">
                    <div class="apply-error-title">${this.t('ai_analysis_modal.apply_error_title')}</div>
                    ${summary
                        ? html`<div style="white-space: pre-wrap;">${summary}</div>`
                        : nothing}
                    ${failures.length > 0
                        ? html`<ul style="margin:0;padding-left: var(--space-4);">
                            ${failures.map((f) => {
                                const line = typeof f.message === 'string' ? f.message : '';
                                const name = typeof f.entity_name === 'string' ? f.entity_name : '';
                                const et = typeof f.entity_type === 'string' ? f.entity_type : '';
                                const head = name.length > 0 || et.length > 0
                                    ? `${name}${name.length > 0 && et.length > 0 ? ' · ' : ''}${et}`
                                    : '';
                                return html`<li class="apply-error-detail">${head.length > 0 ? `${head}: ` : ''}${line}</li>`;
                            })}
                        </ul>`
                        : nothing}
                    <div style="font-size: var(--text-xs); color: var(--text-tertiary);">
                        ${this.t('ai_analysis_modal.apply_error_hint')}
                    </div>
                </div>
                ${summary || failures.length > 0
                    ? html`
                        <span class="apply-error-actions">
                            <button
                                type="button"
                                class="icon-btn"
                                title=${this.t('ai_analysis_modal.apply_error_ai_tooltip')}
                                ?disabled=${repairDisabled}
                                @click=${() => this._onRepairDraftAi()}
                            >
                                ${repairBusy
                                    ? html`<glass-spinner size="sm"></glass-spinner>`
                                    : html`<platform-icon name="sparkle" size="16"></platform-icon>`}
                            </button>
                            <button
                                type="button"
                                class="icon-btn"
                                title=${this.t('ai_analysis_modal.dismiss_error_tooltip')}
                                ?disabled=${busy}
                                @click=${() => this._onDismissApplyError()}
                            >
                                <platform-icon name="x" size="16"></platform-icon>
                            </button>
                        </span>
                    `
                    : nothing}
            </div>
        `;
    }

    _renderEmptyState(entity) {
        const applied = _isApplied(entity);
        const analyzing = this._analyzeOp.busy;
        if (analyzing) {
            return html`
                <div class="loading-state">
                    <glass-spinner></glass-spinner>
                    <span>${this.t('ai_analysis_modal.loading_2')}</span>
                </div>
            `;
        }
        if (applied) {
            return html`
                <div class="empty-state">
                    <platform-icon name="check" size="32"></platform-icon>
                    <div class="hint">${this.t('ai_analysis_modal.empty_applied')}</div>
                    <button class="btn" type="button" @click=${() => this._onAnalyze()}>
                        ${this.t('ai_analysis_modal.action_re_analyze')}
                    </button>
                </div>
            `;
        }
        return html`
            <div class="empty-state">
                <platform-icon name="sparkle" size="32"></platform-icon>
                <div class="hint">${this.t('ai_analysis_modal.empty_no_draft')}</div>
                <button class="btn btn-primary" type="button" @click=${() => this._onAnalyze()}>
                    ${this.t('ai_analysis_modal.action_analyze')}
                </button>
            </div>
        `;
    }

    _effectiveTaskTitle(draftId, item) {
        if (draftId in this._pendingNamePatches) {
            return this._pendingNamePatches[draftId];
        }
        return typeof item.name === 'string' ? item.name : '';
    }

    _isDraftTaskCompleted(draftId, draft) {
        const item = this._draftEntityRow(draft, draftId);
        if (!_isObject(item)) {
            return false;
        }
        const serverAttrs = _isObject(item.attributes) ? item.attributes : {};
        if (draftId in this._pendingAttrPatches) {
            const o = this._pendingAttrPatches[draftId];
            if (_isObject(o) && Object.prototype.hasOwnProperty.call(o, DRAFT_TASK_COMPLETED_ATTR)) {
                return o[DRAFT_TASK_COMPLETED_ATTR] === true;
            }
        }
        return serverAttrs[DRAFT_TASK_COMPLETED_ATTR] === true;
    }

    _toggleDraftTaskCompleted(draftId, draft) {
        const nextDone = !this._isDraftTaskCompleted(draftId, draft);
        const overlay = draftId in this._pendingAttrPatches
            ? { ...this._pendingAttrPatches[draftId] }
            : {};
        overlay[DRAFT_TASK_COMPLETED_ATTR] = nextDone;
        this._pendingAttrPatches = {
            ...this._pendingAttrPatches,
            [draftId]: overlay,
        };
    }

    _onTaskTitleBlur(draftId, draft) {
        const item = this._draftEntityRow(draft, draftId);
        if (!_isObject(item)) {
            throw new Error('CRMAiAnalysisModal: task row not found');
        }
        const orig = typeof item.name === 'string' ? item.name.trim() : '';
        let cur = draftId in this._pendingNamePatches ? String(this._pendingNamePatches[draftId]) : orig;
        cur = cur.trim();
        const np = { ...this._pendingNamePatches };
        if (!cur.length) {
            delete np[draftId];
            this._pendingNamePatches = np;
            return;
        }
        if (cur === orig) {
            delete np[draftId];
        } else {
            np[draftId] = cur;
        }
        this._pendingNamePatches = np;
    }

    _onTaskTitleInput(draftId, event) {
        const t = event && event.target;
        const v = t && t.value;
        if (typeof v !== 'string') {
            throw new Error('CRMAiAnalysisModal: task title input value required');
        }
        this._pendingNamePatches = {
            ...this._pendingNamePatches,
            [draftId]: v,
        };
    }

    _onQuickAddTaskKeydown(event) {
        if (event.key !== 'Enter') {
            return;
        }
        event.preventDefault();
        const title = typeof this._newTaskTitle === 'string' ? this._newTaskTitle.trim() : '';
        if (!title.length) {
            return;
        }
        const row = {
            draft_entity_id: this._newDraftUuid(),
            entity_type: TASK_TYPE,
            name: title,
            attributes: {},
        };
        this._pendingAddEntities = [...this._pendingAddEntities, row];
        this._newTaskTitle = '';
    }

    _renderSuggestedTasksBlock(entity, draft, tasks) {
        const busy = this._draftSaveOp.busy === true;
        return html`
            ${tasks.length === 0
                ? html`<div class="hint" style="color: var(--text-tertiary); font-size: var(--text-sm);">${this.t('ai_analysis_modal.no_tasks')}</div>`
                : html`<div class="tasks-quick-list">${tasks.map((t) => this._renderTaskQuickRow(t, entity, draft, busy))}</div>`}
            <div class="tasks-quick-add-wrap">
                <platform-icon name="sparkle" size="18"></platform-icon>
                <input
                    type="text"
                    data-canon="inline-edit"
                    class="tasks-quick-add-input"
                    .value=${this._newTaskTitle}
                    placeholder=${this.t('ai_analysis_modal.tasks_quick_add_placeholder')}
                    ?disabled=${busy}
                    @input=${(e) => {
                        const v = e.target && e.target.value;
                        this._newTaskTitle = typeof v === 'string' ? v : '';
                    }}
                    @keydown=${(e) => this._onQuickAddTaskKeydown(e)}
                />
            </div>
        `;
    }

    _renderTaskQuickRow(item, entity, draft, busy) {
        const draftId = typeof item.draft_entity_id === 'string' && item.draft_entity_id.length > 0
            ? item.draft_entity_id
            : item.name;
        const removed = this._isPendingRemoveEntity(draftId);
        const done = this._isDraftTaskCompleted(draftId, draft);
        const applyErr = entity !== null ? this._failureMessageForDraft(entity, draftId) : '';
        const rowExtra = applyErr.length > 0 ? 'has-apply-error' : '';
        const titleVal = this._effectiveTaskTitle(draftId, item);
        const dedup = this._dedupBadge(item);
        return html`
            <div class="task-quick-row ${done ? 'task-done' : ''} ${removed ? 'removed' : ''} ${rowExtra}">
                <input
                    type="checkbox"
                    class="task-done-checkbox"
                    .checked=${done}
                    ?disabled=${busy || removed}
                    title=${this.t('ai_analysis_modal.task_done_checkbox')}
                    @change=${() => this._toggleDraftTaskCompleted(draftId, draft)}
                />
                <div class="task-quick-meta">
                    <input
                        type="text"
                        data-canon="inline-edit"
                        class="task-title-input"
                        .value=${titleVal}
                        ?disabled=${busy || removed}
                        @input=${(e) => this._onTaskTitleInput(draftId, e)}
                        @blur=${() => this._onTaskTitleBlur(draftId, draft)}
                    />
                    ${applyErr.length > 0
                        ? html`<span style="font-size:var(--text-xs);color:var(--error);">${applyErr}</span>`
                        : nothing}
                </div>
                <div class="actions" style="display:inline-flex;align-items:center;gap:4px;">
                    ${dedup}
                    <button
                        type="button"
                        class="icon-btn"
                        title=${removed ? this.t('ai_analysis_modal.action_undo') : this.t('ai_analysis_modal.action_remove')}
                        ?disabled=${busy}
                        @click=${() => this._onEntityRowRemoveClick(draftId, draft)}
                    >
                        <platform-icon name=${removed ? 'rotate-ccw' : 'close'} size="12"></platform-icon>
                    </button>
                </div>
            </div>
        `;
    }

    _renderLeftColumn(entity, draft) {
        const summary = this._summaryText(entity, draft);
        const mergedEntities = [...(Array.isArray(draft.entities) ? draft.entities : []), ...this._pendingAddEntities];
        const tasks = mergedEntities.filter((e) => _isObject(e) && e.entity_type === TASK_TYPE);
        return html`
            <section class="column">
                <article class="block summary">
                    <h3 class="block-title">
                        <platform-icon name="sparkle" size="14"></platform-icon>
                        ${this.t('ai_analysis_modal.block_summary_title')}
                    </h3>
                    <p class="summary-text">${summary}</p>
                </article>
                <article class="block">
                    <h3 class="block-title">
                        <platform-icon name="check-square" size="14"></platform-icon>
                        ${this.t('ai_analysis_modal.suggested_tasks_title')}
                    </h3>
                    ${this._renderSuggestedTasksBlock(entity, draft, tasks)}
                </article>
            </section>
        `;
    }

    _renderRightColumn(entity, draft) {
        const entities = this._mergeNonTaskDraftEntities(draft);
        const relationships = this._mergeDraftRelationships(draft);
        const typeOpts = this._allTypeEnumOptions();
        const typesBusy = this._entityTypes.loading === true && typeOpts.length === 0;
        const newSubOpts = this._subtypeEnumOptions(this._newEntityType);
        const showNewSubtypeField = newSubOpts.some((o) => o.value !== '');
        const relTypeCfg = this._relationshipTypeEnumConfigForDraft();
        const relItems = Array.isArray(this._relationshipTypes.items) ? this._relationshipTypes.items : [];
        const relTypesBusy = this._relationshipTypes.loading === true && relItems.length === 0;
        return html`
            <section class="column">
                <article class="block">
                    <div class="block-title-row">
                        <h3 class="block-title">
                            <platform-icon name="link" size="14"></platform-icon>
                            ${this.t('ai_analysis_modal.suggested_entities_title')}
                        </h3>
                        <button
                            type="button"
                            class="icon-btn"
                            title=${this.t('ai_analysis_modal.composer_toggle_entity')}
                            ?disabled=${this._draftSaveOp.busy}
                            @click=${() => { this._showDraftEntityComposer = !this._showDraftEntityComposer; }}
                        >
                            <platform-icon name="plus" size="16"></platform-icon>
                        </button>
                    </div>
                    ${entities.length === 0
                        ? html`<div class="hint" style="color: var(--text-tertiary); font-size: var(--text-sm);">${this.t('ai_analysis_modal.no_entities')}</div>`
                        : html`<div class="items-list entities-list">${entities.map((e) => this._renderEntityRow(e, entity, draft))}</div>`}
                    ${this._showDraftEntityComposer
                        ? html`
                            <div class="draft-composer">
                                <div style="font-weight:600;font-size:var(--text-sm);">${this.t('ai_analysis_modal.composer_add_entity_title')}</div>
                                <platform-field
                                    type="enum"
                                    mode="edit"
                                    label=${this.t('ai_analysis_modal.kind_entity_type')}
                                    .value=${this._newEntityType}
                                    .config=${{ values: typeOpts }}
                                    pill-density="compact"
                                    ?disabled=${typesBusy || this._draftSaveOp.busy}
                                    @change=${(e) => this._onNewEntityTypeChange(e.detail)}
                                ></platform-field>
                                ${showNewSubtypeField
                                    ? html`
                                        <platform-field
                                            type="enum"
                                            mode="edit"
                                            label=${this.t('ai_analysis_modal.kind_entity_subtype')}
                                            .value=${this._newEntitySubtype}
                                            .config=${{ values: newSubOpts }}
                                            pill-density="compact"
                                            ?disabled=${typesBusy || this._draftSaveOp.busy}
                                            @change=${(e) => {
                                                const v = e.detail && typeof e.detail.value === 'string' ? e.detail.value : '';
                                                this._newEntitySubtype = v;
                                            }}
                                        ></platform-field>
                                    `
                                    : nothing}
                                <platform-field
                                    type="string"
                                    mode="edit"
                                    label=${this.t('ai_analysis_modal.add_entity_name_label')}
                                    placeholder=${this.t('ai_analysis_modal.add_entity_name_placeholder')}
                                    .value=${this._newEntityName}
                                    ?disabled=${this._draftSaveOp.busy}
                                    @change=${(e) => {
                                        const v = e.detail && typeof e.detail.value === 'string' ? e.detail.value : '';
                                        this._newEntityName = v;
                                    }}
                                ></platform-field>
                                <div class="draft-composer-actions">
                                    <button
                                        type="button"
                                        class="btn-inline"
                                        ?disabled=${typesBusy || this._draftSaveOp.busy}
                                        @click=${() => this._onAddDraftEntity()}
                                    >
                                        ${this.t('ai_analysis_modal.add_entity_btn')}
                                    </button>
                                </div>
                            </div>
                        `
                        : nothing}
                </article>
                <article class="block">
                    <div class="block-title-row">
                        <h3 class="block-title">
                            <platform-icon name="git-branch" size="14"></platform-icon>
                            ${this.t('ai_analysis_modal.suggested_relationships_title')}
                        </h3>
                        <button
                            type="button"
                            class="icon-btn"
                            title=${this.t('ai_analysis_modal.composer_toggle_rel')}
                            ?disabled=${this._draftSaveOp.busy}
                            @click=${() => { this._showDraftRelComposer = !this._showDraftRelComposer; }}
                        >
                            <platform-icon name="plus" size="16"></platform-icon>
                        </button>
                    </div>
                    ${relationships.length === 0
                        ? html`<div class="hint" style="color: var(--text-tertiary); font-size: var(--text-sm);">${this.t('ai_analysis_modal.no_relationships')}</div>`
                        : html`<div class="items-list">${relationships.map((r) => this._renderRelRow(r, draft))}</div>`}
                    ${this._showDraftRelComposer
                        ? html`
                            <div class="draft-composer">
                                <div style="font-weight:600;font-size:var(--text-sm);">${this.t('ai_analysis_modal.composer_add_rel_title')}</div>
                                <platform-field
                                    type="enum"
                                    mode="edit"
                                    label=${this.t('ai_analysis_modal.rel_source_label')}
                                    .value=${this._newRelSource}
                                    .config=${{ values: this._draftEndpointEnumValues(draft) }}
                                    pill-density="compact"
                                    ?disabled=${relTypesBusy || this._draftSaveOp.busy}
                                    @change=${(e) => {
                                        const v = e.detail && typeof e.detail.value === 'string' ? e.detail.value : '';
                                        this._newRelSource = v;
                                    }}
                                ></platform-field>
                                <platform-field
                                    type="enum"
                                    mode="edit"
                                    label=${this.t('ai_analysis_modal.rel_target_label')}
                                    .value=${this._newRelTarget}
                                    .config=${{ values: this._draftEndpointEnumValues(draft) }}
                                    pill-density="compact"
                                    ?disabled=${relTypesBusy || this._draftSaveOp.busy}
                                    @change=${(e) => {
                                        const v = e.detail && typeof e.detail.value === 'string' ? e.detail.value : '';
                                        this._newRelTarget = v;
                                    }}
                                ></platform-field>
                                <platform-field
                                    type="enum"
                                    mode="edit"
                                    label=${this.t('ai_analysis_modal.rel_type_label')}
                                    .value=${this._newRelType}
                                    .config=${relTypeCfg}
                                    pill-density="compact"
                                    ?disabled=${relTypesBusy || this._draftSaveOp.busy}
                                    @change=${(e) => {
                                        const v = e.detail && typeof e.detail.value === 'string' ? e.detail.value : '';
                                        this._newRelType = v;
                                    }}
                                ></platform-field>
                                <div class="draft-composer-actions">
                                    <button
                                        type="button"
                                        class="btn-inline"
                                        ?disabled=${relTypesBusy || this._draftSaveOp.busy}
                                        @click=${() => this._onAddDraftRelationship(draft)}
                                    >
                                        ${this.t('ai_analysis_modal.add_rel_btn')}
                                    </button>
                                </div>
                            </div>
                        `
                        : nothing}
                </article>
            </section>
        `;
    }

    _summaryText(entity, draft) {
        if (draft && draft.note && typeof draft.note.description === 'string' && draft.note.description.length > 0) {
            return draft.note.description;
        }
        if (typeof entity.description === 'string' && entity.description.length > 0) {
            return entity.description;
        }
        return this.t('ai_analysis_modal.summary_empty');
    }

    _renderAttrAddComposer(draftId, item) {
        if (!(draftId in this._attrAddUiById)) {
            return nothing;
        }
        const ui = this._attrAddUi(draftId);
        const valueFieldType = this._customAttrEditorType(ui.type);
        return html`
            <div class="attr-add-composer">
                <div class="attr-add-composer-title">${this.t('ai_analysis_modal.attr_add_title')}</div>
                <div class="attr-add-composer-grid">
                    <platform-field
                        type="string"
                        mode="edit"
                        .label=${this.t('ai_analysis_modal.attr_add_key_label')}
                        .placeholder=${this.t('ai_analysis_modal.attr_add_key_placeholder')}
                        .value=${ui.key}
                        pill-density="compact"
                        ?disabled=${this._draftSaveOp.busy}
                        @change=${(e) => this._onAttrAddKeyChange(draftId, e.detail)}
                    ></platform-field>
                    <platform-field
                        type="enum"
                        mode="edit"
                        .label=${this.t('ai_analysis_modal.attr_add_type_label')}
                        .value=${ui.type}
                        .config=${this._attrFieldTypeEnumConfig()}
                        pill-density="compact"
                        ?disabled=${this._draftSaveOp.busy}
                        @change=${(e) => this._onAttrAddTypeChange(draftId, e.detail)}
                    ></platform-field>
                </div>
                <platform-field
                    .type=${valueFieldType}
                    mode="edit"
                    .label=${this.t('ai_analysis_modal.attr_add_value_label')}
                    .value=${ui.value}
                    .config=${this._customAttrConfig(ui.type)}
                    pill-density="compact"
                    ?disabled=${this._draftSaveOp.busy}
                    @change=${(e) => this._onAttrAddValueChange(draftId, e.detail)}
                ></platform-field>
                ${ui.error.length > 0
                    ? html`<p class="attr-field-error">${ui.error}</p>`
                    : nothing}
                <div class="attr-add-composer-actions">
                    <button
                        type="button"
                        class="btn-inline"
                        ?disabled=${this._draftSaveOp.busy}
                        @click=${() => this._closeAttrAddUi(draftId)}
                    >
                        ${this.t('ai_analysis_modal.attr_add_cancel')}
                    </button>
                    <button
                        type="button"
                        class="btn-inline"
                        ?disabled=${this._draftSaveOp.busy}
                        @click=${() => this._onAddCustomAttr(draftId, item)}
                    >
                        ${this.t('ai_analysis_modal.attr_add_btn')}
                    </button>
                </div>
            </div>
        `;
    }

    _renderDraftAttributeFields(draftId, item) {
        const type = this._schemaTypeForDraftRow(item, draftId);
        const schema = this._attributesSchema(type);
        const attrs = this._effectiveAttrsForDraftRow(draftId, item);
        const knownKeys = new Set(schema.map((row) => row.key));
        const rows = [...schema];
        const customTypes = _isObject(this._customAttrTypesById[draftId])
            ? this._customAttrTypesById[draftId]
            : {};
        for (const [key, value] of Object.entries(attrs)) {
            if (knownKeys.has(key)) {
                continue;
            }
            const storedCustomType = typeof customTypes[key] === 'string' && CUSTOM_ATTR_FIELD_TYPES.includes(customTypes[key])
                ? customTypes[key]
                : '';
            const inferredType = storedCustomType.length > 0
                ? this._customAttrEditorType(storedCustomType)
                : this._inferAttrFieldType(key, value);
            rows.push({
                key,
                def: { type: inferredType, label: key },
                required: false,
                custom: true,
                customType: storedCustomType,
            });
        }
        const addComposer = this._renderAttrAddComposer(draftId, item);
        if (rows.length === 0 && !(draftId in this._attrAddUiById)) {
            return html`
                <div class="attr-fields-editor">
                    <div class="attr-schema-empty">${this.t('ai_analysis_modal.attrs_schema_empty')}</div>
                </div>
            `;
        }
        const errors = _isObject(this._attrValidationErrorsById[draftId])
            ? this._attrValidationErrorsById[draftId]
            : {};
        return html`
            <div class="attr-fields-editor">
                ${rows.length === 0
                    ? html`<div class="attr-schema-empty">${this.t('ai_analysis_modal.attrs_schema_empty')}</div>`
                    : nothing}
                ${rows.map(({ key, def, required, custom, customType }) => {
                    const fieldType = this._fieldType(def, key);
                    const readOnlyExternal = key === 'external_refs';
                    const value = Object.prototype.hasOwnProperty.call(attrs, key) ? attrs[key] : null;
                    const hintText = _isObject(def) && typeof def.description === 'string' && def.description.length > 0
                        ? def.description
                        : '';
                    const label = this._fieldLabel(key, def);
                    const error = typeof errors[key] === 'string' ? errors[key] : '';
                    const removable = custom === true
                        && typeof customType === 'string'
                        && customType.length > 0
                        && !readOnlyExternal;
                    const config = custom === true && typeof customType === 'string'
                        ? this._customAttrConfig(customType)
                        : this._fieldConfig(def);
                    return html`
                        <div class="attr-field-row ${removable ? 'with-action' : ''}">
                            <div class="attr-field-main ${required ? 'is-required' : ''}">
                                <platform-field
                                    .type=${fieldType}
                                    .value=${value}
                                    mode="edit"
                                    .label=${label}
                                    .hint=${hintText}
                                    .config=${config}
                                    pill-density="compact"
                                    ?disabled=${readOnlyExternal || this._draftSaveOp.busy}
                                    @change=${readOnlyExternal ? undefined : (event) => this._onAttrFieldChange(draftId, item, key, event)}
                                ></platform-field>
                                ${required
                                    ? html`
                                        <span
                                            class="attr-required-mark"
                                            title=${this.t('ai_analysis_modal.attr_field_required')}
                                            aria-label=${this.t('ai_analysis_modal.attr_field_required')}
                                        >*</span>
                                    `
                                    : nothing}
                                ${error.length > 0
                                    ? html`<p class="attr-field-error">${error}</p>`
                                    : nothing}
                            </div>
                            ${removable
                                ? html`
                                    <button
                                        type="button"
                                        class="icon-btn"
                                        title=${this.t('ai_analysis_modal.attr_remove_tooltip')}
                                        ?disabled=${this._draftSaveOp.busy}
                                        @click=${() => this._removeAttrField(draftId, item, key)}
                                    >
                                        <platform-icon name="close" size="12"></platform-icon>
                                    </button>
                                `
                                : nothing}
                        </div>
                    `;
                })}
                ${addComposer}
            </div>
        `;
    }

    _renderEntityRow(item, entity, draft) {
        const draftId = typeof item.draft_entity_id === 'string' && item.draft_entity_id.length > 0
            ? item.draft_entity_id
            : item.name;
        const removed = this._isPendingRemoveEntity(draftId);
        const expanded = this._attrsExpandedIds.indexOf(draftId) !== -1;
        const name = typeof item.name === 'string' && item.name.length > 0
            ? item.name
            : this.t('ai_analysis_modal.existing_entity_fallback');
        const subtitle = this._entitySubtitleDraft(item, draftId);
        const dedup = this._dedupBadge(item);
        const applyErr = entity !== null ? this._failureMessageForDraft(entity, draftId) : '';
        const pendingAttr = draftId in this._pendingAttrPatches;
        const pendingKind = draftId in this._pendingKindPatches;
        const pendingRow = pendingAttr || pendingKind;
        const validationErrors = _isObject(this._attrValidationErrorsById[draftId])
            ? this._attrValidationErrorsById[draftId]
            : {};
        const hasValidationError = Object.keys(validationErrors).length > 0;
        const showAttrsToggle = true;
        const attrAddOpen = draftId in this._attrAddUiById;

        const effIconType = this._effectiveEntityTypeFromItem(item, draftId);
        const kindUi = this._kindUiById[draftId];
        const typeEnumVal = kindUi && typeof kindUi.entity_type === 'string'
            ? kindUi.entity_type
            : this._effectiveEntityTypeFromItem(item, draftId);
        const subEnumVal = kindUi && typeof kindUi.entity_subtype === 'string'
            ? kindUi.entity_subtype
            : this._effectiveEntitySubtypeFromItem(item, draftId);

        const rowExtra = applyErr.length > 0 || pendingRow || hasValidationError ? 'has-apply-error' : '';
        const typeOpts = this._allTypeEnumOptions();
        const subOpts = this._subtypeEnumOptions(typeEnumVal);
        const showSubtypeField = subOpts.some((o) => o.value !== '');
        const typesBusy = this._entityTypes.loading === true && typeOpts.length === 0;

        return html`
            <div class="item-row ${removed ? 'removed' : ''} ${rowExtra}">
                <div class="icon">
                    <platform-icon name=${this._iconForType(effIconType)} size="14"></platform-icon>
                </div>
                <div class="meta">
                    <div class="name">${name}</div>
                    <div class="sub">
                        ${subtitle}
                        ${applyErr.length > 0
                            ? html`<span style="display:block;color:var(--error);margin-top:4px;">${applyErr}</span>`
                            : nothing}
                        ${pendingRow
                            ? html`<span style="display:block;color:var(--accent);margin-top:4px;font-size:var(--text-xs);">${this.t('ai_analysis_modal.row_edit_pending')}</span>`
                            : nothing}
                    </div>
                </div>
                <div class="actions">
                    ${dedup}
                    <button
                        type="button"
                        class="icon-btn"
                        title=${attrAddOpen
                            ? this.t('ai_analysis_modal.attr_add_hide')
                            : this.t('ai_analysis_modal.attr_add_toggle')}
                        ?disabled=${removed || this._draftSaveOp.busy}
                        @click=${() => this._toggleAttrAdd(draftId, item)}
                    >
                        <platform-icon name=${attrAddOpen ? 'close' : 'plus'} size="12"></platform-icon>
                    </button>
                    ${showAttrsToggle
                        ? html`
                            <button
                                type="button"
                                class="icon-btn"
                                title=${expanded ? this.t('ai_analysis_modal.toggle_attrs_hide') : this.t('ai_analysis_modal.toggle_attrs_show')}
                                @click=${() => this._toggleAttrs(draftId, draft)}
                            >
                                <platform-icon name=${expanded ? 'chevron-up' : 'chevron-down'} size="12"></platform-icon>
                            </button>
                        `
                        : nothing}
                    <button
                        type="button"
                        class="icon-btn"
                        title=${removed ? this.t('ai_analysis_modal.action_undo') : this.t('ai_analysis_modal.action_remove')}
                        @click=${() => this._onEntityRowRemoveClick(draftId, draft)}
                    >
                        <platform-icon name=${removed ? 'rotate-ccw' : 'close'} size="12"></platform-icon>
                    </button>
                </div>
                ${expanded
                    ? html`
                        <div class="entity-expanded">
                            <div class="draft-kind-fields">
                                <platform-field
                                    type="enum"
                                    mode="edit"
                                    label=${this.t('ai_analysis_modal.kind_entity_type')}
                                    .value=${typeEnumVal}
                                    .config=${{ values: typeOpts }}
                                    pill-density="compact"
                                    ?disabled=${typesBusy || this._draftSaveOp.busy}
                                    @change=${(e) => this._onDraftEntityTypeChange(draftId, item, e.detail)}
                                ></platform-field>
                                ${showSubtypeField
                                    ? html`
                                        <platform-field
                                            type="enum"
                                            mode="edit"
                                            label=${this.t('ai_analysis_modal.kind_entity_subtype')}
                                            .value=${subEnumVal}
                                            .config=${{ values: subOpts }}
                                            pill-density="compact"
                                            ?disabled=${typesBusy || this._draftSaveOp.busy}
                                            @change=${(e) => this._onDraftEntitySubtypeChange(draftId, item, e.detail)}
                                        ></platform-field>
                                    `
                                    : nothing}
                            </div>
                            ${this._renderDraftAttributeFields(draftId, item)}
                        </div>
                    `
                    : nothing}
            </div>
        `;
    }

    _renderRelRow(rel, draft) {
        const draftId = rel.draft_relationship_id;
        const removed = this._isPendingRemoveRel(draftId);
        const sourceName = this._draftEntityName(draft, rel.source_draft_entity_id);
        const targetName = this._draftEntityName(draft, rel.target_draft_entity_id);
        const relType = typeof rel.relationship_type === 'string' && rel.relationship_type.length > 0
            ? rel.relationship_type
            : this.t('ai_analysis_modal.relationship_fallback');

        return html`
            <div class="item-row ${removed ? 'removed' : ''}">
                <div class="icon">
                    <platform-icon name="git-branch" size="14"></platform-icon>
                </div>
                <div class="meta">
                    <div class="name">${this.t('ai_analysis_modal.relationship_line', { source: sourceName, target: targetName })}</div>
                    <div class="sub">${relType}</div>
                </div>
                <div class="actions">
                    <button
                        type="button"
                        class="icon-btn"
                        title=${removed ? this.t('ai_analysis_modal.action_undo') : this.t('ai_analysis_modal.action_remove')}
                        @click=${() => this._onRelRowRemoveClick(draftId)}
                    >
                        <platform-icon name=${removed ? 'rotate-ccw' : 'close'} size="12"></platform-icon>
                    </button>
                </div>
            </div>
        `;
    }

    _dedupBadge(item) {
        if (item.dedup_action === 'merge') {
            const score = typeof item.dedup_confidence === 'number' && Number.isFinite(item.dedup_confidence)
                ? Math.round(item.dedup_confidence * 100)
                : null;
            const label = score !== null
                ? `${this.t('ai_analysis_modal.dedup_existing')} ${score}%`
                : this.t('ai_analysis_modal.dedup_existing');
            return html`<span class="badge dedup-existing">${label}</span>`;
        }
        if (item.dedup_action === 'create') {
            return html`<span class="badge dedup-new">${this.t('ai_analysis_modal.dedup_new')}</span>`;
        }
        return nothing;
    }

    _iconForType(entityType) {
        if (entityType === 'task') return 'check-square';
        if (entityType === 'member') return 'user';
        if (entityType === 'company') return 'building';
        if (entityType === 'meeting') return 'calendar';
        if (entityType === 'note') return 'doc-detail';
        return 'circle';
    }

    _draftEntityName(draft, draftEntityId) {
        if (!_isObject(draft) || typeof draftEntityId !== 'string') {
            return this.t('ai_analysis_modal.existing_entity_fallback');
        }
        const row = this._draftEntityRow(draft, draftEntityId);
        if (_isObject(row) && typeof row.name === 'string' && row.name.length > 0) {
            return row.name;
        }
        if (_isObject(draft.note) && draft.note.draft_entity_id === draftEntityId) {
            const nm = typeof draft.note.name === 'string' ? draft.note.name.trim() : '';
            return nm.length > 0 ? nm : this.t('ai_analysis_modal.endpoint_note_summary');
        }
        const known = draft.known_entity_id_map;
        if (_isObject(known) && draftEntityId in known) {
            return this.t('ai_analysis_modal.endpoint_known_entity', {
                id: draftEntityId.length > 8 ? `${draftEntityId.slice(0, 8)}…` : draftEntityId,
            });
        }
        return this.t('ai_analysis_modal.existing_entity_fallback');
    }

    renderFooter() {
        const draft = this._draft();
        const hasDraft = draft !== null;
        const pending = this._hasPendingChanges();
        const savingPending = this._draftSaveOp.busy;
        const analyzing = this._analyzeOp.busy;
        const discarding = this._draftDiscardOp.busy;
        const dismissingErr = this._applyErrorDismissOp.busy;
        const footerBusy = analyzing || savingPending || discarding || dismissingErr;

        return html`
            <div class="footer-actions">
                <div class="left">
                    ${this._saveError.length > 0
                        ? html`<span class="submit-error">${this._saveError}</span>`
                        : nothing}
                </div>
                <div class="right">
                    <button type="button" class="btn" @click=${() => this.close()}>
                        ${this.t('ai_analysis_modal.action_close')}
                    </button>
                    ${hasDraft
                        ? html`
                            <button
                                type="button"
                                class="btn"
                                ?disabled=${footerBusy}
                                @click=${() => this._onAnalyze()}
                            >
                                ${analyzing
                                    ? this.t('ai_analysis_modal.action_re_analyzing')
                                    : this.t('ai_analysis_modal.action_re_analyze')}
                            </button>
                            ${pending
                                ? html`
                                    <button
                                        type="button"
                                        class="btn"
                                        ?disabled=${footerBusy}
                                        @click=${() => this._onSavePending()}
                                    >
                                        ${savingPending
                                            ? this.t('ai_analysis_modal.action_saving')
                                            : this.t('ai_analysis_modal.action_save_changes')}
                                    </button>
                                `
                                : nothing}
                            <button
                                type="button"
                                class="btn btn-primary"
                                ?disabled=${footerBusy}
                                @click=${() => this._onApply()}
                            >
                                ${this.t('ai_analysis_modal.action_apply')}
                            </button>
                        `
                        : nothing}
                </div>
            </div>
        `;
    }
}

customElements.define('crm-ai-analysis-modal', CRMAiAnalysisModal);
registerModalKind(CRMAiAnalysisModal.modalKind, 'crm-ai-analysis-modal');
