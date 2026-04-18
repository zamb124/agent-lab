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
import '@platform/lib/components/platform-date-picker.js';
import '@platform/lib/components/fields/platform-field.js';
import '@platform/lib/components/glass-spinner.js';
import '@platform/lib/components/platform-breadcrumbs.js';

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
        _showBulkStatusMenu: { state: true },
        _showFiltersPanel: { state: true },
        _searchMode: { state: true },
        _selectedSubtype: { state: true },
        _filterTags: { state: true },
        _tagInput: { state: true },
        _dateFrom: { state: true },
        _dateTo: { state: true },
        _aggregate: { state: true },
        _attributeFilters: { state: true },
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
                padding-bottom: var(--space-1);
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
                position: relative;
            }

            .cards-scroll {
                flex: 1;
                overflow-y: auto;
                overflow-x: hidden;
                min-height: 0;
                padding: var(--space-1);
                transition: filter 0.2s ease, opacity 0.2s ease;
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
                animation: list-overlay-in 0.2s ease;
            }

            @keyframes list-overlay-in {
                from { opacity: 0; }
                to { opacity: 1; }
            }

            @media (prefers-reduced-motion: reduce) {
                .cards-scroll {
                    transition: none;
                }
                .list-overlay {
                    animation: none;
                }
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
                margin: 0;
                padding: 0 0 var(--space-1) 0;
                font-size: 11px;
                color: var(--text-tertiary);
                line-height: 1.3;
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
            .search-mode-btn:not(:last-child) {
                border-right: 1px solid var(--glass-border-subtle);
            }
            .search-mode-btn.active {
                background: var(--crm-selected-bg);
                color: var(--crm-selected-text);
                font-weight: 500;
            }
            .search-mode-btn:hover:not(.active) {
                background: var(--glass-bg-subtle);
            }

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
            .tag-filter-input:focus {
                border-color: var(--crm-selected-stroke);
            }
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

            .attribute-filters-block {
                display: flex;
                flex-direction: column;
                gap: var(--space-2);
                min-width: 320px;
            }

            .attribute-filter-row {
                display: flex;
                align-items: center;
                gap: var(--space-2);
                flex-wrap: wrap;
            }

            .attribute-select {
                padding: 4px 8px;
                border: 1px solid var(--glass-border-subtle);
                border-radius: var(--radius-md);
                background: transparent;
                color: var(--text-primary);
                font-size: var(--text-xs);
                min-width: 140px;
            }

            .attribute-filter-value {
                min-width: 180px;
                flex: 1;
            }


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
                cursor: help;
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

                .btn-icon {
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
        this._showBulkStatusMenu = false;
        this._showFiltersPanel = false;
        this._searchMode = 'hybrid';
        this._selectedSubtype = null;
        this._filterTags = [];
        this._tagInput = '';
        this._dateFrom = null;
        this._dateTo = null;
        this._aggregate = null;
        this._attributeFilters = [];
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
            this._selectedSubtype = state.entities.filters.entity_subtype;
            this._selectedStatus = state.entities.filters.status;
            this._searchMode = state.entities.filters.search_mode || 'hybrid';
            this._filterTags = state.entities.filters.tags || [];
            this._dateFrom = state.entities.filters.date_from;
            this._dateTo = state.entities.filters.date_to;
            this._aggregate = state.entities.aggregate || null;
            this._attributeFilters = Array.isArray(state.entities.filters.attribute_filters)
                ? state.entities.filters.attribute_filters
                : [];
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
        this._boundToggleFilters = () => { this._showFiltersPanel = !this._showFiltersPanel; };
        window.addEventListener('entities-toggle-filters', this._boundToggleFilters);
        this._reloadData();
    }

    disconnectedCallback() {
        super.disconnectedCallback();
        window.removeEventListener('entities-toggle-filters', this._boundToggleFilters);
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
        await Promise.all([
            CRMStore.loadEntities(crmApi),
            CRMStore.loadAggregate(crmApi),
        ]);
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
        this._tagInput = '';
        CRMStore.clearEntityFilters();
        this._applyFilters();
    }

    _onSearchModeChange(mode) {
        CRMStore.setSearchMode(mode);
        this._applyFiltersDebounced();
    }

    _onSubtypeSelect(subtypeId) {
        const next = this._selectedSubtype === subtypeId ? null : subtypeId;
        CRMStore.setEntityFilters({ entity_subtype: next });
        this._applyFilters();
    }

    _onDateRangeChange(e) {
        const range = e.target.value;
        if (range && typeof range !== 'object') {
            throw new Error('Date range value must be object');
        }
        CRMStore.setEntityFilters({
            date_from: range?.start || null,
            date_to: range?.end || null,
        });
        this._applyFilters();
    }

    _onTagInputChange(e) {
        this._tagInput = e.target.value;
    }

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
        CRMStore.setEntityFilters({ tags: [...this._filterTags, tag] });
        this._tagInput = '';
        this._applyFilters();
    }

    _removeTag(tag) {
        CRMStore.setEntityFilters({ tags: this._filterTags.filter(t => t !== tag) });
        this._applyFilters();
    }

    _applyFiltersDebounced() {
        if (this._debounceTimer) {
            clearTimeout(this._debounceTimer);
        }
        this._debounceTimer = setTimeout(() => {
            this._debounceTimer = null;
            this._applyFilters();
        }, 250);
    }

    _getSubtypes() {
        if (!this._selectedType) return [];
        return this._entityTypes.filter(t => t.parent_type_id === this._selectedType);
    }

    _getActiveSchemaType() {
        const typeId = this._selectedSubtype || this._selectedType;
        if (!typeId) {
            return null;
        }
        return this._entityTypes.find((item) => item.type_id === typeId) || null;
    }

    _getSchemaFieldOptions() {
        const activeType = this._getActiveSchemaType();
        if (!activeType) {
            return [];
        }
        const fields = [];
        const schema = {
            ...(activeType.required_fields || {}),
            ...(activeType.optional_fields || {}),
        };
        for (const [fieldKey, fieldSpec] of Object.entries(schema)) {
            if (!fieldSpec || typeof fieldSpec !== 'object') {
                continue;
            }
            const fieldType = typeof fieldSpec.type === 'string' ? fieldSpec.type : 'string';
            const label = typeof fieldSpec.label === 'string' ? fieldSpec.label : fieldKey;
            fields.push({
                path: `attributes.${fieldKey}`,
                label,
                type: fieldType,
                values: Array.isArray(fieldSpec.values) ? fieldSpec.values : [],
            });
        }
        return fields;
    }

    _getOperatorsForFieldType(fieldType) {
        const map = {
            string: ['$eq', '$ne', '$contains', '$in', '$nin'],
            text: ['$eq', '$ne', '$contains', '$in', '$nin'],
            enum: ['$eq', '$ne', '$in', '$nin'],
            integer: ['$eq', '$ne', '$gt', '$gte', '$lt', '$lte', '$in', '$nin'],
            number: ['$eq', '$ne', '$gt', '$gte', '$lt', '$lte', '$in', '$nin'],
            boolean: ['$eq', '$ne', '$in', '$nin'],
            date: ['$eq', '$ne', '$gt', '$gte', '$lt', '$lte', '$in', '$nin'],
            datetime: ['$eq', '$ne', '$gt', '$gte', '$lt', '$lte', '$in', '$nin'],
            array: ['$contains', '$in', '$nin'],
        };
        return map[fieldType] || ['$eq', '$ne'];
    }

    _upsertAttributeFilter(index, patch) {
        const next = [...this._attributeFilters];
        next[index] = { ...next[index], ...patch };
        CRMStore.setEntityFilters({ attribute_filters: next });
    }

    _removeAttributeFilter(index) {
        CRMStore.setEntityFilters({
            attribute_filters: this._attributeFilters.filter((_, itemIndex) => itemIndex !== index),
        });
        this._applyFilters();
    }

    _addAttributeFilter() {
        const fields = this._getSchemaFieldOptions();
        if (fields.length === 0) {
            return;
        }
        const first = fields[0];
        const defaultOp = this._getOperatorsForFieldType(first.type)[0];
        CRMStore.setEntityFilters({
            attribute_filters: [
                ...this._attributeFilters,
                { field: first.path, op: defaultOp, value: '', field_type: first.type },
            ],
        });
    }

    _hasExpandedFilters() {
        return this._selectedSubtype
            || (this._filterTags && this._filterTags.length > 0)
            || this._dateFrom
            || this._dateTo
            || this._searchMode !== 'hybrid'
            || this._attributeFilters.length > 0;
    }

    async _applyFilters() {
        const crmApi = this.services.get('crmApi');
        await Promise.all([
            CRMStore.loadEntities(crmApi),
            CRMStore.loadAggregate(crmApi),
        ]);
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
        return this._selectedType
            || this._selectedStatus
            || this._query.trim().length > 0
            || this._hasExpandedFilters();
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
                    <platform-breadcrumbs></platform-breadcrumbs>
                    <div class="top-row">
                        <div class="title">
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
                        <button
                            class="btn-icon ${this._showFiltersPanel || this._hasExpandedFilters() ? 'active' : ''}"
                            type="button"
                            title=${this.i18n.t('entity_filters.panel_title')}
                            @click=${() => { this._showFiltersPanel = !this._showFiltersPanel; }}
                        >
                            <platform-icon name="adjustment" size="16"></platform-icon>
                        </button>
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
                </div>
                <div class="filters-collapsible ${this._showFiltersPanel ? 'open' : ''}">
                    <div class="expanded-filters">
                        <div class="expanded-filter-group">
                            <span class="expanded-filter-label">${this.i18n.t('entity_filters.search_label')}</span>
                            <div class="search-mode-toggle">
                                ${['text', 'semantic', 'hybrid'].map(mode => html`
                                    <button
                                        type="button"
                                        class="search-mode-btn ${this._searchMode === mode ? 'active' : ''}"
                                        @click=${() => this._onSearchModeChange(mode)}
                                    >${this.i18n.t(`entities.search_modes.${mode}`)}</button>
                                `)}
                            </div>
                        </div>

                        ${this._getSubtypes().length > 0 ? html`
                            <div class="expanded-filter-group">
                                <span class="expanded-filter-label">${this.i18n.t('entity_filters.subtype_label')}</span>
                                <div class="subtype-chips">
                                    ${this._getSubtypes().map(type => html`
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
                        ` : ''}

                        <div class="expanded-filter-group">
                            <span class="expanded-filter-label">${this.i18n.t('entity_filters.tags_label')}</span>
                            <div class="tag-input-row">
                                <input
                                    type="text"
                                    class="tag-filter-input"
                                    placeholder=${this.i18n.t('entity_filters.tags_placeholder')}
                                    .value=${this._tagInput}
                                    @input=${this._onTagInputChange}
                                    @keydown=${this._onTagInputKeydown}
                                />
                                <button type="button" class="tag-add-btn" @click=${this._addTag}>+</button>
                            </div>
                            ${this._filterTags.length > 0 ? html`
                                <div class="tag-chips">
                                    ${this._filterTags.map(tag => html`
                                        <span class="tag-chip">
                                            ${tag}
                                            <button type="button" class="tag-chip-remove" @click=${() => this._removeTag(tag)}>&times;</button>
                                        </span>
                                    `)}
                                </div>
                            ` : ''}
                        </div>

                        <div class="expanded-filter-group">
                            <span class="expanded-filter-label">${this.i18n.t('entity_filters.date_label')}</span>
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

                        <div class="expanded-filter-group attribute-filters-block">
                            <span class="expanded-filter-label">${this.i18n.t('entity_filters.attributes_label')}</span>
                            ${this._attributeFilters.map((condition, index) => {
                                const schemaFields = this._getSchemaFieldOptions();
                                const selectedField = schemaFields.find((item) => item.path === condition.field) || schemaFields[0];
                                const fieldType = selectedField ? selectedField.type : 'string';
                                const fieldConfig = selectedField && fieldType === 'enum'
                                    ? { values: selectedField.values }
                                    : {};
                                const operators = this._getOperatorsForFieldType(fieldType);
                                const selectedOperator = operators.includes(condition.op) ? condition.op : operators[0];

                                return html`
                                    <div class="attribute-filter-row">
                                        <select
                                            class="attribute-select"
                                            .value=${selectedField?.path || ''}
                                            @change=${(event) => {
                                                const nextField = schemaFields.find((item) => item.path === event.target.value);
                                                if (!nextField) {
                                                    return;
                                                }
                                                const nextOperators = this._getOperatorsForFieldType(nextField.type);
                                                this._upsertAttributeFilter(index, {
                                                    field: nextField.path,
                                                    field_type: nextField.type,
                                                    op: nextOperators[0],
                                                    value: '',
                                                });
                                            }}
                                        >
                                            ${schemaFields.map((item) => html`
                                                <option value=${item.path}>${item.label}</option>
                                            `)}
                                        </select>
                                        <select
                                            class="attribute-select"
                                            .value=${selectedOperator}
                                            @change=${(event) => {
                                                this._upsertAttributeFilter(index, { op: event.target.value });
                                                this._applyFiltersDebounced();
                                            }}
                                        >
                                            ${operators.map((op) => html`<option value=${op}>${op}</option>`)}
                                        </select>
                                        <platform-field
                                            class="attribute-filter-value"
                                            .type=${fieldType}
                                            .config=${fieldConfig}
                                            .value=${condition.value}
                                            mode="edit"
                                            @change=${(event) => {
                                                this._upsertAttributeFilter(index, { value: event.detail.value });
                                                this._applyFiltersDebounced();
                                            }}
                                        ></platform-field>
                                        <button
                                            type="button"
                                            class="tag-add-btn"
                                            @click=${() => this._removeAttributeFilter(index)}
                                        >&times;</button>
                                    </div>
                                `;
                            })}
                            <button type="button" class="tag-add-btn" @click=${this._addAttributeFilter}>
                                ${this.i18n.t('entity_filters.add_attribute_filter')}
                            </button>
                        </div>
                    </div>
                </div>
            ` : ''}
            ${this._entities.length >= 2 && !this._loading
                ? html`<p class="merge-dnd-hint">${this.i18n.t('entities_page.merge_dnd_hint')}</p>`
                : ''}

            <div class="layout">
                <section class="list-panel ${listActive ? 'mobile-active' : ''} ${this._loading ? 'busy' : ''}">
                    ${this._loading ? html`
                        <div class="list-overlay">
                            <glass-spinner size="lg"></glass-spinner>
                        </div>
                    ` : ''}
                    <div class="cards-scroll">
                        ${this._entities.length === 0 && !this._loading ? html`
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
                    <div class="card-score" title="${(() => {
                        const modeTitle = {
                            semantic: this.i18n.t('search.score_title_semantic'),
                            text: this.i18n.t('search.score_title_text'),
                            hybrid: this.i18n.t('search.score_title_hybrid'),
                        }[this._searchMode] ?? '';
                        if (this._searchMode === 'hybrid' && entity.match_type) {
                            const foundBy = {
                                text: this.i18n.t('search.found_by_text'),
                                semantic: this.i18n.t('search.found_by_semantic'),
                                hybrid: this.i18n.t('search.found_by_both'),
                            }[entity.match_type] ?? '';
                            return foundBy ? `${modeTitle}\n${foundBy}` : modeTitle;
                        }
                        return modeTitle;
                    })()}">
                        <div class="score-bar" style="width: ${Math.round(entity.score * 100)}%"></div>
                        <span class="score-label">${(entity.score * 100).toFixed(0)}%</span>
                        <span class="match-type-badge">${this._searchMode}</span>
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
