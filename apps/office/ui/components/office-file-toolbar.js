/**
 * office-file-toolbar — single-row explorer toolbar.
 */

import { html, css, nothing } from 'lit';
import { PlatformElement } from '@platform/lib/platform-element/index.js';
import { buttonStyles } from '@platform/lib/styles/shared/button.styles.js';
import {
    documentsControlHostStyles,
    documentsToolbarControlStyles,
} from '../styles/documents-controls.styles.js';
import '@platform/lib/components/platform-icon.js';
import '@platform/lib/components/fields/platform-field.js';

export class OfficeFileToolbar extends PlatformElement {
    static i18nNamespace = 'documents';

    static properties = {
        pageTitle: { type: String, attribute: 'page-title' },
        searchQuery: { type: String, attribute: 'search-query' },
        searchMode: { type: String, attribute: 'search-mode' },
        semanticSearchAvailable: { type: Boolean, attribute: 'semantic-search-available' },
        viewMode: { type: String, attribute: 'view-mode' },
        actionsDisabled: { type: Boolean, attribute: 'actions-disabled' },
        showBreadcrumbs: { type: Boolean, attribute: 'show-breadcrumbs' },
        breadcrumbs: { type: Array },
    };

    static styles = [
        PlatformElement.styles,
        buttonStyles,
        documentsControlHostStyles,
        documentsToolbarControlStyles,
        css`
            :host {
                display: block;
                min-height: var(--documents-explorer-toolbar-height, 3rem);
            }
            .toolbar {
                display: flex;
                align-items: center;
                gap: var(--space-2);
                min-height: var(--documents-explorer-toolbar-height, 3rem);
            }
            .title-wrap {
                flex: 0 1 auto;
                min-width: 0;
                max-width: 24rem;
            }
            .breadcrumbs {
                display: flex;
                flex-wrap: wrap;
                align-items: center;
                gap: var(--space-1);
                margin: 0 0 var(--space-1);
            }
            .crumb {
                border: none;
                background: transparent;
                color: var(--text-secondary);
                font-size: var(--text-sm);
                font-weight: 500;
                cursor: pointer;
                padding: 0;
            }
            .crumb.current {
                color: var(--text-primary);
                font-weight: 700;
                cursor: default;
            }
            .crumb-sep {
                color: var(--text-tertiary);
                font-size: var(--text-sm);
            }
            .page-title {
                margin: 0;
                font-size: var(--text-lg);
                font-weight: 700;
                color: var(--text-primary);
                overflow: hidden;
                text-overflow: ellipsis;
                white-space: nowrap;
            }
            .search-wrap {
                flex: 1 1 12rem;
                min-width: 8rem;
                max-width: 28rem;
            }
            .search-field {
                display: block;
                width: 100%;
            }
            .actions {
                display: flex;
                flex-shrink: 0;
                align-items: center;
                gap: var(--space-2);
                margin-left: auto;
            }
            .overflow-wrap {
                position: relative;
            }
            .overflow-menu {
                position: absolute;
                top: calc(100% + var(--space-1));
                right: 0;
                z-index: 10;
                min-width: 10rem;
                padding: var(--space-1);
                border-radius: var(--radius-lg);
                border: 1px solid var(--glass-border-medium);
                background: var(--glass-solid-strong);
                box-shadow: var(--glass-shadow-medium);
            }
            .overflow-item {
                display: flex;
                align-items: center;
                gap: var(--space-2);
                width: 100%;
                padding: var(--space-2) var(--space-3);
                border: none;
                border-radius: var(--radius-md);
                background: transparent;
                color: var(--text-primary);
                font-size: var(--text-sm);
                text-align: left;
                cursor: pointer;
            }
            .overflow-item:hover {
                background: var(--glass-solid-medium);
            }
            @media (max-width: 767px) {
                .toolbar {
                    flex-wrap: wrap;
                }
                .title-wrap {
                    width: 100%;
                    max-width: none;
                }
                .search-wrap {
                    flex: 1 1 100%;
                    max-width: none;
                }
                .actions {
                    width: 100%;
                    margin-left: 0;
                    justify-content: flex-end;
                }
            }
        `,
    ];

    constructor() {
        super();
        this.pageTitle = '';
        this.searchQuery = '';
        this.searchMode = 'files';
        this.semanticSearchAvailable = false;
        this.viewMode = 'list';
        this.actionsDisabled = false;
        this.showBreadcrumbs = false;
        this.breadcrumbs = [];
        this._overflowOpen = false;
    }

    _onBreadcrumbClick(crumb) {
        if (!crumb || typeof crumb !== 'object') return;
        if (crumb.current === true) return;
        this.emit('breadcrumb-navigate', { crumb });
    }

    _onSearchChange(e) {
        const value = e.detail && typeof e.detail.value === 'string' ? e.detail.value : '';
        this.emit('search-change', { searchQuery: value });
    }

    _setSearchMode(mode) {
        if (mode !== 'files' && mode !== 'semantic') return;
        if (mode === 'semantic' && this.semanticSearchAvailable !== true) return;
        this.emit('search-mode-change', { searchMode: mode });
    }

    _setView(mode) {
        if (mode !== 'list' && mode !== 'grid') return;
        this.emit('view-change', { viewMode: mode });
    }

    _upload() { this.emit('upload'); }
    _createEmpty() { this.emit('create-empty'); }
    _refresh() {
        this._overflowOpen = false;
        this.emit('refresh');
    }
    _toggleOverflow() {
        this._overflowOpen = !this._overflowOpen;
        this.requestUpdate();
    }

    render() {
        const crumbs = Array.isArray(this.breadcrumbs) ? this.breadcrumbs : [];
        return html`
            <div class="toolbar">
                <div class="title-wrap">
                    ${this.showBreadcrumbs && crumbs.length > 0 ? html`
                        <nav class="breadcrumbs" aria-label=${this.t('breadcrumbs.aria')}>
                            ${crumbs.map((crumb, index) => html`
                                ${index > 0 ? html`<span class="crumb-sep">/</span>` : null}
                                <button
                                    class="crumb ${crumb.current ? 'current' : ''}"
                                    type="button"
                                    ?disabled=${crumb.current === true}
                                    @click=${() => this._onBreadcrumbClick(crumb)}
                                >
                                    ${crumb.label}
                                </button>
                            `)}
                        </nav>
                    ` : html`<h1 class="page-title">${this.pageTitle}</h1>`}
                </div>
                <div class="search-wrap">
                    <platform-field
                        class="search-field"
                        type="string"
                        input-type="search"
                        pill-density="dense"
                        mode="edit"
                        .placeholder=${this.t('toolbar.searchPlaceholder')}
                        .value=${this.searchQuery}
                        @change=${this._onSearchChange}
                    >
                        ${this.semanticSearchAvailable ? html`
                            <div
                                slot="suffix"
                                class="search-mode-segment"
                                role="group"
                                aria-label=${this.t('toolbar.searchModeAria')}
                                @click=${(e) => e.stopPropagation()}
                            >
                                <button
                                    type="button"
                                    class="search-mode-btn ${this.searchMode === 'files' ? 'active' : ''}"
                                    @click=${() => this._setSearchMode('files')}
                                >
                                    ${this.t('toolbar.searchModeFiles')}
                                </button>
                                <button
                                    type="button"
                                    class="search-mode-btn ${this.searchMode === 'semantic' ? 'active' : ''}"
                                    @click=${() => this._setSearchMode('semantic')}
                                >
                                    ${this.t('toolbar.searchModeSemantic')}
                                </button>
                            </div>
                        ` : nothing}
                    </platform-field>
                </div>
                ${this.searchMode === 'files' ? html`
                <div class="view-toggle" role="group" aria-label=${this.t('toolbar.viewToggleAria')}>
                    <button
                        class="view-btn ${this.viewMode === 'list' ? 'active' : ''}"
                        type="button"
                        title=${this.t('view.list')}
                        @click=${() => this._setView('list')}
                    >
                        <platform-icon name="list" size="16"></platform-icon>
                    </button>
                    <button
                        class="view-btn ${this.viewMode === 'grid' ? 'active' : ''}"
                        type="button"
                        title=${this.t('view.grid')}
                        @click=${() => this._setView('grid')}
                    >
                        <platform-icon name="apps" size="16"></platform-icon>
                    </button>
                </div>
                ` : ''}
                <div class="actions">
                    <button class="btn btn-primary" type="button"
                            ?disabled=${this.actionsDisabled}
                            @click=${this._upload}>
                        ${this.t('list.upload')}
                    </button>
                    <button class="btn" type="button"
                            ?disabled=${this.actionsDisabled}
                            @click=${this._createEmpty}>
                        ${this.t('list.newEmpty')}
                    </button>
                    <div class="overflow-wrap">
                        <button class="btn btn-icon-only" type="button" title=${this.t('toolbar.moreActions')}
                                @click=${this._toggleOverflow}>
                            <platform-icon name="more-vertical" size="16"></platform-icon>
                        </button>
                        ${this._overflowOpen ? html`
                            <div class="overflow-menu" role="menu">
                                <button class="overflow-item" type="button" role="menuitem"
                                        @click=${this._refresh}>
                                    <platform-icon name="refresh" size="16"></platform-icon>
                                    ${this.t('toolbar.refresh')}
                                </button>
                            </div>
                        ` : ''}
                    </div>
                </div>
            </div>
        `;
    }
}

customElements.define('office-file-toolbar', OfficeFileToolbar);
