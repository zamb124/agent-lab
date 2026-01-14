/**
 * AI Entity Card - Карточка предложенной сущности с редактированием
 */
import { html, css } from 'lit';
import { PlatformElement } from '@platform/lib/platform-element/index.js';
import { buttonStyles, iconButtonStyles } from '@platform/lib/styles/shared/button.styles.js';
import { formStyles } from '@platform/lib/styles/shared/form.styles.js';
import { glassStyles } from '@platform/lib/styles/shared/glass.styles.js';

const PRIORITY_OPTIONS = [
    { value: 'low', label: 'Низкий' },
    { value: 'medium', label: 'Средний' },
    { value: 'high', label: 'Высокий' },
    { value: 'urgent', label: 'Срочный' },
];

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
                background: var(--glass-solid-subtle);
                border: 1px solid var(--glass-border-subtle);
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
                background: rgba(16, 185, 129, 0.15);
                color: var(--accent);
                border: 1px solid rgba(16, 185, 129, 0.3);
            }

            .dedup-badge.existing {
                background: rgba(245, 158, 11, 0.15);
                color: #f59e0b;
                border: 1px solid rgba(245, 158, 11, 0.3);
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
                background: rgba(245, 158, 11, 0.1);
                border: 1px solid rgba(245, 158, 11, 0.2);
                border-radius: var(--radius-sm);
                margin-bottom: var(--space-2);
            }

            .existing-info strong {
                color: #f59e0b;
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
                border: 1px solid rgba(16, 185, 129, 0.3);
                border-radius: var(--radius-sm);
                color: var(--accent);
                cursor: pointer;
                transition: all var(--duration-fast) ease;
                font-size: var(--text-sm);
                -webkit-tap-highlight-color: transparent;
                touch-action: manipulation;
            }

            .confirm-btn:hover {
                background: var(--accent);
                color: white;
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
                border-color: rgba(16, 185, 129, 0.3);
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
                background: rgba(244, 63, 94, 0.1);
                border-color: rgba(244, 63, 94, 0.3);
                color: var(--error);
            }

            .empty-attributes {
                font-size: var(--text-xs);
                color: var(--text-disabled);
                text-align: center;
                padding: var(--space-2);
            }

            :host-context([data-theme="light"]) .card {
                background: rgba(255, 255, 255, 0.8);
                border-color: rgba(15, 23, 42, 0.1);
            }

            :host-context([data-theme="light"]) .card-header {
                background: rgba(255, 255, 255, 0.5);
            }

            :host-context([data-theme="light"]) .field-input {
                background: rgba(255, 255, 255, 0.9);
                border-color: rgba(15, 23, 42, 0.1);
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
                icon: entityType.icon || '📄',
                color: entityType.color || '#607D8B',
                label: entityType.name
            };
        }
        
        const baseEntityType = types.find(t => t.type_id === baseType);
        if (baseEntityType) {
            return {
                icon: baseEntityType.icon || '📄',
                color: baseEntityType.color || '#607D8B',
                label: baseEntityType.name
            };
        }
        
        return { icon: '📄', color: '#607D8B', label: baseType || 'Сущность' };
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

    _getDedupBadge() {
        const action = this.suggestion.dedup_action;
        const confidence = this.suggestion.dedup_confidence;
        
        if (action === 'merge') {
            const confidencePercent = Math.round((confidence || 0) * 100);
            return {
                class: 'existing',
                label: 'Existing',
                confidence: confidencePercent
            };
        }
        
        return {
            class: 'new',
            label: 'New',
            confidence: null
        };
    }

    render() {
        const config = this._getTypeConfig();
        const isTask = this.suggestion.entity_type === 'task';
        const isNote = this.suggestion.entity_type === 'note';
        const subtypeOptions = this._getSubtypeOptions();
        const dedupBadge = this._getDedupBadge();
        const isUpdate = this.suggestion.dedup_action === 'merge';

        return html`
            <div class="card">
                <div class="card-header">
                    <span class="type-icon">${config.icon}</span>
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
                    <button type="button" class="confirm-btn" @click=${this._onConfirm} title="${isUpdate ? 'Обновить' : 'Создать'}">
                        ${isUpdate ? '↑' : '✓'}
                    </button>
                </div>

                <div class="card-body">
                    ${isUpdate && this.suggestion.dedup_existing_name ? html`
                        <div class="existing-info">
                            Будет обновлено: <strong>${this.suggestion.dedup_existing_name}</strong>
                        </div>
                    ` : ''}

                    <div class="field-group">
                        <label class="field-label">Название</label>
                        <input
                            type="text"
                            class="field-input"
                            .value=${this.suggestion.name || ''}
                            @input=${(e) => this._onFieldChange('name', e)}
                            placeholder="Введите название"
                        />
                    </div>

                    <div class="field-group">
                        <label class="field-label">Описание</label>
                        <textarea
                            class="field-input field-textarea"
                            .value=${this.suggestion.description || ''}
                            @input=${(e) => this._onFieldChange('description', e)}
                            placeholder="Описание..."
                        ></textarea>
                    </div>

                    ${isNote && subtypeOptions.length > 0 ? html`
                        <div class="field-group">
                            <label class="field-label">Подтип</label>
                            <select
                                class="field-input field-select"
                                .value=${this.suggestion.entity_subtype || ''}
                                @change=${(e) => this._onFieldChange('entity_subtype', e)}
                            >
                                <option value="">Без подтипа</option>
                                ${subtypeOptions.map(opt => html`
                                    <option value=${opt.value}>${opt.label}</option>
                                `)}
                            </select>
                        </div>
                    ` : ''}

                    <div class="row">
                        ${isNote ? html`
                            <div class="field-group">
                                <label class="field-label">Дата</label>
                                <input
                                    type="date"
                                    class="field-input"
                                    .value=${this.suggestion.note_date || ''}
                                    @input=${(e) => this._onFieldChange('note_date', e)}
                                />
                            </div>
                        ` : ''}

                        ${isTask ? html`
                            <div class="field-group">
                                <label class="field-label">Дедлайн</label>
                                <input
                                    type="date"
                                    class="field-input"
                                    .value=${this.suggestion.due_date || ''}
                                    @input=${(e) => this._onFieldChange('due_date', e)}
                                />
                            </div>
                            <div class="field-group">
                                <label class="field-label">Приоритет</label>
                                <select
                                    class="field-input field-select"
                                    .value=${this.suggestion.priority || 'medium'}
                                    @change=${(e) => this._onFieldChange('priority', e)}
                                >
                                    ${PRIORITY_OPTIONS.map(opt => html`
                                        <option value=${opt.value}>${opt.label}</option>
                                    `)}
                                </select>
                            </div>
                        ` : ''}
                    </div>

                    <div class="attributes-section">
                        <div class="attributes-header">
                            <span class="attributes-title">Атрибуты</span>
                            <button type="button" class="add-attr-btn" @click=${this._addAttribute} title="Добавить атрибут">
                                +
                            </button>
                        </div>

                        ${this._attributes.length === 0 ? html`
                            <div class="empty-attributes">Нет атрибутов</div>
                        ` : this._attributes.map((attr, i) => html`
                            <div class="attribute-row">
                                <input
                                    type="text"
                                    class="field-input attr-key"
                                    .value=${attr.key}
                                    @input=${(e) => this._onAttributeChange(i, 'key', e)}
                                    placeholder="Ключ"
                                />
                                <input
                                    type="text"
                                    class="field-input attr-value"
                                    .value=${attr.value}
                                    @input=${(e) => this._onAttributeChange(i, 'value', e)}
                                    placeholder="Значение"
                                />
                                <button
                                    type="button"
                                    class="remove-attr-btn"
                                    @click=${() => this._removeAttribute(i)}
                                    title="Удалить"
                                >
                                    −
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
