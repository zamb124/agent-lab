/**
 * Entities List - Список сущностей с превью
 * Наследует CRMPanel для поддержки сворачивания
 */
import { html, css } from 'lit';
import { buttonStyles, iconButtonStyles } from '@platform/lib/styles/shared/button.styles.js';
import { CRMPanel } from './crm-panel.js';
import { CRMStore } from '../store/crm.store.js';
import '@platform/lib/components/platform-icon.js';

export class EntitiesList extends CRMPanel {
    static properties = {
        ...CRMPanel.properties,
        _entities: { state: true },
        _currentEntityId: { state: true },
        _entityTypes: { state: true },
        _loading: { state: true },
    };

    static styles = [
        CRMPanel.panelStyles,
        buttonStyles,
        iconButtonStyles,
        css`
            .content {
                flex: 1;
                overflow-y: auto;
                padding: var(--space-2);
            }

            .entity-item {
                display: flex;
                align-items: flex-start;
                gap: var(--space-3);
                padding: var(--space-3);
                margin-bottom: var(--space-2);
                background: var(--glass-solid-subtle);
                border: 1px solid var(--glass-border-subtle);
                border-radius: var(--radius-lg);
                cursor: pointer;
                transition: all 0.2s;
            }

            .entity-item:hover {
                background: var(--glass-solid-medium);
                border-color: var(--accent-subtle);
                transform: translateX(4px);
            }

            .entity-item.active {
                background: var(--accent-subtle);
                border-color: var(--accent);
            }

            .entity-icon {
                width: 40px;
                height: 40px;
                display: flex;
                align-items: center;
                justify-content: center;
                border-radius: var(--radius-lg);
                font-size: var(--text-xl);
                flex-shrink: 0;
            }

            .entity-content {
                flex: 1;
                min-width: 0;
            }

            .entity-name {
                font-size: var(--text-base);
                font-weight: 500;
                color: var(--text-primary);
                margin-bottom: var(--space-1);
                overflow: hidden;
                text-overflow: ellipsis;
                white-space: nowrap;
            }

            .entity-description {
                font-size: var(--text-sm);
                color: var(--text-secondary);
                line-height: 1.4;
                overflow: hidden;
                text-overflow: ellipsis;
                display: -webkit-box;
                -webkit-line-clamp: 2;
                -webkit-box-orient: vertical;
            }

            .entity-meta {
                display: flex;
                align-items: center;
                gap: var(--space-2);
                margin-top: var(--space-2);
                font-size: var(--text-xs);
                color: var(--text-tertiary);
            }

            .entity-type-badge {
                display: inline-flex;
                align-items: center;
                gap: var(--space-1);
                padding: 2px 6px;
                background: var(--glass-solid-subtle);
                border-radius: var(--radius-sm);
                font-size: var(--text-xs);
            }

            .empty-state {
                display: flex;
                flex-direction: column;
                align-items: center;
                justify-content: center;
                height: 100%;
                color: var(--text-tertiary);
                padding: var(--space-8);
                text-align: center;
            }

            .empty-icon {
                width: 64px;
                height: 64px;
                margin-bottom: var(--space-4);
                opacity: 0.6;
            }
            
            .empty-icon img {
                width: 100%;
                height: 100%;
                object-fit: contain;
            }

            .loading {
                display: flex;
                align-items: center;
                justify-content: center;
                height: 100%;
                color: var(--text-secondary);
            }
            
            .entities-count {
                font-size: var(--text-sm);
                color: var(--text-tertiary);
                font-weight: 400;
            }
        `
    ];

    constructor() {
        super();
        this.panelId = 'entities-list';
        this.panelTitle = 'Сущности';
        this.panelIcon = 'building-one';
        
        this._entities = [];
        this._currentEntityId = null;
        this._entityTypes = [];
        this._loading = false;

        this._entitiesUnsubscribe = CRMStore.subscribe(state => {
            this._entities = state.entities.list || [];
            this._currentEntityId = state.entities.currentEntityId;
            this._entityTypes = state.entities.entityTypes || [];
            this._loading = state.entities.entitiesLoading;
        });
    }

    disconnectedCallback() {
        super.disconnectedCallback();
        this._entitiesUnsubscribe?.();
    }

    _onSelectEntity(entityId) {
        CRMStore.setCurrentEntity(entityId);
        this.dispatchEvent(new CustomEvent('entity-selected', {
            detail: { entityId },
            bubbles: true,
            composed: true,
        }));
    }

    async _onCreateEntity() {
        const modal = document.createElement('entity-modal');
        document.body.appendChild(modal);
        modal.showModal();
        modal.addEventListener('close', () => modal.remove());
        modal.addEventListener('saved', async () => {
            const crmApi = this.services.get('crmApi');
            await CRMStore.loadEntities(crmApi);
        });
    }

    _getEntityTypeConfig(entity) {
        const typeId = entity.entity_subtype || entity.entity_type;
        const entityType = this._entityTypes.find(t => t.type_id === typeId);
        if (entityType) {
            return {
                icon: entityType.icon || '📄',
                color: entityType.color || '#9E9E9E',
                label: entityType.name || typeId,
            };
        }
        return { icon: '📄', color: '#9E9E9E', label: entity.entity_type };
    }

    _formatDate(dateString) {
        if (!dateString) return '';
        const date = new Date(dateString);
        return date.toLocaleDateString('ru-RU', {
            day: 'numeric',
            month: 'short',
        });
    }

    _hexToRgba(hex, alpha) {
        if (!hex) return `rgba(158, 158, 158, ${alpha})`;
        const cleanHex = hex.replace('#', '');
        const r = parseInt(cleanHex.substring(0, 2), 16);
        const g = parseInt(cleanHex.substring(2, 4), 16);
        const b = parseInt(cleanHex.substring(4, 6), 16);
        return `rgba(${r}, ${g}, ${b}, ${alpha})`;
    }
    
    renderHeaderActions() {
        return html`
            <span class="entities-count">(${this._entities.length})</span>
            <button
                class="btn-icon primary"
                @click=${this._onCreateEntity}
                title="Создать сущность"
            >
                <platform-icon name="plus" size="16"></platform-icon>
            </button>
        `;
    }

    renderContent() {
        if (this._loading) {
            return html`<div class="loading">Загрузка...</div>`;
        }

        return html`
            <div class="content">
                ${this._entities.length === 0 ? html`
                    <div class="empty-state">
                        <div class="empty-icon">
                            <img src="/crm/ui/static/assets/icons/book.png" alt="" />
                        </div>
                        <div>Нет сущностей</div>
                        <div style="margin-top: var(--space-2); font-size: var(--text-sm);">
                            Создайте первую сущность
                        </div>
                    </div>
                ` : this._entities.map(entity => {
                    const typeConfig = this._getEntityTypeConfig(entity);
                    const bgColor = this._hexToRgba(typeConfig.color, 0.15);
                    
                    return html`
                        <div
                            class="entity-item ${entity.entity_id === this._currentEntityId ? 'active' : ''}"
                            @click=${() => this._onSelectEntity(entity.entity_id)}
                        >
                            <div
                                class="entity-icon"
                                style="background: ${bgColor}; color: ${typeConfig.color};"
                            >
                                ${typeConfig.icon}
                            </div>
                            <div class="entity-content">
                                <div class="entity-name">${entity.name}</div>
                                ${entity.description ? html`
                                    <div class="entity-description">${entity.description}</div>
                                ` : ''}
                                <div class="entity-meta">
                                    <span class="entity-type-badge">
                                        ${typeConfig.label}
                                    </span>
                                    <span>${this._formatDate(entity.created_at)}</span>
                                </div>
                            </div>
                        </div>
                    `;
                })}
            </div>
        `;
    }
}

customElements.define('entities-list', EntitiesList);
