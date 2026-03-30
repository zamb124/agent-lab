import { html, css } from 'lit';
import { PlatformElement } from '@platform/lib/platform-element/index.js';
import { PlatformModal } from '@platform/lib/components/glass-modal.js';
import { formStyles } from '@platform/lib/styles/shared/form.styles.js';
import { buttonStyles } from '@platform/lib/styles/shared/button.styles.js';
import { CRMStore } from '../store/crm.store.js';
import '@platform/lib/components/platform-icon.js';
import '@platform/lib/components/platform-icon-picker.js';
import '@platform/lib/components/platform-switch.js';
import '@platform/lib/components/platform-help-hint.js';

function getDefaultTypeDraft() {
    return {
        type_id: '',
        name: '',
        description: '',
        prompt: '',
        required_fields_rows: [],
        optional_fields_rows: [],
        namespace_ids: [],
        parent_type_id: '',
        icon: '',
        color: '',
        is_event: false,
        check_duplicates: true,
        weight_coefficient: '1.0',
    };
}

function createEmptySchemaFieldRow(defaultType = 'string') {
    return {
        key: '',
        label: '',
        type: defaultType,
        description: '',
        enum_set_id: '',
        enum_values_text: '',
        extra: {},
    };
}

const TEMPLATE_HINTS = {
    templateName: 'Человекочитаемое название шаблона. Показывается в карточках и модалках выбора пространства. Хорошее название помогает пользователям быстро выбрать правильный бизнес-контекст.',
    templateDescription: 'Описание назначения шаблона. Используйте 1-2 короткие фразы: какие сущности ожидаются и для каких задач создано пространство.',
    templateIcon: 'Иконка нужна для визуальной навигации: отображается в карточках шаблонов и в селекторах. Выбирайте понятный символ, который отражает домен шаблона.',
    typeId: 'Технический идентификатор типа. Должен быть стабильным и уникальным внутри шаблона. Рекомендуемый формат: snake_case, например lead, candidate_profile, incident_note.',
    typeName: 'Пользовательское имя типа. Это название увидит пользователь в интерфейсе при работе с сущностями и карточками.',
    parentType: 'Базовый тип поведения. Обычно note для заметок и task для задач. Если выбрать родителем другой тип шаблона, можно построить иерархию специализированных подтипов.',
    typeIcon: 'Иконка типа отображается в списках, карточках и подсказках. Подберите визуальный маркер, чтобы тип легко различался в плотном интерфейсе.',
    typeColor: 'Дополнительный цветовой акцент типа. Можно оставить пустым, если акцент не нужен. Если заполняете, используйте единый стиль палитры команды.',
    weight: 'Коэффициент важности типа для ранжирования/приоритезации в аналитике. 1.0 — нейтрально. Значение выше усиливает приоритет, ниже — ослабляет.',
    flagIsEvent: 'Если включено, сущности этого типа трактуются как события во времени (например встреча, звонок, инцидент) и могут использоваться в сценариях таймлайна.',
    flagCheckDuplicates: 'Если включено, система будет проверять дубликаты при извлечении/создании сущностей этого типа. Отключайте только если дубликаты допустимы по бизнес-логике.',
    typeDescription: 'Подробное пояснение типа для команды: что хранится в этом типе, какие атрибуты обязательны, в каких процессах используется.',
    typePrompt: 'Подсказка для AI-извлечения и структурирования данных под этот тип. Опишите, какие факты искать, как называть поля и что считать обязательным.',
    namespaces: 'Ограничение областей использования типа. Тип будет доступен только в отмеченных пространствах. Это помогает держать данные доменно чистыми.',
    requiredFields: 'Обязательные атрибуты, без которых запись типа считается неполной. Используйте их для критичных данных, которые нужны в каждом объекте.',
    optionalFields: 'Дополнительные атрибуты для расширенного контекста. Они не обязательны при создании, но повышают качество аналитики и поиска.',
    fieldKey: 'Системный ключ атрибута (snake_case). Используется в JSON/интеграциях и должен быть стабильным. Пример: candidate_name, deal_stage, severity.',
    fieldLabel: 'Отображаемое имя поля для пользователя. Можно писать на русском, так как это подпись в UI, а не технический ключ.',
    fieldType: 'Тип данных атрибута. От него зависит, как поле будет валидироваться и как его интерпретирует AI/поисковый слой.',
    fieldEnum: 'Для enum можно выбрать готовый набор значений из backend (enum set) или задать собственный список вручную.',
};

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
        } catch (error) {
            const message = error instanceof Error ? error.message : 'Ошибка создания шаблона';
            this.error(message);
            throw error;
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

export class TemplatesPage extends PlatformElement {
    static properties = {
        _namespaces: { state: true },
        _templates: { state: true },
        _templateDetails: { state: true },
        _schemaOptions: { state: true },
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
            .card { border: 1px solid var(--crm-stroke); border-radius: var(--radius-lg); padding: var(--space-3); background: var(--crm-surface-muted); transition: border-color var(--duration-fast), background var(--duration-fast), transform var(--duration-fast); }
            .card:hover { border-color: var(--crm-selected-stroke); transform: translateY(-1px); }
            .card-title { color: var(--text-primary); font-size: var(--text-sm); font-weight: 600; margin-bottom: var(--space-1); }
            .card-text { color: var(--text-secondary); font-size: var(--text-sm); }
            .form-grid { display: grid; gap: var(--space-3); grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)); }
            .form-group { display: flex; flex-direction: column; gap: var(--space-2); }
            .form-label { color: var(--text-secondary); font-size: var(--text-sm); font-weight: 500; }
            .label-with-hint { display: inline-flex; align-items: center; gap: var(--space-2); }
            .form-input, .form-select, .form-textarea { border: 1px solid var(--crm-stroke); border-radius: var(--radius-md); background: var(--crm-surface-elevated); color: var(--text-primary); padding: var(--space-2) var(--space-3); font-size: var(--text-sm); }
            .form-textarea { min-height: 88px; resize: vertical; }
            .save-btn { display: inline-flex; align-items: center; justify-content: center; gap: var(--space-2); border: 1px solid var(--crm-button-primary-bg); background: var(--crm-button-primary-bg); color: var(--crm-button-primary-text); border-radius: var(--radius-md); padding: var(--space-2) var(--space-4); cursor: pointer; width: fit-content; }
            .save-btn:disabled { opacity: 0.5; cursor: not-allowed; }
            .soft-btn { border-color: var(--crm-stroke); background: var(--crm-surface-elevated); color: var(--text-primary); }
            .danger-btn { border-color: #B91C1C; background: #7F1D1D; color: #FEE2E2; }
            .menu-btn { width: 32px; height: 32px; display: none; align-items: center; justify-content: center; border-radius: var(--radius-md); background: var(--crm-surface-muted); border: 1px solid var(--crm-stroke); color: var(--text-primary); cursor: pointer; }
            .toolbar { display: flex; gap: var(--space-2); flex-wrap: wrap; align-items: center; }
            .split { display: grid; gap: var(--space-3); grid-template-columns: minmax(260px, 360px) minmax(0, 1fr); }
            .row { display: flex; gap: var(--space-2); flex-wrap: wrap; }
            .flag-row { display: flex; gap: var(--space-3); flex-wrap: wrap; }
            .flag-item { display: inline-flex; align-items: center; gap: var(--space-2); white-space: nowrap; }
            .mono { font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, "Liberation Mono", "Courier New", monospace; font-size: var(--text-xs); }
            .template-card { cursor: pointer; }
            .template-card.active { border-color: var(--crm-selected-stroke); background: var(--crm-selected-bg); }
            .template-meta { display: flex; align-items: center; justify-content: space-between; gap: var(--space-2); margin-top: var(--space-2); }
            .template-leading { display: flex; align-items: center; gap: var(--space-2); }
            .type-grid { display: grid; gap: var(--space-2); grid-template-columns: repeat(auto-fit, minmax(260px, 1fr)); }
            .type-card { border: 1px solid var(--crm-stroke); border-radius: var(--radius-md); padding: var(--space-3); background: var(--crm-surface-muted); display: flex; flex-direction: column; gap: var(--space-2); }
            .type-title { display: flex; align-items: center; gap: var(--space-2); color: var(--text-primary); font-size: var(--text-sm); font-weight: 600; }
            .hint { color: var(--text-tertiary); font-size: var(--text-xs); }
            .chips { display: flex; flex-wrap: wrap; gap: var(--space-1); }
            .chip { border: 1px solid var(--crm-stroke); border-radius: var(--radius-full); padding: 2px var(--space-2); color: var(--text-secondary); background: var(--crm-surface-elevated); font-size: var(--text-xs); }
            .schema-builder-grid { display: grid; gap: var(--space-3); grid-template-columns: 1fr 1fr; }
            .schema-section { border: 1px solid var(--crm-stroke); border-radius: var(--radius-md); background: var(--crm-surface-muted); padding: var(--space-3); display: flex; flex-direction: column; gap: var(--space-2); }
            .schema-section-header { display: flex; align-items: center; justify-content: space-between; gap: var(--space-2); }
            .schema-field-card { border: 1px solid var(--crm-stroke); border-radius: var(--radius-md); background: var(--crm-surface-elevated); padding: var(--space-2); display: grid; gap: var(--space-2); }
            .schema-field-row { display: grid; gap: var(--space-2); grid-template-columns: 1fr 1fr; }
            .schema-field-inline { display: flex; align-items: center; gap: var(--space-2); flex-wrap: wrap; }
            .schema-empty { color: var(--text-tertiary); font-size: var(--text-sm); }
            .schema-preview { border: 1px solid var(--crm-stroke); border-radius: var(--radius-md); background: var(--crm-surface-elevated); color: var(--text-secondary); font-size: var(--text-xs); padding: var(--space-2); max-height: 180px; overflow: auto; white-space: pre-wrap; word-break: break-word; }
            .namespace-selector { display: flex; gap: var(--space-2); flex-wrap: wrap; }
            .namespace-pill { display: inline-flex; align-items: center; gap: var(--space-2); border: 1px solid var(--crm-stroke); border-radius: var(--radius-full); background: var(--crm-surface-elevated); color: var(--text-primary); padding: 4px var(--space-2); font-size: var(--text-xs); cursor: pointer; }
            .namespace-pill.active { border-color: var(--crm-selected-stroke); background: var(--crm-selected-bg); }
            .namespace-pill:disabled { opacity: 0.5; cursor: not-allowed; }
            .icon-input-wrap { display: grid; grid-template-columns: 40px minmax(0, 1fr); gap: var(--space-2); align-items: center; }
            .icon-preview { width: 36px; height: 36px; border-radius: var(--radius-md); border: 1px solid var(--crm-stroke); background: var(--crm-surface-elevated); display: flex; align-items: center; justify-content: center; color: var(--text-secondary); }
            .back-btn { display: inline-flex; align-items: center; gap: var(--space-2); background: none; border: none; color: var(--text-secondary); font-size: var(--text-sm); cursor: pointer; padding: 0; transition: color var(--duration-fast); }
            .back-btn:hover { color: var(--text-primary); }
            details { border: 1px solid var(--crm-stroke); border-radius: var(--radius-md); background: var(--crm-surface-muted); padding: var(--space-3); }
            details > summary { cursor: pointer; color: var(--text-primary); font-size: var(--text-sm); font-weight: 600; margin-bottom: var(--space-2); }
            @media (max-width: 980px) { .split { grid-template-columns: 1fr; } .schema-builder-grid { grid-template-columns: 1fr; } }
            @media (max-width: 767px) { .menu-btn { display: inline-flex; } }
        `,
    ];

    constructor() {
        super();
        this._namespaces = [];
        this._templates = [];
        this._templateDetails = null;
        this._schemaOptions = null;
        this._selectedTemplateId = 'sales';
        this._showTemplateModal = false;
        this._iconOptions = [];
        this._typeDraft = getDefaultTypeDraft();
        this._unsubscribe = CRMStore.subscribe((state) => {
            this._namespaces = state.namespaces.list || [];
            this._templates = state.namespaces.templates || [];
            this._templateDetails = state.namespaces.templateDetails || null;
            this._schemaOptions = state.namespaces.schemaOptions || null;
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
            CRMStore.loadTemplateSchemaOptions(crmApi),
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

    _getSchemaOptionsRequired() {
        if (!this._schemaOptions || typeof this._schemaOptions !== 'object') {
            throw new Error('Schema options are required');
        }
        if (!Array.isArray(this._schemaOptions.field_types)) {
            throw new Error('field_types must be array');
        }
        if (!Array.isArray(this._schemaOptions.enum_sets)) {
            throw new Error('enum_sets must be array');
        }
        return this._schemaOptions;
    }

    _getDefaultFieldType() {
        const options = this._getSchemaOptionsRequired();
        const defaultType = options?.defaults?.field_type;
        if (typeof defaultType === 'string' && defaultType.trim().length > 0) {
            return defaultType.trim();
        }
        if (options.field_types.length === 0) {
            throw new Error('field_types are empty');
        }
        const firstTypeId = options.field_types[0]?.type_id;
        if (typeof firstTypeId !== 'string' || firstTypeId.trim().length === 0) {
            throw new Error('field_types[0].type_id is invalid');
        }
        return firstTypeId;
    }

    _normalizeSchemaRows(schemaValue) {
        if (!schemaValue || typeof schemaValue !== 'object' || Array.isArray(schemaValue)) {
            return [];
        }
        return Object.entries(schemaValue).map(([fieldKey, rawValue]) => {
            if (!rawValue || typeof rawValue !== 'object' || Array.isArray(rawValue)) {
                throw new Error(`Schema field "${fieldKey}" must be object`);
            }
            const defaultType = this._getDefaultFieldType();
            const typeId = typeof rawValue.type === 'string' && rawValue.type.trim().length > 0
                ? rawValue.type.trim()
                : defaultType;
            if (rawValue.values !== undefined && !Array.isArray(rawValue.values)) {
                throw new Error(`Schema field "${fieldKey}".values must be array`);
            }
            const enumValues = Array.isArray(rawValue.values) ? rawValue.values : [];
            const normalizedValues = enumValues
                .map((item) => (typeof item === 'string' ? item.trim() : ''))
                .filter((item) => item.length > 0);
            if (rawValue.enum_set_id !== undefined && typeof rawValue.enum_set_id !== 'string') {
                throw new Error(`Schema field "${fieldKey}".enum_set_id must be string`);
            }
            const extra = Object.fromEntries(
                Object.entries(rawValue).filter(([key]) => !['type', 'label', 'description', 'values', 'enum_set_id'].includes(key))
            );
            return {
                key: fieldKey,
                label: typeof rawValue.label === 'string' ? rawValue.label : '',
                type: typeId,
                description: typeof rawValue.description === 'string' ? rawValue.description : '',
                enum_set_id: typeof rawValue.enum_set_id === 'string' ? rawValue.enum_set_id : '',
                enum_values_text: normalizedValues.join(', '),
                extra,
            };
        });
    }

    _setSchemaRows(sectionKey, rows) {
        if (!['required_fields_rows', 'optional_fields_rows'].includes(sectionKey)) {
            throw new Error(`Unknown schema section: ${sectionKey}`);
        }
        this._typeDraft = { ...this._typeDraft, [sectionKey]: rows };
    }

    _addSchemaRow(sectionKey) {
        const rows = Array.isArray(this._typeDraft[sectionKey]) ? this._typeDraft[sectionKey] : [];
        this._setSchemaRows(sectionKey, [...rows, createEmptySchemaFieldRow(this._getDefaultFieldType())]);
    }

    _removeSchemaRow(sectionKey, index) {
        const rows = Array.isArray(this._typeDraft[sectionKey]) ? this._typeDraft[sectionKey] : [];
        this._setSchemaRows(sectionKey, rows.filter((_, rowIndex) => rowIndex !== index));
    }

    _updateSchemaRow(sectionKey, index, patch) {
        const rows = Array.isArray(this._typeDraft[sectionKey]) ? this._typeDraft[sectionKey] : [];
        this._setSchemaRows(
            sectionKey,
            rows.map((row, rowIndex) => (rowIndex === index ? { ...row, ...patch } : row)),
        );
    }

    _isEnumType(typeId) {
        return typeId === 'enum';
    }

    _resolveEnumValues(enumValuesText) {
        return String(enumValuesText || '')
            .split(/[\n,]/)
            .map((item) => item.trim())
            .filter((item) => item.length > 0);
    }

    _buildSchemaFromRows(rows, sectionLabel) {
        if (!Array.isArray(rows)) {
            throw new Error(`${sectionLabel} rows must be array`);
        }
        const schema = {};
        const seenKeys = new Set();
        const schemaOptions = this._getSchemaOptionsRequired();
        const fieldTypes = new Set(schemaOptions.field_types.map((item) => item.type_id));
        const enumSetsMap = new Map(schemaOptions.enum_sets.map((item) => [item.enum_set_id, item.values]));
        const maxFieldsPerSection = Number(schemaOptions?.validation_limits?.max_fields_per_section || 0);
        if (maxFieldsPerSection > 0 && rows.length > maxFieldsPerSection) {
            throw new Error(`${sectionLabel}: превышен лимит полей (${maxFieldsPerSection})`);
        }

        for (const row of rows) {
            const key = String(row?.key || '').trim();
            if (!key) {
                continue;
            }
            if (!/^[a-zA-Z_][a-zA-Z0-9_]*$/.test(key)) {
                throw new Error(`${sectionLabel}: ключ "${key}" имеет неверный формат`);
            }
            if (seenKeys.has(key)) {
                throw new Error(`${sectionLabel}: дублируется ключ "${key}"`);
            }
            seenKeys.add(key);
            const typeId = String(row?.type || '').trim();
            if (!fieldTypes.has(typeId)) {
                throw new Error(`${sectionLabel}: неизвестный тип "${typeId}" для "${key}"`);
            }
            const descriptor = {
                ...(row?.extra && typeof row.extra === 'object' ? row.extra : {}),
                type: typeId,
            };
            const label = String(row?.label || '').trim();
            if (label) {
                descriptor.label = label;
            }
            const description = String(row?.description || '').trim();
            if (description) {
                descriptor.description = description;
            }

            if (this._isEnumType(typeId)) {
                const enumSetId = String(row?.enum_set_id || '').trim();
                if (enumSetId) {
                    if (!enumSetsMap.has(enumSetId)) {
                        throw new Error(`${sectionLabel}: enum_set_id "${enumSetId}" не найден`);
                    }
                    descriptor.enum_set_id = enumSetId;
                    descriptor.values = enumSetsMap.get(enumSetId);
                } else {
                    const values = this._resolveEnumValues(row?.enum_values_text || '');
                    if (values.length === 0) {
                        throw new Error(`${sectionLabel}: для enum-поля "${key}" нужен enum_set_id или values`);
                    }
                    descriptor.values = values;
                }
            }

            schema[key] = descriptor;
        }
        return schema;
    }

    _getSchemaPreview(sectionKey, sectionLabel) {
        try {
            const rows = Array.isArray(this._typeDraft[sectionKey]) ? this._typeDraft[sectionKey] : [];
            const schema = this._buildSchemaFromRows(rows, sectionLabel);
            return JSON.stringify(schema, null, 2);
        } catch (error) {
            return `Ошибка: ${error.message}`;
        }
    }

    _openTemplateModal() { this._showTemplateModal = true; }
    _closeTemplateModal() { this._showTemplateModal = false; }
    async _onTemplateCreated(e) {
        try {
            this._showTemplateModal = false;
            const templateId = e?.detail?.templateId;
            if (!templateId) {
                throw new Error('Template ID is required after create');
            }
            this._selectedTemplateId = templateId;
            await CRMStore.loadNamespaceTemplateDetails(this.services.get('crmApi'), templateId);
        } catch (error) {
            const message = error instanceof Error ? error.message : 'Ошибка загрузки шаблона';
            this.error(message);
        }
    }

    async _saveTemplateMeta() {
        try {
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
        } catch (error) {
            const message = error instanceof Error ? error.message : 'Ошибка обновления шаблона';
            this.error(message);
        }
    }

    _editType(item) {
        this._typeDraft = {
            type_id: item.type_id || '',
            name: item.name || '',
            description: item.description || '',
            prompt: item.prompt || '',
            required_fields_rows: this._normalizeSchemaRows(item.required_fields || {}),
            optional_fields_rows: this._normalizeSchemaRows(item.optional_fields || {}),
            namespace_ids: Array.isArray(item.namespace_ids) ? item.namespace_ids : [],
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
        CRMStore.loadNamespaceTemplateDetails(this.services.get('crmApi'), templateId).catch((error) => {
            const message = error instanceof Error ? error.message : 'Ошибка загрузки шаблона';
            this.error(message);
        });
    }

    _resolveTemplateIcon(iconName) {
        const value = typeof iconName === 'string' ? iconName.trim() : '';
        return value || 'folder';
    }

    _toggleTypeNamespace(namespaceName, enabled) {
        const current = Array.isArray(this._typeDraft.namespace_ids) ? this._typeDraft.namespace_ids : [];
        const cleanName = String(namespaceName || '').trim();
        if (!cleanName) {
            throw new Error('Namespace name is required');
        }
        const updated = enabled
            ? [...new Set([...current, cleanName])]
            : current.filter((item) => item !== cleanName);
        this._onTypeDraftChange('namespace_ids', updated);
    }

    _getParentTypeOptions() {
        const fromTemplate = Array.isArray(this._templateDetails?.types)
            ? this._templateDetails.types.map((item) => item.type_id).filter((item) => typeof item === 'string' && item.trim().length > 0)
            : [];
        const rootTypes = ['note', 'task'];
        return [...new Set([...rootTypes, ...fromTemplate])];
    }

    async _upsertType() {
        try {
            if (!this._selectedTemplateId) {
                throw new Error('Template not selected');
            }
            const typeId = this._typeDraft.type_id.trim();
            const typeName = this._typeDraft.name.trim();
            if (!typeId || !typeName) {
                this.error('type_id и name обязательны');
                return;
            }
            const requiredFields = this._buildSchemaFromRows(this._typeDraft.required_fields_rows, 'required_fields');
            const optionalFields = this._buildSchemaFromRows(this._typeDraft.optional_fields_rows, 'optional_fields');
            for (const key of Object.keys(requiredFields)) {
                if (Object.prototype.hasOwnProperty.call(optionalFields, key)) {
                    throw new Error(`Ключ "${key}" не может быть одновременно required и optional`);
                }
            }
            const namespaceIds = Array.isArray(this._typeDraft.namespace_ids) ? this._typeDraft.namespace_ids : [];
            const normalizedNamespaceIds = namespaceIds
                .map((item) => (typeof item === 'string' ? item.trim() : ''))
                .filter((item) => item.length > 0);
            if (normalizedNamespaceIds.length !== namespaceIds.length) {
                throw new Error('namespace_ids должен содержать только строки');
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
                namespace_ids: [...new Set(normalizedNamespaceIds)],
                icon: this._typeDraft.icon.trim() || null,
                color: this._typeDraft.color.trim() || null,
                is_event: this._typeDraft.is_event,
                check_duplicates: this._typeDraft.check_duplicates,
                weight_coefficient: Number.parseFloat(this._typeDraft.weight_coefficient || '1') || 1,
            });
            this._typeDraft = getDefaultTypeDraft();
            this.success('Тип шаблона сохранен');
        } catch (error) {
            const message = error instanceof Error ? error.message : 'Ошибка сохранения типа';
            this.error(message);
        }
    }

    async _deleteType(typeId) {
        try {
            if (!this._selectedTemplateId) {
                throw new Error('Template not selected');
            }
            const crmApi = this.services.get('crmApi');
            await CRMStore.deleteNamespaceTemplateType(crmApi, this._selectedTemplateId, typeId);
        } catch (error) {
            const message = error instanceof Error ? error.message : 'Ошибка удаления типа';
            this.error(message);
        }
    }

    render() {
        const templateTypes = this._templateDetails?.types || [];
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
                                <platform-icon name="settings" size="18"></platform-icon>
                                Шаблоны пространств
                            </div>
                            <div class="hero-subtitle">Управление шаблонами для создания новых пространств и типами сущностей в них.</div>
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
                        Редактор выбранного шаблона
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
                                    <label class="form-label label-with-hint">
                                        <span>Название</span>
                                        <platform-help-hint strategy="local" label="Справка: название шаблона" .text=${TEMPLATE_HINTS.templateName}></platform-help-hint>
                                    </label>
                                    <input class="form-input" .value=${this._templateDetails.name || ''} @input=${(e) => { this._templateDetails = { ...this._templateDetails, name: e.target.value }; }} />
                                </div>
                                <div class="form-group">
                                    <label class="form-label label-with-hint">
                                        <span>Описание</span>
                                        <platform-help-hint strategy="local" label="Справка: описание шаблона" .text=${TEMPLATE_HINTS.templateDescription}></platform-help-hint>
                                    </label>
                                    <textarea class="form-textarea" .value=${this._templateDetails.description || ''} @input=${(e) => { this._templateDetails = { ...this._templateDetails, description: e.target.value }; }}></textarea>
                                </div>
                                <div class="form-group">
                                    <label class="form-label label-with-hint">
                                        <span>Иконка</span>
                                        <platform-help-hint strategy="local" label="Справка: иконка шаблона" .text=${TEMPLATE_HINTS.templateIcon}></platform-help-hint>
                                    </label>
                                    <platform-icon-picker .icons=${this._iconOptions} .value=${this._resolveTemplateIcon(this._templateDetails.icon)} @change=${(e) => { this._templateDetails = { ...this._templateDetails, icon: e.detail.value }; }}></platform-icon-picker>
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
                            ${Array.isArray(this._schemaOptions?.field_types) ? '' : html`<div class="schema-empty">Загрузка schema options...</div>`}
                            <div class="form-grid">
                                <div class="form-group">
                                    <label class="form-label label-with-hint">
                                        <span>type_id *</span>
                                        <platform-help-hint strategy="local" label="Справка: type_id" .text=${TEMPLATE_HINTS.typeId}></platform-help-hint>
                                    </label>
                                    <input class="form-input mono" .value=${this._typeDraft.type_id} @input=${(e) => this._onTypeDraftChange('type_id', e.target.value)} />
                                </div>
                                <div class="form-group">
                                    <label class="form-label label-with-hint">
                                        <span>name *</span>
                                        <platform-help-hint strategy="local" label="Справка: имя типа" .text=${TEMPLATE_HINTS.typeName}></platform-help-hint>
                                    </label>
                                    <input class="form-input" .value=${this._typeDraft.name} @input=${(e) => this._onTypeDraftChange('name', e.target.value)} />
                                </div>
                                <div class="form-group">
                                    <label class="form-label label-with-hint">
                                        <span>parent_type_id</span>
                                        <platform-help-hint strategy="local" label="Справка: родительский тип" .text=${TEMPLATE_HINTS.parentType}></platform-help-hint>
                                    </label>
                                    <select class="form-select mono" .value=${this._typeDraft.parent_type_id} @change=${(e) => this._onTypeDraftChange('parent_type_id', e.target.value)}>
                                        <option value="">(без родителя)</option>
                                        ${this._getParentTypeOptions().map((typeId) => html`<option value=${typeId}>${typeId}</option>`)}
                                    </select>
                                </div>
                                <div class="form-group">
                                    <label class="form-label label-with-hint">
                                        <span>Иконка</span>
                                        <platform-help-hint strategy="local" label="Справка: иконка типа" .text=${TEMPLATE_HINTS.typeIcon}></platform-help-hint>
                                    </label>
                                    <platform-icon-picker .icons=${this._iconOptions} .value=${this._resolveTemplateIcon(this._typeDraft.icon)} @change=${(e) => this._onTypeDraftChange('icon', e.detail.value)}></platform-icon-picker>
                                </div>
                                <div class="form-group">
                                    <label class="form-label label-with-hint">
                                        <span>color</span>
                                        <platform-help-hint strategy="local" label="Справка: цвет типа" .text=${TEMPLATE_HINTS.typeColor}></platform-help-hint>
                                    </label>
                                    <input class="form-input" .value=${this._typeDraft.color} @input=${(e) => this._onTypeDraftChange('color', e.target.value)} />
                                </div>
                                <div class="form-group">
                                    <label class="form-label label-with-hint">
                                        <span>weight_coefficient</span>
                                        <platform-help-hint strategy="local" label="Справка: коэффициент веса" .text=${TEMPLATE_HINTS.weight}></platform-help-hint>
                                    </label>
                                    <input type="number" step="0.1" min="0" class="form-input mono" .value=${this._typeDraft.weight_coefficient} @input=${(e) => this._onTypeDraftChange('weight_coefficient', e.target.value)} />
                                </div>
                                <div class="form-group">
                                    <label class="form-label">Флаги</label>
                                    <div class="flag-row">
                                        <div class="flag-item">
                                            <platform-switch size="sm" label="is_event" .checked=${this._typeDraft.is_event} @change=${(e) => this._onTypeDraftChange('is_event', Boolean(e.detail.value))}></platform-switch>
                                            <platform-help-hint strategy="local" label="Справка: is_event" .text=${TEMPLATE_HINTS.flagIsEvent}></platform-help-hint>
                                        </div>
                                        <div class="flag-item">
                                            <platform-switch size="sm" label="check_duplicates" .checked=${this._typeDraft.check_duplicates} @change=${(e) => this._onTypeDraftChange('check_duplicates', Boolean(e.detail.value))}></platform-switch>
                                            <platform-help-hint strategy="local" label="Справка: check_duplicates" .text=${TEMPLATE_HINTS.flagCheckDuplicates}></platform-help-hint>
                                        </div>
                                    </div>
                                </div>
                                <div class="form-group">
                                    <label class="form-label label-with-hint">
                                        <span>Описание</span>
                                        <platform-help-hint strategy="local" label="Справка: описание типа" .text=${TEMPLATE_HINTS.typeDescription}></platform-help-hint>
                                    </label>
                                    <textarea class="form-textarea" .value=${this._typeDraft.description} @input=${(e) => this._onTypeDraftChange('description', e.target.value)}></textarea>
                                </div>
                                <div class="form-group">
                                    <label class="form-label label-with-hint">
                                        <span>Промпт для извлечения</span>
                                        <platform-help-hint strategy="local" label="Справка: промпт типа" .text=${TEMPLATE_HINTS.typePrompt}></platform-help-hint>
                                    </label>
                                    <textarea class="form-textarea" .value=${this._typeDraft.prompt} @input=${(e) => this._onTypeDraftChange('prompt', e.target.value)}></textarea>
                                </div>
                                <div class="form-group">
                                    <label class="form-label label-with-hint">
                                        <span>Разрешенные пространства</span>
                                        <platform-help-hint strategy="local" label="Справка: пространства типа" .text=${TEMPLATE_HINTS.namespaces}></platform-help-hint>
                                    </label>
                                    <div class="namespace-selector">
                                        ${(this._namespaces || []).map((namespace) => {
                                            const checked = (this._typeDraft.namespace_ids || []).includes(namespace.name);
                                            return html`
                                                <button type="button" class="namespace-pill ${checked ? 'active' : ''}" @click=${() => this._toggleTypeNamespace(namespace.name, !checked)}>
                                                    ${namespace.name}
                                                </button>
                                            `;
                                        })}
                                    </div>
                                </div>
                            </div>
                            <div class="schema-builder-grid">
                                <div class="schema-section">
                                    <div class="schema-section-header">
                                        <span class="label-with-hint">
                                            <span>required_fields</span>
                                            <platform-help-hint strategy="local" label="Справка: required_fields" .text=${TEMPLATE_HINTS.requiredFields}></platform-help-hint>
                                        </span>
                                        <button class="save-btn soft-btn" @click=${() => this._addSchemaRow('required_fields_rows')} type="button">+ Поле</button>
                                    </div>
                                    <div class="hint">key — системный идентификатор, label — название для пользователя, type — тип данных, enum — набор значений.</div>
                                    ${Array.isArray(this._typeDraft.required_fields_rows) && this._typeDraft.required_fields_rows.length > 0
                                        ? this._typeDraft.required_fields_rows.map((row, index) => html`
                                            <div class="schema-field-card">
                                                <div class="schema-field-row">
                                                    <input class="form-input mono" placeholder="key (например deal_stage)" .value=${row.key || ''} @input=${(e) => this._updateSchemaRow('required_fields_rows', index, { key: e.target.value })} />
                                                    <input class="form-input" placeholder="label (например Стадия сделки)" .value=${row.label || ''} @input=${(e) => this._updateSchemaRow('required_fields_rows', index, { label: e.target.value })} />
                                                </div>
                                                <div class="schema-field-row">
                                                    <select class="form-select" .value=${row.type || this._getDefaultFieldType()} @change=${(e) => this._updateSchemaRow('required_fields_rows', index, { type: e.target.value })}>
                                                        ${(this._schemaOptions?.field_types || []).map((typeItem) => html`<option value=${typeItem.type_id}>${typeItem.label}</option>`)}
                                                    </select>
                                                    <input class="form-input" placeholder="description (когда и как заполняется поле)" .value=${row.description || ''} @input=${(e) => this._updateSchemaRow('required_fields_rows', index, { description: e.target.value })} />
                                                </div>
                                                ${this._isEnumType(row.type) ? html`
                                                    <div class="schema-field-row">
                                                        <select class="form-select" .value=${row.enum_set_id || ''} @change=${(e) => this._updateSchemaRow('required_fields_rows', index, { enum_set_id: e.target.value })}>
                                                            <option value="">Локальные values</option>
                                                            ${(this._schemaOptions?.enum_sets || []).map((setItem) => html`<option value=${setItem.enum_set_id}>${setItem.label}</option>`)}
                                                        </select>
                                                        <input class="form-input" placeholder="values: high, medium, low" .value=${row.enum_values_text || ''} ?disabled=${Boolean(row.enum_set_id)} @input=${(e) => this._updateSchemaRow('required_fields_rows', index, { enum_values_text: e.target.value })} />
                                                    </div>
                                                ` : ''}
                                                <div class="schema-field-inline">
                                                    <button class="save-btn danger-btn" type="button" @click=${() => this._removeSchemaRow('required_fields_rows', index)}>Удалить</button>
                                                </div>
                                            </div>
                                        `)
                                        : html`<div class="schema-empty">Нет полей</div>`
                                    }
                                </div>
                                <div class="schema-section">
                                    <div class="schema-section-header">
                                        <span class="label-with-hint">
                                            <span>optional_fields</span>
                                            <platform-help-hint strategy="local" label="Справка: optional_fields" .text=${TEMPLATE_HINTS.optionalFields}></platform-help-hint>
                                        </span>
                                        <button class="save-btn soft-btn" @click=${() => this._addSchemaRow('optional_fields_rows')} type="button">+ Поле</button>
                                    </div>
                                    <div class="hint">Для необязательных полей рекомендуйте структуру, но не делайте их блокирующими для сохранения.</div>
                                    ${Array.isArray(this._typeDraft.optional_fields_rows) && this._typeDraft.optional_fields_rows.length > 0
                                        ? this._typeDraft.optional_fields_rows.map((row, index) => html`
                                            <div class="schema-field-card">
                                                <div class="schema-field-row">
                                                    <input class="form-input mono" placeholder="key (например budget)" .value=${row.key || ''} @input=${(e) => this._updateSchemaRow('optional_fields_rows', index, { key: e.target.value })} />
                                                    <input class="form-input" placeholder="label (например Бюджет)" .value=${row.label || ''} @input=${(e) => this._updateSchemaRow('optional_fields_rows', index, { label: e.target.value })} />
                                                </div>
                                                <div class="schema-field-row">
                                                    <select class="form-select" .value=${row.type || this._getDefaultFieldType()} @change=${(e) => this._updateSchemaRow('optional_fields_rows', index, { type: e.target.value })}>
                                                        ${(this._schemaOptions?.field_types || []).map((typeItem) => html`<option value=${typeItem.type_id}>${typeItem.label}</option>`)}
                                                    </select>
                                                    <input class="form-input" placeholder="description (что означает поле)" .value=${row.description || ''} @input=${(e) => this._updateSchemaRow('optional_fields_rows', index, { description: e.target.value })} />
                                                </div>
                                                ${this._isEnumType(row.type) ? html`
                                                    <div class="schema-field-row">
                                                        <select class="form-select" .value=${row.enum_set_id || ''} @change=${(e) => this._updateSchemaRow('optional_fields_rows', index, { enum_set_id: e.target.value })}>
                                                            <option value="">Локальные values</option>
                                                            ${(this._schemaOptions?.enum_sets || []).map((setItem) => html`<option value=${setItem.enum_set_id}>${setItem.label}</option>`)}
                                                        </select>
                                                        <input class="form-input" placeholder="values: high, medium, low" .value=${row.enum_values_text || ''} ?disabled=${Boolean(row.enum_set_id)} @input=${(e) => this._updateSchemaRow('optional_fields_rows', index, { enum_values_text: e.target.value })} />
                                                    </div>
                                                ` : ''}
                                                <div class="schema-field-inline">
                                                    <button class="save-btn danger-btn" type="button" @click=${() => this._removeSchemaRow('optional_fields_rows', index)}>Удалить</button>
                                                </div>
                                            </div>
                                        `)
                                        : html`<div class="schema-empty">Нет полей</div>`
                                    }
                                </div>
                            </div>
                            <details>
                                <summary>JSON preview (advanced, read-only)</summary>
                                <div class="form-grid">
                                    <div class="form-group">
                                        <label class="form-label">required_fields (preview)</label>
                                        <pre class="schema-preview">${this._getSchemaPreview('required_fields_rows', 'required_fields')}</pre>
                                    </div>
                                    <div class="form-group">
                                        <label class="form-label">optional_fields (preview)</label>
                                        <pre class="schema-preview">${this._getSchemaPreview('optional_fields_rows', 'optional_fields')}</pre>
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
            </div>
            ${this._showTemplateModal ? html`
                <template-create-modal
                    .open=${true}
                    @modal-closed=${this._closeTemplateModal}
                    @saved=${this._onTemplateCreated}
                ></template-create-modal>
            ` : ''}
        `;
    }
}

customElements.define('templates-page', TemplatesPage);
