/**
 * Entities Page - Страница сущностей в стиле daily-notes
 * Toolbar (title + search + filters + CTA) -> Cards Grid + Detail Panel
 */
import { html, css } from 'lit';
import { PlatformElement } from '@platform/lib/platform-element/index.js';
import { CRMStore } from '../store/crm.store.js';
import '../components/entity-card.js';
import '../modals/entity-modal.js';
import '@platform/lib/components/platform-icon.js';
import '@platform/lib/components/platform-date-picker.js';

export class EntitiesPage extends PlatformElement {
    static properties = {
        _entities: { state: true },
        _entityTypes: { state: true },
        _currentEntityId: { state: true },
        _currentEntity: { state: true },
        _loading: { state: true },
        _query: { state: true },
        _selectedType: { state: true },
        _selectedStatus: { state: true },
        _currentNamespace: { state: true },
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

            .section-label {
                color: var(--text-tertiary);
                font-size: var(--text-sm);
                margin-bottom: var(--space-1);
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
            }

            .page-header {
                display: flex;
                align-items: center;
                gap: var(--space-2);
                margin-bottom: var(--space-3);
            }

            .top-row {
                display: grid;
                grid-template-columns: auto minmax(260px, 1fr) auto;
                align-items: center;
                gap: var(--space-3);
                margin-bottom: var(--space-4);
            }

            .toolbar-actions {
                display: flex;
                align-items: center;
                margin-left: auto;
                gap: var(--space-2);
            }

            .search-box {
                display: flex;
                align-items: center;
                gap: var(--space-2);
                padding: 0 var(--space-3);
                border-radius: var(--radius-full);
                border: 1px solid var(--crm-stroke);
                background: var(--crm-surface-muted);
                min-height: 44px;
                width: 100%;
            }

            .search-input {
                width: 100%;
                border: none;
                background: transparent;
                color: var(--text-primary);
                font-size: var(--text-base);
                outline: none;
            }

            .cta-btn {
                min-height: 44px;
                border: none;
                border-radius: var(--radius-full);
                background: var(--crm-daily-notes-cta-bg);
                color: var(--text-inverse);
                font-size: var(--text-lg);
                font-weight: 500;
                padding: 0 var(--space-6);
                cursor: pointer;
                transition: background var(--duration-fast);
                white-space: nowrap;
            }

            .cta-btn:hover {
                background: var(--crm-daily-notes-cta-hover);
            }

            .filters-row {
                display: flex;
                flex-wrap: wrap;
                align-items: center;
                gap: var(--space-2);
                margin-bottom: var(--space-4);
            }

            .filter-chip {
                display: inline-flex;
                align-items: center;
                gap: var(--space-1);
                padding: var(--space-2) var(--space-3);
                border-radius: var(--radius-full);
                border: 1px solid var(--crm-stroke);
                background: var(--crm-surface-muted);
                color: var(--text-secondary);
                font-size: var(--text-sm);
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
                height: 24px;
                background: var(--crm-stroke);
                flex-shrink: 0;
            }

            .clear-filters-btn {
                display: inline-flex;
                align-items: center;
                gap: var(--space-1);
                padding: var(--space-1) var(--space-2);
                border: none;
                border-radius: var(--radius-md);
                background: transparent;
                color: var(--text-tertiary);
                font-size: var(--text-xs);
                cursor: pointer;
            }

            .clear-filters-btn:hover {
                color: var(--text-primary);
            }

            .layout {
                display: grid;
                grid-template-columns: 1fr 380px;
                gap: var(--space-4);
                width: 100%;
                flex: 1;
                min-height: 0;
                overflow: hidden;
            }

            .main-column {
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
                padding-right: var(--space-2);
            }

            .cards-grid {
                display: grid;
                grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
                gap: var(--space-4);
                align-content: start;
            }

            .entity-card-item {
                border: 1px solid var(--crm-stroke);
                background: var(--crm-surface);
                border-radius: 16px;
                padding: 20px;
                display: flex;
                flex-direction: column;
                gap: 12px;
                min-height: 160px;
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
                gap: 12px;
            }

            .card-type-icon {
                width: 40px;
                height: 40px;
                display: flex;
                align-items: center;
                justify-content: center;
                border-radius: var(--radius-lg);
                flex-shrink: 0;
            }

            .card-title {
                font-size: 18px;
                line-height: 22px;
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
                font-size: 14px;
                line-height: 20px;
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
                gap: 12px;
                margin-top: auto;
            }

            .card-type-badge {
                display: inline-flex;
                align-items: center;
                gap: 4px;
                padding: 0 10px;
                min-height: 24px;
                font-size: 12px;
                border-radius: 14px;
                font-weight: 500;
                border: none;
                white-space: nowrap;
            }

            .card-meta {
                color: var(--text-tertiary);
                font-size: 12px;
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
                min-height: 22px;
                font-size: 11px;
                border-radius: 11px;
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

            .detail-panel {
                display: flex;
                flex-direction: column;
                min-height: 0;
                overflow: hidden;
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

            .entities-count {
                color: var(--text-tertiary);
                font-size: var(--text-sm);
                font-weight: 400;
            }

            @media (max-width: 1279px) {
                .layout {
                    grid-template-columns: 1fr;
                }
                .detail-panel {
                    min-height: 300px;
                }
                .top-row {
                    grid-template-columns: 1fr;
                    align-items: stretch;
                }
                .toolbar-actions {
                    margin-left: 0;
                    justify-content: flex-start;
                }
                .title {
                    font-size: 32px;
                }
            }
        `,
    ];

    constructor() {
        super();
        this._entities = [];
        this._entityTypes = [];
        this._currentEntityId = null;
        this._currentEntity = null;
        this._loading = false;
        this._query = '';
        this._selectedType = null;
        this._selectedStatus = null;
        this._currentNamespace = null;
        this._debounceTimer = null;

        this._unsubscribe = CRMStore.subscribe((state) => {
            this._entities = state.entities.list;
            this._entityTypes = state.entities.entityTypes;
            this._currentEntityId = state.entities.currentEntityId;
            this._currentEntity = state.entities.currentEntity;
            this._loading = state.entities.entitiesLoading;
            this._selectedType = state.entities.filters.entity_type;
            this._selectedStatus = state.entities.filters.status;

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
            { id: 'active', label: 'Активные' },
            { id: 'archived', label: 'Архив' },
        ];

        return html`
            <div class="section-label">Сущности</div>
            <div class="top-row">
                <div class="title">
                    Сущности
                    <span class="entities-count">(${this._entities.length})</span>
                </div>
                <label class="search-box">
                    <platform-icon name="search" size="16"></platform-icon>
                    <input
                        class="search-input"
                        type="text"
                        placeholder="Поиск по имени или описанию"
                        .value=${this._query}
                        @input=${this._onSearchInput}
                    />
                </label>
                <div class="toolbar-actions">
                    <button class="cta-btn" type="button" @click=${this._onCreateEntity}>
                        Создать сущность
                    </button>
                </div>
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
                        Сбросить
                    </button>
                ` : ''}
            </div>

            <div class="layout">
                <section class="main-column">
                    <div class="cards-scroll">
                        ${this._loading ? html`
                            <div class="empty">Загрузка...</div>
                        ` : this._entities.length === 0 ? html`
                            <div class="empty">
                                <platform-icon name="database" size="48"></platform-icon>
                                <span>Нет сущностей</span>
                                <span style="font-size: var(--text-sm)">Создайте первую или измените фильтры</span>
                            </div>
                        ` : html`
                            <div class="cards-grid">
                                ${this._entities.map((entity) => this._renderEntityCard(entity))}
                            </div>
                        `}
                    </div>
                </section>

                <aside class="detail-panel">
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
                @click=${() => this._onSelectEntity(entity.entity_id)}
            >
                <div class="card-header">
                    <div
                        class="card-type-icon"
                        style="background: ${bgColor}; color: ${typeConfig.color};"
                    >
                        <platform-icon name="${typeConfig.icon}" size="20"></platform-icon>
                    </div>
                    <h3 class="card-title">${entity.name}</h3>
                    ${entity.status ? html`
                        <span
                            class="card-status-dot"
                            style="background: ${this._getStatusColor(entity.status)}"
                            title="${entity.status}"
                        ></span>
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
                    <span
                        class="card-type-badge"
                        style="background: ${bgColor}; color: ${typeConfig.color};"
                    >${typeConfig.label}</span>
                    <span class="card-meta">${this._formatDate(entity.created_at)}</span>
                </div>
            </article>
        `;
    }
}

customElements.define('entities-page', EntitiesPage);
