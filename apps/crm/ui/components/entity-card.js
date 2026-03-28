/**
 * Entity Card - Детальная карточка сущности
 * Показывает: данные, связанные entities, attachments, grants panel
 */
import { html, css } from 'lit';
import { PlatformElement } from '@platform/lib/platform-element/index.js';
import { buttonStyles } from '@platform/lib/styles/shared/button.styles.js';
import { CRMStore } from '../store/crm.store.js';
import './grants-panel.js';
import '@platform/lib/components/platform-icon.js';

export class EntityCard extends PlatformElement {
    static properties = {
        entityId: { type: String },
        showBackButton: { type: Boolean },
        _entity: { state: true },
        _relatedEntities: { state: true },
        _entityTypes: { state: true },
        _loading: { state: true },
        _isOwner: { state: true },
    };

    static styles = [
        PlatformElement.styles,
        buttonStyles,
        css`
            :host {
                display: block;
                width: 100%;
                height: 100%;
                background: var(--crm-surface);
                backdrop-filter: blur(var(--glass-blur-strong));
                border: 1px solid var(--crm-stroke-strong);
                border-radius: var(--radius-2xl);
                overflow: hidden;
            }

            .header {
                display: flex;
                align-items: center;
                gap: var(--space-3);
                padding: var(--space-4);
                border-bottom: 1px solid var(--crm-stroke);
                background: var(--crm-surface-tint);
            }

            .back-btn {
                padding: var(--space-2);
                background: var(--crm-surface-muted);
                border: 1px solid var(--crm-stroke);
                border-radius: var(--radius-lg);
                color: var(--text-primary);
                cursor: pointer;
                transition: all var(--duration-fast);
            }

            .back-btn:hover {
                background: var(--crm-surface);
            }

            .header-icon {
                width: 48px;
                height: 48px;
                display: flex;
                align-items: center;
                justify-content: center;
                border-radius: var(--radius-xl);
                font-size: var(--text-2xl);
                flex-shrink: 0;
            }

            .header-content {
                flex: 1;
                min-width: 0;
            }

            .header-name {
                font-size: var(--text-xl);
                font-weight: 600;
                color: var(--text-primary);
                margin-bottom: var(--space-1);
            }

            .header-type {
                font-size: var(--text-sm);
                color: var(--text-secondary);
            }

            .header-actions {
                display: flex;
                gap: var(--space-2);
            }

            .action-btn {
                padding: var(--space-2) var(--space-3);
                background: var(--crm-surface-muted);
                border: 1px solid var(--crm-stroke);
                border-radius: var(--radius-lg);
                color: var(--text-secondary);
                font-size: var(--text-sm);
                cursor: pointer;
                transition: all var(--duration-fast);
            }

            .action-btn:hover {
                background: var(--crm-surface);
                color: var(--text-primary);
            }

            .action-btn.primary {
                background: var(--accent);
                border-color: var(--accent);
                color: var(--text-inverse);
            }

            .action-btn.primary:hover {
                background: var(--accent-hover);
            }

            .content {
                height: calc(100% - 85px);
                overflow-y: auto;
                padding: var(--space-4);
            }

            .section {
                margin-bottom: var(--space-6);
            }

            .section-title {
                font-size: var(--text-sm);
                font-weight: 600;
                text-transform: uppercase;
                letter-spacing: 0.05em;
                color: var(--text-tertiary);
                margin-bottom: var(--space-3);
            }

            .description {
                font-size: var(--text-base);
                color: var(--text-primary);
                line-height: 1.6;
                white-space: pre-wrap;
            }

            .attributes-grid {
                display: grid;
                grid-template-columns: repeat(auto-fill, minmax(200px, 1fr));
                gap: var(--space-3);
            }

            .attribute-item {
                padding: var(--space-3);
                background: var(--crm-surface-muted);
                border-radius: var(--radius-lg);
            }

            .attribute-label {
                font-size: var(--text-xs);
                color: var(--text-tertiary);
                margin-bottom: var(--space-1);
            }

            .attribute-value {
                font-size: var(--text-base);
                color: var(--text-primary);
                word-break: break-word;
            }

            .related-list {
                display: flex;
                flex-direction: column;
                gap: var(--space-2);
            }

            .related-item {
                display: flex;
                align-items: center;
                gap: var(--space-3);
                padding: var(--space-3);
                background: var(--crm-surface-muted);
                border: 1px solid var(--crm-stroke);
                border-radius: var(--radius-lg);
                cursor: pointer;
                transition: all var(--duration-fast);
                width: 100%;
                text-align: left;
            }

            .related-item:hover {
                background: var(--crm-surface);
                border-color: var(--accent-subtle);
            }

            .related-icon {
                width: 32px;
                height: 32px;
                display: flex;
                align-items: center;
                justify-content: center;
                border-radius: var(--radius-md);
                font-size: var(--text-lg);
                flex-shrink: 0;
            }

            .related-name {
                flex: 1;
                font-size: var(--text-sm);
                color: var(--text-primary);
            }

            .related-type {
                font-size: var(--text-xs);
                color: var(--text-tertiary);
            }

            .empty-state {
                display: flex;
                flex-direction: column;
                align-items: center;
                justify-content: center;
                height: 100%;
                color: var(--text-tertiary);
                text-align: center;
            }

            .empty-icon {
                width: 80px;
                height: 80px;
                margin-bottom: var(--space-4);
                opacity: 0.6;
            }
            
            .empty-icon img {
                width: 100%;
                height: 100%;
                object-fit: contain;
            }

            .tags-list {
                display: flex;
                flex-wrap: wrap;
                gap: var(--space-2);
            }

            .tag {
                padding: var(--space-1) var(--space-3);
                background: var(--crm-surface-tint);
                border-radius: var(--radius-full);
                font-size: var(--text-sm);
                color: var(--text-secondary);
            }

            .request-access-section {
                padding: var(--space-4);
                background: var(--crm-surface-muted);
                border-radius: var(--radius-lg);
                text-align: center;
            }

            .request-access-section p {
                margin: 0 0 var(--space-3) 0;
                color: var(--text-secondary);
                font-size: var(--text-sm);
            }

            :host-context([data-theme="light"]) {
                background: var(--crm-surface);
            }
            
            @media (max-width: 767px) {
                :host {
                    border-radius: 0;
                    border: none;
                }
            }
        `
    ];

    constructor() {
        super();
        this.entityId = null;
        this.showBackButton = false;
        this._entity = null;
        this._relatedEntities = [];
        this._entityTypes = [];
        this._loading = false;
        this._isOwner = false;

        this._unsubscribe = CRMStore.subscribe(state => {
            this._entity = state.entities.currentEntity;
            this._relatedEntities = state.entities.currentEntityRelated || [];
            this._entityTypes = state.entities.entityTypes || [];
            this._loading = state.entities.entitiesLoading;
        });
    }

    disconnectedCallback() {
        super.disconnectedCallback();
        this._unsubscribe?.();
    }

    updated(changedProperties) {
        if (changedProperties.has('entityId') && this.entityId) {
            this._loadEntityCard();
        }
    }

    async _loadEntityCard() {
        if (!this.entityId) return;
        
        const crmApi = this.services.get('crmApi');
        const card = await CRMStore.loadEntityCard(crmApi, this.entityId);
        
        const currentUser = this.auth?.user;
        this._isOwner = currentUser && card.entity?.user_id === currentUser.user_id;
    }

    _getEntityTypeConfig(entity) {
        const typeId = entity?.entity_subtype || entity?.entity_type;
        const entityType = this._entityTypes.find(t => t.type_id === typeId);
        if (entityType) {
            return {
                icon: entityType.icon || 'file',
                color: entityType.color || 'var(--text-tertiary)',
                label: entityType.name || typeId,
            };
        }
        return { icon: 'file', color: 'var(--text-tertiary)', label: entity?.entity_type || '' };
    }

    _hexToRgba(hex, alpha) {
        if (!hex) return `rgba(148, 163, 184, ${alpha})`;
        const cleanHex = hex.replace('#', '');
        const r = parseInt(cleanHex.substring(0, 2), 16);
        const g = parseInt(cleanHex.substring(2, 4), 16);
        const b = parseInt(cleanHex.substring(4, 6), 16);
        return `rgba(${r}, ${g}, ${b}, ${alpha})`;
    }

    _resolveIconName(iconName) {
        if (typeof iconName === 'string' && /^[a-z0-9-]+$/i.test(iconName)) {
            return iconName;
        }
        return 'file';
    }

    _onBack() {
        this.dispatchEvent(new CustomEvent('back'));
    }

    _onEdit() {
        const modal = document.createElement('entity-modal');
        modal.entityId = this.entityId;
        modal.entity = this._entity;
        document.body.appendChild(modal);
        modal.showModal();
        modal.addEventListener('close', () => modal.remove());
        modal.addEventListener('saved', () => this._loadEntityCard());
    }

    _onRequestAccess() {
        const modal = document.createElement('access-request-modal');
        modal.entityId = this.entityId;
        modal.entityName = this._entity?.name;
        document.body.appendChild(modal);
        modal.showModal();
        modal.addEventListener('close', () => modal.remove());
    }

    _onRelatedClick(entityId) {
        CRMStore.setCurrentEntity(entityId);
    }

    _renderAttributes(attributes) {
        if (!attributes || Object.keys(attributes).length === 0) {
            return '';
        }

        return html`
            <div class="section">
                <div class="section-title">Атрибуты</div>
                <div class="attributes-grid">
                    ${Object.entries(attributes).map(([key, value]) => html`
                        <div class="attribute-item">
                            <div class="attribute-label">${key}</div>
                            <div class="attribute-value">${value}</div>
                        </div>
                    `)}
                </div>
            </div>
        `;
    }

    _renderRelated() {
        if (this._relatedEntities.length === 0) {
            return '';
        }

        return html`
            <div class="section">
                <div class="section-title">Связанные сущности</div>
                <div class="related-list">
                    ${this._relatedEntities.map(entity => {
                        const typeConfig = this._getEntityTypeConfig(entity);
                        const bgColor = this._hexToRgba(typeConfig.color, 0.15);
                        
                        return html`
                            <button
                                class="related-item"
                                type="button"
                                @click=${() => this._onRelatedClick(entity.entity_id)}
                            >
                                <div
                                    class="related-icon"
                                    style="background: ${bgColor}; color: ${typeConfig.color};"
                                >
                                    <platform-icon name="${this._resolveIconName(typeConfig.icon)}" size="18"></platform-icon>
                                </div>
                                <div class="related-name">${entity.name}</div>
                                <div class="related-type">${typeConfig.label}</div>
                            </button>
                        `;
                    })}
                </div>
            </div>
        `;
    }

    render() {
        if (!this.entityId) {
            return html`
                <div class="empty-state">
                    <div class="empty-icon">
                        <platform-icon name="book-open" size="56"></platform-icon>
                    </div>
                    <div>Выберите сущность</div>
                    <div style="margin-top: var(--space-2); font-size: var(--text-sm);">
                        из списка или фильтров
                    </div>
                </div>
            `;
        }

        if (this._loading || !this._entity) {
            return html`
                <div class="empty-state">
                    <div>Загрузка...</div>
                </div>
            `;
        }

        const typeConfig = this._getEntityTypeConfig(this._entity);
        const bgColor = this._hexToRgba(typeConfig.color, 0.15);

        return html`
            <div class="header">
                ${this.showBackButton ? html`
                    <button class="back-btn" @click=${this._onBack}>
                        <platform-icon name="arrow-left" size="18"></platform-icon>
                    </button>
                ` : ''}

                <div
                    class="header-icon"
                    style="background: ${bgColor}; color: ${typeConfig.color};"
                >
                    <platform-icon name="${this._resolveIconName(typeConfig.icon)}" size="22"></platform-icon>
                </div>

                <div class="header-content">
                    <div class="header-name">${this._entity.name}</div>
                    <div class="header-type">${typeConfig.label}</div>
                </div>

                <div class="header-actions">
                    ${this._isOwner ? html`
                        <button class="action-btn" @click=${this._onEdit}>
                            <platform-icon name="edit" size="16"></platform-icon>
                            Редактировать
                        </button>
                    ` : html`
                        <button class="action-btn primary" @click=${this._onRequestAccess}>
                            <platform-icon name="access-request" size="16"></platform-icon>
                            Запросить доступ
                        </button>
                    `}
                </div>
            </div>

            <div class="content">
                ${this._entity.description ? html`
                    <div class="section">
                        <div class="section-title">Описание</div>
                        <div class="description">${this._entity.description}</div>
                    </div>
                ` : ''}

                ${this._entity.tags?.length > 0 ? html`
                    <div class="section">
                        <div class="section-title">Теги</div>
                        <div class="tags-list">
                            ${this._entity.tags.map(tag => html`
                                <span class="tag">${tag}</span>
                            `)}
                        </div>
                    </div>
                ` : ''}

                ${this._renderAttributes(this._entity.attributes)}

                ${this._renderRelated()}

                ${this._isOwner ? html`
                    <grants-panel .entityId=${this.entityId}></grants-panel>
                ` : ''}
            </div>
        `;
    }
}

customElements.define('entity-card', EntityCard);
