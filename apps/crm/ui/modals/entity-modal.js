/**
 * CRMEntityModal — единая модалка создания и редактирования сущности CRM.
 *
 * Props:
 *   - mode: 'create' | 'edit' — обязательный.
 *   - id?: string             — entity_id, обязателен для mode='edit'.
 *   - entityType?: string     — prefill для mode='create' (если задан, шаг
 *                                выбора типа пропускается).
 *   - namespace?: string      — prefill для mode='create'.
 *
 * Поток (mode='create'):
 *   1. Шаг "type" — карточки из `useResource('crm/entity_types')` фильтр
 *      по namespace. После выбора типа сидится draft, переход в "form".
 *   2. Шаг "form" — name (required), description, tags, attributes по
 *      объединённой схеме required_fields + optional_fields.
 *   3. submit → `useForm('crm/entity_create_form').submit()` →
 *      `entitiesResource.events.CREATE_REQUESTED` → POST /crm/api/v1/entities
 *      → CREATED → closeAfterSave().
 *
 * Поток (mode='edit'):
 *   1. На open: `useOp('crm/entity_card').run({ entity_id })` загружает
 *      entity + relationships + related_entities + attachments.
 *   2. После SUCCEEDED: сидим draft формы из entity, кэшируем relationships
 *      и attachments для UI.
 *   3. submit → `useForm('crm/entity_edit_form').submit()` →
 *      `entityUpdateOp.events.REQUESTED` → PUT /crm/api/v1/entities/{id}
 *      → SUCCEEDED → closeAfterSave().
 *   4. Связи: CRUD через `useResource('crm/relationships')` + рефреш card.
 *   5. Файлы: upload/delete через `useOp('crm/attachment_*')`.
 */

import { html, css, nothing } from 'lit';
import { PlatformFormModal } from '@platform/lib/components/glass-form-modal.js';
import { registerModalKind } from '@platform/lib/utils/modal-registry.js';
import '@platform/lib/components/platform-icon.js';
import '@platform/lib/components/glass-spinner.js';
import '@platform/lib/components/fields/platform-field.js';

const CREATE_FORM = 'crm/entity_create_form';
const EDIT_FORM = 'crm/entity_edit_form';
const ENTITIES_NAME = 'crm/entities';
const ENTITY_TYPES_NAME = 'crm/entity_types';
const RELATIONSHIPS_NAME = 'crm/relationships';
const RELATIONSHIP_TYPES_NAME = 'crm/relationship_types';

const MODE_CREATE = 'create';
const MODE_EDIT = 'edit';

const ENTITY_STATUS_OPTIONS = [
    { value: 'active', labelKey: 'entity_modal.status_active' },
    { value: 'archived', labelKey: 'entity_modal.status_archived' },
    { value: 'draft', labelKey: 'entity_modal.status_draft' },
    { value: 'completed', labelKey: 'entity_modal.status_completed' },
];

export class CRMEntityModal extends PlatformFormModal {
    static modalKind = 'crm.entity';
    static i18nNamespace = 'crm';

    static properties = {
        ...PlatformFormModal.properties,
        mode: { type: String },
        id: { type: String },
        entityType: { type: String },
        namespace: { type: String },
        _step: { state: true },
        _tagDraft: { state: true },
        _loadingCard: { state: true },
        _loadError: { state: true },
        _entityData: { state: true },
        _relationshipsData: { state: true },
        _relatedById: { state: true },
        _attachmentsData: { state: true },
        _loadingAttachments: { state: true },
        _addRelOpen: { state: true },
        _addRelType: { state: true },
        _addRelDirection: { state: true },
        _addRelTargetQuery: { state: true },
        _addRelTarget: { state: true },
        _addRelSearchResults: { state: true },
        _addRelSearching: { state: true },
        _addRelBusy: { state: true },
        _uploading: { state: true },
    };

    static styles = [
        ...PlatformFormModal.styles,
        css`
            .form-grid { display: grid; gap: var(--space-4); }
            .form-row { display: grid; gap: var(--space-2); }

            .badge-row {
                display: flex;
                gap: var(--space-2);
                flex-wrap: wrap;
                align-items: center;
            }
            .badge {
                display: inline-flex;
                align-items: center;
                gap: var(--space-1);
                padding: 4px var(--space-2);
                border-radius: var(--radius-full);
                background: var(--crm-surface-muted);
                border: 1px solid var(--crm-stroke);
                font-size: var(--text-xs);
                color: var(--text-secondary);
            }
            .badge.type {
                background: var(--crm-selected-bg);
                color: var(--text-primary);
                font-weight: 600;
            }
            .badge .swatch {
                width: 8px;
                height: 8px;
                border-radius: 50%;
                background: var(--accent);
            }
            .change-link {
                background: transparent;
                border: none;
                color: var(--accent);
                cursor: pointer;
                font-size: var(--text-xs);
                padding: 0;
            }

            .type-grid {
                display: grid;
                gap: var(--space-3);
                grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
            }
            .type-card {
                padding: var(--space-3);
                border: 1px solid var(--crm-stroke);
                border-radius: var(--radius-lg);
                background: var(--crm-surface-muted);
                text-align: left;
                cursor: pointer;
                display: grid;
                gap: var(--space-1);
                transition: border-color var(--duration-fast),
                            transform var(--duration-fast);
            }
            .type-card:hover {
                border-color: var(--crm-selected-stroke);
                transform: translateY(-1px);
            }
            .type-card .name {
                display: inline-flex;
                align-items: center;
                gap: var(--space-2);
                color: var(--text-primary);
                font-weight: 600;
                font-size: var(--text-sm);
            }
            .type-card .desc {
                color: var(--text-secondary);
                font-size: var(--text-xs);
                line-height: 1.4;
            }
            .type-card .id {
                font-family: var(--font-mono);
                color: var(--text-tertiary);
                font-size: var(--text-xs);
            }

            .empty {
                padding: var(--space-3);
                text-align: center;
                color: var(--text-tertiary);
                border: 1px dashed var(--crm-stroke);
                border-radius: var(--radius-md);
            }

            .loading-block {
                padding: var(--space-6);
                display: flex;
                justify-content: center;
            }
            .error-block {
                padding: var(--space-4);
                color: var(--color-danger);
                text-align: center;
            }

            .section {
                display: grid;
                gap: var(--space-3);
            }
            .section-title {
                display: flex;
                align-items: center;
                justify-content: space-between;
                font-size: var(--text-sm);
                font-weight: 600;
                color: var(--text-primary);
                padding-top: var(--space-2);
                border-top: 1px solid var(--crm-stroke);
            }

            .attrs-grid {
                display: grid;
                gap: var(--space-3);
                padding: var(--space-3);
                border: 1px solid var(--crm-stroke);
                border-radius: var(--radius-md);
                background: var(--crm-surface-muted);
            }
            .attrs-grid.empty-section {
                color: var(--text-tertiary);
                font-size: var(--text-xs);
                text-align: center;
                padding: var(--space-2) var(--space-3);
            }
            .attr-row { display: grid; gap: var(--space-1); }
            .attr-required { color: var(--color-danger); margin-left: 2px; }
            .attr-hint { color: var(--text-tertiary); font-size: var(--text-xs); }

            .tags-row {
                display: flex;
                flex-wrap: wrap;
                gap: var(--space-1);
                align-items: center;
            }
            .tag-chip {
                display: inline-flex;
                align-items: center;
                gap: var(--space-1);
                padding: 2px var(--space-2);
                border-radius: var(--radius-full);
                background: var(--crm-surface-muted);
                border: 1px solid var(--crm-stroke);
                font-size: var(--text-xs);
                color: var(--text-primary);
            }
            .tag-chip button {
                background: transparent; border: none; color: var(--text-tertiary);
                cursor: pointer; padding: 0; line-height: 1;
            }
            .tag-input {
                flex: 1; min-width: 120px;
                padding: var(--space-1) var(--space-2);
                border: 1px solid var(--crm-stroke);
                border-radius: var(--radius-md);
                background: transparent;
                color: var(--text-primary);
                font-size: var(--text-xs);
            }

            .rel-list, .att-list { display: grid; gap: var(--space-2); }
            .rel-row, .att-row {
                display: grid;
                grid-template-columns: 1fr auto;
                gap: var(--space-2);
                align-items: center;
                padding: var(--space-2) var(--space-3);
                border: 1px solid var(--crm-stroke);
                border-radius: var(--radius-md);
                background: var(--crm-surface-muted);
                font-size: var(--text-sm);
            }
            .rel-row .meta, .att-row .meta {
                display: grid;
                gap: 2px;
                min-width: 0;
            }
            .rel-row .title, .att-row .title {
                color: var(--text-primary);
                font-weight: 500;
                overflow: hidden;
                text-overflow: ellipsis;
                white-space: nowrap;
            }
            .rel-row .sub, .att-row .sub {
                color: var(--text-tertiary);
                font-size: var(--text-xs);
                font-family: var(--font-mono);
            }
            .icon-btn {
                background: transparent; border: none;
                color: var(--text-tertiary);
                cursor: pointer;
                padding: var(--space-1);
                border-radius: var(--radius-md);
            }
            .icon-btn:hover { color: var(--color-danger); background: var(--glass-tint-medium); }
            .icon-btn:disabled { opacity: 0.5; cursor: not-allowed; }

            .rel-add {
                display: grid;
                gap: var(--space-2);
                padding: var(--space-3);
                border: 1px dashed var(--crm-stroke);
                border-radius: var(--radius-md);
            }
            .rel-add .row {
                display: grid;
                grid-template-columns: 140px 1fr 1fr;
                gap: var(--space-2);
            }
            .search-results {
                display: grid;
                gap: 2px;
                max-height: 180px;
                overflow-y: auto;
            }
            .search-result {
                display: grid;
                gap: 2px;
                padding: var(--space-1) var(--space-2);
                border-radius: var(--radius-md);
                cursor: pointer;
                background: transparent;
                border: 1px solid transparent;
                text-align: left;
                color: var(--text-primary);
                font-size: var(--text-sm);
            }
            .search-result:hover {
                background: var(--crm-selected-bg);
                border-color: var(--crm-selected-stroke);
            }
            .search-result .id {
                color: var(--text-tertiary);
                font-size: var(--text-xs);
                font-family: var(--font-mono);
            }

            .att-dropzone {
                display: grid;
                gap: var(--space-2);
                padding: var(--space-3);
                text-align: center;
                border: 1px dashed var(--crm-stroke);
                border-radius: var(--radius-md);
                color: var(--text-tertiary);
                cursor: pointer;
            }
            .att-dropzone.dragover {
                border-color: var(--accent);
                background: var(--crm-selected-bg);
            }
            .att-dropzone input { display: none; }

            .footer-actions {
                display: flex;
                gap: var(--space-3);
                justify-content: flex-end;
                width: 100%;
            }
            .empty-soft {
                padding: var(--space-2) var(--space-3);
                text-align: center;
                color: var(--text-tertiary);
                font-size: var(--text-xs);
            }
        `,
    ];

    constructor() {
        super();
        this.size = 'lg';
        this.headerSavePrimary = true;
        this.mode = '';
        this.id = '';
        this.entityType = '';
        this.namespace = '';

        this._step = 'form';
        this._tagDraft = '';
        this._loadingCard = false;
        this._loadError = null;
        this._entityData = null;
        this._relationshipsData = [];
        this._relatedById = {};
        this._attachmentsData = [];
        this._loadingAttachments = false;
        this._addRelOpen = false;
        this._addRelType = '';
        this._addRelDirection = 'outgoing';
        this._addRelTargetQuery = '';
        this._addRelTarget = null;
        this._addRelSearchResults = [];
        this._addRelSearching = false;
        this._addRelBusy = false;
        this._uploading = false;

        this._createForm = this.useForm(CREATE_FORM);
        this._editForm = this.useForm(EDIT_FORM);
        this._entities = this.useResource(ENTITIES_NAME);
        this._entityTypes = this.useResource(ENTITY_TYPES_NAME);
        this._relationships = this.useResource(RELATIONSHIPS_NAME);
        this._relationshipTypes = this.useResource(RELATIONSHIP_TYPES_NAME);

        this._cardOp = this.useOp('crm/entity_card');
        this._updateOp = this.useOp('crm/entity_update');
        this._attachmentsListOp = this.useOp('crm/attachments_list');
        this._attachmentUploadOp = this.useOp('crm/attachment_upload');
        this._attachmentDeleteOp = this.useOp('crm/attachment_delete');
        this._entitySearchOp = this.useOp('crm/entity_search');

        this._namespaceSel = this.select((s) => {
            const user = s.auth.user;
            if (!user || typeof user.company_id !== 'string') return null;
            const cid = user.company_id;
            const map = s.ui.namespace.selectionByCompany;
            const sel = map[cid];
            if (sel === 'all' || sel === undefined || sel === null) return null;
            return sel;
        });

        this._typesQueryNamespace = '';
        this._searchTimer = null;
    }

    connectedCallback() {
        super.connectedCallback();
        if (this.mode !== MODE_CREATE && this.mode !== MODE_EDIT) {
            throw new Error(`CRMEntityModal: prop "mode" must be 'create' or 'edit', got '${this.mode}'`);
        }
        if (this.mode === MODE_EDIT && (typeof this.id !== 'string' || this.id.length === 0)) {
            throw new Error('CRMEntityModal: prop "id" required for mode=edit');
        }

        if (this.mode === MODE_CREATE) {
            this._initCreateDraft();
            this.useEvent(this._entities.resource.events.CREATED, (event) => this._onCreated(event));
            this.useEvent(this._entities.resource.events.CREATE_FAILED, () => this._onCreateFailed());
            return;
        }

        this._editForm.openForm({
            id: this.id,
            name: '',
            description: '',
            status: '',
            attributes: {},
            tags: [],
        });
        this.useEvent(this._cardOp.op.events.SUCCEEDED, (event) => this._onCardLoaded(event));
        this.useEvent(this._cardOp.op.events.FAILED, (event) => this._onCardFailed(event));
        this.useEvent(this._updateOp.op.events.SUCCEEDED, () => this.closeAfterSave());
        this.useEvent(this._attachmentsListOp.op.events.SUCCEEDED, (event) => this._onAttachmentsLoaded(event));
        this.useEvent(this._attachmentUploadOp.op.events.SUCCEEDED, () => this._reloadAttachments());
        this.useEvent(this._attachmentDeleteOp.op.events.SUCCEEDED, () => this._reloadAttachments());
        this.useEvent(this._relationships.resource.events.CREATED, () => this._onRelationshipChanged());
        this.useEvent(this._relationships.resource.events.REMOVED, () => this._onRelationshipChanged());
        this.useEvent(this._entitySearchOp.op.events.SUCCEEDED, (event) => this._onSearchResults(event));
        this._loadCard();
        this._relationshipTypes.load(null);
    }

    disconnectedCallback() {
        if (this._searchTimer !== null) {
            clearTimeout(this._searchTimer);
            this._searchTimer = null;
        }
        this._activeForm().close();
        super.disconnectedCallback();
    }

    _activeForm() {
        return this.mode === MODE_CREATE ? this._createForm : this._editForm;
    }

    // ── create-режим ─────────────────────────────────────────────────────────

    _initCreateDraft() {
        const ns = typeof this.namespace === 'string' && this.namespace.length > 0
            ? this.namespace
            : (this._namespaceSel.value || 'default');
        const type = typeof this.entityType === 'string' ? this.entityType : '';
        this._createForm.openForm({
            entity_type: type,
            namespace: ns,
            name: '',
            description: '',
            attributes: {},
            tags: [],
        });
        this._step = type.length > 0 ? 'form' : 'type';
        this._loadTypes(ns);
    }

    _loadTypes(ns) {
        if (typeof ns !== 'string' || ns.length === 0) {
            throw new Error('CRMEntityModal._loadTypes: namespace required');
        }
        if (this._typesQueryNamespace === ns) return;
        this._typesQueryNamespace = ns;
        this._entityTypes.load({ namespace: ns });
    }

    _onTypePick(typeId) {
        if (typeof typeId !== 'string' || typeId.length === 0) {
            throw new Error('CRMEntityModal._onTypePick: typeId required');
        }
        this._createForm.setField('entity_type', typeId);
        this._createForm.setField('attributes', {});
        this._step = 'form';
    }

    _onChangeType() {
        this._createForm.setField('entity_type', '');
        this._createForm.setField('attributes', {});
        this._step = 'type';
    }

    _onCreated(event) {
        const payload = event && event.payload ? event.payload : null;
        if (!payload || !payload.item || typeof payload.item.entity_id !== 'string') {
            throw new Error('CRMEntityModal._onCreated: created entity missing entity_id');
        }
        this.closeAfterSave();
    }

    _onCreateFailed() {
        this._createForm.openForm(this._createForm.draft);
    }

    // ── edit-режим ───────────────────────────────────────────────────────────

    _loadCard() {
        this._loadingCard = true;
        this._loadError = null;
        this._cardOp.run({ entity_id: this.id });
    }

    _reloadAttachments() {
        this._loadingAttachments = true;
        this._attachmentsListOp.run({ entity_id: this.id });
    }

    _onRelationshipChanged() {
        this._cardOp.run({ entity_id: this.id });
    }

    _onCardLoaded(event) {
        this._loadingCard = false;
        const card = event && event.payload && event.payload.result;
        if (!card || typeof card !== 'object' || !card.entity) {
            throw new Error('CRMEntityModal: invalid card response (missing entity)');
        }
        this._entityData = card.entity;
        const relationships = Array.isArray(card.relationships) ? card.relationships : [];
        const related = Array.isArray(card.related_entities) ? card.related_entities : [];
        const relatedMap = {};
        for (const r of related) {
            if (r && typeof r.entity_id === 'string') relatedMap[r.entity_id] = r;
        }
        this._relationshipsData = relationships;
        this._relatedById = relatedMap;
        this._attachmentsData = Array.isArray(card.attachments) ? card.attachments : [];
        this._editForm.openForm({
            id: this.id,
            name: typeof this._entityData.name === 'string' ? this._entityData.name : '',
            description: typeof this._entityData.description === 'string' ? this._entityData.description : '',
            status: typeof this._entityData.status === 'string' ? this._entityData.status : 'active',
            attributes: this._entityData.attributes && typeof this._entityData.attributes === 'object'
                ? { ...this._entityData.attributes }
                : {},
            tags: Array.isArray(this._entityData.tags) ? [...this._entityData.tags] : [],
        });
        this.isDirty = false;
    }

    _onCardFailed(event) {
        this._loadingCard = false;
        const message = event && event.payload && typeof event.payload.message === 'string'
            ? event.payload.message
            : this.t('entity_modal.load_failed');
        this._loadError = message;
    }

    _onAttachmentsLoaded(event) {
        this._loadingAttachments = false;
        const result = event && event.payload && event.payload.result;
        if (!Array.isArray(result)) {
            throw new Error('CRMEntityModal._onAttachmentsLoaded: result must be array');
        }
        this._attachmentsData = result;
    }

    _onSearchResults(event) {
        const result = event && event.payload && event.payload.result;
        const items = result && Array.isArray(result.items) ? result.items : [];
        this._addRelSearching = false;
        this._addRelSearchResults = items.filter((item) => item.entity_id !== this.id);
    }

    // ── общие хелперы ────────────────────────────────────────────────────────

    _selectedType() {
        const items = this._entityTypes.items;
        if (this.mode === MODE_CREATE) {
            const draft = this._createForm.draft;
            if (typeof draft.entity_type !== 'string' || draft.entity_type.length === 0) return null;
            for (const item of items) {
                if (item.type_id === draft.entity_type) return item;
            }
            return null;
        }
        if (!this._entityData) return null;
        for (const t of items) {
            if (t.type_id === this._entityData.entity_type) return t;
        }
        return null;
    }

    willUpdate(changed) {
        super.willUpdate(changed);
        if (this.mode === MODE_CREATE) {
            const draft = this._createForm.draft;
            const dirty = (typeof draft.name === 'string' && draft.name.trim().length > 0)
                || (typeof draft.description === 'string' && draft.description.trim().length > 0)
                || (Object.keys(draft.attributes).length > 0)
                || (Array.isArray(draft.tags) && draft.tags.length > 0);
            this.isDirty = dirty;
            return;
        }
        if (!this._entityData) return;
        const draft = this._editForm.draft;
        const origDescription = typeof this._entityData.description === 'string' ? this._entityData.description : '';
        const origStatus = typeof this._entityData.status === 'string' && this._entityData.status.length > 0 ? this._entityData.status : 'active';
        const origAttributes = this._entityData.attributes && typeof this._entityData.attributes === 'object' ? this._entityData.attributes : {};
        const origTags = Array.isArray(this._entityData.tags) ? this._entityData.tags : [];
        const draftDescription = typeof draft.description === 'string' ? draft.description : '';
        const draftStatus = typeof draft.status === 'string' && draft.status.length > 0 ? draft.status : 'active';
        const dirty = (draft.name !== this._entityData.name)
            || (draftDescription !== origDescription)
            || (draftStatus !== origStatus)
            || (JSON.stringify(draft.attributes) !== JSON.stringify(origAttributes))
            || (JSON.stringify(draft.tags) !== JSON.stringify(origTags));
        this.isDirty = dirty;
    }

    _onNameInput(event) { this._activeForm().setField('name', event.target.value); }
    _onDescriptionInput(event) { this._activeForm().setField('description', event.target.value); }
    _onStatusInput(event) { this._editForm.setField('status', event.target.value); }

    _onAttrChange(fieldKey, event) {
        const value = event && event.detail ? event.detail.value : null;
        const form = this._activeForm();
        const draft = form.draft;
        const next = { ...draft.attributes };
        if (value === null || value === undefined || (typeof value === 'string' && value.trim().length === 0)) {
            delete next[fieldKey];
        } else {
            next[fieldKey] = value;
        }
        form.setField('attributes', next);
    }

    _onTagInput(event) { this._tagDraft = event.target.value; }
    _onTagKey(event) {
        if (event.key !== 'Enter' && event.key !== ',') return;
        event.preventDefault();
        const value = this._tagDraft.trim();
        if (value.length === 0) return;
        const form = this._activeForm();
        const draft = form.draft;
        if (Array.isArray(draft.tags) && draft.tags.includes(value)) {
            this._tagDraft = '';
            return;
        }
        const next = Array.isArray(draft.tags) ? [...draft.tags, value] : [value];
        form.setField('tags', next);
        this._tagDraft = '';
    }
    _onTagRemove(tag) {
        const form = this._activeForm();
        const draft = form.draft;
        if (!Array.isArray(draft.tags)) return;
        const next = draft.tags.filter((item) => item !== tag);
        form.setField('tags', next);
    }

    async _performSave() {
        this._activeForm().submit();
    }

    _isCreate() { return this.mode === MODE_CREATE; }

    _saveHeaderTitle() {
        const submitting = this._activeForm().submitting;
        if (submitting) return this.t('entity_modal.action_saving');
        return this._isCreate()
            ? this.t('entity_modal.action_create')
            : this.t('entity_modal.action_save');
    }

    renderHeader() {
        if (this._isCreate()) {
            const type = this._selectedType();
            if (this._step === 'type' || !type) {
                return this.t('entity_modal.header_create');
            }
            return this.t('entity_modal.header_create_with_type', { type: type.name });
        }
        if (!this._entityData) return this.t('entity_modal.header_edit');
        return this.t('entity_modal.header_edit_named', { name: this._entityData.name });
    }

    renderSaveHeaderButton() {
        if (this._isCreate()) {
            if (this._step !== 'form') return null;
            const draft = this._createForm.draft;
            const has_name = typeof draft.name === 'string' && draft.name.trim().length > 0;
            const has_type = typeof draft.entity_type === 'string' && draft.entity_type.length > 0;
            const disabled = this._createForm.submitting || !has_name || !has_type;
            return this._renderHeaderSaveIcon({
                onClick: () => this._performSave(),
                disabled,
                title: this._saveHeaderTitle(),
            });
        }
        const draft = this._editForm.draft;
        const has_name = typeof draft.name === 'string' && draft.name.trim().length > 0;
        const disabled = this._loadingCard || this._editForm.submitting || !has_name;
        return this._renderHeaderSaveIcon({
            onClick: () => this._performSave(),
            disabled,
            title: this._saveHeaderTitle(),
        });
    }

    _renderFieldError(field) {
        const error_key = this._activeForm().errors[field];
        if (!error_key) return null;
        return html`<div class="form-error">${this.t(error_key)}</div>`;
    }

    // ── render: type-step (только create) ────────────────────────────────────

    _renderTypeStep() {
        const items = this._entityTypes.items;
        if (this._entityTypes.loading && items.length === 0) {
            return html`<div class="empty">${this.t('entity_modal.types_loading')}</div>`;
        }
        if (items.length === 0) {
            return html`<div class="empty">${this.t('entity_modal.types_empty')}</div>`;
        }
        return html`
            <div class="form-row">
                <label class="form-label">${this.t('entity_modal.label_type')}</label>
                <div class="type-grid">
                    ${items.map((type) => html`
                        <button
                            type="button"
                            class="type-card"
                            @click=${() => this._onTypePick(type.type_id)}
                        >
                            <span class="name">
                                <span class="swatch" style=${`background: ${typeof type.color === 'string' && type.color.length > 0 ? type.color : 'var(--accent)'}`}></span>
                                <platform-icon name=${typeof type.icon === 'string' && type.icon.length > 0 ? type.icon : 'circle'} size="14"></platform-icon>
                                ${type.name}
                            </span>
                            <span class="desc">${typeof type.description === 'string' && type.description.length > 0 ? type.description : this.t('entity_modal.type_no_description')}</span>
                            <span class="id">${type.type_id}</span>
                        </button>
                    `)}
                </div>
            </div>
        `;
    }

    // ── render: type-badge (общий, ведёт себя по-разному в create/edit) ──────

    _renderTypeBadge() {
        const type = this._selectedType();
        if (this._isCreate()) {
            if (!type) return nothing;
            const swatch_color = typeof type.color === 'string' && type.color.length > 0 ? type.color : 'var(--accent)';
            const draft = this._createForm.draft;
            return html`
                <div class="badge-row">
                    <span class="badge type">
                        <span class="swatch" style=${`background: ${swatch_color}`}></span>
                        <platform-icon name=${typeof type.icon === 'string' && type.icon.length > 0 ? type.icon : 'circle'} size="12"></platform-icon>
                        ${type.name}
                    </span>
                    <span class="badge">
                        <platform-icon name="folder" size="12"></platform-icon>
                        ${draft.namespace}
                    </span>
                    <button type="button" class="change-link" @click=${this._onChangeType}>
                        ${this.t('entity_modal.change_type')}
                    </button>
                </div>
            `;
        }
        if (!this._entityData) return nothing;
        const typeName = type ? type.name : this._entityData.entity_type;
        const typeColor = type && typeof type.color === 'string' && type.color.length > 0 ? type.color : 'var(--accent)';
        const typeIcon = type && typeof type.icon === 'string' && type.icon.length > 0 ? type.icon : 'circle';
        return html`
            <div class="badge-row">
                <span class="badge type">
                    <span class="swatch" style=${`background: ${typeColor}`}></span>
                    <platform-icon name=${typeIcon} size="12"></platform-icon>
                    ${typeName}
                </span>
                <span class="badge">
                    <platform-icon name="folder" size="12"></platform-icon>
                    ${this._entityData.namespace}
                </span>
                <span class="badge">
                    <platform-icon name="hash" size="12"></platform-icon>
                    ${this._entityData.entity_id}
                </span>
            </div>
        `;
    }

    // ── render: attributes (общий) ───────────────────────────────────────────

    _attributesSchema(type) {
        const required = type && type.required_fields && typeof type.required_fields === 'object' ? type.required_fields : {};
        const optional = type && type.optional_fields && typeof type.optional_fields === 'object' ? type.optional_fields : {};
        const out = [];
        for (const [key, def] of Object.entries(required)) out.push({ key, def, required: true });
        for (const [key, def] of Object.entries(optional)) {
            if (key in required) continue;
            out.push({ key, def, required: false });
        }
        return out;
    }

    _fieldType(def) {
        if (!def || typeof def !== 'object') return 'string';
        const t = typeof def.type === 'string' ? def.type.trim() : '';
        return t.length === 0 ? 'string' : t;
    }
    _fieldLabel(key, def) {
        if (def && typeof def.label === 'string' && def.label.length > 0) return def.label;
        return key;
    }
    _fieldConfig(def) {
        if (!def || typeof def !== 'object') return {};
        if (Array.isArray(def.values)) return { values: def.values };
        return {};
    }

    _renderAttributesSection() {
        const type = this._selectedType();
        const schema = this._attributesSchema(type);
        const draft = this._activeForm().draft;
        const attributes = draft.attributes;

        if (schema.length === 0) {
            if (!this._isCreate()) {
                const attrs = Object.entries(attributes);
                if (attrs.length === 0) {
                    return html`<div class="attrs-grid empty-section">${this.t('entity_modal.attrs_empty')}</div>`;
                }
                return html`
                    <div class="attrs-grid">
                        ${attrs.map(([key, value]) => html`
                            <div class="form-row">
                                <platform-field
                                    .type=${'string'}
                                    .value=${value}
                                    mode="edit"
                                    .label=${key}
                                    @change=${(event) => this._onAttrChange(key, event)}
                                ></platform-field>
                            </div>
                        `)}
                    </div>
                `;
            }
            return html`<div class="attrs-grid empty-section">${this.t('entity_modal.attrs_empty')}</div>`;
        }
        return html`
            <div class="attrs-grid">
                ${schema.map(({ key, def, required }) => {
                    const fieldType = this._fieldType(def);
                    const value = attributes[key];
                    return html`
                        <div class="attr-row">
                            <platform-field
                                .type=${fieldType}
                                .value=${value === undefined ? null : value}
                                mode="edit"
                                .label=${this._fieldLabel(key, def) + (required ? ' *' : '')}
                                .config=${this._fieldConfig(def)}
                                @change=${(event) => this._onAttrChange(key, event)}
                            ></platform-field>
                            ${def && typeof def.description === 'string' && def.description.length > 0
                                ? html`<div class="attr-hint">${def.description}</div>`
                                : nothing}
                        </div>
                    `;
                })}
            </div>
        `;
    }

    // ── render: tags ─────────────────────────────────────────────────────────

    _renderTagsSection() {
        const draft = this._activeForm().draft;
        const tags = Array.isArray(draft.tags) ? draft.tags : [];
        return html`
            <div class="form-row">
                <label class="form-label">${this.t('entity_modal.label_tags')}</label>
                <div class="tags-row">
                    ${tags.map((tag) => html`
                        <span class="tag-chip">
                            ${tag}
                            <button type="button" @click=${() => this._onTagRemove(tag)}>
                                <platform-icon name="close" size="12"></platform-icon>
                            </button>
                        </span>
                    `)}
                    <input
                        type="text"
                        class="tag-input"
                        .value=${this._tagDraft}
                        placeholder=${this.t('entity_modal.tag_placeholder')}
                        @input=${this._onTagInput}
                        @keydown=${this._onTagKey}
                    />
                </div>
                ${this._isCreate()
                    ? html`<div class="attr-hint">${this.t('entity_modal.tag_hint')}</div>`
                    : nothing}
            </div>
        `;
    }

    // ── render: relationships (только edit) ──────────────────────────────────

    _onRemoveRelationship(rel) {
        if (!rel || typeof rel.relationship_id !== 'string') return;
        this._relationships.remove(rel.relationship_id);
    }

    _renderRelationshipsSection() {
        return html`
            <div class="section-title">
                <span>${this.t('entity_modal.section_relationships')}</span>
                <button
                    type="button"
                    class="btn btn-secondary btn-sm"
                    @click=${() => this._toggleAddRelationship()}
                >
                    ${this._addRelOpen
                        ? this.t('entity_modal.action_cancel_add_relationship')
                        : this.t('entity_modal.action_add_relationship')}
                </button>
            </div>
            ${this._renderRelationshipsList()}
            ${this._addRelOpen ? this._renderAddRelationship() : nothing}
        `;
    }

    _renderRelationshipsList() {
        if (this._relationshipsData.length === 0) {
            return html`<div class="empty-soft">${this.t('entity_modal.relationships_empty')}</div>`;
        }
        const myId = this.id;
        return html`
            <div class="rel-list">
                ${this._relationshipsData.map((rel) => {
                    const otherId = rel.source_entity_id === myId ? rel.target_entity_id : rel.source_entity_id;
                    const direction = rel.source_entity_id === myId ? 'outgoing' : 'incoming';
                    const other = this._relatedById[otherId];
                    const otherName = other && typeof other.name === 'string' ? other.name : otherId;
                    const directionLabel = direction === 'outgoing'
                        ? this.t('entity_modal.direction_outgoing')
                        : this.t('entity_modal.direction_incoming');
                    const isBusy = this._relationships.isBusy(rel.relationship_id);
                    return html`
                        <div class="rel-row">
                            <div class="meta">
                                <span class="title">${rel.relationship_type} ${directionLabel} ${otherName}</span>
                                <span class="sub">${otherId}</span>
                            </div>
                            <button
                                type="button"
                                class="icon-btn"
                                ?disabled=${isBusy}
                                title=${this.t('entity_modal.action_remove_relationship')}
                                @click=${() => this._onRemoveRelationship(rel)}
                            >
                                <platform-icon name="trash" size="14"></platform-icon>
                            </button>
                        </div>
                    `;
                })}
            </div>
        `;
    }

    _toggleAddRelationship() {
        this._addRelOpen = !this._addRelOpen;
        if (!this._addRelOpen) {
            this._addRelType = '';
            this._addRelDirection = 'outgoing';
            this._addRelTargetQuery = '';
            this._addRelTarget = null;
            this._addRelSearchResults = [];
            this._addRelSearching = false;
        }
    }

    _onAddRelTypeChange(event) { this._addRelType = event.target.value; }
    _onAddRelDirectionChange(event) { this._addRelDirection = event.target.value; }

    _onAddRelTargetQueryInput(event) {
        const value = event.target.value;
        this._addRelTargetQuery = value;
        this._addRelTarget = null;
        if (this._searchTimer !== null) clearTimeout(this._searchTimer);
        if (value.trim().length < 2) {
            this._addRelSearchResults = [];
            this._addRelSearching = false;
            return;
        }
        this._addRelSearching = true;
        this._searchTimer = setTimeout(() => {
            this._searchTimer = null;
            const namespace = this._entityData ? this._entityData.namespace : null;
            const payload = { q: value.trim(), limit: 20 };
            if (typeof namespace === 'string' && namespace.length > 0) payload.namespace = namespace;
            this._entitySearchOp.run(payload);
        }, 250);
    }

    _onPickRelTarget(item) {
        this._addRelTarget = item;
        this._addRelSearchResults = [];
        this._addRelTargetQuery = item.name;
    }

    _canSubmitRelationship() {
        if (this._addRelBusy) return false;
        if (typeof this._addRelType !== 'string' || this._addRelType.length === 0) return false;
        if (!this._addRelTarget || typeof this._addRelTarget.entity_id !== 'string') return false;
        if (this._addRelTarget.entity_id === this.id) return false;
        return true;
    }

    _onSubmitRelationship() {
        if (!this._canSubmitRelationship()) return;
        if (!this._entityData) {
            throw new Error('CRMEntityModal._onSubmitRelationship: entity not loaded');
        }
        const isOutgoing = this._addRelDirection === 'outgoing';
        const sourceId = isOutgoing ? this.id : this._addRelTarget.entity_id;
        const targetId = isOutgoing ? this._addRelTarget.entity_id : this.id;
        this._addRelBusy = true;
        this._relationships.create({
            source_entity_id: sourceId,
            target_entity_id: targetId,
            relationship_type: this._addRelType,
            namespace: this._entityData.namespace,
        });
        this._toggleAddRelationship();
        this._addRelBusy = false;
    }

    _renderAddRelationship() {
        const types = this._relationshipTypes.items;
        return html`
            <div class="rel-add">
                <div class="row">
                    <select class="form-select" .value=${this._addRelDirection} @change=${this._onAddRelDirectionChange}>
                        <option value="outgoing">${this.t('entity_modal.direction_outgoing')}</option>
                        <option value="incoming">${this.t('entity_modal.direction_incoming')}</option>
                    </select>
                    <select class="form-select" .value=${this._addRelType} @change=${this._onAddRelTypeChange}>
                        <option value="" disabled>${this.t('entity_modal.type_pick_placeholder')}</option>
                        ${types.map((rt) => html`
                            <option value=${rt.type_id}>${rt.name}</option>
                        `)}
                    </select>
                    <input
                        type="text"
                        class="form-input"
                        .value=${this._addRelTargetQuery}
                        placeholder=${this.t('entity_modal.target_search_placeholder')}
                        @input=${this._onAddRelTargetQueryInput}
                    />
                </div>
                ${this._addRelSearching
                    ? html`<div class="empty-soft">${this.t('entity_modal.searching')}</div>`
                    : nothing}
                ${this._addRelSearchResults.length > 0
                    ? html`
                        <div class="search-results">
                            ${this._addRelSearchResults.map((item) => html`
                                <button type="button" class="search-result" @click=${() => this._onPickRelTarget(item)}>
                                    <span>${item.name}</span>
                                    <span class="id">${item.entity_id}</span>
                                </button>
                            `)}
                        </div>
                    `
                    : nothing}
                <div class="footer-actions">
                    <button
                        type="button"
                        class="btn btn-primary btn-sm"
                        ?disabled=${!this._canSubmitRelationship()}
                        @click=${() => this._onSubmitRelationship()}
                    >
                        ${this.t('entity_modal.action_save_relationship')}
                    </button>
                </div>
            </div>
        `;
    }

    // ── render: attachments (только edit) ────────────────────────────────────

    _onAttachmentInput(event) {
        const files = Array.from(event.target.files);
        for (const file of files) this._uploadAttachment(file);
        event.target.value = '';
    }
    _onDragOver(event) { event.preventDefault(); event.currentTarget.classList.add('dragover'); }
    _onDragLeave(event) { event.currentTarget.classList.remove('dragover'); }
    _onDrop(event) {
        event.preventDefault();
        event.currentTarget.classList.remove('dragover');
        const files = Array.from(event.dataTransfer.files);
        for (const file of files) this._uploadAttachment(file);
    }

    _uploadAttachment(file) {
        if (!(file instanceof File)) return;
        this._uploading = true;
        this._attachmentUploadOp.run({ entity_id: this.id, file });
    }

    _onRemoveAttachment(att) {
        if (!att || typeof att.document_id !== 'string') return;
        this._attachmentDeleteOp.run({ entity_id: this.id, attachment_id: att.document_id });
    }

    _renderAttachmentsSection() {
        return html`
            <div class="section-title">
                <span>${this.t('entity_modal.section_attachments')}</span>
            </div>
            ${this._attachmentsData.length === 0
                ? html`<div class="empty-soft">${this.t('entity_modal.attachments_empty')}</div>`
                : html`
                    <div class="att-list">
                        ${this._attachmentsData.map((att) => html`
                            <div class="att-row">
                                <div class="meta">
                                    <span class="title">${att.filename}</span>
                                    <span class="sub">${att.document_id}</span>
                                </div>
                                <button
                                    type="button"
                                    class="icon-btn"
                                    title=${this.t('entity_modal.action_remove_attachment')}
                                    @click=${() => this._onRemoveAttachment(att)}
                                >
                                    <platform-icon name="trash" size="14"></platform-icon>
                                </button>
                            </div>
                        `)}
                    </div>
                `}
            <label
                class="att-dropzone"
                @dragover=${this._onDragOver}
                @dragleave=${this._onDragLeave}
                @drop=${this._onDrop}
            >
                <span>
                    <platform-icon name="cloud" size="16"></platform-icon>
                    ${this._uploading
                        ? this.t('entity_modal.attachment_uploading')
                        : this.t('entity_modal.attachment_dropzone')}
                </span>
                <input type="file" multiple @change=${this._onAttachmentInput} />
            </label>
        `;
    }

    // ── render: body / footer ────────────────────────────────────────────────

    renderBody() {
        if (this._isCreate()) return this._renderCreateBody();
        return this._renderEditBody();
    }

    _renderCreateBody() {
        if (this._step === 'type') {
            return this._renderTypeStep();
        }
        const type = this._selectedType();
        if (!type) {
            return html`<div class="empty">${this.t('entity_modal.type_missing')}</div>`;
        }
        const draft = this._createForm.draft;
        return html`
            <form class="form-grid" @submit=${(event) => { event.preventDefault(); this._performSave(); }}>
                ${this._renderTypeBadge()}

                <div class="form-row">
                    <label class="form-label">${this.t('entity_modal.label_name')}</label>
                    <input
                        type="text"
                        class="form-input"
                        autocomplete="off"
                        spellcheck="false"
                        placeholder=${this.t('entity_modal.name_placeholder')}
                        .value=${draft.name}
                        @input=${this._onNameInput}
                    />
                    ${this._renderFieldError('name')}
                </div>

                <div class="form-row">
                    <label class="form-label">${this.t('entity_modal.label_description')}</label>
                    <textarea
                        class="form-textarea"
                        rows="3"
                        placeholder=${this.t('entity_modal.description_placeholder')}
                        .value=${draft.description}
                        @input=${this._onDescriptionInput}
                    ></textarea>
                    ${this._renderFieldError('description')}
                </div>

                <div class="form-row">
                    <label class="form-label">${this.t('entity_modal.label_attributes')}</label>
                    ${this._renderAttributesSection()}
                </div>

                ${this._renderTagsSection()}
            </form>
        `;
    }

    _renderEditBody() {
        if (this._loadingCard && !this._entityData) {
            return html`<div class="loading-block"><glass-spinner></glass-spinner></div>`;
        }
        if (this._loadError && !this._entityData) {
            return html`<div class="error-block">${this._loadError}</div>`;
        }
        if (!this._entityData) {
            return html`<div class="loading-block"><glass-spinner></glass-spinner></div>`;
        }
        const draft = this._editForm.draft;
        return html`
            <form class="form-grid" @submit=${(event) => { event.preventDefault(); this._performSave(); }}>
                ${this._renderTypeBadge()}

                <div class="form-row">
                    <label class="form-label">${this.t('entity_modal.label_name')}</label>
                    <input
                        type="text"
                        class="form-input"
                        autocomplete="off"
                        spellcheck="false"
                        .value=${draft.name}
                        @input=${this._onNameInput}
                    />
                    ${this._renderFieldError('name')}
                </div>

                <div class="form-row">
                    <label class="form-label">${this.t('entity_modal.label_description')}</label>
                    <textarea
                        class="form-textarea"
                        rows="3"
                        .value=${draft.description}
                        @input=${this._onDescriptionInput}
                    ></textarea>
                    ${this._renderFieldError('description')}
                </div>

                <div class="form-row">
                    <label class="form-label">${this.t('entity_modal.label_status')}</label>
                    <select class="form-select" .value=${draft.status} @change=${this._onStatusInput}>
                        ${ENTITY_STATUS_OPTIONS.map((status) => html`
                            <option value=${status.value}>${this.t(status.labelKey)}</option>
                        `)}
                    </select>
                </div>

                <div class="form-row">
                    <label class="form-label">${this.t('entity_modal.label_attributes')}</label>
                    ${this._renderAttributesSection()}
                </div>

                ${this._renderTagsSection()}

                <div class="section">
                    ${this._renderRelationshipsSection()}
                </div>

                <div class="section">
                    ${this._renderAttachmentsSection()}
                </div>
            </form>
        `;
    }

    renderFooter() {
        if (this._isCreate() && this._step === 'type') {
            return html`
                <div class="footer-actions">
                    <button
                        type="button"
                        class="btn btn-secondary"
                        @click=${() => this.close()}
                    >
                        ${this.t('entity_modal.action_cancel')}
                    </button>
                </div>
            `;
        }
        const form = this._activeForm();
        const draft = form.draft;
        const has_name = typeof draft.name === 'string' && draft.name.trim().length > 0;
        const disabled = (this._isCreate() ? false : this._loadingCard) || form.submitting || !has_name;
        const submitting = form.submitting;
        return html`
            <div class="footer-actions">
                <button
                    type="button"
                    class="btn btn-secondary"
                    @click=${() => this.close()}
                >
                    ${this.t('entity_modal.action_cancel')}
                </button>
                <button
                    type="button"
                    class="btn btn-primary"
                    ?disabled=${disabled}
                    @click=${() => this._performSave()}
                >
                    ${submitting
                        ? this.t('entity_modal.action_saving')
                        : this._isCreate()
                            ? this.t('entity_modal.action_create')
                            : this.t('entity_modal.action_save')}
                </button>
            </div>
        `;
    }
}

customElements.define('crm-entity-modal', CRMEntityModal);
registerModalKind(CRMEntityModal.modalKind, 'crm-entity-modal');
