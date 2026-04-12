import { html, css } from 'lit';
import { PlatformElement } from '@platform/lib/platform-element/index.js';
import { CRMStore } from '../store/crm.store.js';
import { EntityTypeForm } from '../components/entity-type-form.js';
import '../components/namespace-grants-panel.js';
import '@platform/lib/components/platform-icon.js';
import '@platform/lib/components/platform-help-hint.js';
import '@platform/lib/components/platform-switch.js';

export class SpacesPage extends PlatformElement {
    static properties = {
        _namespaces: { state: true },
        _entityTypes: { state: true },
        _selectedNamespaceName: { state: true },
        _selectedNamespaceDraftDescription: { state: true },
        _selectedNamespaceDraftAllowedTypeIds: { state: true },
        _selectedNamespaceEditability: { state: true },
        _namespaceEditorLoading: { state: true },
        _namespaceEditorSaving: { state: true },
        _editingTypeId: { state: true },
        _editingTypeDraft: { state: true },
        _showCreateForm: { state: true },
        _createSaving: { state: true },
        _selectedNamespaceCrmDraft: { state: true },
        _schemaOptions: { state: true },
    };

    static styles = [
        PlatformElement.styles,
        css`
            :host { display: flex; flex-direction: column; width: 100%; height: 100%; min-height: 0; overflow: hidden; }
            .container {
                display: flex;
                flex-direction: column;
                gap: var(--space-4);
                height: 100%;
                min-width: 0;
                max-width: 100%;
                box-sizing: border-box;
                overflow-y: auto;
                overflow-x: hidden;
                padding: var(--space-2);
            }
            .section {
                min-width: 0;
                max-width: 100%;
                box-sizing: border-box;
                background: var(--crm-surface);
                border: 1px solid var(--crm-stroke);
                border-radius: var(--radius-xl);
                padding: var(--space-4);
                display: flex;
                flex-direction: column;
                gap: var(--space-3);
            }
            .hero { display: flex; align-items: center; justify-content: space-between; gap: var(--space-3); }
            .hero-title { display: flex; align-items: center; gap: var(--space-2); color: var(--text-primary); font-size: var(--text-lg); font-weight: 700; }
            .hero-subtitle { color: var(--text-secondary); font-size: var(--text-sm); }
            .section-header { display: flex; align-items: center; gap: var(--space-2); color: var(--text-primary); font-size: var(--text-lg); font-weight: 600; }
            .card-text { color: var(--text-secondary); font-size: var(--text-sm); }
            .form-grid { display: grid; gap: var(--space-3); grid-template-columns: repeat(auto-fit, minmax(min(100%, 220px), 1fr)); }
            .form-group { display: flex; flex-direction: column; gap: var(--space-2); }
            .form-label { color: var(--text-secondary); font-size: var(--text-sm); font-weight: 500; }
            .label-with-hint { display: inline-flex; align-items: center; gap: var(--space-2); }
            .form-input, .form-textarea { border: 1px solid var(--crm-stroke); border-radius: var(--radius-md); background: var(--crm-surface-elevated); color: var(--text-primary); padding: var(--space-2) var(--space-3); font-size: var(--text-sm); }
            .form-textarea { min-height: 88px; resize: vertical; }
            .save-btn { display: inline-flex; align-items: center; justify-content: center; gap: var(--space-2); border: 1px solid var(--accent); background: var(--accent); color: var(--platform-btn-primary-text); border-radius: var(--radius-md); padding: var(--space-2) var(--space-4); cursor: pointer; width: fit-content; }
            .save-btn:disabled { opacity: 0.5; cursor: not-allowed; }
            .soft-btn { border-color: var(--crm-stroke); background: var(--crm-surface-elevated); color: var(--text-primary); }
            .namespace-card-grid { display: grid; gap: var(--space-3); grid-template-columns: repeat(auto-fit, minmax(min(100%, 220px), 1fr)); }
            .namespace-card { border: 1px solid var(--crm-stroke); border-radius: var(--radius-lg); padding: var(--space-3); background: var(--crm-surface-muted); cursor: pointer; transition: border-color var(--duration-fast), background var(--duration-fast), transform var(--duration-fast); }
            .namespace-card:hover { border-color: var(--crm-selected-stroke); transform: translateY(-1px); }
            .namespace-card.active { border-color: var(--crm-selected-stroke); background: var(--crm-selected-bg); }
            .namespace-card-title { color: var(--text-primary); font-size: var(--text-sm); font-weight: 600; margin-bottom: var(--space-1); }
            .namespace-info { border: 1px solid var(--crm-stroke); border-radius: var(--radius-md); background: var(--crm-surface-muted); color: var(--text-secondary); padding: var(--space-2) var(--space-3); font-size: var(--text-xs); }
            .chips { display: flex; flex-wrap: wrap; gap: var(--space-1); }
            .chip { border: 1px solid var(--crm-stroke); border-radius: var(--radius-full); padding: 2px var(--space-2); color: var(--text-secondary); background: var(--crm-surface-elevated); font-size: var(--text-xs); }
            .mono { font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, "Liberation Mono", "Courier New", monospace; font-size: var(--text-xs); }
            .menu-btn { width: 32px; height: 32px; display: none; align-items: center; justify-content: center; border-radius: var(--radius-md); background: var(--crm-surface-muted); border: 1px solid var(--crm-stroke); color: var(--text-primary); cursor: pointer; }
            .back-btn { display: inline-flex; align-items: center; gap: var(--space-2); background: none; border: none; color: var(--text-secondary); font-size: var(--text-sm); cursor: pointer; padding: 0; transition: color var(--duration-fast); }
            .back-btn:hover { color: var(--text-primary); }
            .schema-empty { color: var(--text-tertiary); font-size: var(--text-sm); }
            .namespace-selector { display: flex; gap: var(--space-2); flex-wrap: wrap; }
            .namespace-pill { display: inline-flex; align-items: center; gap: var(--space-2); border: 1px solid var(--crm-stroke); border-radius: var(--radius-full); background: var(--crm-surface-elevated); color: var(--text-primary); padding: 4px var(--space-2); font-size: var(--text-xs); cursor: pointer; }
            .namespace-pill.active { border-color: var(--crm-selected-stroke); background: var(--crm-selected-bg); }
            .namespace-pill.locked { opacity: 0.7; cursor: not-allowed; border-color: var(--crm-selected-stroke); background: var(--crm-selected-bg); }
            .namespace-pill:disabled { opacity: 0.5; cursor: not-allowed; }
            .type-edit-card { border: 1px solid var(--crm-stroke); border-radius: var(--radius-md); padding: var(--space-3); background: var(--crm-surface-muted); display: flex; flex-direction: column; gap: var(--space-2); }
            .type-edit-header { display: flex; align-items: center; justify-content: space-between; gap: var(--space-2); }
            .type-edit-title { display: flex; align-items: center; gap: var(--space-2); color: var(--text-primary); font-size: var(--text-sm); font-weight: 600; }
            .type-grid { display: grid; gap: var(--space-2); grid-template-columns: repeat(auto-fit, minmax(min(100%, 280px), 1fr)); }
            .hint { color: var(--text-tertiary); font-size: var(--text-xs); }
            @media (max-width: 767px) {
                .menu-btn { display: inline-flex; }
                .form-grid,
                .namespace-card-grid,
                .type-grid { grid-template-columns: 1fr; }
                .form-input,
                .form-textarea { max-width: 100%; min-width: 0; box-sizing: border-box; }
                .namespace-info { overflow-wrap: anywhere; word-break: break-word; }
            }
        `,
    ];

    constructor() {
        super();
        this._namespaces = [];
        this._entityTypes = [];
        this._selectedNamespaceName = null;
        this._selectedNamespaceDraftDescription = '';
        this._selectedNamespaceDraftAllowedTypeIds = [];
        this._selectedNamespaceEditability = null;
        this._namespaceEditorLoading = false;
        this._namespaceEditorSaving = false;
        this._editingTypeId = null;
        this._editingTypeDraft = null;
        this._showCreateForm = false;
        this._createSaving = false;
        this._selectedNamespaceCrmDraft = SpacesPage.defaultCrmDraft();
        this._schemaOptions = null;
        this._unsubscribe = CRMStore.subscribe((state) => {
            this._namespaces = state.namespaces.list || [];
            this._entityTypes = state.entities.entityTypes || [];
            this._selectedNamespaceName = state.namespaces.settingsSelected || null;
            this._selectedNamespaceEditability = state.namespaces.settingsEditability || null;
            this._namespaceEditorLoading = Boolean(state.namespaces.settingsLoading);
            this._namespaceEditorSaving = Boolean(state.namespaces.settingsSaving);
            this._schemaOptions = state.namespaces.schemaOptions || null;
        });
    }

    disconnectedCallback() {
        super.disconnectedCallback();
        this._unsubscribe?.();
    }

    static defaultCrmDraft() {
        return {
            show_note_voice_ui: true,
            default_note_voice: 'self',
            default_context_entity_id: '',
        };
    }

    _mergeNamespaceCrmDraft(namespace) {
        const base = SpacesPage.defaultCrmDraft();
        if (!namespace || typeof namespace !== 'object') {
            return base;
        }
        const cs = namespace.crm_settings;
        if (!cs || typeof cs !== 'object') {
            return base;
        }
        const voice = cs.default_note_voice;
        const allowedVoice = voice === 'none' || voice === 'last' || voice === 'self';
        return {
            show_note_voice_ui: cs.show_note_voice_ui !== false,
            default_note_voice: allowedVoice ? voice : 'self',
            default_context_entity_id: typeof cs.default_context_entity_id === 'string' ? cs.default_context_entity_id : '',
        };
    }

    _updateNamespaceCrmDraft(field, value) {
        this._selectedNamespaceCrmDraft = { ...this._selectedNamespaceCrmDraft, [field]: value };
    }

    async firstUpdated() {
        const crmApi = this.services.get('crmApi');
        await Promise.all([
            CRMStore.loadNamespaces(crmApi),
            CRMStore.loadEntityTypes(crmApi),
            CRMStore.loadTemplateSchemaOptions(crmApi),
        ]);
        if (this._namespaces.length > 0) {
            const selectedName = this._selectedNamespaceName && this._namespaces.some((item) => item.name === this._selectedNamespaceName)
                ? this._selectedNamespaceName
                : this._namespaces[0].name;
            await this._selectNamespaceForEditing(selectedName);
        }
    }

    _openSidebar() {
        window.dispatchEvent(new CustomEvent('platform-sidebar-open', { bubbles: true, composed: true }));
    }

    _spaceHints() {
        return {
            namespaceDescription: this.i18n.t('spaces_page.hint_namespace_description'),
            namespaceAllowedTypes: this.i18n.t('spaces_page.hint_namespace_allowed_types'),
            crmShowVoiceUi: this.i18n.t('spaces_page.hint_crm_voice_ui'),
            crmDefaultVoice: this.i18n.t('spaces_page.hint_crm_default_voice'),
            crmDefaultContext: this.i18n.t('spaces_page.hint_crm_default_context'),
        };
    }

    _resolveAllowedTypes(namespaceName) {
        return this._entityTypes.filter((entityType) => {
            const namespaceIds = Array.isArray(entityType.namespace_ids) ? entityType.namespace_ids : [];
            return namespaceIds.includes(namespaceName);
        });
    }

    _openNamespaceImports() {
        const name = this._selectedNamespaceName;
        if (!name || typeof name !== 'string') {
            this.warning(this.i18n.t('spaces_page.imports_pick_space'));
            return;
        }
        CRMStore.setSettingsNamespaceSelection(name.trim());
        CRMStore.setCurrentView('namespace_imports');
    }

    async _selectNamespaceForEditing(namespaceName) {
        try {
            if (!namespaceName || typeof namespaceName !== 'string') {
                throw new Error('Namespace name is required');
            }
            const normalizedName = namespaceName.trim();
            if (!normalizedName) {
                throw new Error('Namespace name is required');
            }
            this._editingTypeId = null;
            this._editingTypeDraft = null;
            const crmApi = this.services.get('crmApi');
            CRMStore.setSettingsNamespaceSelection(normalizedName);
            const payload = await CRMStore.loadNamespaceEditability(crmApi, normalizedName);
            const selectedNamespace = this._namespaces.find((item) => item.name === normalizedName);
            this._selectedNamespaceDraftDescription = selectedNamespace?.description || '';
            this._selectedNamespaceDraftAllowedTypeIds = Array.isArray(payload?.current_allowed_type_ids)
                ? [...payload.current_allowed_type_ids]
                : [];
            this._selectedNamespaceCrmDraft = this._mergeNamespaceCrmDraft(selectedNamespace);
        } catch (error) {
            const message = error instanceof Error ? error.message : this.i18n.t('spaces_page.err_load');
            this.error(message);
        }
    }

    _isTypeLocked(typeId) {
        const locked = this._selectedNamespaceEditability?.locked_type_ids;
        return Array.isArray(locked) && locked.includes(typeId);
    }

    _toggleNamespaceAllowedType(typeId, enabled) {
        if (this._isTypeLocked(typeId) && !enabled) {
            return;
        }
        const normalizedTypeId = typeof typeId === 'string' ? typeId.trim() : '';
        if (!normalizedTypeId) {
            throw new Error('Type ID is required');
        }
        const current = Array.isArray(this._selectedNamespaceDraftAllowedTypeIds)
            ? this._selectedNamespaceDraftAllowedTypeIds
            : [];
        const next = enabled
            ? [...new Set([...current, normalizedTypeId])]
            : current.filter((item) => item !== normalizedTypeId);
        this._selectedNamespaceDraftAllowedTypeIds = next;
    }

    _startEditType(entityType) {
        this._editingTypeId = entityType.type_id;
        this._editingTypeDraft = EntityTypeForm.draftFromEntityType(entityType);
    }

    _cancelEditType() {
        this._editingTypeId = null;
        this._editingTypeDraft = null;
    }

    _openCreateForm() {
        this._showCreateForm = true;
        this._editingTypeId = null;
        this._editingTypeDraft = null;
    }

    _closeCreateForm() {
        this._showCreateForm = false;
    }

    async _onTypeCreated(e) {
        try {
            const { type_id, payload } = e.detail;
            if (!type_id || !payload) {
                throw new Error('type_id and payload are required');
            }
            this._createSaving = true;
            const crmApi = this.services.get('crmApi');
            const namespaceIds = this._selectedNamespaceName
                ? [this._selectedNamespaceName]
                : ['default'];
            await crmApi.createEntityType({
                type_id,
                ...payload,
                namespace_ids: namespaceIds,
            });
            await CRMStore.loadEntityTypes(crmApi);
            this._selectedNamespaceDraftAllowedTypeIds = [
                ...new Set([...this._selectedNamespaceDraftAllowedTypeIds, type_id]),
            ];
            await this._saveNamespaceSettings();
            await CRMStore.loadNamespaceEditability(crmApi, this._selectedNamespaceName);
            this._showCreateForm = false;
            this.success(this.i18n.t('spaces_page.success_type_created'));
        } catch (error) {
            const message = error instanceof Error ? error.message : this.i18n.t('spaces_page.err_type_create');
            this.error(message);
        } finally {
            this._createSaving = false;
        }
    }

    async _onTypeEdited(e) {
        try {
            const { type_id, payload } = e.detail;
            if (!type_id || !payload) {
                throw new Error('type_id and payload are required');
            }
            const crmApi = this.services.get('crmApi');
            await crmApi.updateEntityType(type_id, payload);
            await CRMStore.loadEntityTypes(crmApi);
            this._editingTypeId = null;
            this._editingTypeDraft = null;
            this.success(this.i18n.t('spaces_page.success_type_updated'));
        } catch (error) {
            const message = error instanceof Error ? error.message : this.i18n.t('spaces_page.err_type_update');
            this.error(message);
        }
    }

    async _saveNamespaceSettings() {
        try {
            if (!this._selectedNamespaceName) {
                throw new Error('Namespace is not selected');
            }
            const normalizedAllowedTypeIds = Array.isArray(this._selectedNamespaceDraftAllowedTypeIds)
                ? this._selectedNamespaceDraftAllowedTypeIds
                    .map((item) => String(item).trim())
                    .filter((item) => item.length > 0)
                : [];
            const ctxRaw = (this._selectedNamespaceCrmDraft.default_context_entity_id || '').trim();
            const payload = {
                description: this._selectedNamespaceDraftDescription.trim() || null,
                allowed_type_ids: [...new Set(normalizedAllowedTypeIds)],
                crm_settings: {
                    show_note_voice_ui: Boolean(this._selectedNamespaceCrmDraft.show_note_voice_ui),
                    default_note_voice: this._selectedNamespaceCrmDraft.default_note_voice,
                    default_context_entity_id: ctxRaw.length > 0 ? ctxRaw : null,
                },
            };
            const crmApi = this.services.get('crmApi');
            await CRMStore.updateExistingNamespace(crmApi, this._selectedNamespaceName, payload);
            this.success(this.i18n.t('spaces_page.success_namespace_saved'));
        } catch (error) {
            const message = error instanceof Error ? error.message : this.i18n.t('spaces_page.err_namespace_save');
            this.error(message);
        }
    }

    _renderTypePills() {
        return (this._entityTypes || []).map((entityType) => {
            const checked = (this._selectedNamespaceDraftAllowedTypeIds || []).includes(entityType.type_id);
            const locked = this._isTypeLocked(entityType.type_id);
            if (locked) {
                return html`
                    <button type="button" class="namespace-pill locked active" disabled title=${this.i18n.t('spaces_page.type_locked_title')}>
                        <platform-icon name="lock" size="10"></platform-icon>
                        ${entityType.name}
                    </button>
                `;
            }
            return html`
                <button type="button" class="namespace-pill ${checked ? 'active' : ''}" @click=${() => this._toggleNamespaceAllowedType(entityType.type_id, !checked)}>
                    ${entityType.name}
                </button>
            `;
        });
    }

    _renderTypeEditor() {
        if (!this._editingTypeId || !this._editingTypeDraft) {
            return '';
        }
        return html`
            <entity-type-form
                mode="edit"
                type-id=${this._editingTypeId}
                .draft=${{ ...this._editingTypeDraft }}
                .schemaOptions=${this._schemaOptions}
                @type-saved=${this._onTypeEdited}
                @type-cancel=${this._cancelEditType}
            ></entity-type-form>
        `;
    }

    _renderCreateForm() {
        if (!this._showCreateForm) {
            return '';
        }
        return html`
            <entity-type-form
                mode="create"
                .draft=${EntityTypeForm.defaultDraft()}
                .schemaOptions=${this._schemaOptions}
                .saving=${this._createSaving}
                @type-saved=${this._onTypeCreated}
                @type-cancel=${this._closeCreateForm}
            ></entity-type-form>
        `;
    }

    _renderAllowedTypeCards() {
        const allowedTypes = this._resolveAllowedTypes(this._selectedNamespaceName);
        if (allowedTypes.length === 0) {
            return html`<div class="card-text">${this.i18n.t('spaces_page.no_allowed_types')}</div>`;
        }
        return html`
            <div class="type-grid">
                ${allowedTypes.map((entityType) => {
                    const locked = this._isTypeLocked(entityType.type_id);
                    return html`
                        <div class="type-edit-card">
                            <div class="type-edit-header">
                                <div class="type-edit-title">
                                    ${entityType.name}
                                    ${locked ? html`<platform-icon name="lock" size="12" title=${this.i18n.t('spaces_page.type_in_use_title')}></platform-icon>` : ''}
                                </div>
                                <button class="save-btn soft-btn" @click=${() => this._startEditType(entityType)}>${this.i18n.t('spaces_page.edit')}</button>
                            </div>
                            <div class="hint mono">${entityType.type_id}</div>
                            <div class="card-text">${entityType.description || this.i18n.t('spaces_page.no_description')}</div>
                        </div>
                    `;
                })}
            </div>
        `;
    }

    render() {
        const spaceHints = this._spaceHints();
        return html`
            <div class="container">
                <div class="section">
                    <button class="back-btn" @click=${() => CRMStore.setCurrentView('settings')}>
                        <platform-icon name="arrow-left" size="14"></platform-icon>
                        ${this.i18n.t('spaces_page.sidebar_title')}
                    </button>
                    <div class="hero">
                        <div>
                            <div class="hero-title">
                                <button class="menu-btn" @click=${this._openSidebar} title=${this.i18n.t('settings_hub.open_menu')}>
                                    <platform-icon name="menu" size="18"></platform-icon>
                                </button>
                                <platform-icon name="folder" size="18"></platform-icon>
                                ${this.i18n.t('spaces_page.hero_title')}
                            </div>
                            <div class="hero-subtitle">${this.i18n.t('spaces_page.hero_subtitle')}</div>
                        </div>
                        <button type="button" class="save-btn soft-btn" @click=${this._openNamespaceImports}>
                            <platform-icon name="database" size="14"></platform-icon>
                            ${this.i18n.t('spaces_page.imports_nav')}
                        </button>
                    </div>
                    <div class="namespace-card-grid">
                        ${this._namespaces.map((namespace) => html`
                            <div
                                class="namespace-card ${namespace.name === this._selectedNamespaceName ? 'active' : ''}"
                                @click=${() => this._selectNamespaceForEditing(namespace.name)}
                            >
                                <div class="namespace-card-title">${namespace.name}</div>
                                <div class="card-text">${namespace.description || this.i18n.t('spaces_page.no_description')}</div>
                                <div class="chips">
                                    ${this._resolveAllowedTypes(namespace.name).map((entityType) => html`<span class="chip">${entityType.name}</span>`)}
                                </div>
                            </div>
                        `)}
                    </div>
                </div>

                ${this._selectedNamespaceName ? html`
                    <div class="section">
                        <div class="section-header">
                            <platform-icon name="edit" size="16"></platform-icon>
                            ${this.i18n.t('spaces_page.editor_title', { name: this._selectedNamespaceName })}
                        </div>
                        ${this._namespaceEditorLoading ? html`<div class="schema-empty">${this.i18n.t('spaces_page.loading_constraints')}</div>` : ''}
                        ${this._selectedNamespaceEditability ? html`
                            <div class="namespace-info">
                                ${this.i18n.t('spaces_page.entity_count_line', { count: String(this._selectedNamespaceEditability.entity_count) })}
                                ${this._selectedNamespaceEditability.locked_type_ids?.length > 0
                                    ? html`${this.i18n.t('spaces_page.locked_types_suffix', { ids: this._selectedNamespaceEditability.locked_type_ids.join(', ') })}`
                                    : ''}
                            </div>
                        ` : ''}
                        <div class="form-grid">
                            <div class="form-group">
                                <label class="form-label label-with-hint">
                                    <span>${this.i18n.t('spaces_page.label_namespace_description')}</span>
                                    <platform-help-hint strategy="local" label=${this.i18n.t('spaces_page.help_label_namespace')} .text=${spaceHints.namespaceDescription}></platform-help-hint>
                                </label>
                                <textarea
                                    class="form-textarea"
                                    .value=${this._selectedNamespaceDraftDescription}
                                    @input=${(e) => { this._selectedNamespaceDraftDescription = e.target.value; }}
                                ></textarea>
                            </div>
                            <div class="form-group">
                                <label class="form-label label-with-hint">
                                    <span>${this.i18n.t('spaces_page.label_allowed_types')}</span>
                                    <platform-help-hint strategy="local" label=${this.i18n.t('spaces_page.help_label_allowed_types')} .text=${spaceHints.namespaceAllowedTypes}></platform-help-hint>
                                </label>
                                <div class="namespace-selector">
                                    ${this._renderTypePills()}
                                </div>
                                ${this._selectedNamespaceEditability ? html`
                                    <div class="chips">
                                        <span class="chip">${this.i18n.t('spaces_page.chip_entity_count', { count: String(this._selectedNamespaceEditability.entity_count) })}</span>
                                        ${(this._selectedNamespaceEditability.used_type_ids || []).map((typeId) => html`<span class="chip mono">${typeId}</span>`)}
                                    </div>
                                ` : ''}
                            </div>
                            <div class="form-group">
                                <label class="form-label label-with-hint">
                                    <span>${this.i18n.t('spaces_page.crm_notes_block')}</span>
                                    <platform-help-hint strategy="local" label=${this.i18n.t('spaces_page.help_label_voice')} .text=${spaceHints.crmShowVoiceUi}></platform-help-hint>
                                </label>
                                <div style="display:flex;align-items:center;gap:var(--space-2);flex-wrap:wrap;">
                                    <platform-switch
                                        size="sm"
                                        label=${this.i18n.t('spaces_page.toggle_voice_label')}
                                        .checked=${Boolean(this._selectedNamespaceCrmDraft.show_note_voice_ui)}
                                        @change=${(e) => this._updateNamespaceCrmDraft('show_note_voice_ui', Boolean(e.detail.value))}
                                    ></platform-switch>
                                </div>
                            </div>
                            <div class="form-group">
                                <label class="form-label label-with-hint">
                                    <span>${this.i18n.t('spaces_page.default_voice')}</span>
                                    <platform-help-hint strategy="local" label=${this.i18n.t('spaces_page.help_label_default_voice')} .text=${spaceHints.crmDefaultVoice}></platform-help-hint>
                                </label>
                                <select
                                    class="form-input"
                                    style="max-width:320px;"
                                    .value=${this._selectedNamespaceCrmDraft.default_note_voice}
                                    @change=${(e) => this._updateNamespaceCrmDraft('default_note_voice', e.target.value)}
                                >
                                    <option value="self">${this.i18n.t('spaces_page.voice_self')}</option>
                                    <option value="none">${this.i18n.t('spaces_page.voice_none')}</option>
                                    <option value="last">${this.i18n.t('spaces_page.voice_last')}</option>
                                </select>
                            </div>
                            <div class="form-group">
                                <label class="form-label label-with-hint">
                                    <span>${this.i18n.t('spaces_page.default_context_label')}</span>
                                    <platform-help-hint strategy="local" label=${this.i18n.t('spaces_page.help_label_context')} .text=${spaceHints.crmDefaultContext}></platform-help-hint>
                                </label>
                                <input
                                    class="form-input mono"
                                    placeholder=${this.i18n.t('spaces_page.optional_placeholder')}
                                    .value=${this._selectedNamespaceCrmDraft.default_context_entity_id}
                                    @input=${(e) => this._updateNamespaceCrmDraft('default_context_entity_id', e.target.value)}
                                />
                            </div>
                        </div>
                        <button class="save-btn" ?disabled=${this._namespaceEditorSaving} @click=${this._saveNamespaceSettings}>
                            <platform-icon name="save" size="14"></platform-icon>
                            ${this._namespaceEditorSaving ? this.i18n.t('entity_modal.saving') : this.i18n.t('spaces_page.save_namespace')}
                        </button>
                    </div>

                    <div class="section">
                        <div class="section-header" style="justify-content: space-between;">
                            <div style="display: inline-flex; align-items: center; gap: var(--space-2);">
                                <platform-icon name="list" size="16"></platform-icon>
                                ${this.i18n.t('spaces_page.types_in_space')}
                            </div>
                            ${!this._showCreateForm ? html`
                                <button class="save-btn" @click=${this._openCreateForm}>
                                    <platform-icon name="plus" size="14"></platform-icon>
                                    ${this.i18n.t('spaces_page.add_type')}
                                </button>
                            ` : ''}
                        </div>
                        <div class="hint">${this.i18n.t('spaces_page.types_hint')}</div>
                        ${this._renderCreateForm()}
                        ${this._renderAllowedTypeCards()}
                        ${this._renderTypeEditor()}
                    </div>
                    <div class="section">
                        <div class="section-header">
                            <platform-icon name="lock" size="16"></platform-icon>
                            ${this.i18n.t('grants.namespace_section_title', { name: this._selectedNamespaceName })}
                        </div>
                        <namespace-grants-panel namespace=${this._selectedNamespaceName}></namespace-grants-panel>
                    </div>
                ` : html`<div class="section"><div class="card-text">${this.i18n.t('spaces_page.pick_space')}</div></div>`}
            </div>
        `;
    }
}

customElements.define('spaces-page', SpacesPage);
