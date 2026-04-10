/**
 * Entity Card - Детальная карточка сущности
 * Показывает: данные, связанные entities, attachments, grants panel
 * Граф связей загружается лениво по кнопке пользователя
 */
import { html, css } from 'lit';
import { PlatformElement } from '@platform/lib/platform-element/index.js';
import { buttonStyles } from '@platform/lib/styles/shared/button.styles.js';
import { platformConfirm } from '@platform/lib/components/platform-confirm-modal.js';
import { AppEvents } from '@platform/lib/utils/types.js';
import { CRMStore } from '../store/crm.store.js';
import { nextModalLayerZIndex } from '@platform/lib/utils/modal-z-stack.js';
import './grants-panel.js';
import '@platform/lib/components/platform-icon.js';
import '@platform/lib/components/fields/platform-field.js';

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
        _deleting: { state: true },
        _headerMenuOpen: { state: true },
        _headerMenuAnchor: { state: true },
        _headerMenuZ: { state: true },
        _entityGrants: { state: true },
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
                background: var(--accent-secondary);
                border: 1px solid var(--accent-secondary);
                border-radius: var(--radius-lg);
                color: var(--platform-btn-secondary-text);
                font-size: var(--text-sm);
                cursor: pointer;
                transition: all var(--duration-fast);
            }

            .action-btn:hover {
                background: var(--platform-btn-secondary-hover);
                border-color: var(--platform-btn-secondary-hover);
                color: var(--platform-btn-secondary-text);
            }

            .action-btn.primary {
                background: var(--accent);
                border-color: var(--accent);
                color: var(--platform-btn-primary-text);
            }

            .action-btn.primary:hover {
                background: var(--platform-btn-primary-hover);
                border-color: var(--platform-btn-primary-hover);
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

            .icon-btn.danger {
                border-color: rgba(244, 63, 94, 0.4);
                color: var(--error, #f43f5e);
            }

            .icon-btn.danger:hover:not(:disabled) {
                background: rgba(244, 63, 94, 0.12);
                border-color: var(--error, #f43f5e);
                color: var(--error, #f43f5e);
            }

            .icon-btn:disabled {
                opacity: 0.5;
                cursor: not-allowed;
            }

            .header-menu-root {
                position: relative;
            }

            .header-dropdown {
                min-width: 240px;
                padding: var(--space-2);
                background: var(--crm-surface);
                border: 1px solid var(--crm-stroke-strong);
                border-radius: var(--radius-lg);
                box-shadow: 0 8px 32px rgba(0, 0, 0, 0.24);
            }

            .header-dropdown-item {
                width: 100%;
                display: flex;
                align-items: center;
                gap: var(--space-3);
                padding: var(--space-2) var(--space-3);
                border: none;
                border-radius: var(--radius-md);
                background: transparent;
                color: var(--text-primary);
                font-size: var(--text-sm);
                text-align: left;
                cursor: pointer;
                transition: background var(--duration-fast);
            }

            .header-dropdown-item:hover {
                background: var(--crm-surface-muted);
            }

            .header-dropdown-item.danger {
                color: var(--error, #f43f5e);
            }

            .header-dropdown-item.danger:hover {
                background: rgba(244, 63, 94, 0.1);
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
                display: flex;
                align-items: center;
                gap: var(--space-1);
                font-size: var(--text-xs);
                color: var(--text-tertiary);
                margin-bottom: var(--space-1);
            }

            .attribute-value {
                font-size: var(--text-base);
                color: var(--text-primary);
                word-break: break-word;
            }

            .attr-badge {
                display: inline-flex;
                align-items: center;
                padding: 0 4px;
                border-radius: var(--radius-sm);
                font-size: 9px;
                font-weight: 600;
                text-transform: uppercase;
                letter-spacing: 0.03em;
                line-height: 14px;
                flex-shrink: 0;
            }

            .attr-badge.required {
                background: rgba(239, 68, 68, 0.12);
                color: #ef4444;
            }

            .attr-badge.optional {
                background: rgba(59, 130, 246, 0.10);
                color: #3b82f6;
            }

            .attr-badge.public {
                background: rgba(34, 197, 94, 0.10);
                color: #22c55e;
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
                background: var(--accent);
                color: var(--platform-btn-primary-text);
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
        this._deleting = false;
        this._headerMenuOpen = false;
        this._headerMenuAnchor = null;
        this._headerMenuZ = 0;
        this._entityGrants = [];
        this._syncedAccessRequestsForEntityId = '';
        this._boundAuthChangeForOwnership = this._onAuthChangeForOwnership.bind(this);
        this._boundCloseHeaderMenu = this._closeHeaderMenuOnOutside.bind(this);

        this._unsubscribe = CRMStore.subscribe(state => {
            this._entity = state.entities.currentEntity;
            this._relatedEntities = state.entities.currentEntityRelated || [];
            this._entityTypes = state.entities.entityTypes || [];
            this._loading = state.entities.cardLoading || false;
            this._entityGrants = state.grants.currentEntityGrants || [];
            this._syncOwnershipAndAccessUI();
        });
    }

    connectedCallback() {
        super.connectedCallback();
        window.addEventListener(AppEvents.AUTH_CHANGE, this._boundAuthChangeForOwnership);
        document.addEventListener('pointerdown', this._boundCloseHeaderMenu, true);
        this._syncOwnershipAndAccessUI();
    }

    disconnectedCallback() {
        document.removeEventListener('pointerdown', this._boundCloseHeaderMenu, true);
        window.removeEventListener(AppEvents.AUTH_CHANGE, this._boundAuthChangeForOwnership);
        super.disconnectedCallback();
        this._unsubscribe?.();
    }

    _onAuthChangeForOwnership() {
        this._syncOwnershipAndAccessUI();
    }

    updated(changedProperties) {
        if (changedProperties.has('entityId')) {
            this._graphVisible = false;
            this._headerMenuOpen = false;
            this._syncedAccessRequestsForEntityId = '';
            if (this.entityId) {
                this._loadEntityCard();
            }
        }
    }

    _closeHeaderMenuOnOutside(ev) {
        if (!this._headerMenuOpen) {
            return;
        }
        const root = this.renderRoot;
        const trigger = root.querySelector('.header-menu-trigger');
        const panel = root.querySelector('.header-dropdown');
        if (!trigger || !panel) {
            return;
        }
        const path = ev.composedPath();
        for (const n of path) {
            if (n === trigger || n === panel) {
                return;
            }
            if (n instanceof Node && trigger.contains(n)) {
                return;
            }
            if (n instanceof Node && panel.contains(n)) {
                return;
            }
        }
        this._headerMenuOpen = false;
        this.requestUpdate();
    }

    _toggleHeaderMenu(ev) {
        ev.preventDefault();
        ev.stopPropagation();
        if (this._headerMenuOpen) {
            this._headerMenuOpen = false;
            return;
        }
        const btn = ev.currentTarget;
        const r = btn.getBoundingClientRect();
        this._headerMenuAnchor = {
            top: Math.round(r.bottom + 6),
            right: Math.round(document.documentElement.clientWidth - r.right),
        };
        this._headerMenuZ = nextModalLayerZIndex();
        this._headerMenuOpen = true;
    }

    _hasPublicGrant() {
        return this._entityGrants.some((g) => g.grant_type === 'public');
    }

    async _headerMenuMakePublic() {
        this._headerMenuOpen = false;
        if (!this.entityId) {
            return;
        }
        const crmApi = this.crmApi;
        await CRMStore.makeEntityPublic(crmApi, this.entityId);
        this.success(this.i18n.t('grants.success_entity_public'));
    }

    _headerMenuShareUser() {
        this._headerMenuOpen = false;
        if (!this.entityId) {
            return;
        }
        const modal = document.createElement('share-modal');
        modal.entityId = this.entityId;
        modal.shareType = 'user';
        document.body.appendChild(modal);
        modal.showModal();
        modal.addEventListener('close', () => modal.remove());
        modal.addEventListener('shared', () => {
            void CRMStore.loadEntityGrants(this.crmApi, this.entityId);
        });
    }

    _headerMenuShareCompany() {
        this._headerMenuOpen = false;
        if (!this.entityId) {
            return;
        }
        const modal = document.createElement('share-modal');
        modal.entityId = this.entityId;
        modal.shareType = 'company';
        document.body.appendChild(modal);
        modal.showModal();
        modal.addEventListener('close', () => modal.remove());
        modal.addEventListener('shared', () => {
            void CRMStore.loadEntityGrants(this.crmApi, this.entityId);
        });
    }

    _syncOwnershipAndAccessUI() {
        const authUserId = this._platformAuthUserId(this.auth?.user);
        const entity = this._entity;
        const eid = typeof entity?.entity_id === 'string' ? entity.entity_id.trim() : '';
        const entityOwnerId =
            typeof entity?.user_id === 'string' && entity.user_id.trim().length > 0
                ? entity.user_id.trim()
                : null;
        const nextOwner = Boolean(authUserId && entityOwnerId && eid && entityOwnerId === authUserId);
        const prevOwner = this._isOwner;
        this._isOwner = nextOwner;

        if (!nextOwner) {
            this._pendingAccessRequests = [];
            this._syncedAccessRequestsForEntityId = '';
            if (prevOwner !== nextOwner) {
                this.requestUpdate();
            }
            return;
        }

        const shouldLoadRequests = eid !== this._syncedAccessRequestsForEntityId || (!prevOwner && nextOwner);
        if (shouldLoadRequests) {
            this._syncedAccessRequestsForEntityId = eid;
            this._loadPendingRequests();
        } else if (prevOwner !== nextOwner) {
            this.requestUpdate();
        }
    }

    async _loadEntityCard() {
        if (!this.entityId) return;

        const crmApi = this.crmApi;
        await CRMStore.loadEntityCard(crmApi, this.entityId);
        this._syncOwnershipAndAccessUI();
    }

    _platformAuthUserId(user) {
        if (!user || typeof user !== 'object') {
            return null;
        }
        if (typeof user.user_id === 'string' && user.user_id.trim().length > 0) {
            return user.user_id.trim();
        }
        if (typeof user.id === 'string' && user.id.trim().length > 0) {
            return user.id.trim();
        }
        return null;
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

    async _onDelete() {
        this._headerMenuOpen = false;
        if (!this.entityId || !this._entity || this._deleting) {
            return;
        }
        const displayName =
            typeof this._entity.name === 'string' && this._entity.name.trim().length > 0
                ? this._entity.name.trim()
                : this.entityId;
        const confirmed = await platformConfirm(
            this.i18n.t('entities_page.delete_entity_confirm', { name: displayName }),
            {
                title: this.i18n.t('entities_page.delete_entity_title'),
                variant: 'danger',
                confirmVariant: 'danger',
                confirmText: this.i18n.t('delete', {}, 'common'),
                cancelText: this.i18n.t('cancel', {}, 'common'),
            }
        );
        if (!confirmed) {
            return;
        }
        this._deleting = true;
        try {
            await CRMStore.deleteEntity(this.crmApi, this.entityId);
        } catch {
            this.error(this.i18n.t('entities_page.delete_entity_failed'));
        } finally {
            this._deleting = false;
        }
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

    _getAttributeFieldType(fieldKey) {
        const typeId = this._entity?.entity_subtype || this._entity?.entity_type;
        const entityType = this._entityTypes.find(t => t.type_id === typeId);
        if (!entityType) return 'string';
        const spec = entityType.required_fields?.[fieldKey]
            || entityType.optional_fields?.[fieldKey];
        return spec?.type || 'string';
    }

    _getAttributeFieldConfig(fieldKey) {
        const typeId = this._entity?.entity_subtype || this._entity?.entity_type;
        const entityType = this._entityTypes.find(t => t.type_id === typeId);
        if (!entityType) return {};
        const spec = entityType.required_fields?.[fieldKey]
            || entityType.optional_fields?.[fieldKey];
        if (spec?.type === 'enum') {
            return { values: spec.values || [] };
        }
        return {};
    }

    _getEntityTypeForCurrent() {
        const typeId = this._entity?.entity_subtype || this._entity?.entity_type;
        return this._entityTypes.find(t => t.type_id === typeId) || null;
    }

    _isAttributeRequired(key) {
        const entityType = this._getEntityTypeForCurrent();
        return Boolean(entityType?.required_fields?.[key]);
    }

    _isAttributeOptional(key) {
        const entityType = this._getEntityTypeForCurrent();
        return Boolean(entityType?.optional_fields?.[key]);
    }

    _isAttributePublic(key) {
        const entityType = this._getEntityTypeForCurrent();
        return (entityType?.public_fields || []).includes(key);
    }

    _getAttributeLabel(key) {
        const entityType = this._getEntityTypeForCurrent();
        const spec = entityType?.required_fields?.[key]
            || entityType?.optional_fields?.[key];
        return spec?.label || key;
    }

    _renderAttributeBadges(key) {
        const badges = [];
        if (this._isAttributeRequired(key)) {
            badges.push(html`<span class="attr-badge required">${this.i18n.t('entity_card.badge_required')}</span>`);
        } else if (this._isAttributeOptional(key)) {
            badges.push(html`<span class="attr-badge optional">${this.i18n.t('entity_card.badge_optional')}</span>`);
        }
        if (this._isAttributePublic(key)) {
            badges.push(html`<span class="attr-badge public">${this.i18n.t('entity_card.badge_public')}</span>`);
        }
        return badges;
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
                            <div class="attribute-label">
                                ${this._getAttributeLabel(key)}
                                ${this._renderAttributeBadges(key)}
                            </div>
                            <platform-field
                                .type=${this._getAttributeFieldType(key)}
                                .value=${value}
                                .config=${this._getAttributeFieldConfig(key)}
                                mode="view"
                            ></platform-field>
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
                        <div class="header-menu-root">
                            <button
                                class="icon-btn header-menu-trigger"
                                type="button"
                                title=${this.i18n.t('entity_card.actions_menu_tooltip')}
                                aria-label=${this.i18n.t('entity_card.actions_menu_tooltip')}
                                aria-haspopup="menu"
                                aria-expanded=${this._headerMenuOpen ? 'true' : 'false'}
                                @click=${this._toggleHeaderMenu}
                            >
                                <platform-icon name="more-vertical" size="16"></platform-icon>
                            </button>
                            ${this._headerMenuOpen && this._headerMenuAnchor
                                ? html`
                                    <div
                                        class="header-dropdown"
                                        role="menu"
                                        style="position: fixed; top: ${this._headerMenuAnchor.top}px; right: ${this._headerMenuAnchor.right}px; z-index: ${this._headerMenuZ}"
                                        @pointerdown=${(e) => e.stopPropagation()}
                                    >
                                        ${!this._hasPublicGrant()
                                            ? html`
                                                <button
                                                    type="button"
                                                    class="header-dropdown-item"
                                                    role="menuitem"
                                                    @click=${this._headerMenuMakePublic}
                                                >
                                                    <platform-icon name="globe" size="16"></platform-icon>
                                                    ${this.i18n.t('grants.make_public_entity')}
                                                </button>
                                            `
                                            : ''}
                                        <button
                                            type="button"
                                            class="header-dropdown-item"
                                            role="menuitem"
                                            @click=${this._headerMenuShareUser}
                                        >
                                            <platform-icon name="user" size="16"></platform-icon>
                                            ${this.i18n.t('grants.share_user')}
                                        </button>
                                        <button
                                            type="button"
                                            class="header-dropdown-item"
                                            role="menuitem"
                                            @click=${this._headerMenuShareCompany}
                                        >
                                            <platform-icon name="building-one" size="16"></platform-icon>
                                            ${this.i18n.t('grants.share_company')}
                                        </button>
                                        <button
                                            type="button"
                                            class="header-dropdown-item danger"
                                            role="menuitem"
                                            ?disabled=${this._deleting}
                                            @click=${this._onDelete}
                                        >
                                            <platform-icon name="trash" size="16"></platform-icon>
                                            ${this.i18n.t('entity_card.delete_entity_tooltip')}
                                        </button>
                                    </div>
                                `
                                : ''}
                        </div>
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
