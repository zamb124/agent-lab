/**
 * Entities Page - Страница сущностей
 * Desktop: Toolbar + Cards Grid + Detail Panel (grid 1fr 380px)
 * Mobile: Menu btn + Toolbar + Tabs (Список / Карточка)
 */
import { html, css } from 'lit';
import { PlatformElement } from '@platform/lib/platform-element/index.js';
import { platformConfirm } from '@platform/lib/components/platform-confirm-modal.js';
import { CRMStore } from '../store/crm.store.js';
import '../components/entity-card.js';
import '../modals/entity-modal.js';
import '../modals/entity-merge-modal.js';
import '@platform/lib/components/platform-icon.js';

const MERGE_DRAG_MIME = 'application/x-crm-entity-merge';

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
        _mergeDragSourceId: { state: true },
        _mergeDropHoverId: { state: true },
        _selectedIds: { state: true },
        _bulkOperating: { state: true },
        _showExportMenu: { state: true },
        _showBulkStatusMenu: { state: true },
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

            .loading-more {
                text-align: center;
                padding: var(--space-3);
                color: var(--text-secondary);
                font-size: var(--text-sm);
            }

            .scroll-sentinel {
                height: 1px;
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

            .entity-card-item.merge-drag-source {
                opacity: 0.55;
            }

            .entity-card-item.merge-drop-hover {
                border-color: var(--accent);
                box-shadow: 0 0 0 2px rgba(99, 102, 241, 0.35);
            }

            .merge-dnd-hint {
                margin: 0 0 var(--space-2) 0;
                font-size: var(--text-xs);
                color: var(--text-tertiary);
                line-height: 1.4;
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

            .card-footer-end {
                display: flex;
                align-items: center;
                justify-content: flex-end;
                gap: 10px;
                flex-shrink: 0;
                margin-left: auto;
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

            .export-dropdown {
                position: relative;
            }
            .btn-icon {
                display: flex;
                align-items: center;
                justify-content: center;
                width: 32px;
                height: 32px;
                border: 1px solid var(--glass-border-subtle);
                border-radius: var(--radius-md);
                background: transparent;
                color: var(--text-secondary);
                cursor: pointer;
            }
            .btn-icon:hover { background: var(--glass-bg-subtle); }
            .export-menu {
                position: absolute;
                top: 100%;
                right: 0;
                z-index: 10;
                display: flex;
                flex-direction: column;
                background: var(--bg-elevated);
                border: 1px solid var(--glass-border-subtle);
                border-radius: var(--radius-md);
                overflow: hidden;
                margin-top: 4px;
                min-width: 80px;
                box-shadow: var(--glass-shadow-subtle);
            }
            .export-menu button {
                padding: 8px 12px;
                border: none;
                background: transparent;
                color: var(--text-primary);
                font-size: 13px;
                cursor: pointer;
                text-align: left;
            }
            .export-menu button:hover { background: var(--glass-bg-subtle); }

            .entity-card-item.selected {
                border-color: var(--accent, #3b82f6);
                background: rgba(59, 130, 246, 0.06);
                box-shadow: 0 0 0 1px var(--accent, #3b82f6);
            }

            .bulk-actions {
                display: inline-flex;
                align-items: center;
                gap: 6px;
                margin-left: auto;
            }

            .bulk-badge {
                display: inline-flex;
                align-items: center;
                justify-content: center;
                min-width: 22px;
                height: 22px;
                padding: 0 6px;
                border-radius: var(--radius-full);
                background: var(--accent, #3b82f6);
                color: #fff;
                font-size: 11px;
                font-weight: 700;
            }

            .bulk-action-btn {
                width: 32px;
                height: 32px;
                border-radius: var(--radius-full);
                border: none;
                display: inline-flex;
                align-items: center;
                justify-content: center;
                cursor: pointer;
                transition: transform 0.15s, box-shadow 0.15s, opacity 0.15s;
            }

            .bulk-action-btn:hover {
                transform: scale(1.1);
                box-shadow: 0 2px 8px rgba(0,0,0,0.18);
            }

            .bulk-action-btn:disabled {
                opacity: 0.5;
                cursor: not-allowed;
                transform: none;
                box-shadow: none;
            }

            .bulk-action-btn--status {
                background: var(--accent, #3b82f6);
                color: #fff;
            }

            .bulk-action-btn--delete {
                background: var(--error, #f43f5e);
                color: #fff;
            }

            .bulk-action-btn--clear {
                background: var(--crm-surface-muted);
                color: var(--text-secondary);
                border: 1px solid var(--crm-stroke);
            }

            .bulk-status-wrapper {
                position: relative;
                display: inline-flex;
            }

            .bulk-status-menu {
                position: absolute;
                top: 100%;
                right: 0;
                z-index: 20;
                min-width: 140px;
                margin-top: 6px;
                padding: 4px 0;
                background: var(--bg-elevated);
                border: 1px solid var(--glass-border-subtle);
                border-radius: var(--radius-lg);
                box-shadow: var(--glass-shadow-medium);
            }

            .bulk-status-item {
                display: block;
                width: 100%;
                padding: 8px 14px;
                font-size: 13px;
                text-align: left;
                color: var(--text-primary);
                background: none;
                border: none;
                cursor: pointer;
                transition: background 0.1s;
            }

            .bulk-status-item:hover {
                background: var(--glass-bg-subtle);
            }

            .card-score {
                display: flex;
                align-items: center;
                gap: 6px;
                height: 16px;
                position: relative;
                background: var(--glass-bg-subtle, rgba(255,255,255,0.06));
                border-radius: 8px;
                overflow: hidden;
                margin-bottom: 4px;
            }
            .score-bar {
                position: absolute;
                left: 0;
                top: 0;
                height: 100%;
                background: linear-gradient(90deg, #3b82f6, #8b5cf6);
                opacity: 0.25;
                border-radius: 8px;
            }
            .score-label {
                position: relative;
                z-index: 1;
                font-size: 10px;
                font-weight: 600;
                color: var(--text-secondary);
                padding-left: 6px;
            }
            .match-type-badge {
                position: relative;
                z-index: 1;
                font-size: 9px;
                text-transform: uppercase;
                color: var(--text-tertiary);
                margin-left: auto;
                padding-right: 6px;
            }

            .access-badge {
                display: inline-flex;
                align-items: center;
                justify-content: center;
                width: 22px;
                height: 22px;
                border-radius: 50%;
                flex-shrink: 0;
            }
            .access-badge--shared {
                background: rgba(59, 130, 246, 0.15);
                color: #3b82f6;
            }
            .access-badge--public {
                background: rgba(34, 197, 94, 0.15);
                color: #22c55e;
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

            .entity-card-drag-handle {
                flex-shrink: 0;
                width: 32px;
                height: 32px;
                margin: -4px -4px 0 0;
                padding: 0;
                box-sizing: border-box;
                display: inline-flex;
                align-items: center;
                justify-content: center;
                border-radius: var(--radius-md);
                background: transparent;
                color: var(--text-tertiary);
                cursor: grab;
                touch-action: none;
                user-select: none;
                -webkit-user-select: none;
                transition: color var(--duration-fast), background var(--duration-fast);
            }

            .entity-card-drag-handle * {
                pointer-events: none;
            }

            .entity-card-drag-handle:hover {
                color: var(--text-secondary);
                background: var(--crm-surface-tint);
            }

            .entity-card-drag-handle:active {
                cursor: grabbing;
            }

            .card-header-end {
                display: flex;
                align-items: center;
                gap: 8px;
                flex-shrink: 0;
                margin-left: auto;
            }

            .card-delete-btn {
                width: 32px;
                height: 32px;
                display: inline-flex;
                align-items: center;
                justify-content: center;
                flex-shrink: 0;
                padding: 0;
                border-radius: var(--radius-md);
                border: 1px solid rgba(244, 63, 94, 0.35);
                background: var(--crm-surface-muted);
                color: var(--error, #f43f5e);
                cursor: pointer;
                transition: background var(--duration-fast), border-color var(--duration-fast);
            }

            .card-delete-btn:hover {
                background: rgba(244, 63, 94, 0.12);
                border-color: var(--error, #f43f5e);
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

            .empty.empty-import {
                gap: var(--space-4);
                padding: var(--space-6) var(--space-4);
                max-width: 440px;
                margin: 0 auto;
                box-sizing: border-box;
            }

            .empty-import-text {
                color: var(--text-secondary);
                font-size: var(--text-base);
                line-height: 1.5;
                margin: 0;
                text-align: center;
            }

            .import-wizard-btn {
                display: inline-flex;
                align-items: center;
                justify-content: center;
                gap: var(--space-2);
                min-height: 40px;
                border: none;
                border-radius: var(--radius-full);
                background: var(--crm-daily-notes-cta-bg);
                color: var(--text-inverse);
                font-size: var(--text-sm);
                font-weight: 500;
                padding: 0 var(--space-5);
                cursor: pointer;
                font-family: inherit;
                transition: background var(--duration-fast);
            }

            .import-wizard-btn:hover {
                background: var(--crm-daily-notes-cta-hover);
            }

            .import-wizard-btn:focus-visible {
                outline: 2px solid var(--accent-tertiary);
                outline-offset: 2px;
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
        this._loadingMore = false;
        this._hasMore = false;
        this._query = '';
        this._selectedType = null;
        this._selectedStatus = null;
        this._currentNamespace = null;
        this._isMobile = false;
        this._mobileTab = 'list';
        this._debounceTimer = null;
        this._entitiesMergeFirstId = '';
        this._mergeDragSourceId = '';
        this._mergeDropHoverId = '';
        this._selectedIds = new Set();
        this._bulkOperating = false;
        this._showExportMenu = false;
        this._showBulkStatusMenu = false;
        this._goToImportWizard = this._goToImportWizard.bind(this);
        this._scrollObserver = null;

        this._unsubscribe = CRMStore.subscribe((state) => {
            this._entities = state.entities.list;
            this._entityTypes = state.entities.entityTypes;
            this._currentEntityId = state.entities.currentEntityId;
            this._loading = state.entities.entitiesLoading;
            this._loadingMore = state.entities.loadingMore;
            this._hasMore = state.entities.hasMore;
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
        this._disconnectScrollObserver();
        if (this._debounceTimer) {
            clearTimeout(this._debounceTimer);
        }
    }

    updated(changedProperties) {
        super.updated(changedProperties);
        this._setupScrollObserver();
    }

    _setupScrollObserver() {
        this._disconnectScrollObserver();
        const sentinel = this.renderRoot?.querySelector('.scroll-sentinel');
        if (!sentinel) return;

        const scrollContainer = this.renderRoot?.querySelector('.cards-scroll');
        this._scrollObserver = new IntersectionObserver(
            (entries) => {
                const entry = entries[0];
                if (entry.isIntersecting && this._hasMore && !this._loadingMore && !this._loading) {
                    this._onLoadMore();
                }
            },
            { root: scrollContainer, rootMargin: '200px' },
        );
        this._scrollObserver.observe(sentinel);
    }

    _disconnectScrollObserver() {
        if (this._scrollObserver) {
            this._scrollObserver.disconnect();
            this._scrollObserver = null;
        }
    }

    async _onLoadMore() {
        const crmApi = this.services.get('crmApi');
        await CRMStore.loadMoreEntities(crmApi);
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

    _goToImportWizard() {
        const c = CRMStore.state.namespaces.current;
        const name = typeof c === 'string' && c.trim()
            ? c.trim()
            : (c && typeof c === 'object' && typeof c.name === 'string' && c.name.trim() ? c.name.trim() : 'default');
        CRMStore.setSettingsNamespaceSelection(name);
        CRMStore.setCurrentView('namespace_imports');
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
        this._entitiesMergeFirstId = '';
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

    _clearMergeDnDVisual() {
        this._mergeDragSourceId = '';
        this._mergeDropHoverId = '';
    }

    _onMergeCardDragStart(event, entityId) {
        if (this._isMobile) {
            return;
        }
        const id = typeof entityId === 'string' ? entityId.trim() : '';
        if (!id) {
            event.preventDefault();
            return;
        }
        this._mergeDragSourceId = id;
        this._mergeDropHoverId = '';
        event.dataTransfer.setData(MERGE_DRAG_MIME, id);
        event.dataTransfer.setData('text/plain', id);
        event.dataTransfer.effectAllowed = 'copyMove';
    }

    _onMergeCardDragEnd() {
        this._clearMergeDnDVisual();
    }

    _onMergeCardDragOver(event, targetEntityId) {
        if (this._isMobile) {
            return;
        }
        const sourceId = this._mergeDragSourceId;
        const tid = typeof targetEntityId === 'string' ? targetEntityId.trim() : '';
        if (!sourceId || !tid || sourceId === tid) {
            return;
        }
        event.preventDefault();
        event.dataTransfer.dropEffect = 'move';
        if (this._mergeDropHoverId !== tid) {
            this._mergeDropHoverId = tid;
        }
    }

    _onMergeCardDragLeave(event, targetEntityId) {
        if (this._isMobile) {
            return;
        }
        const tid = typeof targetEntityId === 'string' ? targetEntityId.trim() : '';
        const related = event.relatedTarget;
        if (related instanceof Node && event.currentTarget.contains(related)) {
            return;
        }
        if (this._mergeDropHoverId === tid) {
            this._mergeDropHoverId = '';
        }
    }

    _onMergeCardDrop(event, targetEntityId) {
        if (this._isMobile) {
            return;
        }
        event.preventDefault();
        const tid = typeof targetEntityId === 'string' ? targetEntityId.trim() : '';
        let sid = '';
        try {
            sid = event.dataTransfer.getData(MERGE_DRAG_MIME).trim();
        } catch {
            sid = '';
        }
        if (!sid) {
            sid = event.dataTransfer.getData('text/plain').trim();
        }
        this._clearMergeDnDVisual();
        if (!sid || !tid || sid === tid) {
            return;
        }
        this._openMergeModal(sid, tid);
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
        if (event.ctrlKey || event.metaKey) {
            this._onToggleSelect(entityId, !this._selectedIds.has(entityId));
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
        return { icon: 'folder', color: 'var(--text-tertiary)', label: entity.entity_type };
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

    _hasActiveFilters() {
        return this._selectedType || this._selectedStatus || this._query.trim().length > 0;
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

    _isEntityOwner(entity) {
        const uid = this._platformAuthUserId(this.auth?.user);
        if (!uid || !entity || typeof entity.user_id !== 'string' || entity.user_id.trim().length === 0) {
            return false;
        }
        return entity.user_id.trim() === uid;
    }

    async _confirmDeleteEntity(entity) {
        if (!entity?.entity_id) {
            return;
        }
        const displayName =
            typeof entity.name === 'string' && entity.name.trim().length > 0
                ? entity.name.trim()
                : entity.entity_id;
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
        try {
            await CRMStore.deleteEntity(this.crmApi, entity.entity_id);
        } catch {
            this.error(this.i18n.t('entities_page.delete_entity_failed'));
        }
    }

    _onDeleteEntityFromList(event, entity) {
        event.stopPropagation();
        event.preventDefault();
        this._confirmDeleteEntity(entity);
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
                        <platform-icon name="folder" size="14"></platform-icon>
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
                        <div class="export-dropdown">
                            <button class="btn-icon" type="button" title="Export" @click=${this._toggleExportMenu}>
                                <platform-icon name="save" size="16"></platform-icon>
                            </button>
                            ${this._showExportMenu ? html`
                                <div class="export-menu">
                                    <button @click=${() => this._onExport('csv')}>CSV</button>
                                    <button @click=${() => this._onExport('json')}>JSON</button>
                                </div>
                            ` : ''}
                        </div>
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

                        ${this._selectedIds.size > 0 ? html`
                            <div class="filter-divider"></div>
                            <div class="bulk-actions">
                                <span class="bulk-badge">${this._selectedIds.size}</span>
                                <div class="bulk-status-wrapper">
                                    <button
                                        class="bulk-action-btn bulk-action-btn--status"
                                        type="button"
                                        ?disabled=${this._bulkOperating}
                                        title=${this.i18n.t('entities.bulk.change_status')}
                                        @click=${() => { this._showBulkStatusMenu = !this._showBulkStatusMenu; }}
                                    >
                                        <platform-icon name="edit" size="16"></platform-icon>
                                    </button>
                                    ${this._showBulkStatusMenu ? html`
                                        <div class="bulk-status-menu">
                                            ${['pending', 'approved', 'rejected'].map(status => html`
                                                <button class="bulk-status-item"
                                                    @click=${() => this._onBulkUpdateStatus(status)}>
                                                    ${this.i18n.t(`entities.status.${status}`)}
                                                </button>
                                            `)}
                                        </div>
                                    ` : ''}
                                </div>
                                <button
                                    class="bulk-action-btn bulk-action-btn--delete"
                                    type="button"
                                    ?disabled=${this._bulkOperating}
                                    title=${this.i18n.t('entities.bulk.delete')}
                                    @click=${this._onBulkDelete}
                                >
                                    <platform-icon name="trash" size="16"></platform-icon>
                                </button>
                                <button
                                    class="bulk-action-btn bulk-action-btn--clear"
                                    type="button"
                                    title=${this.i18n.t('entities.bulk.cancel')}
                                    @click=${this._onBulkClear}
                                >
                                    <platform-icon name="close" size="16"></platform-icon>
                                </button>
                            </div>
                        ` : ''}
                    </div>
                    ${this._entities.length >= 2 && !this._loading
                        ? html`<p class="merge-dnd-hint">${this.i18n.t('entities_page.merge_dnd_hint')}</p>`
                        : ''}
                </div>
            ` : ''}

            <div class="layout">
                <section class="list-panel ${listActive ? 'mobile-active' : ''}">
                    <div class="cards-scroll">
                        ${this._loading ? html`
                            <div class="empty">${this.i18n.t('loading', {}, 'common')}</div>
                        ` : this._entities.length === 0 ? html`
                            <div class="empty ${!this._hasActiveFilters() ? 'empty-import' : ''}">
                                ${!this._hasActiveFilters() ? html`
                                    <p class="empty-import-text">${this.i18n.t('import_wizard_cta.empty_entities_hint')}</p>
                                    <button class="import-wizard-btn" type="button" @click=${this._goToImportWizard}>
                                        <platform-icon name="import" size="18"></platform-icon>
                                        ${this.i18n.t('import_wizard_cta.open_wizard')}
                                    </button>
                                ` : html`
                                    <platform-icon name="database" size="40"></platform-icon>
                                    <span>${this.i18n.t('entities.empty')}</span>
                                    <span style="font-size: var(--text-sm)">${this.i18n.t('entities_page.empty_filters_hint')}</span>
                                `}
                            </div>
                        ` : html`
                            <div class="cards-grid">
                                ${this._entities.map((entity) => this._renderEntityCard(entity))}
                            </div>
                            ${this._loadingMore ? html`
                                <div class="loading-more">${this.i18n.t('loading', {}, 'common')}</div>
                            ` : ''}
                            <div class="scroll-sentinel"></div>
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
        const showDelete = this._isEntityOwner(entity);
        const eid = entity.entity_id;
        const mergeSource = this._mergeDragSourceId === eid;
        const mergeHover =
            !this._isMobile &&
            this._mergeDropHoverId === eid &&
            this._mergeDragSourceId &&
            this._mergeDragSourceId !== eid;

        const showHeaderEnd = !this._isMobile;

        const isSelected = this._selectedIds.has(eid);

        return html`
            <article
                class="entity-card-item ${isActive ? 'active' : ''} ${isSelected ? 'selected' : ''} ${mergeSource ? 'merge-drag-source' : ''} ${mergeHover ? 'merge-drop-hover' : ''}"
                @dragover=${(e) => this._onMergeCardDragOver(e, eid)}
                @dragleave=${(e) => this._onMergeCardDragLeave(e, eid)}
                @drop=${(e) => this._onMergeCardDrop(e, eid)}
                @click=${(e) => this._onEntityListClick(entity.entity_id, e)}
            >
                <div class="card-header">
                    <div class="card-type-icon" style="background: ${bgColor}; color: ${typeConfig.color};">
                        <platform-icon name="${typeConfig.icon}" size="18"></platform-icon>
                    </div>
                    <h3 class="card-title">${entity.name}</h3>
                    ${showHeaderEnd
                        ? html`
                            <div class="card-header-end">
                                <div
                                    class="entity-card-drag-handle"
                                    draggable="true"
                                    title=${this.i18n.t('entities_page.drag_merge_handle')}
                                    role="button"
                                    tabindex="0"
                                    aria-label=${this.i18n.t('entities_page.drag_merge_handle')}
                                    @dragstart=${(e) => this._onMergeCardDragStart(e, eid)}
                                    @dragend=${this._onMergeCardDragEnd}
                                    @click=${(e) => e.stopPropagation()}
                                >
                                    <platform-icon name="drag-handle" size="18" ?filled=${true}></platform-icon>
                                </div>
                            </div>
                        `
                        : ''}
                </div>
                ${entity.score != null ? html`
                    <div class="card-score">
                        <div class="score-bar" style="width: ${Math.round(entity.score * 100)}%"></div>
                        <span class="score-label">${(entity.score * 100).toFixed(0)}%</span>
                        ${entity.match_type ? html`<span class="match-type-badge">${entity.match_type}</span>` : ''}
                    </div>
                ` : ''}
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
                    ${this._renderAccessBadge(entity.access_level)}
                    <div class="card-footer-end">
                        <span class="card-meta">${this._formatDate(entity.created_at)}</span>
                        ${showDelete
                            ? html`
                                <button
                                    type="button"
                                    class="card-delete-btn"
                                    draggable="false"
                                    title=${this.i18n.t('entities_page.delete_entity_tooltip')}
                                    aria-label=${this.i18n.t('entities_page.delete_entity_tooltip')}
                                    @click=${(e) => this._onDeleteEntityFromList(e, entity)}
                                >
                                    <platform-icon name="trash" size="16"></platform-icon>
                                </button>
                            `
                            : ''}
                    </div>
                </div>
            </article>
        `;
    }

    _toggleExportMenu() {
        this._showExportMenu = !this._showExportMenu;
    }

    async _onExport(format) {
        this._showExportMenu = false;
        try {
            const crmApi = this.services.get('crmApi');
            const blob = await crmApi.exportEntities({ format });
            const url = URL.createObjectURL(blob);
            const a = document.createElement('a');
            a.href = url;
            a.download = `entities.${format}`;
            a.click();
            URL.revokeObjectURL(url);
        } catch (err) {
            this.error(err instanceof Error ? err.message : String(err));
        }
    }

    _onToggleSelect(entityId, checked) {
        const ids = new Set(this._selectedIds);
        if (checked) {
            ids.add(entityId);
        } else {
            ids.delete(entityId);
        }
        this._selectedIds = ids;
    }

    _onBulkClear() {
        this._selectedIds = new Set();
    }

    async _onBulkDelete() {
        if (this._selectedIds.size === 0) return;
        this._bulkOperating = true;
        try {
            const crmApi = this.services.get('crmApi');
            const result = await crmApi.bulkDeleteEntities([...this._selectedIds]);
            if (result.errors && result.errors.length > 0) {
                this.error(`${result.errors.length} entities failed`);
            }
            this._selectedIds = new Set();
            await CRMStore.loadEntities(crmApi);
        } catch (err) {
            this.error(err instanceof Error ? err.message : String(err));
        } finally {
            this._bulkOperating = false;
        }
    }

    async _onBulkUpdateStatus(status) {
        this._showBulkStatusMenu = false;
        if (this._selectedIds.size === 0) return;
        this._bulkOperating = true;
        try {
            const crmApi = this.services.get('crmApi');
            const items = [...this._selectedIds].map((id) => ({
                entity_id: id,
                updates: { status },
            }));
            const result = await crmApi.bulkUpdateEntities(items);
            if (result.errors && result.errors.length > 0) {
                this.error(`${result.errors.length} entities failed`);
            }
            this._selectedIds = new Set();
            await CRMStore.loadEntities(crmApi);
        } catch (err) {
            this.error(err instanceof Error ? err.message : String(err));
        } finally {
            this._bulkOperating = false;
        }
    }

    _renderAccessBadge(accessLevel) {
        if (!accessLevel || accessLevel === 'owner') return '';
        const config = {
            shared: { icon: 'share', cls: 'access-badge--shared' },
            public: { icon: 'globe', cls: 'access-badge--public' },
        };
        const badge = config[accessLevel];
        if (!badge) return '';
        return html`
            <span class="access-badge ${badge.cls}" title="${accessLevel}">
                <platform-icon name="${badge.icon}" size="12"></platform-icon>
            </span>
        `;
    }
}

customElements.define('entities-page', EntitiesPage);
