/**
 * Карточка предложенной сущности (AI) с редактированием полей.
 */
import { html, css } from 'lit';
import { PlatformElement } from '@platform/lib/platform-element/index.js';
import { buttonStyles, iconButtonStyles } from '@platform/lib/styles/shared/button.styles.js';
import { formStyles } from '@platform/lib/styles/shared/form.styles.js';
import { glassStyles } from '@platform/lib/styles/shared/glass.styles.js';
import '@platform/lib/components/platform-icon.js';
import '@platform/lib/components/platform-date-picker.js';

export class AIEntityCard extends PlatformElement {
    static properties = {
        suggestion: { type: Object },
        index: { type: Number },
        entityTypes: { type: Array },
        _attributes: { state: true },
    };

    static styles = [
        PlatformElement.styles,
        buttonStyles,
        iconButtonStyles,
        formStyles,
        glassStyles,
        css`
            :host {
                display: block;
            }

            .card {
                background: var(--crm-surface-muted);
                border: 1px solid var(--crm-stroke);
                border-radius: var(--radius-lg);
                overflow: hidden;
                transition: all var(--duration-fast) ease;
            }

            .card:hover {
                border-color: var(--glass-border-medium);
            }

            .card-header {
                display: flex;
                align-items: center;
                gap: var(--space-2);
                padding: var(--space-3);
                background: var(--glass-tint-subtle);
                border-bottom: 1px solid var(--glass-border-subtle);
            }

            .type-icon {
                font-size: var(--text-lg);
                line-height: 1;
            }

            .type-label {
                flex: 1;
                font-size: var(--text-sm);
                font-weight: var(--font-semibold);
                color: var(--text-primary);
            }

            .type-badge {
                font-size: var(--text-xs);
                padding: var(--space-1) var(--space-2);
                background: var(--glass-tint-medium);
                border-radius: var(--radius-sm);
                color: var(--text-secondary);
            }

            .dedup-badge {
                font-size: var(--text-xs);
                padding: var(--space-1) var(--space-2);
                border-radius: var(--radius-sm);
                font-weight: var(--font-semibold);
                text-transform: uppercase;
                letter-spacing: 0.02em;
            }

            .dedup-badge.new {
                background: var(--accent-subtle);
                color: var(--accent);
                border: 1px solid var(--crm-selected-stroke);
            }

            .dedup-badge.existing {
                background: var(--accent-quaternary-subtle);
                color: var(--accent-quaternary);
                border: 1px solid var(--warning-border);
            }

            .dedup-confidence {
                font-size: var(--text-xs);
                color: var(--text-tertiary);
                margin-left: var(--space-1);
            }

            .existing-info {
                font-size: var(--text-xs);
                color: var(--text-secondary);
                padding: var(--space-2);
                background: var(--accent-quaternary-subtle);
                border: 1px solid var(--warning-border);
                border-radius: var(--radius-sm);
                margin-bottom: var(--space-2);
            }

            .existing-info strong {
                color: var(--accent-quaternary);
            }

            .confirm-btn {
                position: relative;
                z-index: 1;
                width: 28px;
                height: 28px;
                min-width: 28px;
                min-height: 28px;
                display: flex;
                align-items: center;
                justify-content: center;
                background: var(--accent-subtle);
                border: 1px solid var(--crm-selected-stroke);
                border-radius: var(--radius-sm);
                color: var(--accent);
                cursor: pointer;
                transition: all var(--duration-fast) ease;
                font-size: var(--text-sm);
                -webkit-tap-highlight-color: transparent;
                touch-action: manipulation;
            }

            .confirm-btn:hover {
                background: var(--crm-button-primary-bg);
                color: var(--crm-button-primary-text);
            }

            .card-body {
                padding: var(--space-3);
                display: flex;
                flex-direction: column;
                gap: var(--space-3);
            }

            .field-group {
                display: flex;
                flex-direction: column;
                gap: var(--space-1);
            }

            .field-label {
                font-size: var(--text-xs);
                color: var(--text-tertiary);
                text-transform: uppercase;
                letter-spacing: 0.05em;
            }

            .field-input {
                width: 100%;
                padding: var(--space-2);
                font-size: var(--text-sm);
                color: var(--text-primary);
                background: var(--glass-tint-subtle);
                border: 1px solid var(--glass-border-subtle);
                border-radius: var(--radius-sm);
                outline: none;
                transition: all var(--duration-fast) ease;
                font-family: inherit;
                box-sizing: border-box;
            }

            .field-input:focus {
                background: var(--glass-tint-medium);
                border-color: var(--accent);
            }

            .field-textarea {
                min-height: 60px;
                resize: vertical;
                line-height: 1.4;
            }

            .field-select {
                appearance: none;
                cursor: pointer;
                padding-right: var(--space-6);
                background-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='10' height='10' viewBox='0 0 10 10'%3E%3Cpath fill='%23999' d='M5 7L1 3h8z'/%3E%3C/svg%3E");
                background-repeat: no-repeat;
                background-position: right var(--space-2) center;
            }

            .row {
                display: flex;
                gap: var(--space-2);
            }

            .row .field-group {
                flex: 1;
            }

            .attributes-section {
                border-top: 1px solid var(--glass-border-subtle);
                padding-top: var(--space-3);
            }

            .attributes-header {
                display: flex;
                align-items: center;
                justify-content: space-between;
                margin-bottom: var(--space-2);
            }

            .attributes-title {
                font-size: var(--text-xs);
                color: var(--text-tertiary);
                text-transform: uppercase;
                letter-spacing: 0.05em;
            }

            .add-attr-btn {
                position: relative;
                z-index: 1;
                width: 24px;
                height: 24px;
                min-width: 24px;
                min-height: 24px;
                display: flex;
                align-items: center;
                justify-content: center;
                background: var(--glass-tint-subtle);
                border: 1px solid var(--glass-border-subtle);
                border-radius: var(--radius-sm);
                color: var(--text-secondary);
                cursor: pointer;
                font-size: var(--text-sm);
                transition: all var(--duration-fast) ease;
                -webkit-tap-highlight-color: transparent;
                touch-action: manipulation;
            }

            .add-attr-btn:hover {
                background: var(--accent-subtle);
                border-color: var(--crm-selected-stroke);
                color: var(--accent);
            }

            .attribute-row {
                display: flex;
                align-items: center;
                gap: var(--space-2);
                margin-bottom: var(--space-2);
            }

            .attribute-row:last-child {
                margin-bottom: 0;
            }

            .attr-key {
                width: 80px;
                flex-shrink: 0;
            }

            .attr-value {
                flex: 1;
            }

            .remove-attr-btn {
                position: relative;
                z-index: 1;
                width: 24px;
                height: 24px;
                min-width: 24px;
                min-height: 24px;
                display: flex;
                align-items: center;
                justify-content: center;
                background: transparent;
                border: 1px solid var(--glass-border-subtle);
                border-radius: var(--radius-sm);
                color: var(--text-tertiary);
                cursor: pointer;
                font-size: var(--text-sm);
                transition: all var(--duration-fast) ease;
                flex-shrink: 0;
                -webkit-tap-highlight-color: transparent;
                touch-action: manipulation;
            }

            .remove-attr-btn:hover {
                background: var(--crm-danger-bg);
                border-color: var(--crm-danger-stroke);
                color: var(--error);
            }

            .empty-attributes {
                font-size: var(--text-xs);
                color: var(--text-disabled);
                text-align: center;
                padding: var(--space-2);
            }

            :host-context([data-theme="light"]) .card {
                background: var(--crm-surface-muted);
                border-color: var(--crm-stroke);
            }

            :host-context([data-theme="light"]) .card-header {
                background: var(--crm-surface-tint);
            }

            :host-context([data-theme="light"]) .field-input {
                background: var(--crm-surface-elevated);
                border-color: var(--crm-stroke);
            }
        `
    ];

    constructor() {
        super();
        this.suggestion = {};
        this.index = 0;
        this.entityTypes = [];
        this._attributes = [];
        this._attributesInitialized = false;
    }

    willUpdate(changedProperties) {
        if (changedProperties.has('suggestion') && this.suggestion?.attributes && !this._attributesInitialized) {
            this._attributes = Object.entries(this.suggestion.attributes).map(
                ([key, value]) => ({ key, value: String(value) })
            );
            this._attributesInitialized = true;
        }
    }

    _getTypeConfig() {
        const subtype = this.suggestion.entity_subtype;
        const baseType = this.suggestion.entity_type;
        const types = Array.isArray(this.entityTypes) ? this.entityTypes : [];
        
        const typeId = subtype || baseType;
        const entityType = types.find(t => t.type_id === typeId);
        
        if (entityType) {
            return {
                icon: entityType.icon || 'folder',
                color: entityType.color || 'var(--text-tertiary)',
                label: entityType.name
            };
        }
        
        const baseEntityType = types.find(t => t.type_id === baseType);
        if (baseEntityType) {
            return {
                icon: baseEntityType.icon || 'folder',
                color: baseEntityType.color || 'var(--text-tertiary)',
                label: baseEntityType.name
            };
        }
        
        return {
            icon: 'folder',
            color: 'var(--text-tertiary)',
            label: baseType || this.i18n.t('ai_entity_card.entity_fallback'),
        };
    }

    _getPriorityOptions() {
        return [
            { value: 'low', label: this.i18n.t('tasks.priority_low') },
            { value: 'medium', label: this.i18n.t('tasks.priority_medium') },
            { value: 'high', label: this.i18n.t('tasks.priority_high') },
            { value: 'urgent', label: this.i18n.t('tasks.priority_urgent') },
        ];
    }

    _getSubtypeOptions() {
        const baseType = this.suggestion.entity_type;
        const types = Array.isArray(this.entityTypes) ? this.entityTypes : [];
        return types
            .filter(t => t.parent_type_id === baseType)
            .map(t => ({ value: t.type_id, label: t.name }));
    }

    _onFieldChange(field, e) {
        const value = e.target.value;
        this.emit('update', {
            index: this.index,
            field,
            value
        });
    }

    _onAttributeChange(attrIndex, field, e) {
        const value = e.target.value;
        const newAttributes = [...this._attributes];
        newAttributes[attrIndex] = { ...newAttributes[attrIndex], [field]: value };
        this._attributes = newAttributes;
        this._emitAttributesUpdate();
    }

    _addAttribute() {
        this._attributes = [...this._attributes, { key: '', value: '' }];
        this._emitAttributesUpdate();
    }

    _removeAttribute(attrIndex) {
        this._attributes = this._attributes.filter((_, i) => i !== attrIndex);
        this._emitAttributesUpdate();
    }

    _emitAttributesUpdate() {
        const attributes = {};
        for (const attr of this._attributes) {
            if (attr.key.trim()) {
                attributes[attr.key.trim()] = attr.value;
            }
        }
        this.emit('update', {
            index: this.index,
            field: 'attributes',
            value: attributes
        });
    }

    _onConfirm() {
        const isUpdate = this.suggestion.dedup_action === 'merge';
        this.emit('confirm', { 
            index: this.index,
            isUpdate,
            existingId: this.suggestion.dedup_existing_id
        });
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

    _getDedupBadge() {
        const action = this.suggestion.dedup_action;
        const confidence = this.suggestion.dedup_confidence;

        if (action === 'merge') {
            const confidencePercent = Math.round((confidence || 0) * 100);
            return {
                class: 'existing',
                label: this.i18n.t('ai_entity_card.dedup_merge'),
                confidence: confidencePercent,
            };
        }

        return {
            class: 'new',
            label: this.i18n.t('ai_entity_card.dedup_new'),
            confidence: null,
        };
    }

    render() {
        const config = this._getTypeConfig();
        const isTask = this.suggestion.entity_type === 'task';
        const isNote = this.suggestion.entity_type === 'note';
        const subtypeOptions = this._getSubtypeOptions();
        const dedupBadge = this._getDedupBadge();
        const isUpdate = this.suggestion.dedup_action === 'merge';
        const priorityOptions = this._getPriorityOptions();

        return html`
            <div class="card">
                <div class="card-header">
                    <span class="type-icon">
                        <platform-icon name="${this._resolveIconName(config.icon)}" size="18"></platform-icon>
                    </span>
                    <span class="type-label">${config.label}</span>
                    <span class="dedup-badge ${dedupBadge.class}">
                        ${dedupBadge.label}
                        ${dedupBadge.confidence ? html`
                            <span class="dedup-confidence">${dedupBadge.confidence}%</span>
                        ` : ''}
                    </span>
                    ${this.suggestion.entity_subtype ? html`
                        <span class="type-badge">${this.suggestion.entity_subtype}</span>
                    ` : ''}
                    <button
                        type="button"
                        class="confirm-btn"
                        @click=${this._onConfirm}
                        title="${isUpdate ? this.i18n.t('ai_entity_card.update') : this.i18n.t('ai_entity_card.create')}"
                    >
                        <platform-icon name="${isUpdate ? 'arrow-up' : 'check'}" size="14"></platform-icon>
                    </button>
                </div>

                <div class="card-body">
                    ${isUpdate && this.suggestion.dedup_existing_name ? html`
                        <div class="existing-info">
                            ${this.i18n.t('ai_entity_card.will_update_prefix')}
                            <strong>${this.suggestion.dedup_existing_name}</strong>
                        </div>
                    ` : ''}

                    <div class="field-group">
                        <label class="field-label">${this.i18n.t('entities.name')}</label>
                        <input
                            type="text"
                            class="field-input"
                            .value=${this.suggestion.name || ''}
                            @input=${(e) => this._onFieldChange('name', e)}
                            placeholder=${this.i18n.t('ai_entity_card.name_placeholder')}
                        />
                    </div>

                    <div class="field-group">
                        <label class="field-label">${this.i18n.t('tasks.description')}</label>
                        <textarea
                            class="field-input field-textarea"
                            .value=${this.suggestion.description || ''}
                            @input=${(e) => this._onFieldChange('description', e)}
                            placeholder=${this.i18n.t('ai_entity_card.description_placeholder')}
                        ></textarea>
                    </div>

                    ${isNote && subtypeOptions.length > 0 ? html`
                        <div class="field-group">
                            <label class="field-label">${this.i18n.t('ai_entity_card.subtype_label')}</label>
                            <select
                                class="field-input field-select"
                                .value=${this.suggestion.entity_subtype || ''}
                                @change=${(e) => this._onFieldChange('entity_subtype', e)}
                            >
                                <option value="">${this.i18n.t('ai_entity_card.no_subtype')}</option>
                                ${subtypeOptions.map(opt => html`
                                    <option value=${opt.value}>${opt.label}</option>
                                `)}
                            </select>
                        </div>
                    ` : ''}

                    <div class="row">
                        ${isNote ? html`
                            <div class="field-group">
                                <label class="field-label">${this.i18n.t('notes.date')}</label>
                                <platform-date-picker
                                    class="field-input"
                                    mode="date"
                                    value-format="iso"
                                    .value=${this.suggestion.note_date || null}
                                    @change=${(e) => this._onFieldChange('note_date', e)}
                                ></platform-date-picker>
                            </div>
                        ` : ''}

                        ${isTask ? html`
                            <div class="field-group">
                                <label class="field-label">${this.i18n.t('tasks.due_date')}</label>
                                <platform-date-picker
                                    class="field-input"
                                    mode="date"
                                    value-format="iso"
                                    .value=${this.suggestion.due_date || null}
                                    @change=${(e) => this._onFieldChange('due_date', e)}
                                ></platform-date-picker>
                            </div>
                            <div class="field-group">
                                <label class="field-label">${this.i18n.t('tasks.priority')}</label>
                                <select
                                    class="field-input field-select"
                                    .value=${this.suggestion.priority || 'medium'}
                                    @change=${(e) => this._onFieldChange('priority', e)}
                                >
                                    ${priorityOptions.map(opt => html`
                                        <option value=${opt.value}>${opt.label}</option>
                                    `)}
                                </select>
                            </div>
                        ` : ''}
                    </div>

                    <div class="attributes-section">
                        <div class="attributes-header">
                            <span class="attributes-title">${this.i18n.t('ai_entity_card.attributes')}</span>
                            <button
                                type="button"
                                class="add-attr-btn"
                                @click=${this._addAttribute}
                                title=${this.i18n.t('ai_entity_card.add_attribute_title')}
                            >
                                <platform-icon name="plus" size="14"></platform-icon>
                            </button>
                        </div>

                        ${this._attributes.length === 0 ? html`
                            <div class="empty-attributes">${this.i18n.t('ai_entity_card.empty_attributes')}</div>
                        ` : this._attributes.map((attr, i) => html`
                            <div class="attribute-row">
                                <input
                                    type="text"
                                    class="field-input attr-key"
                                    .value=${attr.key}
                                    @input=${(e) => this._onAttributeChange(i, 'key', e)}
                                    placeholder=${this.i18n.t('ai_entity_card.attr_key_placeholder')}
                                />
                                <input
                                    type="text"
                                    class="field-input attr-value"
                                    .value=${attr.value}
                                    @input=${(e) => this._onAttributeChange(i, 'value', e)}
                                    placeholder=${this.i18n.t('ai_entity_card.attr_value_placeholder')}
                                />
                                <button
                                    type="button"
                                    class="remove-attr-btn"
                                    @click=${() => this._removeAttribute(i)}
                                    title=${this.i18n.t('delete', {}, 'common')}
                                >
                                    <platform-icon name="close" size="12"></platform-icon>
                                </button>
                            </div>
                        `)}
                    </div>
                </div>
            </div>
        `;
    }
}

customElements.define('ai-entity-card', AIEntityCard);
