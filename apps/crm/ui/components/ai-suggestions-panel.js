/**
 * AI Suggestions Panel - Панель AI предложений с группировкой по типам
 */
import { html, css } from 'lit';
import { PlatformElement } from '@platform/lib/platform-element/index.js';
import { buttonStyles } from '@platform/lib/styles/shared/button.styles.js';
import { glassStyles } from '@platform/lib/styles/shared/glass.styles.js';
import { CRMStore } from '../store/crm.store.js';
import '@platform/lib/components/platform-icon.js';
import './ai-entity-card.js';
import './ai-relationship-card.js';

export class AISuggestionsPanel extends PlatformElement {
    static properties = {
        _entities: { state: true },
        _relationships: { state: true },
        _entityTypes: { state: true },
        _relationshipTypes: { state: true },
        _confirming: { state: true },
    };

    static styles = [
        PlatformElement.styles,
        buttonStyles,
        glassStyles,
        css`
            :host {
                display: block;
                width: 320px;
                height: 100%;
                background: var(--crm-surface);
                border: 1px solid var(--crm-stroke-strong);
                border-radius: var(--radius-2xl);
                overflow: hidden;
                flex-shrink: 0;
            }

            .panel-header {
                display: flex;
                align-items: center;
                justify-content: space-between;
                padding: var(--space-4);
                background: var(--crm-surface-tint);
                border-bottom: 1px solid var(--crm-stroke);
            }

            .panel-title {
                font-size: var(--text-base);
                font-weight: var(--font-semibold);
                color: var(--text-primary);
            }

            .panel-actions {
                display: flex;
                gap: var(--space-2);
            }

            .confirm-all-btn {
                padding: var(--space-2) var(--space-3);
                background: var(--accent-gradient);
                border: none;
                border-radius: var(--radius-md);
                color: var(--text-inverse);
                font-size: var(--text-sm);
                font-weight: var(--font-medium);
                cursor: pointer;
                transition: all var(--duration-fast) var(--easing-default);
            }

            .confirm-all-btn:hover:not(:disabled) {
                transform: translateY(-1px);
                box-shadow: var(--accent-glow);
            }

            .confirm-all-btn:disabled {
                opacity: 0.5;
                cursor: not-allowed;
            }

            .close-btn {
                width: 32px;
                height: 32px;
                display: flex;
                align-items: center;
                justify-content: center;
                background: var(--crm-surface-tint);
                border: 1px solid var(--crm-stroke);
                border-radius: var(--radius-md);
                color: var(--text-secondary);
                cursor: pointer;
                font-size: var(--text-lg);
                transition: all var(--duration-fast) var(--easing-default);
            }

            .close-btn:hover {
                background: var(--crm-surface-tint-strong);
                color: var(--text-primary);
            }

            .panel-content {
                height: calc(100% - 65px);
                overflow-y: auto;
                padding: var(--space-4);
            }

            .type-section {
                margin-bottom: var(--space-4);
            }

            .type-section:last-child {
                margin-bottom: 0;
            }

            .section-header {
                display: flex;
                align-items: center;
                gap: var(--space-2);
                margin-bottom: var(--space-3);
            }

            .section-title {
                font-size: var(--text-sm);
                font-weight: var(--font-semibold);
                color: var(--text-secondary);
            }

            .section-count {
                padding: var(--space-1) var(--space-2);
                background: var(--crm-surface-tint-strong);
                border-radius: var(--radius-full);
                font-size: var(--text-xs);
                color: var(--text-tertiary);
            }

            .cards-list {
                display: flex;
                flex-direction: column;
                gap: var(--space-3);
            }

            .empty-state {
                display: flex;
                flex-direction: column;
                align-items: center;
                justify-content: center;
                padding: var(--space-8);
                text-align: center;
            }

            .empty-icon {
                width: 64px;
                height: 64px;
                margin-bottom: var(--space-3);
                opacity: 0.6;
            }
            
            .empty-icon img {
                width: 100%;
                height: 100%;
                object-fit: contain;
            }

            .empty-text {
                font-size: var(--text-sm);
                color: var(--text-tertiary);
            }

            :host-context([data-theme="light"]) {
                background: var(--crm-surface);
                border-color: var(--crm-stroke-strong);
            }

            :host-context([data-theme="light"]) .panel-header {
                background: var(--crm-surface-tint);
            }

            @media (max-width: 767px) {
                :host {
                    width: 100%;
                    border-radius: 0;
                    border: none;
                }
            }
        `
    ];

    constructor() {
        super();
        this._entities = [];
        this._relationships = [];
        this._entityTypes = [];
        this._relationshipTypes = [];
        this._confirming = false;
        this._unsubscribe = null;
    }

    connectedCallback() {
        super.connectedCallback();
        this._initFromStore();
        this._subscribeToStore();
    }

    _initFromStore() {
        const state = CRMStore.state;
        const suggestions = state.ai.suggestions || [];
        this._entities = suggestions.filter(s => s.entity_type && !s.relationship_type);
        this._relationships = suggestions.filter(s => s.relationship_type);
        this._entityTypes = state.entities.entityTypes || [];
        this._relationshipTypes = state.entities.relationshipTypes || [];
    }

    _subscribeToStore() {
        this._unsubscribe = CRMStore.subscribe(state => {
            const suggestions = state.ai.suggestions || [];
            this._entities = suggestions.filter(s => s.entity_type && !s.relationship_type);
            this._relationships = suggestions.filter(s => s.relationship_type);
            this._entityTypes = state.entities.entityTypes || [];
            this._relationshipTypes = state.entities.relationshipTypes || [];
        });
    }

    disconnectedCallback() {
        super.disconnectedCallback();
        this._unsubscribe?.();
        this._unsubscribe = null;
    }

    _groupEntitiesByType() {
        const groups = {};
        for (const entity of this._entities) {
            const type = entity.entity_type;
            if (!groups[type]) {
                groups[type] = [];
            }
            groups[type].push(entity);
        }

        const baseTypes = this._entityTypes
            .filter(t => !t.parent_type_id)
            .map(t => t.type_id);
        
        const ordered = [];
        for (const type of baseTypes) {
            if (groups[type]) {
                ordered.push({ type, entities: groups[type] });
            }
        }

        for (const type of Object.keys(groups)) {
            if (!baseTypes.includes(type)) {
                ordered.push({ type, entities: groups[type] });
            }
        }

        return ordered;
    }

    _getTypeLabel(typeId) {
        const entityType = this._entityTypes.find(t => t.type_id === typeId);
        return entityType ? entityType.name : typeId;
    }

    _getEntityIndex(entity) {
        const suggestions = [...this._entities, ...this._relationships];
        return suggestions.findIndex(s => s === entity);
    }

    _onUpdateEntity(e) {
        const { index, field, value } = e.detail;
        CRMStore.updateSuggestion(index, { [field]: value });
    }

    async _onConfirmEntity(e) {
        const { index, isUpdate, existingId } = e.detail;
        const crmApi = this.services.get('crmApi');
        try {
            if (isUpdate && existingId) {
                await CRMStore.updateExistingEntity(crmApi, index, existingId);
                this.success('Сущность обновлена');
            } else {
                await CRMStore.confirmSuggestion(crmApi, index);
                this.success('Сущность создана');
            }
        } catch (err) {
            this.error(`Ошибка: ${err.message}`);
        }
    }

    async _onConfirmRelationship(e) {
        const { index } = e.detail;
        const crmApi = this.services.get('crmApi');
        try {
            await CRMStore.confirmRelationship(crmApi, index);
            this.success('Связь создана');
        } catch (err) {
            this.error(`Ошибка создания связи: ${err.message}`);
        }
    }

    async _onConfirmAll() {
        this._confirming = true;
        const crmApi = this.services.get('crmApi');
        try {
            const count = await CRMStore.confirmAllSuggestions(crmApi);
            this.success(`Создано ${count} записей`);
        } catch (err) {
            this.error(`Ошибка: ${err.message}`);
        } finally {
            this._confirming = false;
        }
    }

    _onClose() {
        CRMStore.clearAISuggestions();
    }

    render() {
        const groups = this._groupEntitiesByType();
        const hasContent = this._entities.length > 0 || this._relationships.length > 0;
        const totalCount = this._entities.length + this._relationships.length;

        return html`
            <div class="panel-header">
                <span class="panel-title">AI Предложения</span>
                <div class="panel-actions">
                    ${hasContent ? html`
                        <button
                            class="confirm-all-btn"
                            @click=${this._onConfirmAll}
                            ?disabled=${this._confirming}
                        >
                            ${this._confirming ? 'Создание...' : `Создать все (${totalCount})`}
                        </button>
                    ` : ''}
                    <button class="close-btn" @click=${this._onClose} title="Закрыть">
                        <platform-icon name="close" size="14"></platform-icon>
                    </button>
                </div>
            </div>

            <div class="panel-content">
                ${!hasContent ? html`
                    <div class="empty-state">
                        <div class="empty-icon">
                            <platform-icon name="book-open" size="56"></platform-icon>
                        </div>
                        <div class="empty-text">Нет предложений</div>
                    </div>
                ` : html`
                    ${groups.map(group => html`
                        <div class="type-section">
                            <div class="section-header">
                                <span class="section-title">
                                    ${this._getTypeLabel(group.type)}
                                </span>
                                <span class="section-count">${group.entities.length}</span>
                            </div>
                            <div class="cards-list">
                                ${group.entities.map((entity, i) => {
                                    const globalIndex = this._entities.indexOf(entity);
                                    return html`
                                        <ai-entity-card
                                            .suggestion=${entity}
                                            .index=${globalIndex}
                                            .entityTypes=${this._entityTypes}
                                            @update=${this._onUpdateEntity}
                                            @confirm=${this._onConfirmEntity}
                                        ></ai-entity-card>
                                    `;
                                })}
                            </div>
                        </div>
                    `)}

                    ${this._relationships.length > 0 ? html`
                        <div class="type-section">
                            <div class="section-header">
                                <span class="section-title">Связи</span>
                                <span class="section-count">${this._relationships.length}</span>
                            </div>
                            <div class="cards-list">
                                ${this._relationships.map((rel, i) => {
                                    const globalIndex = this._entities.length + i;
                                    return html`
                                        <ai-relationship-card
                                            .suggestion=${rel}
                                            .index=${globalIndex}
                                            .relationshipTypes=${this._relationshipTypes}
                                            @confirm=${this._onConfirmRelationship}
                                        ></ai-relationship-card>
                                    `;
                                })}
                            </div>
                        </div>
                    ` : ''}
                `}
            </div>
        `;
    }
}

customElements.define('ai-suggestions-panel', AISuggestionsPanel);
