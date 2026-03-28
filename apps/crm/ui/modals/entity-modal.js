/**
 * Entity Modal - Создание/редактирование сущности
 * Использует PlatformModal с fullscreen и drag поддержкой
 */
import { html, css } from 'lit';
import { PlatformModal } from '@platform/lib/components/glass-modal.js';
import { formStyles } from '@platform/lib/styles/shared/form.styles.js';
import { buttonStyles } from '@platform/lib/styles/shared/button.styles.js';
import { CRMStore } from '../store/crm.store.js';
import '@platform/lib/components/tag-input.js';
import '@platform/lib/components/platform-icon.js';
import '@platform/lib/components/platform-date-picker.js';

export class EntityModal extends PlatformModal {
    static properties = {
        ...PlatformModal.properties,
        entityId: { type: String },
        entity: { type: Object },
        _formData: { state: true },
        _entityTypes: { state: true },
        _selectedType: { state: true },
        _saving: { state: true },
        _attributeRows: { state: true },
    };

    static styles = [
        PlatformModal.styles,
        formStyles,
        buttonStyles,
        css`
            .form-grid {
                display: grid;
                gap: var(--space-4);
            }

            .form-row {
                display: flex;
                gap: var(--space-3);
            }

            .form-row > * {
                flex: 1;
            }

            .type-chips {
                display: flex;
                flex-wrap: wrap;
                gap: var(--space-2);
            }

            .type-chip {
                display: inline-flex;
                align-items: center;
                gap: var(--space-1);
                padding: var(--space-2) var(--space-3);
                background: var(--crm-surface-muted);
                border: 1px solid var(--crm-stroke);
                border-radius: var(--radius-lg);
                color: var(--text-secondary);
                font-size: var(--text-sm);
                cursor: pointer;
                transition: all var(--duration-fast);
            }

            .type-chip:hover {
                background: var(--crm-surface);
                color: var(--text-primary);
            }

            .type-chip.active {
                background: var(--crm-selected-bg);
                border-color: var(--crm-selected-stroke);
                color: var(--crm-selected-text);
            }

            .attributes-section {
                margin-top: var(--space-4);
            }

            .attribute-row {
                display: flex;
                gap: var(--space-2);
                margin-bottom: var(--space-2);
            }

            .attribute-row input {
                flex: 1;
            }

            .add-attribute-btn {
                display: flex;
                align-items: center;
                gap: var(--space-1);
                padding: var(--space-2);
                background: transparent;
                border: 1px dashed var(--glass-border-subtle);
                border-radius: var(--radius-md);
                color: var(--text-tertiary);
                font-size: var(--text-sm);
                cursor: pointer;
                width: 100%;
                justify-content: center;
                transition: all 0.2s;
            }

            .add-attribute-btn:hover {
                border-color: var(--accent);
                color: var(--accent);
            }

            .remove-btn {
                padding: var(--space-2);
                background: transparent;
                border: none;
                color: var(--text-tertiary);
                cursor: pointer;
                transition: all 0.2s;
            }

            .remove-btn:hover {
                color: var(--error);
            }

            .footer-actions {
                display: flex;
                gap: var(--space-3);
                justify-content: flex-end;
                width: 100%;
            }

            .btn {
                padding: var(--space-2) var(--space-4);
                border-radius: var(--radius-lg);
                font-size: var(--text-sm);
                font-weight: 500;
                cursor: pointer;
                transition: all var(--duration-fast);
            }

            .btn-secondary {
                background: var(--crm-surface-muted);
                border: 1px solid var(--crm-stroke);
                color: var(--text-secondary);
            }

            .btn-secondary:hover {
                background: var(--crm-surface);
                color: var(--text-primary);
            }

            .btn-primary {
                background: var(--accent);
                border: 1px solid var(--accent);
                color: var(--text-inverse);
            }

            .btn-primary:hover:not(:disabled) {
                background: var(--accent-hover);
            }

            .btn-primary:disabled {
                opacity: 0.5;
                cursor: not-allowed;
            }

            .no-types-message {
                padding: var(--space-3);
                background: var(--glass-solid-subtle);
                border-radius: var(--radius-md);
                color: var(--text-tertiary);
                font-size: var(--text-sm);
                text-align: center;
            }
        `
    ];

    constructor() {
        super();
        this.size = 'lg';
        this.entityId = null;
        this.entity = null;
        this._formData = {
            entity_type: 'person',
            entity_subtype: null,
            name: '',
            description: '',
            tags: [],
            attributes: {},
            due_date: null,
            priority: null,
        };
        this._entityTypes = [];
        this._selectedType = 'person';
        this._saving = false;
        this._attributeRows = [];

        this._unsubscribe = CRMStore.subscribe(state => {
            this._entityTypes = state.entities.entityTypes || [];
        });
    }

    disconnectedCallback() {
        super.disconnectedCallback();
        this._unsubscribe?.();
    }

    async firstUpdated() {
        super.firstUpdated?.();
        
        const crmApi = this.services.get('crmApi');
        await CRMStore.loadEntityTypes(crmApi);
        
        if (this.entity) {
            this._formData = {
                entity_type: this.entity.entity_type || 'person',
                entity_subtype: this.entity.entity_subtype || null,
                name: this.entity.name || '',
                description: this.entity.description || '',
                tags: this.entity.tags || [],
                attributes: this.entity.attributes || {},
                due_date: this.entity.due_date || null,
                priority: this.entity.priority || null,
            };
            this._selectedType = this.entity.entity_type || 'person';
            this._attributeRows = Object.entries(this.entity.attributes || {}).map(
                ([key, value]) => ({ key, value })
            );
        }
    }

    get _isEditing() {
        return !!this.entityId;
    }

    renderHeader() {
        return this._isEditing ? 'Редактировать сущность' : 'Новая сущность';
    }

    _getBaseTypes() {
        return this._entityTypes.filter(t => !t.parent_type_id);
    }

    _getSubtypes(parentTypeId) {
        return this._entityTypes.filter(t => t.parent_type_id === parentTypeId);
    }

    _onTypeSelect(typeId) {
        this._selectedType = typeId;
        this._formData = {
            ...this._formData,
            entity_type: typeId,
            entity_subtype: null,
        };
    }

    _onSubtypeSelect(subtypeId) {
        this._formData = {
            ...this._formData,
            entity_subtype: this._formData.entity_subtype === subtypeId ? null : subtypeId,
        };
    }

    _onNameInput(e) {
        this._formData = { ...this._formData, name: e.target.value };
    }

    _onDescriptionInput(e) {
        this._formData = { ...this._formData, description: e.target.value };
    }

    _onTagsChange(e) {
        this._formData = { ...this._formData, tags: e.detail.tags };
    }

    _onDueDateChange(e) {
        this._formData = { ...this._formData, due_date: e.target.value || null };
    }

    _onPriorityChange(e) {
        this._formData = { ...this._formData, priority: e.target.value || null };
    }

    _onAddAttribute() {
        this._attributeRows = [...this._attributeRows, { key: '', value: '' }];
    }

    _onAttributeKeyChange(index, value) {
        this._attributeRows = this._attributeRows.map((row, i) =>
            i === index ? { ...row, key: value } : row
        );
    }

    _onAttributeValueChange(index, value) {
        this._attributeRows = this._attributeRows.map((row, i) =>
            i === index ? { ...row, value } : row
        );
    }

    _onRemoveAttribute(index) {
        this._attributeRows = this._attributeRows.filter((_, i) => i !== index);
    }

    async _onSave() {
        if (!this._formData.name.trim()) {
            this.error('Название обязательно');
            return;
        }

        this._saving = true;

        const attributes = {};
        for (const row of this._attributeRows) {
            if (row.key.trim()) {
                attributes[row.key.trim()] = row.value;
            }
        }

        const data = {
            entity_type: this._formData.entity_type,
            entity_subtype: this._formData.entity_subtype,
            name: this._formData.name.trim(),
            description: this._formData.description.trim() || null,
            tags: this._formData.tags,
            attributes,
            due_date: this._formData.due_date,
            priority: this._formData.priority,
        };

        const crmApi = this.services.get('crmApi');

        if (this._isEditing) {
            await CRMStore.updateEntity(crmApi, this.entityId, data);
            this.success('Сущность обновлена');
        } else {
            await CRMStore.createEntity(crmApi, data);
            this.success('Сущность создана');
        }

        this._saving = false;
        this.dispatchEvent(new CustomEvent('saved'));
        this.close();
    }

    _resolveIconName(iconName) {
        if (typeof iconName === 'string' && /^[a-z0-9-]+$/i.test(iconName)) {
            return iconName;
        }
        return 'file';
    }

    renderBody() {
        const baseTypes = this._getBaseTypes();
        const subtypes = this._getSubtypes(this._selectedType);
        const isTask = this._selectedType === 'task';

        return html`
            <div class="form-grid">
                <div class="form-group">
                    <label class="form-label">Тип</label>
                    ${baseTypes.length > 0 ? html`
                        <div class="type-chips">
                            ${baseTypes.map(type => html`
                                <button
                                    type="button"
                                    class="type-chip ${this._selectedType === type.type_id ? 'active' : ''}"
                                    @click=${() => this._onTypeSelect(type.type_id)}
                                >
                                    <platform-icon name="${this._resolveIconName(type.icon)}" size="16"></platform-icon>
                                    <span>${type.name}</span>
                                </button>
                            `)}
                        </div>
                    ` : html`
                        <div class="no-types-message">Загрузка типов...</div>
                    `}
                </div>

                ${subtypes.length > 0 ? html`
                    <div class="form-group">
                        <label class="form-label">Подтип</label>
                        <div class="type-chips">
                            ${subtypes.map(type => html`
                                <button
                                    type="button"
                                    class="type-chip ${this._formData.entity_subtype === type.type_id ? 'active' : ''}"
                                    @click=${() => this._onSubtypeSelect(type.type_id)}
                                >
                                    <platform-icon name="${this._resolveIconName(type.icon)}" size="16"></platform-icon>
                                    <span>${type.name}</span>
                                </button>
                            `)}
                        </div>
                    </div>
                ` : ''}

                <div class="form-group">
                    <label class="form-label">Название *</label>
                    <input
                        type="text"
                        class="form-input"
                        placeholder="Введите название"
                        .value=${this._formData.name}
                        @input=${this._onNameInput}
                    />
                </div>

                <div class="form-group">
                    <label class="form-label">Описание</label>
                    <textarea
                        class="form-textarea"
                        rows="4"
                        placeholder="Введите описание"
                        .value=${this._formData.description}
                        @input=${this._onDescriptionInput}
                    ></textarea>
                </div>

                <div class="form-group">
                    <label class="form-label">Теги</label>
                    <tag-input
                        .tags=${this._formData.tags}
                        placeholder="Введите тег и нажмите Enter"
                        @change=${this._onTagsChange}
                    ></tag-input>
                </div>

                ${isTask ? html`
                    <div class="form-row">
                        <div class="form-group">
                            <label class="form-label">Дедлайн</label>
                            <platform-date-picker
                                class="form-input"
                                mode="date"
                                value-format="iso"
                                .value=${this._formData.due_date || null}
                                @change=${this._onDueDateChange}
                            ></platform-date-picker>
                        </div>
                        <div class="form-group">
                            <label class="form-label">Приоритет</label>
                            <select
                                class="form-select"
                                .value=${this._formData.priority || ''}
                                @change=${this._onPriorityChange}
                            >
                                <option value="">Не указан</option>
                                <option value="low">Низкий</option>
                                <option value="medium">Средний</option>
                                <option value="high">Высокий</option>
                                <option value="urgent">Срочный</option>
                            </select>
                        </div>
                    </div>
                ` : ''}

                <div class="attributes-section">
                    <label class="form-label">Дополнительные атрибуты</label>
                    ${this._attributeRows.map((row, index) => html`
                        <div class="attribute-row">
                            <input
                                type="text"
                                class="form-input"
                                placeholder="Ключ"
                                .value=${row.key}
                                @input=${(e) => this._onAttributeKeyChange(index, e.target.value)}
                            />
                            <input
                                type="text"
                                class="form-input"
                                placeholder="Значение"
                                .value=${row.value}
                                @input=${(e) => this._onAttributeValueChange(index, e.target.value)}
                            />
                            <button
                                type="button"
                                class="remove-btn"
                                @click=${() => this._onRemoveAttribute(index)}
                            >
                                <platform-icon name="close" size="14"></platform-icon>
                            </button>
                        </div>
                    `)}
                    <button
                        type="button"
                        class="add-attribute-btn"
                        @click=${this._onAddAttribute}
                    >
                        + Добавить атрибут
                    </button>
                </div>
            </div>
        `;
    }

    renderFooter() {
        return html`
            <div class="footer-actions">
                <button
                    type="button"
                    class="btn btn-secondary"
                    @click=${() => this.close()}
                >
                    Отмена
                </button>
                <button
                    type="button"
                    class="btn btn-primary"
                    ?disabled=${this._saving}
                    @click=${this._onSave}
                >
                    ${this._saving ? 'Сохранение...' : 'Сохранить'}
                </button>
            </div>
        `;
    }
}

customElements.define('entity-modal', EntityModal);
