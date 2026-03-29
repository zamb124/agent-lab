import { html, css } from 'lit';
import { PlatformElement } from '@platform/lib/platform-element/index.js';
import { PlatformModal } from '@platform/lib/components/glass-modal.js';
import { formStyles } from '@platform/lib/styles/shared/form.styles.js';
import { buttonStyles } from '@platform/lib/styles/shared/button.styles.js';
import { CRMStore } from '../store/crm.store.js';
import '@platform/lib/components/platform-icon.js';
import '@platform/lib/components/platform-icon-picker.js';

function parseJson(rawValue, fieldName) {
    try {
        const parsed = JSON.parse(rawValue);
        if (parsed === null || typeof parsed !== 'object') {
            throw new Error(`${fieldName} должен быть object/array`);
        }
        return parsed;
    } catch {
        throw new Error(`${fieldName}: некорректный JSON`);
    }
}

function getDefaultTypeDraft() {
    return {
        type_id: '',
        name: '',
        description: '',
        prompt: '',
        required_fields: '{}',
        optional_fields: '{}',
        namespace_ids: '[]',
        parent_type_id: '',
        icon: '',
        color: '',
        is_event: false,
        check_duplicates: true,
        weight_coefficient: '1.0',
    };
}

class TemplateCreateModal extends PlatformModal {
    static properties = {
        ...PlatformModal.properties,
        _templateId: { state: true },
        _name: { state: true },
        _description: { state: true },
        _icon: { state: true },
        _saving: { state: true },
        _iconOptions: { state: true },
    };

    static styles = [
        PlatformModal.styles,
        formStyles,
        buttonStyles,
        css`
            .form-grid { display: grid; gap: var(--space-4); }
            .icon-input-wrap { display: grid; grid-template-columns: 40px minmax(0, 1fr); gap: var(--space-2); align-items: center; }
            .icon-preview { width: 36px; height: 36px; border-radius: var(--radius-md); border: 1px solid var(--crm-stroke); background: var(--crm-surface-elevated); display: flex; align-items: center; justify-content: center; color: var(--text-secondary); }
            .footer-actions { display: flex; gap: var(--space-3); justify-content: flex-end; width: 100%; }
            .btn { padding: var(--space-2) var(--space-4); border-radius: var(--radius-lg); font-size: var(--text-sm); font-weight: 500; cursor: pointer; transition: all var(--duration-fast); }
            .btn-secondary { background: var(--crm-button-secondary-bg); border: 1px solid var(--crm-button-secondary-bg); color: var(--crm-button-secondary-text); }
            .btn-secondary:hover { background: var(--crm-button-secondary-hover); border-color: var(--crm-button-secondary-hover); color: var(--crm-button-secondary-text); }
            .btn-primary { background: var(--crm-button-primary-bg); border: 1px solid var(--crm-button-primary-bg); color: var(--crm-button-primary-text); }
            .btn-primary:hover:not(:disabled) { background: var(--crm-button-primary-hover); border-color: var(--crm-button-primary-hover); }
            .btn-primary:disabled { opacity: 0.5; cursor: not-allowed; }
        `,
    ];

    constructor() {
        super();
        this.size = 'md';
        this._templateId = '';
        this._name = '';
        this._description = '';
        this._icon = 'folder';
        this._saving = false;
        this._iconOptions = [];
    }

    renderHeader() {
        return 'Новый шаблон';
    }

    _resolveTemplateIcon(iconName) {
        const value = typeof iconName === 'string' ? iconName.trim() : '';
        return value || 'folder';
    }

    firstUpdated() {
        super.firstUpdated?.();
        const iconOptions = this.icon.availableIcons;
        if (!Array.isArray(iconOptions) || iconOptions.length === 0) {
            throw new Error('Icon options are required');
        }
        this._iconOptions = iconOptions;
    }

    async _onSave() {
        const templateId = this._templateId.trim();
        const templateName = this._name.trim();
        if (!templateId || !templateName) {
            this.error('Template ID и название обязательны');
            return;
        }
        this._saving = true;
        try {
            const crmApi = this.services.get('crmApi');
            await CRMStore.createNamespaceTemplate(crmApi, {
                template_id: templateId,
                name: templateName,
                description: this._description.trim() || null,
                icon: this._icon.trim() || null,
            });
            this.dispatchEvent(new CustomEvent('saved', {
                detail: { templateId },
                bubbles: true,
                composed: true,
            }));
            this.close();
            this.success('Шаблон создан');
        } finally {
            this._saving = false;
        }
    }

    renderBody() {
        return html`
            <div class="form-grid">
                <div class="form-group">
                    <label class="form-label">Template ID *</label>
                    <input class="form-input mono" .value=${this._templateId} @input=${(e) => { this._templateId = e.target.value; }} />
                </div>
                <div class="form-group">
                    <label class="form-label">Название *</label>
                    <input class="form-input" .value=${this._name} @input=${(e) => { this._name = e.target.value; }} />
                </div>
                <div class="form-group">
                    <label class="form-label">Описание</label>
                    <textarea class="form-textarea" .value=${this._description} @input=${(e) => { this._description = e.target.value; }}></textarea>
                </div>
                <div class="form-group">
                    <label class="form-label">Иконка шаблона</label>
                    <platform-icon-picker
                        .icons=${this._iconOptions}
                        .value=${this._resolveTemplateIcon(this._icon)}
                        @change=${(e) => { this._icon = e.detail.value; }}
                    ></platform-icon-picker>
                </div>
            </div>
        `;
    }

    renderFooter() {
        const submitDisabled = this._saving || !this._templateId.trim() || !this._name.trim();
        return html`
            <div class="footer-actions">
                <button type="button" class="btn btn-secondary" @click=${() => this.close()}>Отмена</button>
                <button type="button" class="btn btn-primary" ?disabled=${submitDisabled} @click=${this._onSave}>
                    ${this._saving ? 'Создание...' : 'Создать'}
                </button>
            </div>
        `;
    }
}

customElements.define('template-create-modal', TemplateCreateModal);

export class SettingsPage extends PlatformElement {
    static properties = {
        _namespaces: { state: true },
        _templates: { state: true },
        _templateDetails: { state: true },
        _entityTypes: { state: true },
        _selectedTemplateId: { state: true },
        _showTemplateModal: { state: true },
        _iconOptions: { state: true },
        _typeDraft: { state: true },
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
            .section-header.between { justify-content: space-between; }
            .section-header-main { display: inline-flex; align-items: center; gap: var(--space-2); }
            .grid { display: grid; gap: var(--space-3); grid-template-columns: repeat(auto-fit, minmax(240px, 1fr)); }
            .card {
                border: 1px solid var(--crm-stroke);
                border-radius: var(--radius-lg);
                padding: var(--space-3);
                background: var(--crm-surface-muted);
                transition: border-color var(--duration-fast), background var(--duration-fast), transform var(--duration-fast);
            }
            .card:hover { border-color: var(--crm-selected-stroke); transform: translateY(-1px); }
            .card-title { color: var(--text-primary); font-size: var(--text-sm); font-weight: 600; margin-bottom: var(--space-1); }
            .card-text { color: var(--text-secondary); font-size: var(--text-sm); }
            .form-grid { display: grid; gap: var(--space-3); grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)); }
            .form-group { display: flex; flex-direction: column; gap: var(--space-2); }
            .form-label { color: var(--text-secondary); font-size: var(--text-sm); font-weight: 500; }
            .form-input, .form-select, .form-textarea { border: 1px solid var(--crm-stroke); border-radius: var(--radius-md); background: var(--crm-surface-elevated); color: var(--text-primary); padding: var(--space-2) var(--space-3); font-size: var(--text-sm); }
            .form-textarea { min-height: 88px; resize: vertical; }
            .save-btn { display: inline-flex; align-items: center; justify-content: center; gap: var(--space-2); border: 1px solid var(--crm-button-primary-bg); background: var(--crm-button-primary-bg); color: var(--crm-button-primary-text); border-radius: var(--radius-md); padding: var(--space-2) var(--space-4); cursor: pointer; width: fit-content; }
            .save-btn:disabled { opacity: 0.5; cursor: not-allowed; }
            .soft-btn { border-color: var(--crm-stroke); background: var(--crm-surface-elevated); color: var(--text-primary); }
            .danger-btn { border-color: #B91C1C; background: #7F1D1D; color: #FEE2E2; }
            .namespace-list { display: grid; gap: var(--space-2); }
            .namespace-row { border: 1px solid var(--crm-stroke); border-radius: var(--radius-md); padding: var(--space-3); background: var(--crm-surface-muted); }
            .namespace-name { color: var(--text-primary); font-size: var(--text-sm); font-weight: 600; margin-bottom: var(--space-2); }
            .chips { display: flex; flex-wrap: wrap; gap: var(--space-1); }
            .chip { border: 1px solid var(--crm-stroke); border-radius: var(--radius-full); padding: 2px var(--space-2); color: var(--text-secondary); background: var(--crm-surface-elevated); font-size: var(--text-xs); }
            .menu-btn { width: 32px; height: 32px; display: none; align-items: center; justify-content: center; border-radius: var(--radius-md); background: var(--crm-surface-muted); border: 1px solid var(--crm-stroke); color: var(--text-primary); cursor: pointer; }
            .toolbar { display: flex; gap: var(--space-2); flex-wrap: wrap; align-items: center; }
            .split { display: grid; gap: var(--space-3); grid-template-columns: minmax(260px, 360px) minmax(0, 1fr); }
            .row { display: flex; gap: var(--space-2); flex-wrap: wrap; }
            .mono { font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, "Liberation Mono", "Courier New", monospace; font-size: var(--text-xs); }
            .template-card { cursor: pointer; }
            .template-card.active { border-color: var(--crm-selected-stroke); background: var(--crm-selected-bg); }
            .template-meta { display: flex; align-items: center; justify-content: space-between; gap: var(--space-2); margin-top: var(--space-2); }
            .template-leading { display: flex; align-items: center; gap: var(--space-2); }
            .type-grid { display: grid; gap: var(--space-2); grid-template-columns: repeat(auto-fit, minmax(260px, 1fr)); }
            .type-card { border: 1px solid var(--crm-stroke); border-radius: var(--radius-md); padding: var(--space-3); background: var(--crm-surface-muted); display: flex; flex-direction: column; gap: var(--space-2); }
            .type-title { display: flex; align-items: center; gap: var(--space-2); color: var(--text-primary); font-size: var(--text-sm); font-weight: 600; }
            .hint { color: var(--text-tertiary); font-size: var(--text-xs); }
            .icon-input-wrap { display: grid; grid-template-columns: 40px minmax(0, 1fr); gap: var(--space-2); align-items: center; }
            .icon-preview { width: 36px; height: 36px; border-radius: var(--radius-md); border: 1px solid var(--crm-stroke); background: var(--crm-surface-elevated); display: flex; align-items: center; justify-content: center; color: var(--text-secondary); }
            details { border: 1px solid var(--crm-stroke); border-radius: var(--radius-md); background: var(--crm-surface-muted); padding: var(--space-3); }
            details > summary { cursor: pointer; color: var(--text-primary); font-size: var(--text-sm); font-weight: 600; margin-bottom: var(--space-2); }
            @media (max-width: 980px) { .split { grid-template-columns: 1fr; } }
            @media (max-width: 767px) { .menu-btn { display: inline-flex; } }
        `,
    ];

    constructor() {
        super();
        this._namespaces = [];
        this._templates = [];
        this._templateDetails = null;
        this._entityTypes = [];
        this._selectedTemplateId = 'sales';
        this._showTemplateModal = false;
        this._iconOptions = [];
        this._typeDraft = getDefaultTypeDraft();
        this._unsubscribe = CRMStore.subscribe((state) => {
            this._namespaces = state.namespaces.list || [];
            this._templates = state.namespaces.templates || [];
            this._templateDetails = state.namespaces.templateDetails || null;
            this._entityTypes = state.entities.entityTypes || [];
        });
    }

    disconnectedCallback() {
        super.disconnectedCallback();
        this._unsubscribe?.();
    }

    async firstUpdated() {
        const crmApi = this.services.get('crmApi');
        const iconOptions = this.icon.availableIcons;
        if (!Array.isArray(iconOptions) || iconOptions.length === 0) {
            throw new Error('Icon options are required');
        }
        this._iconOptions = iconOptions;
        await Promise.all([
            CRMStore.loadNamespaces(crmApi),
            CRMStore.loadNamespaceTemplates(crmApi),
            CRMStore.loadEntityTypes(crmApi),
        ]);
        if (this._templates.length > 0) {
            if (!this._templates.some((template) => template.template_id === this._selectedTemplateId)) {
                this._selectedTemplateId = this._templates[0].template_id;
            }
            await CRMStore.loadNamespaceTemplateDetails(crmApi, this._selectedTemplateId);
        }
    }

    _openSidebar() {
        window.dispatchEvent(new CustomEvent('platform-sidebar-open', { bubbles: true, composed: true }));
    }

    _onTypeDraftChange(field, value) { this._typeDraft = { ...this._typeDraft, [field]: value }; }

    _resolveAllowedTypes(namespaceName) {
        return this._entityTypes.filter((entityType) => {
            const namespaceIds = Array.isArray(entityType.namespace_ids) ? entityType.namespace_ids : [];
            return namespaceIds.includes(namespaceName);
        });
    }

    _openTemplateModal() { this._showTemplateModal = true; }
    _closeTemplateModal() { this._showTemplateModal = false; }
    async _onTemplateCreated(e) {
        this._showTemplateModal = false;
        const templateId = e?.detail?.templateId;
        if (!templateId) {
            throw new Error('Template ID is required after create');
        }
        this._selectedTemplateId = templateId;
        await CRMStore.loadNamespaceTemplateDetails(this.services.get('crmApi'), templateId);
    }

    async _saveTemplateMeta() {
        if (!this._templateDetails || !this._selectedTemplateId) {
            throw new Error('Template not selected');
        }
        const crmApi = this.services.get('crmApi');
        await CRMStore.updateNamespaceTemplate(crmApi, this._selectedTemplateId, {
            name: this._templateDetails.name,
            description: this._templateDetails.description,
            icon: this._templateDetails.icon || null,
        });
        await CRMStore.loadNamespaceTemplateDetails(crmApi, this._selectedTemplateId);
        this.success('Шаблон обновлен');
    }

    _editType(item) {
        this._typeDraft = {
            type_id: item.type_id || '',
            name: item.name || '',
            description: item.description || '',
            prompt: item.prompt || '',
            required_fields: JSON.stringify(item.required_fields || {}, null, 2),
            optional_fields: JSON.stringify(item.optional_fields || {}, null, 2),
            namespace_ids: JSON.stringify(item.namespace_ids || [], null, 2),
            parent_type_id: item.parent_type_id || '',
            icon: item.icon || '',
            color: item.color || '',
            is_event: item.is_event === true,
            check_duplicates: item.check_duplicates !== false,
            weight_coefficient: String(item.weight_coefficient ?? 1),
        };
    }

    _selectTemplate(templateId) {
        this._selectedTemplateId = templateId;
        CRMStore.loadNamespaceTemplateDetails(this.services.get('crmApi'), templateId);
    }

    _resolveTemplateIcon(iconName) {
        const value = typeof iconName === 'string' ? iconName.trim() : '';
        return value || 'folder';
    }

    async _upsertType() {
        if (!this._selectedTemplateId) {
            throw new Error('Template not selected');
        }
        const typeId = this._typeDraft.type_id.trim();
        const typeName = this._typeDraft.name.trim();
        if (!typeId || !typeName) {
            this.error('type_id и name обязательны');
            return;
        }
        const requiredFields = parseJson(this._typeDraft.required_fields, 'required_fields');
        const optionalFields = parseJson(this._typeDraft.optional_fields, 'optional_fields');
        const namespaceIds = parseJson(this._typeDraft.namespace_ids, 'namespace_ids');
        if (!Array.isArray(namespaceIds)) {
            throw new Error('namespace_ids должен быть JSON массивом');
        }
        const crmApi = this.services.get('crmApi');
        await CRMStore.upsertNamespaceTemplateType(crmApi, this._selectedTemplateId, {
            type_id: typeId,
            parent_type_id: this._typeDraft.parent_type_id.trim() || null,
            name: typeName,
            description: this._typeDraft.description.trim() || null,
            prompt: this._typeDraft.prompt.trim() || null,
            required_fields: requiredFields,
            optional_fields: optionalFields,
            namespace_ids: namespaceIds,
            icon: this._typeDraft.icon.trim() || null,
            color: this._typeDraft.color.trim() || null,
            is_event: this._typeDraft.is_event,
            check_duplicates: this._typeDraft.check_duplicates,
            weight_coefficient: Number.parseFloat(this._typeDraft.weight_coefficient || '1') || 1,
        });
        this._typeDraft = getDefaultTypeDraft();
        this.success('Тип шаблона сохранен');
    }

    async _deleteType(typeId) {
        if (!this._selectedTemplateId) {
            throw new Error('Template not selected');
        }
        const crmApi = this.services.get('crmApi');
        await CRMStore.deleteNamespaceTemplateType(crmApi, this._selectedTemplateId, typeId);
    }

    render() {
        const templateTypes = this._templateDetails?.types || [];
        return html`
            <div class="container">
                <div class="section">
                    <div class="hero">
                        <div>
                            <div class="hero-title">
                                <button class="menu-btn" @click=${this._openSidebar} title="Открыть меню">
                                    <platform-icon name="menu" size="18"></platform-icon>
                                </button>
                                <platform-icon name="settings" size="18"></platform-icon>
                                Настройки CRM
                            </div>
                            <div class="hero-subtitle">Настройка шаблонов пространств, типов сущностей и параметров извлечения.</div>
                        </div>
                    </div>
                    <div class="section-header between">
                        <div class="section-header-main">
                            <platform-icon name="folder" size="18"></platform-icon>
                            Шаблоны
                        </div>
                        <button class="save-btn" @click=${this._openTemplateModal}>
                            <platform-icon name="plus" size="14"></platform-icon>
                            Создать шаблон
                        </button>
                    </div>
                    <div class="grid">
                        ${this._templates.map((template) => html`
                            <div
                                class="card template-card ${template.template_id === this._selectedTemplateId ? 'active' : ''}"
                                @click=${() => this._selectTemplate(template.template_id)}
                            >
                                <div class="template-leading">
                                    <platform-icon name=${this._resolveTemplateIcon(template.icon)} size="18"></platform-icon>
                                    <div class="card-title">${template.name}</div>
                                </div>
                                <div class="card-text">${template.description || ''}</div>
                                <div class="template-meta">
                                    <span class="chip mono">${template.template_id}</span>
                                    <span class="chip">${Array.isArray(template.entity_type_ids) ? template.entity_type_ids.length : 0} типов</span>
                                </div>
                            </div>
                        `)}
                    </div>
                </div>

                <div class="section">
                    <div class="section-header">
                        <platform-icon name="edit" size="18"></platform-icon>
                        Редактор шаблона
                    </div>
                    <div class="toolbar">
                        <span class="chip mono">${this._selectedTemplateId || 'template not selected'}</span>
                        <button class="save-btn" @click=${this._saveTemplateMeta}>
                            <platform-icon name="save" size="14"></platform-icon>
                            Сохранить шаблон
                        </button>
                    </div>

                    ${this._templateDetails ? html`
                        <div class="split">
                            <div class="section">
                                <div class="section-header">
                                    <platform-icon name="folder" size="16"></platform-icon>
                                    Метаданные шаблона
                                </div>
                                <div class="form-group">
                                    <label class="form-label">Название</label>
                                    <input
                                        class="form-input"
                                        .value=${this._templateDetails.name || ''}
                                        @input=${(e) => { this._templateDetails = { ...this._templateDetails, name: e.target.value }; }}
                                    />
                                </div>
                                <div class="form-group">
                                    <label class="form-label">Описание</label>
                                    <textarea
                                        class="form-textarea"
                                        .value=${this._templateDetails.description || ''}
                                        @input=${(e) => { this._templateDetails = { ...this._templateDetails, description: e.target.value }; }}
                                    ></textarea>
                                </div>
                                <div class="form-group">
                                    <label class="form-label">Иконка</label>
                                    <platform-icon-picker
                                        .icons=${this._iconOptions}
                                        .value=${this._resolveTemplateIcon(this._templateDetails.icon)}
                                        @change=${(e) => { this._templateDetails = { ...this._templateDetails, icon: e.detail.value }; }}
                                    ></platform-icon-picker>
                                </div>
                                <div class="chips">
                                    <span class="chip mono">${this._templateDetails.template_id}</span>
                                    <span class="chip">${templateTypes.length} типов</span>
                                </div>
                            </div>
                            <div class="section">
                                <div class="section-header">
                                    <platform-icon name="list" size="16"></platform-icon>
                                    Типы в шаблоне
                                </div>
                                <div class="type-grid">
                                    ${templateTypes.map((item) => html`
                                        <div class="type-card">
                                            <div class="type-title">
                                                <platform-icon name=${this._resolveTemplateIcon(item.icon)} size="16"></platform-icon>
                                                ${item.name}
                                            </div>
                                            <div class="hint mono">${item.type_id}</div>
                                            <div class="card-text">${item.description || 'Описание не задано'}</div>
                                            <div class="chips">
                                                ${(item.namespace_ids || []).map((namespaceId) => html`<span class="chip">${namespaceId}</span>`)}
                                            </div>
                                            <div class="row">
                                                <button class="save-btn soft-btn" @click=${() => this._editType(item)}>Редактировать</button>
                                                <button class="save-btn danger-btn" @click=${() => this._deleteType(item.type_id)}>Удалить</button>
                                            </div>
                                        </div>
                                    `)}
                                    ${templateTypes.length === 0 ? html`<div class="card-text">В шаблоне пока нет типов.</div>` : ''}
                                </div>
                            </div>
                        </div>

                        <div class="section">
                            <div class="section-header">
                                <platform-icon name="plus" size="16"></platform-icon>
                                Тип шаблона
                            </div>
                            <div class="form-grid">
                                <div class="form-group">
                                    <label class="form-label">type_id *</label>
                                    <input class="form-input mono" .value=${this._typeDraft.type_id} @input=${(e) => this._onTypeDraftChange('type_id', e.target.value)} />
                                </div>
                                <div class="form-group">
                                    <label class="form-label">name *</label>
                                    <input class="form-input" .value=${this._typeDraft.name} @input=${(e) => this._onTypeDraftChange('name', e.target.value)} />
                                </div>
                                <div class="form-group">
                                    <label class="form-label">parent_type_id</label>
                                    <input class="form-input mono" .value=${this._typeDraft.parent_type_id} @input=${(e) => this._onTypeDraftChange('parent_type_id', e.target.value)} />
                                </div>
                                <div class="form-group">
                                    <label class="form-label">Иконка</label>
                                    <platform-icon-picker
                                        .icons=${this._iconOptions}
                                        .value=${this._resolveTemplateIcon(this._typeDraft.icon)}
                                        @change=${(e) => this._onTypeDraftChange('icon', e.detail.value)}
                                    ></platform-icon-picker>
                                </div>
                                <div class="form-group">
                                    <label class="form-label">color</label>
                                    <input class="form-input" .value=${this._typeDraft.color} @input=${(e) => this._onTypeDraftChange('color', e.target.value)} />
                                </div>
                                <div class="form-group">
                                    <label class="form-label">weight_coefficient</label>
                                    <input class="form-input mono" .value=${this._typeDraft.weight_coefficient} @input=${(e) => this._onTypeDraftChange('weight_coefficient', e.target.value)} />
                                </div>
                                <div class="form-group">
                                    <label class="form-label">Флаги</label>
                                    <div class="row">
                                        <label><input type="checkbox" .checked=${this._typeDraft.is_event} @change=${(e) => this._onTypeDraftChange('is_event', e.target.checked)} /> is_event</label>
                                        <label><input type="checkbox" .checked=${this._typeDraft.check_duplicates} @change=${(e) => this._onTypeDraftChange('check_duplicates', e.target.checked)} /> check_duplicates</label>
                                    </div>
                                </div>
                            </div>
                            <details>
                                <summary>Поля схемы и промпт (advanced)</summary>
                                <div class="form-grid">
                                    <div class="form-group">
                                        <label class="form-label">prompt</label>
                                        <textarea class="form-textarea" .value=${this._typeDraft.prompt} @input=${(e) => this._onTypeDraftChange('prompt', e.target.value)}></textarea>
                                    </div>
                                    <div class="form-group">
                                        <label class="form-label">description</label>
                                        <textarea class="form-textarea" .value=${this._typeDraft.description} @input=${(e) => this._onTypeDraftChange('description', e.target.value)}></textarea>
                                    </div>
                                    <div class="form-group">
                                        <label class="form-label">required_fields (JSON)</label>
                                        <textarea class="form-textarea mono" .value=${this._typeDraft.required_fields} @input=${(e) => this._onTypeDraftChange('required_fields', e.target.value)}></textarea>
                                    </div>
                                    <div class="form-group">
                                        <label class="form-label">optional_fields (JSON)</label>
                                        <textarea class="form-textarea mono" .value=${this._typeDraft.optional_fields} @input=${(e) => this._onTypeDraftChange('optional_fields', e.target.value)}></textarea>
                                    </div>
                                    <div class="form-group">
                                        <label class="form-label">namespace_ids (JSON array)</label>
                                        <textarea class="form-textarea mono" .value=${this._typeDraft.namespace_ids} @input=${(e) => this._onTypeDraftChange('namespace_ids', e.target.value)}></textarea>
                                    </div>
                                </div>
                            </details>
                            <button class="save-btn" @click=${this._upsertType}>
                                <platform-icon name="save" size="14"></platform-icon>
                                Сохранить тип
                            </button>
                        </div>
                    ` : html`<div class="card-text">Выберите шаблон для редактирования</div>`}
                </div>

                <div class="section">
                    <div class="section-header">
                        <platform-icon name="folder" size="18"></platform-icon>
                        Пространства и разрешенные типы
                    </div>
                    <div class="namespace-list">
                        ${this._namespaces.map((namespace) => html`
                            <div class="namespace-row">
                                <div class="namespace-name">${namespace.name}</div>
                                <div class="chips">
                                    ${this._resolveAllowedTypes(namespace.name).map((entityType) => html`<span class="chip">${entityType.name}</span>`)}
                                </div>
                            </div>
                        `)}
                    </div>
                </div>
            </div>
            ${this._showTemplateModal ? html`
                <template-create-modal
                    .open=${true}
                    @close=${this._closeTemplateModal}
                    @saved=${this._onTemplateCreated}
                ></template-create-modal>
            ` : ''}
        `;
    }
}

customElements.define('settings-page', SettingsPage);
