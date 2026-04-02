/**
 * Entities Page - Страница сущностей
 * Desktop: Toolbar + Cards Grid + Detail Panel (grid 1fr 380px)
 * Mobile: Menu btn + Toolbar + Tabs (Список / Карточка)
 */
import { html, css } from 'lit';
import { PlatformElement } from '@platform/lib/platform-element/index.js';
import { CRMStore } from '../store/crm.store.js';
import '../components/entity-card.js';
import '../modals/entity-modal.js';
import '../modals/entity-merge-modal.js';
import '@platform/lib/components/platform-icon.js';

export class EntitiesPage extends PlatformElement {
    static properties = {
        _entities: { state: true },
        _entityTypes: { state: true },
        _currentEntityId: { state: true },
        _loading: { state: true },
        _query: { state: true },
        _selectedType: { state: true },
        _selectedStatus: { state: true },
        _currentNamespace: { state: true },
        _isMobile: { state: true },
        _mobileTab: { state: true },
        _debounceTimer: { state: true },
    };

    static styles = [
        PlatformElement.styles,
        css`
            :host {
                display: flex;
                flex-direction: column;
                width: 100%;
                height: 100%;
                min-height: 0;
                overflow: hidden;
            }

            /* === HEADER === */

            .page-toolbar {
                flex-shrink: 0;
                padding-bottom: var(--space-2);
            }

            .section-label {
                color: var(--text-tertiary);
                font-size: var(--text-sm);
                margin-bottom: var(--space-1);
            }

            .top-row {
                display: flex;
                align-items: center;
                gap: var(--space-3);
                margin-bottom: var(--space-3);
            }

            .title {
                display: flex;
                align-items: center;
                gap: var(--space-2);
                font-size: 42px;
                line-height: 1;
                font-weight: 700;
                color: var(--text-primary);
                margin: 0;
                white-space: nowrap;
            }

            .entities-count {
                color: var(--text-tertiary);
                font-size: var(--text-sm);
                font-weight: 400;
            }

            .search-box {
                display: flex;
                align-items: center;
                gap: var(--space-2);
                padding: 0 var(--space-3);
                border-radius: var(--radius-full);
                border: 1px solid var(--crm-stroke);
                background: var(--crm-surface-muted);
                min-height: 40px;
                flex: 1;
                min-width: 0;
            }

            .search-input {
                width: 100%;
                border: none;
                background: transparent;
                color: var(--text-primary);
                font-size: var(--text-sm);
                outline: none;
            }

            .cta-btn {
                min-height: 40px;
                border: none;
                border-radius: var(--radius-full);
                background: var(--crm-daily-notes-cta-bg);
                color: var(--text-inverse);
                font-size: var(--text-base);
                font-weight: 500;
                padding: 0 var(--space-5);
                cursor: pointer;
                transition: background var(--duration-fast);
                white-space: nowrap;
                flex-shrink: 0;
            }

            .cta-btn:hover {
                background: var(--crm-daily-notes-cta-hover);
            }

            /* === FILTERS === */

            .filters-row {
                display: flex;
                flex-wrap: wrap;
                align-items: center;
                gap: var(--space-2);
            }

            .filter-chip {
                display: inline-flex;
                align-items: center;
                gap: 4px;
                padding: 6px 12px;
                border-radius: var(--radius-full);
                border: 1px solid var(--crm-stroke);
                background: var(--crm-surface-muted);
                color: var(--text-secondary);
                font-size: 13px;
                font-weight: 500;
                cursor: pointer;
                transition: all var(--duration-fast);
                white-space: nowrap;
            }

            .filter-chip:hover {
                background: var(--crm-surface);
                color: var(--text-primary);
            }

            .filter-chip.active {
                background: var(--crm-selected-bg);
                border-color: var(--crm-selected-stroke);
                color: var(--crm-selected-text);
            }

            .filter-divider {
                width: 1px;
                height: 20px;
                background: var(--crm-stroke);
                flex-shrink: 0;
            }

            .clear-filters-btn {
                display: inline-flex;
                align-items: center;
                gap: 4px;
                padding: 4px 8px;
                border: none;
                border-radius: var(--radius-md);
                background: transparent;
                color: var(--text-tertiary);
                font-size: 12px;
                cursor: pointer;
            }

            .clear-filters-btn:hover {
                color: var(--text-primary);
            }

            /* === DESKTOP LAYOUT === */

            .layout {
                display: grid;
                grid-template-columns: 1fr 380px;
                gap: var(--space-4);
                flex: 1;
                min-height: 0;
                overflow: hidden;
            }

            .list-panel {
                display: flex;
                flex-direction: column;
                min-height: 0;
                overflow: hidden;
            }

            .cards-scroll {
                flex: 1;
                overflow-y: auto;
                overflow-x: hidden;
                min-height: 0;
                padding: var(--space-1);
            }

            .cards-grid {
                display: grid;
                grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
                gap: var(--space-3);
                align-content: start;
            }

            .detail-panel {
                display: flex;
                flex-direction: column;
                min-height: 0;
                overflow: hidden;
            }

            /* === CARDS === */

            .entity-card-item {
                border: 1px solid var(--crm-stroke);
                background: var(--crm-surface);
                border-radius: 16px;
                padding: 16px;
                display: flex;
                flex-direction: column;
                gap: 10px;
                min-height: 130px;
                cursor: pointer;
                transition: border-color var(--duration-fast), background var(--duration-fast);
            }

            .entity-card-item:hover {
                border-color: var(--crm-stroke-strong);
                background: var(--crm-surface-elevated);
            }

            .entity-card-item.active {
                border-color: var(--crm-selected-stroke);
                background: var(--crm-selected-bg);
            }

            .card-header {
                display: flex;
                align-items: center;
                gap: 10px;
            }

            .card-type-icon {
                width: 36px;
                height: 36px;
                display: flex;
                align-items: center;
                justify-content: center;
                border-radius: var(--radius-lg);
                flex-shrink: 0;
            }

            .card-title {
                font-size: 15px;
                line-height: 20px;
                font-weight: 700;
                color: var(--text-primary);
                margin: 0;
                overflow: hidden;
                text-overflow: ellipsis;
                white-space: nowrap;
                flex: 1;
                min-width: 0;
            }

            .card-description {
                margin: 0;
                color: var(--text-secondary);
                font-size: 13px;
                line-height: 18px;
                overflow: hidden;
                text-overflow: ellipsis;
                display: -webkit-box;
                -webkit-line-clamp: 2;
                -webkit-box-orient: vertical;
            }

            .card-footer {
                display: flex;
                align-items: center;
                justify-content: space-between;
                gap: 8px;
                margin-top: auto;
            }

            .card-type-badge {
                display: inline-flex;
                align-items: center;
                gap: 4px;
                padding: 0 10px;
                min-height: 22px;
                font-size: 11px;
                border-radius: 12px;
                font-weight: 500;
                border: none;
                white-space: nowrap;
            }

            .card-meta {
                color: var(--text-tertiary);
                font-size: 11px;
            }

            .card-tags {
                display: flex;
                flex-wrap: nowrap;
                gap: 6px;
                overflow: hidden;
            }

            .card-tag {
                display: inline-flex;
                align-items: center;
                padding: 0 8px;
                min-height: 20px;
                font-size: 11px;
                border-radius: 10px;
                background: var(--crm-surface-tint);
                color: var(--text-secondary);
                white-space: nowrap;
            }

            .card-status-dot {
                width: 8px;
                height: 8px;
                border-radius: 50%;
                flex-shrink: 0;
            }

            .empty {
                border: 1px dashed var(--crm-stroke);
                border-radius: var(--radius-xl);
                min-height: 200px;
                display: flex;
                flex-direction: column;
                align-items: center;
                justify-content: center;
                color: var(--text-tertiary);
                gap: var(--space-2);
            }

            /* === MOBILE === */

            .mobile-tabs {
                display: none;
            }

            @media (max-width: 1279px) {
                .layout {
                    grid-template-columns: 1fr;
                }
            }

            @media (max-width: 767px) {
                :host {
                    overflow: hidden;
                }

                .mobile-tabs {
                    display: flex;
                    gap: var(--space-2);
                    padding: var(--space-2) var(--space-3);
                    flex-shrink: 0;
                }

                .mobile-tab {
                    flex: 1;
                    display: flex;
                    align-items: center;
                    justify-content: center;
                    gap: var(--space-1);
                    padding: var(--space-2);
                    border-radius: var(--radius-md);
                    background: transparent;
                    border: 1px solid var(--crm-stroke);
                    color: var(--text-secondary);
                    font-size: var(--text-sm);
                    font-weight: 500;
                    cursor: pointer;
                    white-space: nowrap;
                    transition: all var(--duration-fast);
                }

                .mobile-tab:hover {
                    background: var(--crm-surface);
                    color: var(--text-primary);
                }

                .mobile-tab.active {
                    background: var(--crm-selected-bg);
                    border-color: var(--crm-selected-stroke);
                    color: var(--text-primary);
                }

                .mobile-tab:disabled {
                    opacity: 0.4;
                    cursor: default;
                }

                .page-toolbar {
                    padding: var(--space-2) var(--space-3);
                    flex-shrink: 0;
                    max-width: 100%;
                    overflow: hidden;
                    box-sizing: border-box;
                }

                .section-label {
                    display: none;
                }

                .title {
                    display: none;
                }

                .top-row {
                    flex-direction: column;
                    gap: var(--space-2);
                    margin-bottom: var(--space-2);
                }

                .search-box {
                    display: none;
                }

                .cta-btn {
                    display: none;
                }

                .filters-row {
                    gap: 6px;
                    overflow-x: auto;
                    flex-wrap: nowrap;
                    scrollbar-width: none;
                    -webkit-overflow-scrolling: touch;
                    padding-bottom: 2px;
                }

                .filters-row::-webkit-scrollbar {
                    display: none;
                }

                .filter-chip {
                    padding: 5px 10px;
                    font-size: 12px;
                    flex-shrink: 0;
                }

                .layout {
                    grid-template-columns: 1fr;
                    flex: 1;
                    min-height: 0;
                    max-width: 100%;
                    overflow: hidden;
                }

                .list-panel,
                .detail-panel {
                    display: none;
                }

                .list-panel.mobile-active {
                    display: flex;
                    flex: 1;
                    min-height: 0;
                }

                .detail-panel.mobile-active {
                    display: flex;
                    flex: 1;
                    min-height: 0;
                    overflow-y: auto;
                    -webkit-overflow-scrolling: touch;
                }

                .cards-scroll {
                    padding: var(--space-2) var(--space-3);
                    max-width: 100%;
                    box-sizing: border-box;
                }

                .cards-grid {
                    grid-template-columns: 1fr;
                    gap: var(--space-2);
                    max-width: 100%;
                }

                .entity-card-item {
                    padding: 14px;
                    min-height: 0;
                    gap: 8px;
                    border-radius: 12px;
                    overflow: hidden;
                    max-width: 100%;
                    box-sizing: border-box;
                }

                .card-type-icon {
                    width: 32px;
                    height: 32px;
                }

                .card-title {
                    font-size: 14px;
                    line-height: 18px;
                }

                .card-description {
                    font-size: 12px;
                    line-height: 16px;
                    -webkit-line-clamp: 1;
                }

                .card-footer {
                    gap: 6px;
                }
            }
        `,
    ];

    constructor() {
        super();
        this._entities = [];
        this._entityTypes = [];
        this._currentEntityId = null;
        this._loading = false;
        this._query = '';
        this._selectedType = null;
        this._selectedStatus = null;
        this._currentNamespace = null;
        this._isMobile = false;
        this._mobileTab = 'list';
        this._debounceTimer = null;
        this._entitiesMergeFirstId = '';

        this._unsubscribe = CRMStore.subscribe((state) => {
            this._entities = state.entities.list;
            this._entityTypes = state.entities.entityTypes;
            this._currentEntityId = state.entities.currentEntityId;
            this._loading = state.entities.entitiesLoading;
            this._selectedType = state.entities.filters.entity_type;
            this._selectedStatus = state.entities.filters.status;
            this._isMobile = state.ui.isMobile;

            const prevNs = this._currentNamespace;
            this._currentNamespace = state.namespaces.current;
            const prevName = this._resolveNamespaceName(prevNs);
            const nextName = this._resolveNamespaceName(this._currentNamespace);
            if (prevName !== nextName && prevName !== null) {
                this._reloadData();
            }
        });
    }

    connectedCallback() {
        super.connectedCallback();
        this._reloadData();
    }

    disconnectedCallback() {
        super.disconnectedCallback();
        this._unsubscribe?.();
        if (this._debounceTimer) {
            clearTimeout(this._debounceTimer);
        }
    }

    _resolveNamespaceName(ns) {
        if (!ns) return null;
        if (typeof ns === 'string') return ns;
        if (typeof ns === 'object' && typeof ns.name === 'string') return ns.name;
        throw new Error('Invalid namespace value');
    }

    async _reloadData() {
        const crmApi = this.services.get('crmApi');
        const ns = this._resolveNamespaceName(CRMStore.state.namespaces.current);
        await CRMStore.loadEntityTypes(crmApi, ns || 'default');
        await CRMStore.loadEntities(crmApi);
    }

    _onSearchInput(event) {
        this._query = event.target.value;
        CRMStore.setEntityFilters({ search: this._query });
        if (this._debounceTimer) {
            clearTimeout(this._debounceTimer);
        }
        this._debounceTimer = setTimeout(() => {
            this._debounceTimer = null;
            this._applyFilters();
        }, 300);
    }

    _onTypeSelect(typeId) {
        const next = this._selectedType === typeId ? null : typeId;
        CRMStore.setEntityFilters({ entity_type: next, entity_subtype: null });
        this._applyFilters();
    }

    _onStatusSelect(status) {
        const next = this._selectedStatus === status ? null : status;
        CRMStore.setEntityFilters({ status: next });
        this._applyFilters();
    }

    _onClearFilters() {
        this._query = '';
        CRMStore.clearEntityFilters();
        this._applyFilters();
    }

    async _applyFilters() {
        const crmApi = this.services.get('crmApi');
        await CRMStore.loadEntities(crmApi);
    }

    _onSelectEntity(entityId) {
        CRMStore.setCurrentEntity(entityId);
        if (this._isMobile) {
            this._mobileTab = 'card';
        }
    }

    _openMergeModal(entityIdA, entityIdB) {
        const a = typeof entityIdA === 'string' ? entityIdA.trim() : '';
        const b = typeof entityIdB === 'string' ? entityIdB.trim() : '';
        if (!a || !b || a === b) {
            throw new Error('Merge requires two distinct entity IDs');
        }
        const modal = document.createElement('entity-merge-modal');
        modal.entityIdA = a;
        modal.entityIdB = b;
        document.body.appendChild(modal);
        modal.showModal();
        modal.addEventListener('close', () => modal.remove());
        modal.addEventListener('merged', () => {
            this._applyFilters();
        });
    }

    _onEntityListClick(entityId, event) {
        if (event.shiftKey) {
            if (!this._entitiesMergeFirstId) {
                this._entitiesMergeFirstId = entityId;
                this.info(this.i18n.t('entities.merge_first_marked'));
                return;
            }
            if (this._entitiesMergeFirstId === entityId) {
                this._entitiesMergeFirstId = '';
                return;
            }
            this._openMergeModal(this._entitiesMergeFirstId, entityId);
            this._entitiesMergeFirstId = '';
            return;
        }
        this._onSelectEntity(entityId);
    }

    _onMobileTab(tab) {
        this._mobileTab = tab;
    }

    _onCreateEntity() {
        const modal = document.createElement('entity-modal');
        document.body.appendChild(modal);
        modal.showModal();
        modal.addEventListener('close', () => modal.remove());
        modal.addEventListener('saved', () => this._applyFilters());
    }

    _getBaseTypes() {
        return this._entityTypes.filter((t) => !t.parent_type_id);
    }

    _getEntityTypeConfig(entity) {
        const typeId = entity.entity_subtype || entity.entity_type;
        const match = this._entityTypes.find((t) => t.type_id === typeId);
        if (match) {
            return {
                icon: this._resolveIconName(match.icon),
                color: match.color || 'var(--text-tertiary)',
                label: match.name || typeId,
            };
        }
        return { icon: 'file', color: 'var(--text-tertiary)', label: entity.entity_type };
    }

    _resolveIconName(iconName) {
        if (typeof iconName === 'string' && /^[a-z0-9-]+$/i.test(iconName)) {
            return iconName;
        }
        return 'file';
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

    _formatDate(dateString) {
        if (!dateString) return '';
        const d = new Date(dateString);
        return d.toLocaleDateString('ru-RU', { day: 'numeric', month: 'short' });
    }

    _getLimitedText(text, maxLength = 140) {
        if (typeof text !== 'string') return '';
        const normalized = text.trim();
        if (normalized.length <= maxLength) return normalized;
        return `${normalized.slice(0, maxLength).trimEnd()}...`;
    }

    _getStatusColor(status) {
        if (status === 'active') return '#4ade80';
        if (status === 'archived') return '#94a3b8';
        if (status === 'draft') return '#facc15';
        return '#94a3b8';
    }

    _hasActiveFilters() {
        return this._selectedType || this._selectedStatus || this._query.trim().length > 0;
    }

    render() {
        const baseTypes = this._getBaseTypes();
        const statuses = [
            { id: 'active', label: this.i18n.t('entities_page.status_active') },
            { id: 'archived', label: this.i18n.t('entities_page.status_archived') },
        ];

        const listActive = !this._isMobile || this._mobileTab === 'list';
        const cardActive = !this._isMobile || this._mobileTab === 'card';

        return html`
            ${this._isMobile ? html`
                <div class="mobile-tabs">
                    <button
                        class="mobile-tab ${this._mobileTab === 'list' ? 'active' : ''}"
                        type="button"
                        @click=${() => this._onMobileTab('list')}
                    >
                        <platform-icon name="list" size="14"></platform-icon>
                        ${this.i18n.t('entities_page.tab_list')}
                    </button>
                    <button
                        class="mobile-tab ${this._mobileTab === 'card' ? 'active' : ''}"
                        type="button"
                        @click=${() => this._onMobileTab('card')}
                        ?disabled=${!this._currentEntityId}
                    >
                        <platform-icon name="file" size="14"></platform-icon>
                        ${this.i18n.t('entities_page.tab_card')}
                    </button>
                </div>
            ` : ''}

            ${listActive ? html`
                <div class="page-toolbar">
                    ${!this._isMobile ? html`<div class="section-label">${this.i18n.t('entities.title')}</div>` : ''}
                    <div class="top-row">
                        <div class="title">
                            ${this.i18n.t('entities.title')}
                            <span class="entities-count">(${this._entities.length})</span>
                        </div>
                        <label class="search-box">
                            <platform-icon name="search" size="14"></platform-icon>
                            <input
                                class="search-input"
                                type="text"
                                placeholder=${this.i18n.t('search.placeholder')}
                                .value=${this._query}
                                @input=${this._onSearchInput}
                            />
                        </label>
                        <button class="cta-btn" type="button" @click=${this._onCreateEntity}>${this.i18n.t('create', {}, 'common')}</button>
                    </div>
                    <div class="filters-row">
                        ${baseTypes.map((type) => html`
                            <button
                                class="filter-chip ${this._selectedType === type.type_id ? 'active' : ''}"
                                type="button"
                                @click=${() => this._onTypeSelect(type.type_id)}
                            >
                                <platform-icon name="${this._resolveIconName(type.icon)}" size="14"></platform-icon>
                                ${type.name}
                            </button>
                        `)}
                        ${baseTypes.length > 0 ? html`<div class="filter-divider"></div>` : ''}
                        ${statuses.map((s) => html`
                            <button
                                class="filter-chip ${this._selectedStatus === s.id ? 'active' : ''}"
                                type="button"
                                @click=${() => this._onStatusSelect(s.id)}
                            >
                                ${s.label}
                            </button>
                        `)}
                        ${this._hasActiveFilters() ? html`
                            <button class="clear-filters-btn" type="button" @click=${this._onClearFilters}>
                                <platform-icon name="close" size="12"></platform-icon>
                                ${this.i18n.t('filters.clear')}
                            </button>
                        ` : ''}
                    </div>
                </div>
            ` : ''}

            <div class="layout">
                <section class="list-panel ${listActive ? 'mobile-active' : ''}">
                    <div class="cards-scroll">
                        ${this._loading ? html`
                            <div class="empty">${this.i18n.t('loading', {}, 'common')}</div>
                        ` : this._entities.length === 0 ? html`
                            <div class="empty">
                                <platform-icon name="database" size="40"></platform-icon>
                                <span>${this.i18n.t('entities.empty')}</span>
                                <span style="font-size: var(--text-sm)">${this.i18n.t('entities_page.empty_filters_hint')}</span>
                            </div>
                        ` : html`
                            <div class="cards-grid">
                                ${this._entities.map((entity) => this._renderEntityCard(entity))}
                            </div>
                        `}
                    </div>
                </section>

                <aside class="detail-panel ${cardActive ? 'mobile-active' : ''}">
                    <entity-card .entityId=${this._currentEntityId}></entity-card>
                </aside>
            </div>
        `;
    }

    _renderEntityCard(entity) {
        const typeConfig = this._getEntityTypeConfig(entity);
        const bgColor = this._hexToRgba(typeConfig.color, 0.15);
        const isActive = entity.entity_id === this._currentEntityId;
        const tags = Array.isArray(entity.tags) ? entity.tags.slice(0, 3) : [];

        return html`
            <article
                class="entity-card-item ${isActive ? 'active' : ''}"
                @click=${(e) => this._onEntityListClick(entity.entity_id, e)}
            >
                <div class="card-header">
                    <div class="card-type-icon" style="background: ${bgColor}; color: ${typeConfig.color};">
                        <platform-icon name="${typeConfig.icon}" size="18"></platform-icon>
                    </div>
                    <h3 class="card-title">${entity.name}</h3>
                    ${entity.status ? html`
                        <span class="card-status-dot" style="background: ${this._getStatusColor(entity.status)}" title="${entity.status}"></span>
                    ` : ''}
                </div>
                ${entity.description ? html`
                    <p class="card-description">${this._getLimitedText(entity.description)}</p>
                ` : ''}
                ${tags.length > 0 ? html`
                    <div class="card-tags">
                        ${tags.map((tag) => html`<span class="card-tag">${tag}</span>`)}
                    </div>
                ` : ''}
                <div class="card-footer">
                    <span class="card-type-badge" style="background: ${bgColor}; color: ${typeConfig.color};">${typeConfig.label}</span>
                    <span class="card-meta">${this._formatDate(entity.created_at)}</span>
                </div>
            </article>
        `;
    }
}

customElements.define('entities-page', EntitiesPage);
