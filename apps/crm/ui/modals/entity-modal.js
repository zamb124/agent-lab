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
import '@platform/lib/components/fields/platform-field.js';

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
        _fieldErrors: { state: true },
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
                flex-wrap: wrap;
            }

            .attribute-row input {
                flex: 1;
            }

            .field-error {
                border-color: #ef4444 !important;
                box-shadow: 0 0 0 2px rgba(239, 68, 68, 0.2);
            }

            .field-error-text {
                width: 100%;
                font-size: 11px;
                color: #ef4444;
                margin-top: -4px;
            }

            .required-fields-hint {
                font-size: 12px;
                color: var(--text-tertiary);
                margin-bottom: var(--space-2);
                padding: 6px 10px;
                background: rgba(239, 68, 68, 0.08);
                border-radius: var(--radius-sm);
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

            .no-types-message {
                padding: var(--space-3);
                background: var(--glass-solid-subtle);
                border-radius: var(--radius-md);
                color: var(--text-tertiary);
                font-size: var(--text-sm);
                text-align: center;
            }

            .task-date-picker {
                width: 100%;
                --platform-date-picker-labeled-bg: var(--crm-surface);
                --platform-date-picker-labeled-border: var(--crm-stroke);
                --platform-date-picker-labeled-height: 44px;
                --platform-date-picker-labeled-padding: 0 var(--space-3);
            }
        `
    ];

    constructor() {
        super();
        this.size = 'lg';
        this.entityId = null;
        this.entity = null;
        this._formData = {
            entity_type: 'note',
            entity_subtype: null,
            name: '',
            description: '',
            tags: [],
            attributes: {},
            due_date: null,
            priority: null,
        };
        this._entityTypes = [];
        this._selectedType = 'note';
        this._saving = false;
        this._attributeRows = [];
        this._fieldErrors = {};

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
        const namespace = CRMStore.state.namespaces.current;
        const namespaceName = typeof namespace === 'string'
            ? namespace
            : (namespace && typeof namespace.name === 'string' ? namespace.name : 'default');
        await CRMStore.loadEntityTypes(crmApi, namespaceName);
        if (!this.entity && this._entityTypes.length > 0) {
            const defaultType = this._entityTypes.find((item) => !item.parent_type_id) || this._entityTypes[0];
            this._selectedType = defaultType.type_id;
            this._formData = {
                ...this._formData,
                entity_type: defaultType.type_id,
            };
        }
        
        if (this.entity) {
            this._formData = {
                entity_type: this.entity.entity_type || 'note',
                entity_subtype: this.entity.entity_subtype || null,
                name: this.entity.name || '',
                description: this.entity.description || '',
                tags: this.entity.tags || [],
                attributes: this.entity.attributes || {},
                due_date: this.entity.due_date || null,
                priority: this.entity.priority || null,
            };
            this._selectedType = this.entity.entity_type || 'note';
            this._attributeRows = Object.entries(this.entity.attributes || {}).map(
                ([key, value]) => ({ key, value })
            );
        }
    }

    get _isEditing() {
        return !!this.entityId;
    }

    renderHeader() {
        return this._isEditing
            ? this.i18n.t('entity_modal.header_edit')
            : this.i18n.t('entity_modal.header_create');
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
            this.error(this.i18n.t('entity_modal.err_name_required'));
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

        try {
            const crmApi = this.services.get('crmApi');

            if (this._isEditing) {
                await CRMStore.updateEntity(crmApi, this.entityId, data);
                this.success(this.i18n.t('entity_modal.success_updated'));
            } else {
                await CRMStore.createEntity(crmApi, data);
                this.success(this.i18n.t('entity_modal.success_created'));
            }

            this.dispatchEvent(new CustomEvent('saved'));
            this.close();
        } catch (error) {
            const message = error instanceof Error
                ? error.message
                : this.i18n.t('entity_modal.err_save');
            this._fieldErrors = this._parseFieldErrors(message);
            this.error(message);
            throw error;
        } finally {
            this._saving = false;
        }
    }

    _parseFieldErrors(errorMessage) {
        const errors = {};
        const parts = errorMessage.split('; ');
        for (const part of parts) {
            const colonIdx = part.indexOf(':');
            if (colonIdx > 0) {
                const field = part.substring(0, colonIdx).trim();
                errors[field] = part.substring(colonIdx + 1).trim();
            }
        }
        return errors;
    }

    _getFieldSpec(fieldKey) {
        const typeId = this._formData.entity_subtype || this._formData.entity_type;
        const entityType = this._entityTypes.find(t => t.type_id === typeId);
        if (!entityType) return null;
        const spec = entityType.required_fields?.[fieldKey]
            || entityType.optional_fields?.[fieldKey];
        return spec || null;
    }

    _getFieldType(fieldKey) {
        const spec = this._getFieldSpec(fieldKey);
        return spec?.type || 'string';
    }

    _getFieldConfig(fieldKey) {
        const spec = this._getFieldSpec(fieldKey);
        if (!spec) return {};
        if (spec.type === 'enum') {
            return { values: spec.values || [] };
        }
        return {};
    }

    _getRequiredFieldNames() {
        const typeId = this._formData.entity_subtype || this._formData.entity_type;
        const entityType = this._entityTypes.find(t => t.type_id === typeId);
        if (!entityType || !entityType.required_fields) return [];
        return Object.keys(entityType.required_fields);
    }

    _renderRequiredFields() {
        const requiredNames = this._getRequiredFieldNames();
        if (requiredNames.length === 0) return '';
        const existingKeys = new Set(this._attributeRows.map(r => r.key.trim()));
        const missing = requiredNames.filter(f => !existingKeys.has(f));
        if (missing.length === 0) return '';
        return html`
            <div class="required-fields-hint">
                ${this.i18n.t('entity_modal.required_fields', { fields: missing.join(', ') },
                    'crm', `Required: ${missing.join(', ')}`)}
            </div>
        `;
    }

    _resolveIconName(iconName) {
        if (iconName === 'file') {
            return 'folder';
        }
        if (typeof iconName === 'string' && /^[a-z0-9-]+$/i.test(iconName)) {
            return iconName;
        }
        return 'folder';
    }

    renderBody() {
        const baseTypes = this._getBaseTypes();
        const subtypes = this._getSubtypes(this._selectedType);
        const isTask = this._selectedType === 'task';

        return html`
            <div class="form-grid">
                <div class="form-group">
                    <label class="form-label">${this.i18n.t('entity_modal.label_type')}</label>
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
                        <div class="no-types-message">${this.i18n.t('entity_modal.loading_types')}</div>
                    `}
                </div>

                ${subtypes.length > 0 ? html`
                    <div class="form-group">
                        <label class="form-label">${this.i18n.t('entity_modal.label_subtype')}</label>
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
                    <label class="form-label">${this.i18n.t('entity_modal.label_name')}</label>
                    <input
                        type="text"
                        class="form-input"
                        placeholder=${this.i18n.t('entity_modal.placeholder_name')}
                        .value=${this._formData.name}
                        @input=${this._onNameInput}
                    />
                </div>

                <div class="form-group">
                    <label class="form-label">${this.i18n.t('entity_modal.label_description')}</label>
                    <textarea
                        class="form-textarea"
                        rows="4"
                        placeholder=${this.i18n.t('entity_modal.placeholder_description')}
                        .value=${this._formData.description}
                        @input=${this._onDescriptionInput}
                    ></textarea>
                </div>

                <div class="form-group">
                    <label class="form-label">${this.i18n.t('entity_modal.label_tags')}</label>
                    <tag-input
                        .tags=${this._formData.tags}
                        placeholder=${this.i18n.t('tasks.tags_placeholder')}
                        @change=${this._onTagsChange}
                    ></tag-input>
                </div>

                ${isTask ? html`
                    <div class="form-row">
                        <div class="form-group">
                            <label class="form-label">${this.i18n.t('entity_modal.label_due')}</label>
                            <platform-date-picker
                                class="task-date-picker"
                                mode="date"
                                value-format="iso"
                                .value=${this._formData.due_date || null}
                                @change=${this._onDueDateChange}
                            ></platform-date-picker>
                        </div>
                        <div class="form-group">
                            <label class="form-label">${this.i18n.t('entity_modal.label_priority')}</label>
                            <select
                                class="form-select"
                                .value=${this._formData.priority || ''}
                                @change=${this._onPriorityChange}
                            >
                                <option value="">${this.i18n.t('entity_modal.priority_unset')}</option>
                                <option value="low">${this.i18n.t('tasks.priority_low')}</option>
                                <option value="medium">${this.i18n.t('tasks.priority_medium')}</option>
                                <option value="high">${this.i18n.t('tasks.priority_high')}</option>
                                <option value="urgent">${this.i18n.t('tasks.priority_urgent')}</option>
                            </select>
                        </div>
                    </div>
                ` : ''}

                <div class="attributes-section">
                    <label class="form-label">${this.i18n.t('entity_modal.label_extra_attributes')}</label>
                    ${this._renderRequiredFields()}
                    ${this._attributeRows.map((row, index) => html`
                        <div class="attribute-row">
                            <input
                                type="text"
                                class="form-input ${this._fieldErrors[row.key] ? 'field-error' : ''}"
                                placeholder=${this.i18n.t('ai_entity_card.attr_key_placeholder')}
                                .value=${row.key}
                                @input=${(e) => this._onAttributeKeyChange(index, e.target.value)}
                            />
                            <platform-field
                                .type=${this._getFieldType(row.key)}
                                .value=${row.value}
                                .config=${this._getFieldConfig(row.key)}
                                mode="edit"
                                style="flex: 1;"
                                @change=${(e) => this._onAttributeValueChange(index, e.detail.value)}
                            ></platform-field>
                            <button
                                type="button"
                                class="remove-btn"
                                @click=${() => this._onRemoveAttribute(index)}
                            >
                                <platform-icon name="close" size="14"></platform-icon>
                            </button>
                            ${this._fieldErrors[row.key] ? html`
                                <span class="field-error-text">${this._fieldErrors[row.key]}</span>
                            ` : ''}
                        </div>
                    `)}
                    <button
                        type="button"
                        class="add-attribute-btn"
                        @click=${this._onAddAttribute}
                    >
                        ${this.i18n.t('entity_modal.add_attribute')}
                    </button>
                </div>
            </div>
        `;
    }

    renderSaveHeaderButton() {
        const title = this._saving
            ? this.i18n.t('entity_modal.saving')
            : this.i18n.t('save', {}, 'common');
        return this._renderHeaderSaveIcon({
            onClick: () => this._onSave(),
            disabled: this._saving,
            title,
        });
    }

    renderFooter() {
        return html`
            <div class="footer-actions">
                <button
                    type="button"
                    class="btn btn-secondary"
                    @click=${() => this.close()}
                >
                    ${this.i18n.t('cancel', {}, 'common')}
                </button>
            </div>
        `;
    }
}

customElements.define('entity-modal', EntityModal);
