/**
 * Entity Card - Детальная карточка сущности
 * Показывает: данные, связанные entities, attachments, grants panel
 * Граф связей загружается лениво по кнопке пользователя
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
        _pendingAccessRequests: { state: true },
        _requestsLoading: { state: true },
        _processingRequestId: { state: true },
        _graphVisible: { state: true },
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
                background: var(--crm-button-secondary-bg);
                border: 1px solid var(--crm-button-secondary-bg);
                border-radius: var(--radius-lg);
                color: var(--crm-button-secondary-text);
                font-size: var(--text-sm);
                cursor: pointer;
                transition: all var(--duration-fast);
            }

            .action-btn:hover {
                background: var(--crm-button-secondary-hover);
                border-color: var(--crm-button-secondary-hover);
                color: var(--crm-button-secondary-text);
            }

            .action-btn.primary {
                background: var(--crm-button-primary-bg);
                border-color: var(--crm-button-primary-bg);
                color: var(--crm-button-primary-text);
            }

            .action-btn.primary:hover {
                background: var(--crm-button-primary-hover);
                border-color: var(--crm-button-primary-hover);
            }

            .icon-btn {
                width: 36px;
                height: 36px;
                display: inline-flex;
                align-items: center;
                justify-content: center;
                border-radius: var(--radius-lg);
                border: 1px solid var(--crm-stroke);
                background: var(--crm-surface-muted);
                color: var(--text-secondary);
                cursor: pointer;
                transition: all var(--duration-fast);
                padding: 0;
                flex-shrink: 0;
            }

            .icon-btn:hover {
                background: var(--crm-surface);
                color: var(--text-primary);
                border-color: var(--accent-subtle);
            }

            .content {
                height: calc(100% - 85px);
                overflow-y: auto;
                padding: var(--space-4);
                animation: card-fade-in 0.15s ease-out;
            }

            @keyframes card-fade-in {
                from { opacity: 0; transform: translateY(4px); }
                to { opacity: 1; transform: translateY(0); }
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
                gap: var(--space-2);
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

            .show-graph-btn {
                width: 100%;
                padding: var(--space-3);
                background: var(--crm-surface-muted);
                border: 1px dashed var(--crm-stroke);
                border-radius: var(--radius-lg);
                color: var(--text-secondary);
                font-size: var(--text-sm);
                cursor: pointer;
                display: flex;
                align-items: center;
                justify-content: center;
                gap: var(--space-2);
                transition: all var(--duration-fast);
            }

            .show-graph-btn:hover {
                border-color: var(--accent-subtle);
                color: var(--text-primary);
            }

            .requests-list {
                display: flex;
                flex-direction: column;
                gap: var(--space-2);
            }

            .request-item {
                border: 1px solid var(--crm-stroke);
                border-radius: var(--radius-lg);
                background: var(--crm-surface-muted);
                padding: var(--space-3);
                display: flex;
                flex-direction: column;
                gap: var(--space-2);
            }

            .request-title {
                font-size: var(--text-sm);
                font-weight: 600;
                color: var(--text-primary);
            }

            .request-message {
                font-size: var(--text-sm);
                color: var(--text-secondary);
                white-space: pre-wrap;
            }

            .request-actions {
                display: flex;
                justify-content: flex-end;
                gap: var(--space-2);
            }

            .request-btn {
                height: 30px;
                border: none;
                border-radius: var(--radius-md);
                padding: 0 var(--space-3);
                font-size: var(--text-xs);
                cursor: pointer;
            }

            .request-btn.approve {
                background: var(--crm-button-primary-bg);
                color: var(--crm-button-primary-text);
            }

            .request-btn.reject {
                background: rgba(255, 136, 92, 0.18);
                color: #ff885c;
            }

            .request-btn:disabled {
                opacity: 0.6;
                cursor: not-allowed;
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
        this._pendingAccessRequests = [];
        this._requestsLoading = false;
        this._processingRequestId = '';
        this._graphVisible = false;

        this._unsubscribe = CRMStore.subscribe(state => {
            this._entity = state.entities.currentEntity;
            this._relatedEntities = state.entities.currentEntityRelated || [];
            this._entityTypes = state.entities.entityTypes || [];
            this._loading = state.entities.cardLoading || false;
        });
    }

    disconnectedCallback() {
        super.disconnectedCallback();
        this._unsubscribe?.();
    }

    updated(changedProperties) {
        if (changedProperties.has('entityId')) {
            this._graphVisible = false;
            if (this.entityId) {
                this._loadEntityCard();
            }
        }
    }

    async _loadEntityCard() {
        if (!this.entityId) return;

        const crmApi = this.crmApi;
        const card = await CRMStore.loadEntityCard(crmApi, this.entityId);

        const currentUser = this.auth?.user;
        this._isOwner = currentUser && card.entity?.user_id === currentUser.user_id;
        if (this._isOwner) {
            await this._loadPendingRequests();
        } else {
            this._pendingAccessRequests = [];
        }
    }

    _resolveRequestEntityId(request) {
        const entityId = request?.resource_id || request?.entity_id;
        if (typeof entityId !== 'string' || entityId.trim().length === 0) {
            throw new Error('Access request entity id is required');
        }
        return entityId;
    }

    _resolveRequestId(request) {
        const requestId = request?.request_id || request?.id;
        if (typeof requestId !== 'string' || requestId.trim().length === 0) {
            throw new Error('Access request id is required');
        }
        return requestId;
    }

    _resolveRequesterLabel(request) {
        if (typeof request?.requester_name === 'string' && request.requester_name.trim().length > 0) {
            return request.requester_name;
        }
        if (typeof request?.requester_id === 'string' && request.requester_id.trim().length > 0) {
            return request.requester_id;
        }
        if (typeof request?.user_id === 'string' && request.user_id.trim().length > 0) {
            return request.user_id;
        }
        return this.i18n.t('entity_card.requester_fallback');
    }

    async _loadPendingRequests() {
        const crmApi = this.crmApi;
        this._requestsLoading = true;
        try {
            const requests = await CRMStore.loadAccessRequests(crmApi, 'pending');
            if (!Array.isArray(requests)) {
                throw new Error('Access requests payload must be array');
            }
            this._pendingAccessRequests = requests.filter((request) => this._resolveRequestEntityId(request) === this.entityId);
        } finally {
            this._requestsLoading = false;
        }
    }

    async _approveRequest(request) {
        const requestId = this._resolveRequestId(request);
        this._processingRequestId = requestId;
        try {
            const crmApi = this.crmApi;
            await CRMStore.approveAccessRequest(crmApi, requestId);
            await this._loadPendingRequests();
        } finally {
            this._processingRequestId = '';
        }
    }

    async _rejectRequest(request) {
        const requestId = this._resolveRequestId(request);
        this._processingRequestId = requestId;
        try {
            const crmApi = this.crmApi;
            await CRMStore.rejectAccessRequest(crmApi, requestId);
            await this._loadPendingRequests();
        } finally {
            this._processingRequestId = '';
        }
    }

    _getEntityTypeConfig(entity) {
        const typeId = entity?.entity_subtype || entity?.entity_type;
        const entityType = this._entityTypes.find(t => t.type_id === typeId);
        if (entityType) {
            return {
                icon: this._resolveIconName(entityType.icon),
                color: entityType.color || 'var(--text-tertiary)',
                label: entityType.name || typeId,
            };
        }
        return { icon: 'folder', color: 'var(--text-tertiary)', label: entity?.entity_type || '' };
    }

    _hexToRgba(hex, alpha) {
        if (!hex || hex.startsWith('var(')) {
            return `rgba(148, 163, 184, ${alpha})`;
        }
        const clean = hex.replace('#', '');
        const r = parseInt(clean.substring(0, 2), 16);
        const g = parseInt(clean.substring(2, 4), 16);
        const b = parseInt(clean.substring(4, 6), 16);
        return `rgba(${r}, ${g}, ${b}, ${alpha})`;
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

    async _onShowGraph() {
        this._graphVisible = true;
        await this.updateComplete;
        await import('./mini-graph-preview.js');
    }

    _renderAttributes(attributes) {
        if (!attributes || Object.keys(attributes).length === 0) {
            return '';
        }

        return html`
            <div class="section">
                <div class="section-title">${this.i18n.t('entities.attributes')}</div>
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
                <div class="section-title">${this.i18n.t('entity_card.related_entities')}</div>
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
                                    <platform-icon name="${typeConfig.icon}" size="18"></platform-icon>
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

    _renderGraph() {
        if (!this.entityId) return '';

        if (!this._graphVisible) {
            return html`
                <div class="section">
                    <div class="section-title">${this.i18n.t('entity_card.graph_section')}</div>
                    <button class="show-graph-btn" type="button" @click=${this._onShowGraph}>
                        <platform-icon name="link" size="16"></platform-icon>
                        ${this.i18n.t('entity_card.show_graph')}
                    </button>
                </div>
            `;
        }

        return html`
            <div class="section">
                <div class="section-title">${this.i18n.t('entity_card.graph_section')}</div>
                <mini-graph-preview
                    .entityId=${this.entityId}
                    .maxDepth=${5}
                    height="200px"
                    @entity-open=${(e) => this._onRelatedClick(e.detail.entityId)}
                ></mini-graph-preview>
            </div>
        `;
    }

    _renderPendingAccessRequests() {
        if (!this._isOwner) {
            return '';
        }
        return html`
            <div class="section">
                <div class="section-title">${this.i18n.t('entity_card.access_requests')}</div>
                ${this._requestsLoading ? html`
                    <div class="request-item">
                        <div class="request-message">${this.i18n.t('entity_card.requests_loading')}</div>
                    </div>
                ` : this._pendingAccessRequests.length === 0 ? html`
                    <div class="request-item">
                        <div class="request-message">${this.i18n.t('entity_card.requests_empty')}</div>
                    </div>
                ` : html`
                    <div class="requests-list">
                        ${this._pendingAccessRequests.map((request) => {
                            const requestId = this._resolveRequestId(request);
                            const message = request?.message && typeof request.message === 'string'
                                ? request.message
                                : this.i18n.t('entity_card.no_comment');
                            return html`
                                <div class="request-item">
                                    <div class="request-title">${this._resolveRequesterLabel(request)}</div>
                                    <div class="request-message">${message}</div>
                                    <div class="request-actions">
                                        <button
                                            class="request-btn reject"
                                            type="button"
                                            ?disabled=${this._processingRequestId === requestId}
                                            @click=${() => this._rejectRequest(request)}
                                        >
                                            ${this.i18n.t('entity_card.request_reject')}
                                        </button>
                                        <button
                                            class="request-btn approve"
                                            type="button"
                                            ?disabled=${this._processingRequestId === requestId}
                                            @click=${() => this._approveRequest(request)}
                                        >
                                            ${this.i18n.t('entity_card.request_approve')}
                                        </button>
                                    </div>
                                </div>
                            `;
                        })}
                    </div>
                `}
            </div>
        `;
    }

    render() {
        if (!this.entityId) {
            return html`
                <div class="empty-state">
                    <platform-icon name="book-open" size="56"></platform-icon>
                    <div>${this.i18n.t('entity_card.empty_pick_title')}</div>
                    <div style="font-size: var(--text-sm);">
                        ${this.i18n.t('entity_card.empty_pick_subtitle')}
                    </div>
                </div>
            `;
        }

        if (this._loading || !this._entity) {
            return html`
                <div class="empty-state">
                    <div>${this.i18n.t('loading', {}, 'common')}</div>
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
                    <platform-icon name="${typeConfig.icon}" size="22"></platform-icon>
                </div>

                <div class="header-content">
                    <div class="header-name">${this._entity.name}</div>
                    <div class="header-type">${typeConfig.label}</div>
                </div>

                <div class="header-actions">
                    ${this._isOwner ? html`
                        <button class="icon-btn" @click=${this._onEdit} title=${this.i18n.t('edit', {}, 'common')}>
                            <platform-icon name="edit" size="16"></platform-icon>
                        </button>
                    ` : html`
                        <button class="icon-btn" @click=${this._onRequestAccess} title=${this.i18n.t('entity_card.request_access_tooltip')}>
                            <platform-icon name="lock" size="16"></platform-icon>
                        </button>
                    `}
                </div>
            </div>

            <div class="content">
                ${this._entity.description ? html`
                    <div class="section">
                        <div class="section-title">${this.i18n.t('tasks.description')}</div>
                        <div class="description">${this._entity.description}</div>
                    </div>
                ` : ''}

                ${this._entity.tags?.length > 0 ? html`
                    <div class="section">
                        <div class="section-title">${this.i18n.t('tasks.tags')}</div>
                        <div class="tags-list">
                            ${this._entity.tags.map(tag => html`
                                <span class="tag">${tag}</span>
                            `)}
                        </div>
                    </div>
                ` : ''}

                ${this._renderAttributes(this._entity.attributes)}

                ${this._renderRelated()}

                ${this._renderGraph()}

                ${this._renderPendingAccessRequests()}

                ${this._isOwner ? html`
                    <grants-panel .entityId=${this.entityId}></grants-panel>
                ` : ''}
            </div>
        `;
    }
}

customElements.define('entity-card', EntityCard);
