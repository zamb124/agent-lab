/**
 * CRMNamespaceDetailPage — настройки конкретного namespace.
 *
 * Маршрут: `/crm/namespaces/:itemId` (parent: `namespaces`).
 *
 * UX-аналог `templates-page`, но работает с **instance** namespace и его
 * привязанными типами. Список типов пространства — GET `entity_types?namespace=itemId`.
 *
 * Источники данных:
 *   - useResource('crm/namespaces')         — метаданные namespace (описание и др.).
 *   - useOp('crm/namespace_editability')    — статистика, locked_type_ids,
 *     all_namespaces_type_ids (типы для всех namespace, которых ещё нет здесь) и current_allowed_type_ids.
 *   - useResource('crm/entity_types', { autoload: false }) — load({ namespace: itemId }).
 *   - useOp('crm/entity_type_update')       — PUT с query namespace.
 *   - useOp('crm/template_schema_options')  — опции SchemaFieldBuilder
 *                                             (общие для шаблонов и типов).
 *   - useOp('crm/namespace_update')         — body.allowed_type_ids: сервис клонирует/удаляет строки
 *     EntityType в этом namespace; после успеха перезапускается editability.
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
import '@platform/lib/components/platform-empty-state.js';
import '@platform/lib/components/platform-breadcrumbs.js';
import '@platform/lib/components/platform-icon.js';
import '@platform/lib/components/platform-button.js';
import '@platform/lib/components/platform-palette-color-picker.js';
import '@platform/lib/components/platform-help-hint.js';
import '@platform/lib/components/platform-switch.js';
import '@platform/lib/components/platform-cron-field.js';
import '@platform/lib/components/fields/platform-field.js';
import { platformConfirm } from '@platform/lib/components/platform-confirm-modal.js';

import '../components/entity-type-editor.js';
import '../components/namespace-note-defaults-fields.js';
import {
    normalizeDefaultNoteVoiceMode,
    parseNoteVoiceDefaultsFromCrmSettings,
} from '../_helpers/namespace-crm-note-defaults.js';
import {
    DEFAULT_SUGGESTS_CRON,
    buildSuggestsSettingsPayload,
    parseSuggestsSettingsFromCrmSettings,
} from '../_helpers/namespace-crm-suggests.js';
import {
    buildDefaultSidebarNav,
    sidebarNavTreeToApiPayload,
} from '../_helpers/build-default-sidebar-nav.js';
import {
    normalizeSchemaRows,
    buildSchemaFromRows,
} from '../components/schema-field-builder.js';
import { isSchemaFieldRow, type SchemaFieldRow } from '../components/schema-field-builder.js';
import { entityTypeNoteSubtreeLocked } from '../_helpers/entity-type-note-subtree-lock.js';
import {
    CRM_ENTITY_TYPE_CREATE_MODE_CHOSEN,
    CRM_ENTITY_TYPE_PRESET_PICKER_APPLIED,
} from '../_helpers/entity-type-create-events.js';
import { buildEntityTypeDraftFromTemplateTypeItem } from '../_helpers/entity-type-draft-from-preset.js';
import { isPlainRecord } from '@platform/lib/events/payload.js';
import type {
    CSSResultGroup,
    PropertyDeclarations,
    PropertyValues,
    TemplateResult,
} from 'lit';
import type {
    OpController,
    ResourceController,
} from '@platform/lib/base/use-resource.js';

const DEFAULT_TYPE_DRAFT = Object.freeze({
    type_id: '',
    name: '',
    description: '',
    prompt: '',
    required_fields_rows: Object.freeze([]),
    optional_fields_rows: Object.freeze([]),
    parent_type_id: '',
    icon: '',
    color: '',
    is_event: false,
    check_duplicates: true,
    is_context_anchor: false,
    is_voice_target: false,
    weight_coefficient: '1.0',
});

function displayText(value: unknown): string {
    if (value === undefined || value === null || value === false || value === 0 || value === '') return '';
    if (typeof value === 'number' && !Number.isFinite(value)) return '';
    return String(value);
}

function blankToNull(value: string): string | null {
    const trimmed = value.trim();
    return trimmed.length === 0 ? null : trimmed;
}

interface CrmTypeDraft {
    type_id: string;
    name: string;
    description: string;
    prompt: string;
    required_fields_rows: SchemaFieldRow[];
    optional_fields_rows: SchemaFieldRow[];
    parent_type_id: string;
    icon: string;
    color: string;
    is_event: boolean;
    check_duplicates: boolean;
    is_context_anchor: boolean;
    is_voice_target: boolean;
    weight_coefficient: string;
}

function anyRecord(value: unknown): Record<string, unknown> | null {
    return isPlainRecord(value) ? value : null;
}

function eventRecord(event: { payload: unknown }, field: 'result' | 'item'): Record<string, unknown> | null {
    if (!isPlainRecord(event.payload)) return null;
    const value = event.payload[field];
    return isPlainRecord(value) ? value : null;
}

function schemaRows(value: unknown): SchemaFieldRow[] {
    if (!Array.isArray(value)) return [];
    if (!value.every(isSchemaFieldRow)) {
        throw new Error('entity type draft: schema rows are invalid');
    }
    return value;
}

function makeTypeDraft(overrides: Record<string, unknown> = {}): CrmTypeDraft {
    const draft: CrmTypeDraft = {
        ...DEFAULT_TYPE_DRAFT,
        required_fields_rows: [],
        optional_fields_rows: [],
    };
    if (typeof overrides.type_id === 'string') draft.type_id = overrides.type_id;
    if (typeof overrides.name === 'string') draft.name = overrides.name;
    if (typeof overrides.description === 'string') draft.description = overrides.description;
    if (typeof overrides.prompt === 'string') draft.prompt = overrides.prompt;
    if (typeof overrides.parent_type_id === 'string') draft.parent_type_id = overrides.parent_type_id;
    if (typeof overrides.icon === 'string') draft.icon = overrides.icon;
    if (typeof overrides.color === 'string') draft.color = overrides.color;
    if (typeof overrides.is_event === 'boolean') draft.is_event = overrides.is_event;
    if (typeof overrides.check_duplicates === 'boolean') draft.check_duplicates = overrides.check_duplicates;
    if (typeof overrides.is_context_anchor === 'boolean') draft.is_context_anchor = overrides.is_context_anchor;
    if (typeof overrides.is_voice_target === 'boolean') draft.is_voice_target = overrides.is_voice_target;
    if (typeof overrides.weight_coefficient === 'string') draft.weight_coefficient = overrides.weight_coefficient;
    draft.required_fields_rows = schemaRows(overrides.required_fields_rows);
    draft.optional_fields_rows = schemaRows(overrides.optional_fields_rows);
    return draft;
}

export class CRMNamespaceDetailPage extends PlatformPage {
    static i18nNamespace = 'crm';

    static override properties: PropertyDeclarations = {
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
        _suggestsEnabled: { state: true },
        _suggestsCron: { state: true },
        _suggestsScheduleTaskId: { state: true },
        _suggestsSaveBusy: { state: true },
    };
    declare itemId: string;
    declare _description: string;
    declare _defaultNoteVoiceMode: string;
    declare _showNoteVoiceUi: boolean;
    declare _allowedTypeIds: string[];
    declare _typeDraft: CrmTypeDraft;
    declare _editingTypeId: string;
    declare _typeFormOpen: boolean;
    declare _schemaOptions: Record<string, unknown> | null;
    declare _savingMeta: boolean;
    declare _savingAllowed: boolean;
    declare _savingType: boolean;
    declare _creatingType: boolean;
    declare _sidebarMenuBusy: boolean;
    declare _suggestsEnabled: boolean;
    declare _suggestsCron: string;
    declare _suggestsScheduleTaskId: string;
    declare _suggestsSaveBusy: boolean;

    static override styles: CSSResultGroup = [
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
            .namespace-detail-stack {
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

            .namespace-detail-left-col {
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
            .meta-row-label {
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
                font-weight: 600;
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
                color: var(--error);
                border-color: var(--error);
            }
            .btn-danger:hover:not(:disabled) {
                background: var(--error);
                color: white;
            }
            .btn:disabled { opacity: 0.5; cursor: not-allowed; }

            platform-empty-state { padding: var(--space-6); }
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
            .switch-row {
                display: flex;
                align-items: center;
                gap: var(--space-2);
                flex-wrap: wrap;
            }
            .switch-row platform-switch {
                flex: 1;
                min-width: 0;
            }
        `,
    ];

    private _namespaces: ResourceController;
    private _editabilityOp: OpController;
    private _namespaceUpdateOp: OpController;
    private _entityTypes: ResourceController;
    private _entityTypeUpdateOp: OpController;
    private _schemaOptionsOp: OpController;
    private _lastRequestedId: string;

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
        this._suggestsEnabled = false;
        this._suggestsCron = DEFAULT_SUGGESTS_CRON;
        this._suggestsScheduleTaskId = '';
        this._suggestsSaveBusy = false;
        this._lastRequestedId = '';

        this._namespaces = this.useResource('crm/namespaces');
        this._editabilityOp = this.useOp('crm/namespace_editability');
        this._namespaceUpdateOp = this.useOp('crm/namespace_update');
        this._entityTypes = this.useResource('crm/entity_types', { autoload: false });
        this._entityTypeUpdateOp = this.useOp('crm/entity_type_update');
        this._schemaOptionsOp = this.useOp('crm/template_schema_options');
    }

    _fieldLabelWithHint(labelKey: string, hintKey: string): TemplateResult {
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

    override connectedCallback(): void {
        super.connectedCallback();
        this._schemaOptionsOp.run(null);
        this.useEvent(this._schemaOptionsOp.op.events.SUCCEEDED, (event) => {
            const result = eventRecord(event, 'result');
            if (result === null) return;
            this._schemaOptions = result;
        });
        this.useEvent(this._namespaces.resource.events.ITEM_LOADED, (event) => {
            const item = eventRecord(event, 'item');
            if (item === null || item.name !== this.itemId) return;
            this._hydrateFromNamespace(item);
        });
        this.useEvent(this._namespaces.resource.events.LIST_LOADED, () => {
            const item = this._namespaces.byId[this.itemId];
            if (item !== undefined) this._hydrateFromNamespace(item);
        });
        this.useEvent(this._editabilityOp.op.events.SUCCEEDED, (event) => {
            const result = eventRecord(event, 'result');
            if (result === null || result.namespace !== this.itemId) return;
            const ids = result.current_allowed_type_ids;
            if (!Array.isArray(ids)) {
                throw new Error('namespace_editability: current_allowed_type_ids must be an array');
            }
            this._allowedTypeIds = ids.filter((id) => typeof id === 'string' && id.length > 0);
        });
        this.useEvent(this._namespaceUpdateOp.op.events.SUCCEEDED, (event) => {
            this._savingMeta = false;
            this._savingAllowed = false;
            this._sidebarMenuBusy = false;
            this._suggestsSaveBusy = false;
            const result = eventRecord(event, 'result');
            if (result !== null && result.name === this.itemId) {
                this._hydrateFromNamespace(result);
            }
        });
        this.useEvent(this._namespaceUpdateOp.op.events.FAILED, () => {
            this._savingMeta = false;
            this._savingAllowed = false;
            this._sidebarMenuBusy = false;
            this._suggestsSaveBusy = false;
        });
        this.useEvent(this._entityTypeUpdateOp.op.events.SUCCEEDED, () => {
            this._savingType = false;
            this._typeFormOpen = false;
            this._typeDraft = makeTypeDraft();
            this._editingTypeId = '';
        });
        this.useEvent(this._entityTypeUpdateOp.op.events.FAILED, () => {
            this._savingType = false;
        });
        this.useEvent(this._entityTypes.resource.events.CREATED, (event) => {
            this._creatingType = false;
            this._typeFormOpen = false;
            this._typeDraft = makeTypeDraft();
            this._editingTypeId = '';
            const item = eventRecord(event, 'item');
            if (item === null || typeof item.type_id !== 'string') return;
            const next = this._allowedTypeIds.includes(item.type_id)
                ? this._allowedTypeIds
                : [...this._allowedTypeIds, item.type_id];
            this._allowedTypeIds = next;
            this._namespaceUpdateOp.run({
                name: this.itemId,
                allowed_type_ids: next,
            });
        });
        this.useEvent(this._entityTypes.resource.events.CREATE_FAILED, () => {
            this._creatingType = false;
        });
        this.useEvent(CRM_ENTITY_TYPE_CREATE_MODE_CHOSEN, (event) => {
            const payload = isPlainRecord(event.payload) ? event.payload : null;
            if (payload === null) {
                throw new Error('CRMNamespaceDetailPage: create_mode_chosen payload required');
            }
            if (payload.mode === 'blank') {
                this._openNewTypeForm();
                return;
            }
            if (payload.mode === 'from_presets') {
                this.openModal('crm.entity_type_preset_picker');
                return;
            }
            throw new Error('CRMNamespaceDetailPage: create_mode_chosen unknown mode');
        });
        this.useEvent(CRM_ENTITY_TYPE_PRESET_PICKER_APPLIED, (event) => {
            const payload = isPlainRecord(event.payload) ? event.payload : null;
            if (payload === null) {
                throw new Error('CRMNamespaceDetailPage: preset_picker_applied payload required');
            }
            const snap = anyRecord(payload.type_snapshot);
            if (snap === null || typeof snap.type_id !== 'string') {
                throw new Error('CRMNamespaceDetailPage: preset_picker_applied type_snapshot required');
            }
            this._editingTypeId = '';
            this._typeDraft = buildEntityTypeDraftFromTemplateTypeItem(
                snap,
                this._namespaceEntityTypeCatalogRows(),
                makeTypeDraft,
                { namespaceIds: false },
            );
            this._typeFormOpen = true;
        });
    }

    override willUpdate(changed: PropertyValues<this>): void {
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
        this._suggestsEnabled = false;
        this._suggestsCron = DEFAULT_SUGGESTS_CRON;
        this._suggestsScheduleTaskId = '';
        this._suggestsSaveBusy = false;
        this._namespaces.get(this.itemId);
        this._editabilityOp.run({ name: this.itemId });
        this._entityTypes.load({ namespace: this.itemId });
    }

    _namespace(): Record<string, unknown> | null {
        return anyRecord(this._namespaces.byId[this.itemId]);
    }

    _hydrateFromNamespace(item: Record<string, unknown>): void {
        this._description = typeof item.description === 'string' ? item.description : '';
        const crmSettings = isPlainRecord(item.crm_settings) ? item.crm_settings : null;
        const parsed = parseNoteVoiceDefaultsFromCrmSettings(crmSettings);
        this._defaultNoteVoiceMode = parsed.defaultNoteVoiceMode;
        this._showNoteVoiceUi = parsed.showNoteVoiceUi;
        const suggests = parseSuggestsSettingsFromCrmSettings(crmSettings);
        this._suggestsEnabled = suggests.enabled;
        this._suggestsCron = suggests.cron;
        this._suggestsScheduleTaskId = suggests.scheduleTaskId;
    }

    _onDescriptionChange(e: CustomEvent) {
        const v = e.detail.value;
        this._description = typeof v === 'string' ? v : '';
    }

    _onNoteDefaultVoiceFromChild(e: CustomEvent) {
        const d = e.detail;
        if (d === undefined || d === null || typeof d !== 'object' || typeof d.value !== 'string') {
            return;
        }
        const v = d.value;
        if (v === 'none' || v === 'last' || v === 'self') {
            this._defaultNoteVoiceMode = v;
        }
    }

    _onNoteVoiceShowUiFromChild(e: CustomEvent) {
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
            description: this._description.trim().length > 0 ? this._description.trim() : null,
            crm_settings: {
                default_note_voice: normalizeDefaultNoteVoiceMode(this._defaultNoteVoiceMode),
                show_note_voice_ui: this._showNoteVoiceUi === true,
            },
        });
    }

    _onSidebarNavReset() {
        this._sidebarMenuBusy = true;
        this._namespaceUpdateOp.run({
            name: this.itemId,
            crm_settings: { sidebar_navigation: null },
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
                groupGraph: this.t('sidebar.nav_group_graph'),
                graphView3d: this.t('graph.view_mode_3d'),
                graphViewMindmap: this.t('graph.view_mode_mindmap'),
            },
        });
        const payload = sidebarNavTreeToApiPayload(tree);
        this._sidebarMenuBusy = true;
        this._namespaceUpdateOp.run({
            name: this.itemId,
            crm_settings: { sidebar_navigation: payload },
        });
    }

    _onSuggestsSwitch(e: CustomEvent) {
        const d = isPlainRecord(e.detail) ? e.detail : null;
        if (!d || typeof d.value !== 'boolean') {
            throw new Error('suggests switch: expected detail.value (boolean)');
        }
        this._suggestsEnabled = d.value;
    }

    _onSuggestsCronInput(e: CustomEvent) {
        const d = isPlainRecord(e.detail) ? e.detail : null;
        if (!d || typeof d.value !== 'string') {
            throw new Error('suggests cron: expected detail.value (string)');
        }
        this._suggestsCron = d.value;
    }

    _onSaveSuggests() {
        const cronRaw = typeof this._suggestsCron === 'string' ? this._suggestsCron.trim() : '';
        if (this._suggestsEnabled && cronRaw.length === 0) {
            this.toast('namespace_detail_page.suggests_cron_required', { type: 'error' });
            return;
        }
        this._suggestsSaveBusy = true;
        this._namespaceUpdateOp.run({
            name: this.itemId,
            crm_settings: {
                suggests: buildSuggestsSettingsPayload({
                    enabled: this._suggestsEnabled,
                    cron: this._suggestsCron,
                }),
            },
        });
    }

    _onToggleType(typeId: unknown, allowed: boolean): void {
        if (typeof typeId !== 'string' || typeId.length === 0) return;
        if (this._typeIsAllNamespaces(typeId)) return;
        const next = allowed
            ? [...new Set([...this._allowedTypeIds, typeId])]
            : this._allowedTypeIds.filter((id) => id !== typeId);
        this._allowedTypeIds = next;
        this._savingAllowed = true;
        this._namespaceUpdateOp.run({
            name: this.itemId,
            allowed_type_ids: next,
        });
    }

    async _onRequestDisallowType(typeId: string): Promise<void> {
        if (typeof typeId !== 'string' || typeId.length === 0) return;
        if (this._typeIsAllNamespaces(typeId)) return;
        const confirmed = await platformConfirm(
            this.t('namespace_detail_page.confirm_remove_from_namespace_msg', { type_id: typeId }),
            {
                title: this.t('namespace_detail_page.confirm_remove_from_namespace_title'),
                variant: 'danger',
                confirmText: this.t('namespace_detail_page.action_disallow'),
                cancelText: this.t('templates_page.btn_cancel'),
            },
        );
        if (!confirmed) return;
        this._onToggleType(typeId, false);
    }

    _openNewTypeForm() {
        this._editingTypeId = '';
        this._typeDraft = makeTypeDraft();
        this._typeFormOpen = true;
    }

    _namespaceEntityTypeCatalogRows(): { type_id: string; parent_type_id: string }[] {
        const items = Array.isArray(this._entityTypes.items) ? this._entityTypes.items : [];
        return items.flatMap((row) => {
            if (!isPlainRecord(row) || typeof row.type_id !== 'string' || row.type_id.length === 0) {
                return [];
            }
            const parentTypeId = typeof row.parent_type_id === 'string' && row.parent_type_id.length > 0
                ? row.parent_type_id
                : '';
            return [{ type_id: row.type_id, parent_type_id: parentTypeId }];
        });
    }

    _editType(item: Record<string, unknown>): void {
        if (!item || typeof item.type_id !== 'string') {
            throw new Error('CRMNamespaceDetailPage._editType: item.type_id required');
        }
        this._editingTypeId = item.type_id;
        this._typeFormOpen = true;
        const catalogRows = this._namespaceEntityTypeCatalogRows();
        const parentId = typeof item.parent_type_id === 'string' ? item.parent_type_id : '';
        const noteLocked = entityTypeNoteSubtreeLocked(
            { type_id: item.type_id, parent_type_id: parentId },
            catalogRows,
        );
        this._typeDraft = {
            type_id: item.type_id,
            name: displayText(item.name),
            description: displayText(item.description),
            prompt: displayText(item.prompt),
            required_fields_rows: normalizeSchemaRows(item.required_fields && typeof item.required_fields === 'object' ? item.required_fields : {}),
            optional_fields_rows: normalizeSchemaRows(item.optional_fields && typeof item.optional_fields === 'object' ? item.optional_fields : {}),
            parent_type_id: parentId,
            icon: displayText(item.icon),
            color: displayText(item.color),
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

    _onTypeDraftChanged(event: CustomEvent) {
        const detail = event.detail;
        const next = detail !== null && typeof detail === 'object' && 'typeDraft' in detail
            ? detail.typeDraft
            : undefined;
        if (!next) return;
        this._typeDraft = next;
    }

    _onSchemaRowsChanged(event: CustomEvent) {
        const detail = isPlainRecord(event.detail) ? event.detail : null;
        if (detail === null) return;
        const section = detail.section;
        if (section !== 'required_fields_rows' && section !== 'optional_fields_rows') return;
        if (!Array.isArray(detail.rows)) return;
        this._typeDraft = { ...this._typeDraft, [section]: schemaRows(detail.rows) };
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
            (k: string, v?: Record<string, string>) => this.t(k, v),
        );
        const optionalFields = buildSchemaFromRows(
            this._typeDraft.optional_fields_rows,
            this.t('schema_sections.optional_fields'),
            this._schemaOptions,
            (k: string, v?: Record<string, string>) => this.t(k, v),
        );
        for (const key of Object.keys(requiredFields)) {
            if (Object.prototype.hasOwnProperty.call(optionalFields, key)) {
                throw new Error(this.t('errors.key_both_sections', { key }));
            }
        }
        const noteLocked = entityTypeNoteSubtreeLocked(this._typeDraft, this._namespaceEntityTypeCatalogRows());
        const body = {
            parent_type_id: blankToNull(this._typeDraft.parent_type_id),
            name,
            description: blankToNull(this._typeDraft.description),
            prompt: blankToNull(this._typeDraft.prompt),
            required_fields: requiredFields,
            optional_fields: optionalFields,
            icon: blankToNull(this._typeDraft.icon),
            color: blankToNull(this._typeDraft.color),
            is_event: this._typeDraft.is_event === true,
            check_duplicates: this._typeDraft.check_duplicates !== false,
            is_context_anchor: noteLocked ? false : this._typeDraft.is_context_anchor === true,
            is_voice_target: noteLocked ? false : this._typeDraft.is_voice_target === true,
            weight_coefficient: Number.parseFloat(this._typeDraft.weight_coefficient || '1') || 1,
        };
        if (this._editingTypeId.length > 0) {
            this._savingType = true;
            this._entityTypeUpdateOp.run({
                type_id: this._editingTypeId,
                namespace: this.itemId,
                ...body,
            });
            return;
        }
        this._creatingType = true;
        this._entityTypes.create({ type_id: typeId, namespace: this.itemId, ...body });
    }

    _getParentTypeOptions(): string[] {
        const items = Array.isArray(this._entityTypes.items) ? this._entityTypes.items : [];
        const ids = items
            .map((item) => (isPlainRecord(item) && typeof item.type_id === 'string' ? item.type_id : null))
            .filter((id): id is string => typeof id === 'string' && id.length > 0);
        return [...new Set(['note', 'task', ...ids])];
    }

    _typeIsLocked(typeId: string): boolean {
        const result = anyRecord(this._editabilityOp.lastResult);
        if (!result || !Array.isArray(result.locked_type_ids)) return false;
        return result.locked_type_ids.includes(typeId);
    }

    _typeIsAllNamespaces(typeId: string): boolean {
        const result = anyRecord(this._editabilityOp.lastResult);
        if (!result || !Array.isArray(result.all_namespaces_type_ids)) return false;
        return result.all_namespaces_type_ids.includes(typeId);
    }

    override render(): TemplateResult {
        if (typeof this.itemId !== 'string' || this.itemId.length === 0) {
            return html`<platform-empty-state icon="info" title=${this.t('namespace_detail_page.no_id')}></platform-empty-state>`;
        }
        const ns = this._namespace();
        if (ns === null) {
            return html`<platform-empty-state loading></platform-empty-state>`;
        }

        return html`
            <div class="breadcrumbs-wrap">
                <platform-breadcrumbs current-label=${ns.name}></platform-breadcrumbs>
            </div>
            <div class="header-wrap">
                <page-header
                    title=${ns.name}
                    subtitle=${this.t('namespace_detail_page.subtitle')}
                >
                    <platform-button
                        slot="actions"
                        variant="secondary"
                        type="button"
                        @click=${() => this.navigate('namespace_integrations', { itemId: this.itemId })}
                    >
                        <platform-icon name="integration" size="18"></platform-icon>
                        ${this.t('namespace_detail_page.link_integrations')}
                    </platform-button>
                </page-header>
            </div>
            <div class="scroll">
                <div class="namespace-detail-stack">
                    <div class="layout">
                        <div class="namespace-detail-left-col">
                            ${this._renderLeftPanel(ns)}
                            ${this._renderSidebarMenuPanel(ns)}
                            ${this._renderSuggestsPanel()}
                        </div>
                        ${this._renderRightPanel()}
                    </div>
                </div>
            </div>
        `;
    }

    _renderLeftPanel(ns: Record<string, unknown>): TemplateResult {
        const editabilityResult = this._editabilityOp.lastResult;
        const editability = anyRecord(editabilityResult);
        return html`
            <div class="panel">
                <div class="panel-header">
                    <span class="panel-title panel-title-row-hint">
                        <platform-icon name="folder" size="18"></platform-icon>
                        <span>${this.t('namespace_detail_page.meta_section')}</span>
                        <platform-help-hint
                            .text=${this.t('namespace_detail_page.meta_section_hint')}
                            label=${this.t('templates_page.field_hint_button_aria')}
                        ></platform-help-hint>
                    </span>
                </div>

                <div class="field">
                    ${this._fieldLabelWithHint(
                        'namespace_modal.label_name',
                        'namespace_detail_page.meta_name_hint',
                    )}
                    <div class="hint mono">${ns.name}</div>
                </div>

                <platform-field
                    type="text"
                    mode="edit"
                    .label=${this.t('namespace_modal.label_description')}
                    .hint=${this.t('namespace_detail_page.meta_description_hint')}
                    .placeholder=${this.t('namespace_modal.description_placeholder')}
                    .value=${this._description}
                    ?disabled=${this._savingMeta}
                    @change=${this._onDescriptionChange}
                ></platform-field>

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
                            <span class="meta-row-label">
                                <span>${this.t('namespace_modal.entity_count')}</span>
                                <platform-help-hint
                                    .text=${this.t('namespace_detail_page.meta_stat_entity_count_hint')}
                                    label=${this.t('templates_page.field_hint_button_aria')}
                                ></platform-help-hint>
                            </span>
                            <strong>${editability.entity_count}</strong>
                        </div>
                        <div class="meta-row">
                            <span class="meta-row-label">
                                <span>${this.t('namespace_modal.used_types')}</span>
                                <platform-help-hint
                                    .text=${this.t('namespace_detail_page.meta_stat_used_types_hint')}
                                    label=${this.t('templates_page.field_hint_button_aria')}
                                ></platform-help-hint>
                            </span>
                            <strong>${Array.isArray(editability.used_type_ids) ? editability.used_type_ids.length : 0}</strong>
                        </div>
                        <div class="meta-row">
                            <span class="meta-row-label">
                                <span>${this.t('namespace_modal.can_update_types')}</span>
                                <platform-help-hint
                                    .text=${this.t('namespace_detail_page.meta_stat_can_update_hint')}
                                    label=${this.t('templates_page.field_hint_button_aria')}
                                ></platform-help-hint>
                            </span>
                            <strong>${editability.can_update_allowed_types
                                ? this.t('namespace_modal.yes')
                                : this.t('namespace_modal.no')}</strong>
                        </div>
                    </div>
                ` : ''}
            </div>
        `;
    }

    _renderSidebarMenuPanel(ns: Record<string, unknown>): TemplateResult {
        const crmSettings = isPlainRecord(ns.crm_settings) ? ns.crm_settings : null;
        const custom = crmSettings !== null
            && Array.isArray(crmSettings.sidebar_navigation)
            && crmSettings.sidebar_navigation.length > 0;
        const modeHint = custom
            ? this.t('namespace_detail_page.sidebar_menu_mode_custom')
            : this.t('namespace_detail_page.sidebar_menu_mode_derived');
        return html`
            <div class="panel">
                <div class="panel-header">
                    <span class="panel-title panel-title-row-hint">
                        <platform-icon name="menu" size="18"></platform-icon>
                        <span>${this.t('namespace_detail_page.sidebar_menu_section')}</span>
                        <platform-help-hint
                            .text=${this.t('namespace_detail_page.sidebar_menu_section_hint')}
                            label=${this.t('templates_page.field_hint_button_aria')}
                        ></platform-help-hint>
                    </span>
                </div>
                <p class="hint">${this.t('namespace_detail_page.sidebar_menu_hint')}</p>
                <p class="hint mono">${modeHint}</p>
                <div class="actions-row">
                    <button
                        class="btn btn-soft"
                        type="button"
                        ?disabled=${this._sidebarMenuBusy}
                        @click=${this._onSidebarNavSnapshot}
                    >
                        ${this.t('namespace_detail_page.sidebar_menu_snapshot')}
                    </button>
                    <button
                        class="btn btn-danger"
                        type="button"
                        ?disabled=${this._sidebarMenuBusy || !custom}
                        @click=${this._onSidebarNavReset}
                    >
                        ${this.t('namespace_detail_page.sidebar_menu_reset')}
                    </button>
                </div>
            </div>
        `;
    }

    _renderSuggestsPanel(): TemplateResult {
        const disabled = this._suggestsSaveBusy
            || this._savingMeta
            || this._savingAllowed
            || this._sidebarMenuBusy;
        return html`
            <div class="panel">
                <div class="panel-header">
                    <span class="panel-title panel-title-row-hint">
                        <platform-icon name="sparkle" size="18"></platform-icon>
                        <span>${this.t('namespace_detail_page.suggests_section')}</span>
                        <platform-help-hint
                            .text=${this.t('namespace_detail_page.suggests_section_hint')}
                            label=${this.t('templates_page.field_hint_button_aria')}
                        ></platform-help-hint>
                    </span>
                </div>
                <p class="hint">${this.t('namespace_detail_page.suggests_hint')}</p>
                <div class="switch-row">
                    <platform-switch
                        size="sm"
                        label=${this.t('namespace_detail_page.suggests_toggle')}
                        .checked=${this._suggestsEnabled}
                        ?disabled=${disabled}
                        @change=${this._onSuggestsSwitch}
                    ></platform-switch>
                </div>
                <div class="field">
                    <platform-cron-field
                        .label=${this.t('namespace_detail_page.suggests_cron_label')}
                        .value=${this._suggestsCron}
                        placeholder=${this.t('namespace_detail_page.suggests_cron_placeholder')}
                        ?disabled=${disabled}
                        @input=${this._onSuggestsCronInput}
                        @change=${this._onSuggestsCronInput}
                    ></platform-cron-field>
                    <p class="hint">${this.t('namespace_detail_page.suggests_cron_help')}</p>
                </div>
                <p class="hint mono">
                    ${this._suggestsScheduleTaskId.length > 0
                        ? this.t('namespace_detail_page.suggests_schedule_id', { id: this._suggestsScheduleTaskId })
                        : this.t('namespace_detail_page.suggests_schedule_empty')}
                </p>
                <div class="actions-row">
                    <button
                        class="btn btn-primary"
                        type="button"
                        ?disabled=${disabled}
                        @click=${this._onSaveSuggests}
                    >
                        ${this._suggestsSaveBusy
                            ? this.t('namespace_detail_page.suggests_saving')
                            : this.t('namespace_detail_page.suggests_save')}
                    </button>
                </div>
            </div>
        `;
    }

    _renderRightPanel(): TemplateResult {
        const items = Array.isArray(this._entityTypes.items) ? this._entityTypes.items : [];
        if (this._typeFormOpen) {
            return this._renderTypeFormPanel();
        }
        return this._renderTypesListPanel(items);
    }

    _renderTypesListPanel(allTypes: Record<string, unknown>[]): TemplateResult {
        return html`
            <div class="panel">
                <div class="panel-header">
                    <span class="panel-title">
                        <platform-icon name="list" size="18"></platform-icon>
                        ${this.t('namespace_detail_page.types_section')}
                    </span>
                    <span class="actions-row" style="flex-wrap: nowrap; align-items: center;">
                        <span class="hint">
                            ${this.t('namespace_detail_page.allowed_count', {
                                allowed: String(this._allowedTypeIds.length),
                                total: String(allTypes.length),
                            })}
                        </span>
                        <button
                            class="btn btn-soft"
                            type="button"
                            @click=${() => this.openModal('crm.entity_type_create_mode')}
                        >
                            ${this.t('namespace_detail_page.action_new_type')}
                        </button>
                    </span>
                </div>
                ${this._entityTypes.loading && allTypes.length === 0
                    ? html`<platform-empty-state loading></platform-empty-state>`
                    : allTypes.length === 0
                    ? html`<platform-empty-state icon="columns" title=${this.t('namespace_detail_page.no_types')}></platform-empty-state>`
                    : html`
                        <div class="types-grid">
                            ${allTypes.map((item) => this._renderTypeCard(item))}
                        </div>
                    `}
            </div>
        `;
    }

    _renderTypeCard(item: Record<string, unknown>): TemplateResult {
        const typeId = item.type_id;
        if (typeof typeId !== 'string' || typeId.length === 0) {
            throw new Error('CRMNamespaceDetailPage: type_id required');
        }
        const allowed = this._allowedTypeIds.includes(typeId);
        const locked = this._typeIsLocked(typeId);
        const allNamespaces = this._typeIsAllNamespaces(typeId);
        const classes = ['type-card'];
        if (allowed) classes.push('allowed');
        if (locked) classes.push('locked');
        if (allNamespaces) classes.push('all-namespaces');
        return html`
            <div class=${classes.join(' ')}>
                <div class="type-title">
                    <platform-icon name=${typeof item.icon === 'string' && item.icon.length > 0 ? item.icon : 'circle'} size="16"></platform-icon>
                    <span>${item.name}</span>
                </div>
                <div class="hint mono">${typeId}</div>
                ${item.description ? html`<div class="hint">${item.description}</div>` : ''}
                <div class="actions-row">
                    <button
                        class="btn ${allowed ? 'btn-soft' : 'btn-primary'}"
                        type="button"
                        title=${allNamespaces ? this.t('namespace_detail_page.type_all_namespaces_hint') : ''}
                        ?disabled=${this._savingAllowed || (locked && allowed) || allNamespaces}
                        @click=${() => (allowed
                            ? this._onRequestDisallowType(typeId)
                            : this._onToggleType(item.type_id, true))}
                    >
                        ${allowed
                            ? this.t('namespace_detail_page.action_disallow')
                            : this.t('namespace_detail_page.action_allow')}
                    </button>
                    <button
                        class="btn btn-soft"
                        type="button"
                        @click=${() => this._editType(item)}
                    >
                        ${this.t('templates_page.edit_type')}
                    </button>
                </div>
            </div>
        `;
    }

    _renderTypeFormPanel(): TemplateResult {
        const namespaces = Array.isArray(this._namespaces.items) ? this._namespaces.items : [];
        return html`
            <div class="panel">
                <div class="panel-header">
                    <span class="panel-title">
                        <button
                            class="btn btn-soft panel-back"
                            type="button"
                            title=${this.t('namespace_detail_page.back_to_types')}
                            aria-label=${this.t('namespace_detail_page.back_to_types')}
                            @click=${this._onResetTypeDraft}
                        >
                            <platform-icon name="chevron-left" size="18"></platform-icon>
                        </button>
                        <platform-icon name="list" size="18"></platform-icon>
                        ${this.t('namespace_detail_page.types_section')}
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
                    .entityTypeCatalogRows=${this._namespaceEntityTypeCatalogRows()}
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

customElements.define('crm-namespace-detail-page', CRMNamespaceDetailPage);
