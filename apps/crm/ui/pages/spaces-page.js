import { html, css } from 'lit';
import { PlatformElement } from '@platform/lib/platform-element/index.js';
import { CRMStore } from '../store/crm.store.js';
import '@platform/lib/components/platform-icon.js';
import '@platform/lib/components/platform-help-hint.js';

const SPACES_HINTS = {
    namespaceDescription: 'Описание текущего пространства. Изменение описания не влияет на существующие сущности и доступно всегда.',
    namespaceAllowedTypes: 'Типы, которые можно создавать в этом пространстве. Используемые типы нельзя убрать. Новые типы можно добавить всегда.',
    typePrompt: 'Подсказка для AI-извлечения и структурирования данных под этот тип.',
    typeDescription: 'Подробное пояснение типа: что хранится, какие атрибуты обязательны, в каких процессах используется.',
};

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
    };

    static styles = [
        PlatformElement.styles,
        css`
            :host { display: flex; flex-direction: column; width: 100%; height: 100%; min-height: 0; overflow: hidden; }
            .container { display: flex; flex-direction: column; gap: var(--space-4); height: 100%; overflow-y: auto; padding: var(--space-2); }
            .section { background: var(--crm-surface); border: 1px solid var(--crm-stroke); border-radius: var(--radius-xl); padding: var(--space-4); display: flex; flex-direction: column; gap: var(--space-3); }
            .hero { display: flex; align-items: center; justify-content: space-between; gap: var(--space-3); }
            .hero-title { display: flex; align-items: center; gap: var(--space-2); color: var(--text-primary); font-size: var(--text-lg); font-weight: 700; }
            .hero-subtitle { color: var(--text-secondary); font-size: var(--text-sm); }
            .section-header { display: flex; align-items: center; gap: var(--space-2); color: var(--text-primary); font-size: var(--text-lg); font-weight: 600; }
            .card-text { color: var(--text-secondary); font-size: var(--text-sm); }
            .form-grid { display: grid; gap: var(--space-3); grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)); }
            .form-group { display: flex; flex-direction: column; gap: var(--space-2); }
            .form-label { color: var(--text-secondary); font-size: var(--text-sm); font-weight: 500; }
            .label-with-hint { display: inline-flex; align-items: center; gap: var(--space-2); }
            .form-input, .form-textarea { border: 1px solid var(--crm-stroke); border-radius: var(--radius-md); background: var(--crm-surface-elevated); color: var(--text-primary); padding: var(--space-2) var(--space-3); font-size: var(--text-sm); }
            .form-textarea { min-height: 88px; resize: vertical; }
            .save-btn { display: inline-flex; align-items: center; justify-content: center; gap: var(--space-2); border: 1px solid var(--crm-button-primary-bg); background: var(--crm-button-primary-bg); color: var(--crm-button-primary-text); border-radius: var(--radius-md); padding: var(--space-2) var(--space-4); cursor: pointer; width: fit-content; }
            .save-btn:disabled { opacity: 0.5; cursor: not-allowed; }
            .soft-btn { border-color: var(--crm-stroke); background: var(--crm-surface-elevated); color: var(--text-primary); }
            .namespace-card-grid { display: grid; gap: var(--space-3); grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)); }
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
            .type-grid { display: grid; gap: var(--space-2); grid-template-columns: repeat(auto-fit, minmax(280px, 1fr)); }
            .hint { color: var(--text-tertiary); font-size: var(--text-xs); }
            @media (max-width: 767px) { .menu-btn { display: inline-flex; } }
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
        this._unsubscribe = CRMStore.subscribe((state) => {
            this._namespaces = state.namespaces.list || [];
            this._entityTypes = state.entities.entityTypes || [];
            this._selectedNamespaceName = state.namespaces.settingsSelected || null;
            this._selectedNamespaceEditability = state.namespaces.settingsEditability || null;
            this._namespaceEditorLoading = Boolean(state.namespaces.settingsLoading);
            this._namespaceEditorSaving = Boolean(state.namespaces.settingsSaving);
        });
    }

    disconnectedCallback() {
        super.disconnectedCallback();
        this._unsubscribe?.();
    }

    async firstUpdated() {
        const crmApi = this.services.get('crmApi');
        await Promise.all([
            CRMStore.loadNamespaces(crmApi),
            CRMStore.loadEntityTypes(crmApi),
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

    _resolveAllowedTypes(namespaceName) {
        return this._entityTypes.filter((entityType) => {
            const namespaceIds = Array.isArray(entityType.namespace_ids) ? entityType.namespace_ids : [];
            return namespaceIds.includes(namespaceName);
        });
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
        } catch (error) {
            const message = error instanceof Error ? error.message : 'Ошибка загрузки настроек пространства';
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
        this._editingTypeDraft = {
            name: entityType.name || '',
            description: entityType.description || '',
            prompt: entityType.prompt || '',
        };
    }

    _cancelEditType() {
        this._editingTypeId = null;
        this._editingTypeDraft = null;
    }

    async _saveEditType() {
        try {
            if (!this._editingTypeId || !this._editingTypeDraft) {
                throw new Error('No type selected for editing');
            }
            const crmApi = this.services.get('crmApi');
            await crmApi.updateEntityType(this._editingTypeId, {
                name: this._editingTypeDraft.name.trim() || null,
                description: this._editingTypeDraft.description.trim() || null,
                prompt: this._editingTypeDraft.prompt.trim() || null,
            });
            await CRMStore.loadEntityTypes(crmApi);
            this._editingTypeId = null;
            this._editingTypeDraft = null;
            this.success('Тип обновлен');
        } catch (error) {
            const message = error instanceof Error ? error.message : 'Ошибка обновления типа';
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
            const payload = {
                description: this._selectedNamespaceDraftDescription.trim() || null,
                allowed_type_ids: [...new Set(normalizedAllowedTypeIds)],
            };
            const crmApi = this.services.get('crmApi');
            await CRMStore.updateExistingNamespace(crmApi, this._selectedNamespaceName, payload);
            this.success('Пространство сохранено');
        } catch (error) {
            const message = error instanceof Error ? error.message : 'Ошибка сохранения пространства';
            this.error(message);
        }
    }

    _renderTypePills() {
        return (this._entityTypes || []).map((entityType) => {
            const checked = (this._selectedNamespaceDraftAllowedTypeIds || []).includes(entityType.type_id);
            const locked = this._isTypeLocked(entityType.type_id);
            if (locked) {
                return html`
                    <button type="button" class="namespace-pill locked active" disabled title="Тип используется сущностями, нельзя убрать">
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
            <div class="type-edit-card">
                <div class="type-edit-header">
                    <div class="type-edit-title">
                        <platform-icon name="edit" size="14"></platform-icon>
                        Редактирование типа: <span class="mono">${this._editingTypeId}</span>
                    </div>
                    <button class="save-btn soft-btn" @click=${this._cancelEditType}>Отмена</button>
                </div>
                <div class="hint">type_id неизменяем. Можно редактировать название, описание и промпт.</div>
                <div class="form-grid">
                    <div class="form-group">
                        <label class="form-label">Название</label>
                        <input class="form-input" .value=${this._editingTypeDraft.name}
                            @input=${(e) => { this._editingTypeDraft = { ...this._editingTypeDraft, name: e.target.value }; }} />
                    </div>
                    <div class="form-group">
                        <label class="form-label label-with-hint">
                            <span>Описание</span>
                            <platform-help-hint strategy="local" label="Справка: описание типа" .text=${SPACES_HINTS.typeDescription}></platform-help-hint>
                        </label>
                        <textarea class="form-textarea" .value=${this._editingTypeDraft.description}
                            @input=${(e) => { this._editingTypeDraft = { ...this._editingTypeDraft, description: e.target.value }; }}></textarea>
                    </div>
                    <div class="form-group">
                        <label class="form-label label-with-hint">
                            <span>Промпт для извлечения</span>
                            <platform-help-hint strategy="local" label="Справка: промпт типа" .text=${SPACES_HINTS.typePrompt}></platform-help-hint>
                        </label>
                        <textarea class="form-textarea" .value=${this._editingTypeDraft.prompt}
                            @input=${(e) => { this._editingTypeDraft = { ...this._editingTypeDraft, prompt: e.target.value }; }}></textarea>
                    </div>
                </div>
                <button class="save-btn" @click=${this._saveEditType}>
                    <platform-icon name="save" size="14"></platform-icon>
                    Сохранить тип
                </button>
            </div>
        `;
    }

    _renderAllowedTypeCards() {
        const allowedTypes = this._resolveAllowedTypes(this._selectedNamespaceName);
        if (allowedTypes.length === 0) {
            return html`<div class="card-text">Нет разрешенных типов в пространстве</div>`;
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
                                    ${locked ? html`<platform-icon name="lock" size="12" title="Используется сущностями"></platform-icon>` : ''}
                                </div>
                                <button class="save-btn soft-btn" @click=${() => this._startEditType(entityType)}>Редактировать</button>
                            </div>
                            <div class="hint mono">${entityType.type_id}</div>
                            <div class="card-text">${entityType.description || 'Описание не задано'}</div>
                        </div>
                    `;
                })}
            </div>
        `;
    }

    render() {
        return html`
            <div class="container">
                <div class="section">
                    <button class="back-btn" @click=${() => CRMStore.setCurrentView('settings')}>
                        <platform-icon name="arrow-left" size="14"></platform-icon>
                        Настройки
                    </button>
                    <div class="hero">
                        <div>
                            <div class="hero-title">
                                <button class="menu-btn" @click=${this._openSidebar} title="Открыть меню">
                                    <platform-icon name="menu" size="18"></platform-icon>
                                </button>
                                <platform-icon name="folder" size="18"></platform-icon>
                                Настройки пространств
                            </div>
                            <div class="hero-subtitle">Управление пространствами компании: описания, разрешенные типы, редактирование метаданных типов.</div>
                        </div>
                    </div>
                    <div class="namespace-card-grid">
                        ${this._namespaces.map((namespace) => html`
                            <div
                                class="namespace-card ${namespace.name === this._selectedNamespaceName ? 'active' : ''}"
                                @click=${() => this._selectNamespaceForEditing(namespace.name)}
                            >
                                <div class="namespace-card-title">${namespace.name}</div>
                                <div class="card-text">${namespace.description || 'Описание не задано'}</div>
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
                            Редактор пространства: ${this._selectedNamespaceName}
                        </div>
                        ${this._namespaceEditorLoading ? html`<div class="schema-empty">Загрузка ограничений пространства...</div>` : ''}
                        ${this._selectedNamespaceEditability ? html`
                            <div class="namespace-info">
                                Сущностей: ${this._selectedNamespaceEditability.entity_count}.
                                Добавлять новые типы можно всегда.
                                ${this._selectedNamespaceEditability.locked_type_ids?.length > 0
                                    ? html` Типы с данными (${this._selectedNamespaceEditability.locked_type_ids.join(', ')}) нельзя убрать.`
                                    : ''}
                            </div>
                        ` : ''}
                        <div class="form-grid">
                            <div class="form-group">
                                <label class="form-label label-with-hint">
                                    <span>Описание пространства</span>
                                    <platform-help-hint strategy="local" label="Справка: описание пространства" .text=${SPACES_HINTS.namespaceDescription}></platform-help-hint>
                                </label>
                                <textarea
                                    class="form-textarea"
                                    .value=${this._selectedNamespaceDraftDescription}
                                    @input=${(e) => { this._selectedNamespaceDraftDescription = e.target.value; }}
                                ></textarea>
                            </div>
                            <div class="form-group">
                                <label class="form-label label-with-hint">
                                    <span>Разрешенные типы</span>
                                    <platform-help-hint strategy="local" label="Справка: разрешенные типы" .text=${SPACES_HINTS.namespaceAllowedTypes}></platform-help-hint>
                                </label>
                                <div class="namespace-selector">
                                    ${this._renderTypePills()}
                                </div>
                                ${this._selectedNamespaceEditability ? html`
                                    <div class="chips">
                                        <span class="chip">Сущностей: ${this._selectedNamespaceEditability.entity_count}</span>
                                        ${(this._selectedNamespaceEditability.used_type_ids || []).map((typeId) => html`<span class="chip mono">${typeId}</span>`)}
                                    </div>
                                ` : ''}
                            </div>
                        </div>
                        <button class="save-btn" ?disabled=${this._namespaceEditorSaving} @click=${this._saveNamespaceSettings}>
                            <platform-icon name="save" size="14"></platform-icon>
                            ${this._namespaceEditorSaving ? 'Сохранение...' : 'Сохранить пространство'}
                        </button>
                    </div>

                    <div class="section">
                        <div class="section-header">
                            <platform-icon name="list" size="16"></platform-icon>
                            Типы в пространстве
                        </div>
                        <div class="hint">Можно редактировать название, описание и промпт. Идентификатор (type_id) неизменяем.</div>
                        ${this._renderAllowedTypeCards()}
                        ${this._renderTypeEditor()}
                    </div>
                ` : html`<div class="section"><div class="card-text">Выберите пространство для редактирования</div></div>`}
            </div>
        `;
    }
}

customElements.define('spaces-page', SpacesPage);
