/**
 * EntitiesPage — основной экран сущностей CRM.
 *
 * Layout: на десктопе — `cards-grid` слева + `entity-card` справа (380px),
 * на мобильном — табы «Список / Карточка». Все доменные данные — через
 * фабрики платформы:
 *
 *   - useCursorList('crm/entities_list')   — лента сущностей с фильтрами
 *     namespace / type / subtype / status / tags / date range / search.
 *   - useResource('crm/entity_types')      — типы для чипсов и иконок.
 *   - useOp('crm/entity_aggregate')        — счётчики (типы / статусы /
 *     месяцы) для пустых состояний и подсказок.
 *   - useOp('crm/entity_bulk_delete')      — массовое удаление.
 *   - useOp('crm/entity_bulk_update')      — массовая смена статуса.
 *
 * UI-команды (модалки, тосты, навигация) — только через helpers `PlatformPage`
 * (`openModal`, `toast`, `navigate`). Никаких прямых dispatch UI/ROUTER/AUTH,
 * httpRequest, fetch, services.* / store / features.
 *
 * Live-обновления:
 *   - подписка на `CoreEvents.UI_NAMESPACE_CHANGED` — перезагрузка ленты и
 *     счётчиков.
 *   - подписка на `crm/entity/updated` (бэкенд публикует
 *     `publish_ui_event_to_user`) — рефреш текущей выдачи.
 */

import { html, css, nothing } from 'lit';
import { PlatformPage } from '@platform/lib/base/PlatformPage.js';
import { CoreEvents } from '@platform/lib/events/contract.js';
import { platformConfirm } from '@platform/lib/components/platform-confirm-modal.js';
import '@platform/lib/components/platform-icon.js';
import '@platform/lib/components/platform-date-picker.js';
import '@platform/lib/components/platform-breadcrumbs.js';
import '@platform/lib/components/glass-spinner.js';
import '../components/entity-card.js';

const MERGE_DRAG_MIME = 'application/x-crm-entity-merge';
const SEARCH_MODES = ['text', 'semantic', 'hybrid'];
const STATUS_FILTERS = ['active', 'archived'];
const BULK_STATUSES = ['pending', 'approved', 'rejected'];

export class CRMEntitiesPage extends PlatformPage {
    static i18nNamespace = 'crm';

    static properties = {
        _query: { state: true },
        _searchMode: { state: true },
        _selectedType: { state: true },
        _selectedSubtype: { state: true },
        _selectedStatus: { state: true },
        _filterTags: { state: true },
        _tagInput: { state: true },
        _dateFrom: { state: true },
        _dateTo: { state: true },
        _showFiltersPanel: { state: true },
        _isMobile: { state: true },
        _mobileTab: { state: true },
        _currentEntityId: { state: true },
        _selectedIds: { state: true },
        _showBulkStatusMenu: { state: true },
        _mergeDragSourceId: { state: true },
        _mergeDropHoverId: { state: true },
    };

    static styles = [
        PlatformPage.styles,
        css`
            :host {
                display: flex;
                flex-direction: column;
                width: 100%;
                height: 100%;
                min-height: 0;
                overflow: hidden;
            }

            .page-toolbar {
                flex-shrink: 0;
                padding-bottom: var(--space-1);
            }

            .breadcrumbs-wrap {
                flex-shrink: 0;
                margin-bottom: var(--space-2);
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
                margin-bottom: var(--space-2);
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
            .cta-btn:hover { background: var(--crm-daily-notes-cta-hover); }

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
            .filter-chip:hover { background: var(--crm-surface); color: var(--text-primary); }
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
            .clear-filters-btn:hover { color: var(--text-primary); }

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
            .btn-icon.active {
                background: var(--crm-selected-bg);
                border-color: var(--crm-selected-stroke);
                color: var(--crm-selected-text);
            }

            .filters-collapsible {
                overflow: hidden;
                max-height: 0;
                opacity: 0;
                transition: max-height 0.3s ease, opacity 0.2s ease, padding 0.3s ease;
                padding: 0 var(--space-4);
            }
            .filters-collapsible.open {
                max-height: 500px;
                opacity: 1;
                padding: var(--space-3) var(--space-4);
            }

            .expanded-filters {
                display: flex;
                flex-wrap: wrap;
                gap: var(--space-4);
                align-items: flex-start;
            }

            .expanded-filter-group {
                display: flex;
                flex-direction: column;
                gap: var(--space-1);
                min-width: 0;
            }

            .expanded-filter-label {
                font-size: var(--text-xs);
                color: var(--text-tertiary);
                font-weight: 500;
                text-transform: uppercase;
                letter-spacing: 0.04em;
            }

            .search-mode-toggle {
                display: flex;
                gap: 0;
                border: 1px solid var(--glass-border-subtle);
                border-radius: var(--radius-md);
                overflow: hidden;
            }
            .search-mode-btn {
                padding: 4px 10px;
                font-size: var(--text-xs);
                border: none;
                background: transparent;
                color: var(--text-secondary);
                cursor: pointer;
                transition: all var(--duration-fast);
                white-space: nowrap;
            }
            .search-mode-btn:not(:last-child) { border-right: 1px solid var(--glass-border-subtle); }
            .search-mode-btn.active {
                background: var(--crm-selected-bg);
                color: var(--crm-selected-text);
                font-weight: 500;
            }
            .search-mode-btn:hover:not(.active) { background: var(--glass-bg-subtle); }

            .subtype-chips {
                display: flex;
                flex-wrap: wrap;
                gap: var(--space-1);
            }

            .tag-input-row {
                display: flex;
                gap: var(--space-1);
                align-items: center;
            }
            .tag-filter-input {
                padding: 4px 8px;
                border: 1px solid var(--glass-border-subtle);
                border-radius: var(--radius-md);
                background: transparent;
                color: var(--text-primary);
                font-size: var(--text-xs);
                outline: none;
                min-width: 100px;
            }
            .tag-filter-input:focus { border-color: var(--crm-selected-stroke); }
            .tag-add-btn {
                padding: 4px 8px;
                border: 1px solid var(--glass-border-subtle);
                border-radius: var(--radius-md);
                background: transparent;
                color: var(--text-secondary);
                cursor: pointer;
                font-size: var(--text-xs);
            }
            .tag-add-btn:hover { background: var(--glass-bg-subtle); }
            .tag-chips {
                display: flex;
                flex-wrap: wrap;
                gap: var(--space-1);
                margin-top: 2px;
            }
            .tag-chip {
                display: inline-flex;
                align-items: center;
                gap: 3px;
                padding: 2px 8px;
                background: var(--crm-selected-bg);
                border: 1px solid var(--crm-selected-stroke);
                border-radius: var(--radius-full);
                color: var(--crm-selected-text);
                font-size: 11px;
            }
            .tag-chip-remove {
                display: inline-flex;
                align-items: center;
                justify-content: center;
                width: 12px;
                height: 12px;
                border: none;
                background: transparent;
                color: inherit;
                cursor: pointer;
                padding: 0;
                font-size: 12px;
                line-height: 1;
                opacity: 0.7;
            }
            .tag-chip-remove:hover { opacity: 1; }

            .date-filter-picker {
                --platform-date-picker-label-size: 11px;
                --platform-date-picker-value-size: 12px;
                max-width: 220px;
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
            }
            .bulk-status-item:hover { background: var(--glass-bg-subtle); }

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
                position: relative;
            }
            .list-panel.busy .cards-scroll {
                filter: saturate(0.92);
                opacity: 0.6;
                pointer-events: none;
            }

            .list-overlay {
                position: absolute;
                inset: 0;
                z-index: 6;
                display: flex;
                align-items: center;
                justify-content: center;
                pointer-events: none;
            }

            .cards-scroll {
                flex: 1;
                overflow-y: auto;
                overflow-x: hidden;
                min-height: 0;
                padding: var(--space-1);
                transition: filter 0.2s ease, opacity 0.2s ease;
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
            .scroll-sentinel { height: 1px; }

            .merge-dnd-hint {
                margin: 0;
                padding: 0 0 var(--space-1) 0;
                font-size: 11px;
                color: var(--text-tertiary);
                line-height: 1.3;
            }

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
            .entity-card-item.selected {
                border-color: var(--accent, #3b82f6);
                background: rgba(59, 130, 246, 0.06);
                box-shadow: 0 0 0 1px var(--accent, #3b82f6);
            }
            .entity-card-item.merge-drag-source { opacity: 0.55; }
            .entity-card-item.merge-drop-hover {
                border-color: var(--accent);
                box-shadow: 0 0 0 2px rgba(99, 102, 241, 0.35);
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
            .card-header-end {
                display: flex;
                align-items: center;
                gap: 8px;
                flex-shrink: 0;
                margin-left: auto;
            }
            .entity-card-drag-handle {
                flex-shrink: 0;
                width: 32px;
                height: 32px;
                display: inline-flex;
                align-items: center;
                justify-content: center;
                border-radius: var(--radius-md);
                background: transparent;
                color: var(--text-tertiary);
                cursor: grab;
                touch-action: none;
                user-select: none;
                transition: color var(--duration-fast), background var(--duration-fast);
            }
            .entity-card-drag-handle * { pointer-events: none; }
            .entity-card-drag-handle:hover {
                color: var(--text-secondary);
                background: var(--crm-surface-tint);
            }
            .entity-card-drag-handle:active { cursor: grabbing; }

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
                background: var(--crm-surface-tint);
                color: var(--text-secondary);
            }
            .card-meta { color: var(--text-tertiary); font-size: 11px; }
            .card-delete-btn {
                width: 32px;
                height: 32px;
                display: inline-flex;
                align-items: center;
                justify-content: center;
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
                padding: var(--space-6) var(--space-4);
                box-sizing: border-box;
            }
            .empty-import { gap: var(--space-4); max-width: 440px; margin: 0 auto; }
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
            }
            .import-wizard-btn:hover { background: var(--crm-daily-notes-cta-hover); }

            .detail-panel {
                display: flex;
                flex-direction: column;
                min-height: 0;
                overflow: hidden;
            }

            .mobile-tabs { display: none; }

            @media (max-width: 1279px) {
                .layout { grid-template-columns: 1fr; }
            }

            @media (max-width: 767px) {
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
                }
                .mobile-tab.active {
                    background: var(--crm-selected-bg);
                    border-color: var(--crm-selected-stroke);
                    color: var(--text-primary);
                }
                .mobile-tab:disabled { opacity: 0.4; cursor: default; }
                .page-toolbar { padding: var(--space-2) var(--space-3); }
                .section-label { display: none; }
                .title { display: none; }
                .top-row { flex-direction: column; gap: var(--space-2); }
                .search-box { display: none; }
                .cta-btn { display: none; }
                .btn-icon { display: none; }
                .filters-row { gap: 6px; overflow-x: auto; flex-wrap: nowrap; padding-bottom: 2px; }
                .filters-row::-webkit-scrollbar { display: none; }
                .filter-chip { padding: 5px 10px; font-size: 12px; flex-shrink: 0; }
                .layout { grid-template-columns: 1fr; }
                .list-panel, .detail-panel { display: none; }
                .list-panel.mobile-active { display: flex; flex: 1; min-height: 0; }
                .detail-panel.mobile-active { display: flex; flex: 1; min-height: 0; overflow-y: auto; }
                .cards-scroll { padding: var(--space-2) var(--space-3); }
                .cards-grid { grid-template-columns: 1fr; gap: var(--space-2); }
                .entity-card-item { padding: 14px; min-height: 0; gap: 8px; border-radius: 12px; }
            }
        `,
    ];

    constructor() {
        super();
        this._query = '';
        this._searchMode = 'hybrid';
        this._selectedType = null;
        this._selectedSubtype = null;
        this._selectedStatus = null;
        this._filterTags = [];
        this._tagInput = '';
        this._dateFrom = null;
        this._dateTo = null;
        this._showFiltersPanel = false;
        this._isMobile = typeof window !== 'undefined' && window.innerWidth <= 767;
        this._mobileTab = 'list';
        this._currentEntityId = null;
        this._selectedIds = new Set();
        this._showBulkStatusMenu = false;
        this._mergeDragSourceId = '';
        this._mergeDropHoverId = '';
        this._entitiesMergeFirstId = '';
        this._debounceTimer = null;
        this._scrollObserver = null;
        this._mql = null;
        this._mqlListener = null;
        this._lastNamespace = undefined;

        this._entities = this.useCursorList('crm/entities_list');
        this._entityTypes = this.useResource('crm/entity_types');
        this._aggregate = this.useOp('crm/entity_aggregate');
        this._bulkDelete = this.useOp('crm/entity_bulk_delete');
        this._bulkUpdate = this.useOp('crm/entity_bulk_update');

        this._authSel = this.select((s) => s.auth.user);
        this._namespaceSel = this.select((s) => {
            const user = s.auth.user;
            if (!user || typeof user.company_id !== 'string') return 'all';
            const cid = user.company_id;
            const map = s.ui.namespace.selectionByCompany;
            const selection = map[cid];
            if (selection === 'all' || selection === undefined) return 'all';
            return selection;
        });
    }

    connectedCallback() {
        super.connectedCallback();
        if (typeof window !== 'undefined' && typeof window.matchMedia === 'function') {
            this._mql = window.matchMedia('(max-width: 767px)');
            this._mqlListener = (e) => { this._isMobile = e.matches; };
            this._mql.addEventListener('change', this._mqlListener);
            this._isMobile = this._mql.matches;
        }

        this.useEvent(CoreEvents.UI_NAMESPACE_CHANGED, () => this._reloadAll());
        this.useEvent('crm/entity/updated', () => this._reloadList());

        this.useEvent('crm/entity_bulk_delete/succeeded', () => {
            this._selectedIds = new Set();
            this._reloadList();
        });
        this.useEvent('crm/entity_bulk_update/succeeded', () => {
            this._selectedIds = new Set();
            this._showBulkStatusMenu = false;
            this._reloadList();
        });
        this.useEvent('crm/entity_merge/succeeded', () => {
            this._selectedIds = new Set();
            this._entitiesMergeFirstId = '';
            this._reloadList();
        });

        this._lastNamespace = this._currentNamespace();
        this._reloadAll();
    }

    disconnectedCallback() {
        if (this._mql && this._mqlListener) {
            this._mql.removeEventListener('change', this._mqlListener);
        }
        if (this._debounceTimer) {
            clearTimeout(this._debounceTimer);
            this._debounceTimer = null;
        }
        this._disconnectScrollObserver();
        super.disconnectedCallback();
    }

    updated(changed) {
        super.updated(changed);
        this._setupScrollObserver();
    }

    _setupScrollObserver() {
        this._disconnectScrollObserver();
        const sentinel = this.renderRoot.querySelector('.scroll-sentinel');
        if (!sentinel) return;
        const scrollContainer = this.renderRoot.querySelector('.cards-scroll');
        this._scrollObserver = new IntersectionObserver(
            (entries) => {
                const entry = entries[0];
                if (entry.isIntersecting && this._entities.hasMore && !this._entities.loadingMore && !this._entities.loading) {
                    this._entities.loadMore();
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

    _currentNamespace() {
        const selection = this._namespaceSel.value;
        return selection === 'all' ? null : selection;
    }

    _buildFilters() {
        const filters = {};
        const ns = this._currentNamespace();
        if (typeof ns === 'string' && ns.length > 0) filters.namespace = ns;
        if (this._selectedType) filters.entity_type = this._selectedType;
        if (this._selectedSubtype) filters.entity_subtype = this._selectedSubtype;
        if (this._selectedStatus) filters.status = this._selectedStatus;
        if (this._query.trim().length > 0) {
            filters.q = this._query.trim();
            filters.search_mode = this._searchMode;
        }
        if (this._filterTags.length > 0) filters.tags = [...this._filterTags];
        if (this._dateFrom) filters.date_from = this._dateFrom;
        if (this._dateTo) filters.date_to = this._dateTo;
        return filters;
    }

    _reloadAll() {
        const ns = this._currentNamespace();
        this._entityTypes.load({ namespace: ns === null ? undefined : ns });
        this._aggregate.run({ namespace: ns === null ? undefined : ns });
        this._reloadList();
    }

    _reloadList() {
        this._entities.load(this._buildFilters());
    }

    _reloadListDebounced() {
        if (this._debounceTimer) clearTimeout(this._debounceTimer);
        this._debounceTimer = setTimeout(() => {
            this._debounceTimer = null;
            this._reloadList();
        }, 300);
    }

    _onSearchInput(event) {
        this._query = event.target.value;
        this._reloadListDebounced();
    }

    _onSearchModeChange(mode) {
        this._searchMode = mode;
        if (this._query.trim().length > 0) this._reloadListDebounced();
    }

    _onTypeSelect(typeId) {
        this._selectedType = this._selectedType === typeId ? null : typeId;
        this._selectedSubtype = null;
        this._reloadList();
    }

    _onSubtypeSelect(subtypeId) {
        this._selectedSubtype = this._selectedSubtype === subtypeId ? null : subtypeId;
        this._reloadList();
    }

    _onStatusSelect(status) {
        this._selectedStatus = this._selectedStatus === status ? null : status;
        this._reloadList();
    }

    _onClearFilters() {
        this._query = '';
        this._tagInput = '';
        this._selectedType = null;
        this._selectedSubtype = null;
        this._selectedStatus = null;
        this._filterTags = [];
        this._dateFrom = null;
        this._dateTo = null;
        this._searchMode = 'hybrid';
        this._reloadList();
    }

    _onTagInputChange(e) { this._tagInput = e.target.value; }

    _onTagInputKeydown(e) {
        if (e.key === 'Enter') {
            e.preventDefault();
            this._addTag();
        }
    }

    _addTag() {
        const tag = this._tagInput.trim();
        if (!tag) return;
        if (this._filterTags.includes(tag)) return;
        this._filterTags = [...this._filterTags, tag];
        this._tagInput = '';
        this._reloadList();
    }

    _removeTag(tag) {
        this._filterTags = this._filterTags.filter((t) => t !== tag);
        this._reloadList();
    }

    _onDateRangeChange(e) {
        const range = e.target.value;
        if (range && typeof range !== 'object') {
            throw new Error('Date range value must be object');
        }
        this._dateFrom = range && range.start ? range.start : null;
        this._dateTo = range && range.end ? range.end : null;
        this._reloadList();
    }

    _onMobileTab(tab) { this._mobileTab = tab; }

    _onSelectEntity(entityId) {
        this._currentEntityId = entityId;
        if (this._isMobile) this._mobileTab = 'card';
    }

    _onCreateEntity() {
        this.openModal('crm.entity', { mode: 'create' });
    }

    _goToImportWizard() {
        this.navigate('namespace_imports');
    }

    _hasExpandedFilters() {
        return Boolean(
            this._selectedSubtype
            || (this._filterTags && this._filterTags.length > 0)
            || this._dateFrom
            || this._dateTo
            || this._searchMode !== 'hybrid',
        );
    }

    _hasActiveFilters() {
        return Boolean(
            this._selectedType
            || this._selectedStatus
            || (this._query && this._query.trim().length > 0)
            || this._hasExpandedFilters(),
        );
    }

    _baseTypes() {
        const items = this._entityTypes.items;
        if (!Array.isArray(items)) return [];
        return items.filter((t) => !t.parent_type_id);
    }

    _subtypes() {
        if (!this._selectedType) return [];
        const items = this._entityTypes.items;
        if (!Array.isArray(items)) return [];
        return items.filter((t) => t.parent_type_id === this._selectedType);
    }

    _entityTypeConfig(entity) {
        const items = this._entityTypes.items;
        if (Array.isArray(items)) {
            const typeId = entity.entity_subtype || entity.entity_type;
            const match = items.find((t) => t.type_id === typeId);
            if (match) {
                return {
                    icon: this._resolveIconName(match.icon),
                    color: typeof match.color === 'string' && match.color.length > 0 ? match.color : 'var(--text-tertiary)',
                    label: match.name || typeId,
                };
            }
        }
        return { icon: 'folder', color: 'var(--text-tertiary)', label: entity.entity_type };
    }

    _resolveIconName(iconName) {
        if (iconName === 'file') return 'folder';
        if (typeof iconName === 'string' && /^[a-z0-9-]+$/i.test(iconName)) return iconName;
        return 'folder';
    }

    _hexToRgba(hex, alpha) {
        if (typeof hex !== 'string' || hex.length === 0 || hex.startsWith('var(')) {
            return `rgba(148, 163, 184, ${alpha})`;
        }
        const clean = hex.replace('#', '');
        if (clean.length !== 6) return `rgba(148, 163, 184, ${alpha})`;
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

    _isEntityOwner(entity) {
        const user = this._authSel.value;
        if (!user || typeof entity.user_id !== 'string') return false;
        const uid = typeof user.user_id === 'string' ? user.user_id : null;
        if (!uid) return false;
        return entity.user_id === uid;
    }

    _onToggleSelect(entityId, checked) {
        const ids = new Set(this._selectedIds);
        if (checked) ids.add(entityId);
        else ids.delete(entityId);
        this._selectedIds = ids;
    }

    _onBulkClear() { this._selectedIds = new Set(); }

    async _onBulkDelete() {
        if (this._selectedIds.size === 0) return;
        const confirmed = await platformConfirm(
            this.t('entities_page.delete_entity_confirm', { name: `${this._selectedIds.size}` }),
            {
                title: this.t('entities.bulk.delete'),
                variant: 'danger',
                confirmVariant: 'danger',
                confirmText: this.t('delete', {}, 'common'),
                cancelText: this.t('cancel', {}, 'common'),
            },
        );
        if (!confirmed) return;
        this._bulkDelete.run({ entity_ids: [...this._selectedIds] });
    }

    _onBulkUpdateStatus(status) {
        this._showBulkStatusMenu = false;
        if (this._selectedIds.size === 0) return;
        const items = [...this._selectedIds].map((id) => ({ entity_id: id, updates: { status } }));
        this._bulkUpdate.run({ items });
    }

    async _confirmDeleteEntity(entity) {
        if (!entity || typeof entity.entity_id !== 'string') return;
        const displayName = typeof entity.name === 'string' && entity.name.trim().length > 0
            ? entity.name.trim()
            : entity.entity_id;
        const confirmed = await platformConfirm(
            this.t('entities_page.delete_entity_confirm', { name: displayName }),
            {
                title: this.t('entities_page.delete_entity_title'),
                variant: 'danger',
                confirmVariant: 'danger',
                confirmText: this.t('delete', {}, 'common'),
                cancelText: this.t('cancel', {}, 'common'),
            },
        );
        if (!confirmed) return;
        this._bulkDelete.run({ entity_ids: [entity.entity_id] });
    }

    _onDeleteEntityFromList(event, entity) {
        event.stopPropagation();
        event.preventDefault();
        this._confirmDeleteEntity(entity);
    }

    _openMergeModal(idA, idB) {
        const a = typeof idA === 'string' ? idA.trim() : '';
        const b = typeof idB === 'string' ? idB.trim() : '';
        if (!a || !b || a === b) return;
        this._entitiesMergeFirstId = '';
        this.openModal('crm.entity_merge', { entityIdA: a, entityIdB: b });
    }

    _clearMergeDnDVisual() {
        this._mergeDragSourceId = '';
        this._mergeDropHoverId = '';
    }

    _onMergeCardDragStart(event, entityId) {
        if (this._isMobile) return;
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

    _onMergeCardDragEnd() { this._clearMergeDnDVisual(); }

    _onMergeCardDragOver(event, targetEntityId) {
        if (this._isMobile) return;
        const sourceId = this._mergeDragSourceId;
        const tid = typeof targetEntityId === 'string' ? targetEntityId.trim() : '';
        if (!sourceId || !tid || sourceId === tid) return;
        event.preventDefault();
        event.dataTransfer.dropEffect = 'move';
        if (this._mergeDropHoverId !== tid) this._mergeDropHoverId = tid;
    }

    _onMergeCardDragLeave(event, targetEntityId) {
        if (this._isMobile) return;
        const tid = typeof targetEntityId === 'string' ? targetEntityId.trim() : '';
        const related = event.relatedTarget;
        if (related instanceof Node && event.currentTarget.contains(related)) return;
        if (this._mergeDropHoverId === tid) this._mergeDropHoverId = '';
    }

    _onMergeCardDrop(event, targetEntityId) {
        if (this._isMobile) return;
        event.preventDefault();
        const tid = typeof targetEntityId === 'string' ? targetEntityId.trim() : '';
        let sid = '';
        try {
            sid = event.dataTransfer.getData(MERGE_DRAG_MIME).trim();
        } catch (err) {
            if (!(err instanceof DOMException)) throw err;
            sid = '';
        }
        if (!sid) sid = event.dataTransfer.getData('text/plain').trim();
        this._clearMergeDnDVisual();
        if (!sid || !tid || sid === tid) return;
        this._openMergeModal(sid, tid);
    }

    _onEntityListClick(entityId, event) {
        if (event.shiftKey) {
            if (!this._entitiesMergeFirstId) {
                this._entitiesMergeFirstId = entityId;
                this.toast('crm:entities.merge_first_marked', { type: 'info' });
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

    _renderToolbar() {
        const baseTypes = this._baseTypes();
        const items = this._entities.items;
        return html`
            <div class="page-toolbar">
                ${!this._isMobile
                    ? html`<div class="section-label">${this.t('entities.title')}</div>`
                    : nothing}
                <div class="top-row">
                    <h1 class="title">
                        ${this.t('entities.title')}
                        <span class="entities-count">(${items.length})</span>
                    </h1>
                    <label class="search-box">
                        <platform-icon name="search" size="14"></platform-icon>
                        <input
                            class="search-input"
                            type="text"
                            placeholder=${this.t('entities.search_placeholder')}
                            .value=${this._query}
                            @input=${this._onSearchInput}
                        />
                    </label>
                    <button
                        class="btn-icon ${this._showFiltersPanel || this._hasExpandedFilters() ? 'active' : ''}"
                        type="button"
                        title=${this.t('entity_filters.panel_title')}
                        @click=${() => { this._showFiltersPanel = !this._showFiltersPanel; }}
                    >
                        <platform-icon name="adjustment" size="16"></platform-icon>
                    </button>
                    <button class="cta-btn" type="button" @click=${this._onCreateEntity}>
                        ${this.t('create', {}, 'common')}
                    </button>
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
                    ${baseTypes.length > 0 ? html`<div class="filter-divider"></div>` : nothing}
                    ${STATUS_FILTERS.map((s) => html`
                        <button
                            class="filter-chip ${this._selectedStatus === s ? 'active' : ''}"
                            type="button"
                            @click=${() => this._onStatusSelect(s)}
                        >
                            ${this.t(`entities_page.status_${s}`)}
                        </button>
                    `)}
                    ${this._hasActiveFilters()
                        ? html`
                            <button class="clear-filters-btn" type="button" @click=${this._onClearFilters}>
                                <platform-icon name="close" size="12"></platform-icon>
                                ${this.t('entity_filters.reset')}
                            </button>
                        `
                        : nothing}
                    ${this._renderBulkActions()}
                </div>
            </div>
            ${this._renderExpandedFilters()}
        `;
    }

    _renderBulkActions() {
        if (this._selectedIds.size === 0) return nothing;
        const busy = this._bulkDelete.busy || this._bulkUpdate.busy;
        return html`
            <div class="filter-divider"></div>
            <div class="bulk-actions">
                <span class="bulk-badge">${this._selectedIds.size}</span>
                <div class="bulk-status-wrapper">
                    <button
                        class="bulk-action-btn bulk-action-btn--status"
                        type="button"
                        ?disabled=${busy}
                        title=${this.t('entities.bulk.change_status')}
                        @click=${() => { this._showBulkStatusMenu = !this._showBulkStatusMenu; }}
                    >
                        <platform-icon name="edit" size="16"></platform-icon>
                    </button>
                    ${this._showBulkStatusMenu
                        ? html`
                            <div class="bulk-status-menu">
                                ${BULK_STATUSES.map((status) => html`
                                    <button
                                        class="bulk-status-item"
                                        type="button"
                                        @click=${() => this._onBulkUpdateStatus(status)}
                                    >
                                        ${this.t(`entities.status.${status}`)}
                                    </button>
                                `)}
                            </div>
                        `
                        : nothing}
                </div>
                <button
                    class="bulk-action-btn bulk-action-btn--delete"
                    type="button"
                    ?disabled=${busy}
                    title=${this.t('entities.bulk.delete')}
                    @click=${() => this._onBulkDelete()}
                >
                    <platform-icon name="trash" size="16"></platform-icon>
                </button>
                <button
                    class="bulk-action-btn bulk-action-btn--clear"
                    type="button"
                    title=${this.t('entities.bulk.cancel')}
                    @click=${() => this._onBulkClear()}
                >
                    <platform-icon name="close" size="16"></platform-icon>
                </button>
            </div>
        `;
    }

    _renderExpandedFilters() {
        const subtypes = this._subtypes();
        return html`
            <div class="filters-collapsible ${this._showFiltersPanel ? 'open' : ''}">
                <div class="expanded-filters">
                    <div class="expanded-filter-group">
                        <span class="expanded-filter-label">${this.t('entity_filters.search_label')}</span>
                        <div class="search-mode-toggle">
                            ${SEARCH_MODES.map((mode) => html`
                                <button
                                    type="button"
                                    class="search-mode-btn ${this._searchMode === mode ? 'active' : ''}"
                                    @click=${() => this._onSearchModeChange(mode)}
                                >
                                    ${this.t(`entities.search_modes.${mode}`)}
                                </button>
                            `)}
                        </div>
                    </div>

                    ${subtypes.length > 0
                        ? html`
                            <div class="expanded-filter-group">
                                <span class="expanded-filter-label">${this.t('entity_filters.subtype_label')}</span>
                                <div class="subtype-chips">
                                    ${subtypes.map((type) => html`
                                        <button
                                            class="filter-chip ${this._selectedSubtype === type.type_id ? 'active' : ''}"
                                            type="button"
                                            @click=${() => this._onSubtypeSelect(type.type_id)}
                                        >
                                            <platform-icon name="${this._resolveIconName(type.icon)}" size="14"></platform-icon>
                                            ${type.name}
                                        </button>
                                    `)}
                                </div>
                            </div>
                        `
                        : nothing}

                    <div class="expanded-filter-group">
                        <span class="expanded-filter-label">${this.t('entity_filters.tags_label')}</span>
                        <div class="tag-input-row">
                            <input
                                type="text"
                                class="tag-filter-input"
                                placeholder=${this.t('entity_filters.tags_placeholder')}
                                .value=${this._tagInput}
                                @input=${this._onTagInputChange}
                                @keydown=${this._onTagInputKeydown}
                            />
                            <button type="button" class="tag-add-btn" @click=${() => this._addTag()}>+</button>
                        </div>
                        ${this._filterTags.length > 0
                            ? html`
                                <div class="tag-chips">
                                    ${this._filterTags.map((tag) => html`
                                        <span class="tag-chip">
                                            ${tag}
                                            <button
                                                type="button"
                                                class="tag-chip-remove"
                                                @click=${() => this._removeTag(tag)}
                                            >&times;</button>
                                        </span>
                                    `)}
                                </div>
                            `
                            : nothing}
                    </div>

                    <div class="expanded-filter-group">
                        <span class="expanded-filter-label">${this.t('entity_filters.date_label')}</span>
                        <platform-date-picker
                            class="date-filter-picker"
                            mode="date"
                            selection="range"
                            value-format="iso"
                            compact
                            .value=${{ start: this._dateFrom, end: this._dateTo }}
                            @change=${this._onDateRangeChange}
                        ></platform-date-picker>
                    </div>
                </div>
            </div>
        `;
    }

    _renderEntityCard(entity) {
        const typeConfig = this._entityTypeConfig(entity);
        const bgColor = this._hexToRgba(typeConfig.color, 0.15);
        const isActive = entity.entity_id === this._currentEntityId;
        const isSelected = this._selectedIds.has(entity.entity_id);
        const tags = Array.isArray(entity.tags) ? entity.tags.slice(0, 3) : [];
        const showDelete = this._isEntityOwner(entity);
        const eid = entity.entity_id;
        const mergeSource = this._mergeDragSourceId === eid;
        const mergeHover = !this._isMobile
            && this._mergeDropHoverId === eid
            && this._mergeDragSourceId
            && this._mergeDragSourceId !== eid;
        const showHeaderEnd = !this._isMobile;

        return html`
            <article
                class="entity-card-item
                    ${isActive ? 'active' : ''}
                    ${isSelected ? 'selected' : ''}
                    ${mergeSource ? 'merge-drag-source' : ''}
                    ${mergeHover ? 'merge-drop-hover' : ''}"
                @dragover=${(e) => this._onMergeCardDragOver(e, eid)}
                @dragleave=${(e) => this._onMergeCardDragLeave(e, eid)}
                @drop=${(e) => this._onMergeCardDrop(e, eid)}
                @click=${(e) => this._onEntityListClick(eid, e)}
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
                                    title=${this.t('entities_page.drag_merge_handle')}
                                    role="button"
                                    tabindex="0"
                                    aria-label=${this.t('entities_page.drag_merge_handle')}
                                    @dragstart=${(e) => this._onMergeCardDragStart(e, eid)}
                                    @dragend=${() => this._onMergeCardDragEnd()}
                                    @click=${(e) => e.stopPropagation()}
                                >
                                    <platform-icon name="drag-handle" size="18" ?filled=${true}></platform-icon>
                                </div>
                            </div>
                        `
                        : nothing}
                </div>

                ${entity.description
                    ? html`<p class="card-description">${this._getLimitedText(entity.description)}</p>`
                    : nothing}

                ${tags.length > 0
                    ? html`
                        <div class="card-tags">
                            ${tags.map((tag) => html`<span class="card-tag">${tag}</span>`)}
                        </div>
                    `
                    : nothing}

                <div class="card-footer">
                    <span class="card-type-badge" style="background: ${bgColor}; color: ${typeConfig.color};">
                        ${typeConfig.label}
                    </span>
                    <div class="card-footer-end">
                        <span class="card-meta">${this._formatDate(entity.created_at)}</span>
                        ${showDelete
                            ? html`
                                <button
                                    type="button"
                                    class="card-delete-btn"
                                    draggable="false"
                                    title=${this.t('entities_page.delete_entity_tooltip')}
                                    aria-label=${this.t('entities_page.delete_entity_tooltip')}
                                    @click=${(e) => this._onDeleteEntityFromList(e, entity)}
                                >
                                    <platform-icon name="trash" size="16"></platform-icon>
                                </button>
                            `
                            : nothing}
                    </div>
                </div>
            </article>
        `;
    }

    _renderEmpty() {
        if (this._hasActiveFilters()) {
            return html`
                <div class="empty">
                    <platform-icon name="database" size="40"></platform-icon>
                    <span>${this.t('entities.empty')}</span>
                    <span style="font-size: var(--text-sm)">${this.t('entities_page.empty_filters_hint')}</span>
                </div>
            `;
        }
        return html`
            <div class="empty empty-import">
                <p class="empty-import-text">${this.t('import_wizard_cta.empty_entities_hint')}</p>
                <button class="import-wizard-btn" type="button" @click=${() => this._goToImportWizard()}>
                    <platform-icon name="import" size="18"></platform-icon>
                    ${this.t('import_wizard_cta.open_wizard')}
                </button>
            </div>
        `;
    }

    _selectedEntity() {
        if (!this._currentEntityId) return null;
        const items = this._entities.items;
        if (!Array.isArray(items)) return null;
        const found = items.find((e) => e && e.entity_id === this._currentEntityId);
        if (found) return found;
        return null;
    }

    render() {
        const items = this._entities.items;
        const loading = this._entities.loading;
        const loadingMore = this._entities.loadingMore;
        const listActive = !this._isMobile || this._mobileTab === 'list';
        const cardActive = !this._isMobile || this._mobileTab === 'card';
        const selectedEntity = this._selectedEntity();

        return html`
            <div class="breadcrumbs-wrap">
                <platform-breadcrumbs></platform-breadcrumbs>
            </div>
            ${this._isMobile
                ? html`
                    <div class="mobile-tabs">
                        <button
                            class="mobile-tab ${this._mobileTab === 'list' ? 'active' : ''}"
                            type="button"
                            @click=${() => this._onMobileTab('list')}
                        >
                            <platform-icon name="list" size="14"></platform-icon>
                            ${this.t('entities_page.tab_list')}
                        </button>
                        <button
                            class="mobile-tab ${this._mobileTab === 'card' ? 'active' : ''}"
                            type="button"
                            ?disabled=${!this._currentEntityId}
                            @click=${() => this._onMobileTab('card')}
                        >
                            <platform-icon name="folder" size="14"></platform-icon>
                            ${this.t('entities_page.tab_card')}
                        </button>
                    </div>
                `
                : nothing}

            ${listActive ? this._renderToolbar() : nothing}

            ${items.length >= 2 && !loading
                ? html`<p class="merge-dnd-hint">${this.t('entities_page.merge_dnd_hint')}</p>`
                : nothing}

            <div class="layout">
                <section class="list-panel ${listActive ? 'mobile-active' : ''} ${loading ? 'busy' : ''}">
                    ${loading
                        ? html`<div class="list-overlay"><glass-spinner size="lg"></glass-spinner></div>`
                        : nothing}
                    <div class="cards-scroll">
                        ${items.length === 0 && !loading
                            ? this._renderEmpty()
                            : html`
                                <div class="cards-grid">
                                    ${items.map((entity) => this._renderEntityCard(entity))}
                                </div>
                                ${loadingMore
                                    ? html`<div class="loading-more">${this.t('loading', {}, 'common')}</div>`
                                    : nothing}
                                <div class="scroll-sentinel"></div>
                            `}
                    </div>
                </section>

                <aside class="detail-panel ${cardActive ? 'mobile-active' : ''}">
                    <crm-entity-card
                        .entity=${selectedEntity}
                        .entityId=${this._currentEntityId}
                    ></crm-entity-card>
                </aside>
            </div>
        `;
    }
}

customElements.define('crm-entities-page', CRMEntitiesPage);
