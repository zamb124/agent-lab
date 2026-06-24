/**
 * office-explorer-tree — nested catalogs for Documents explorer.
 */

import { html, css } from 'lit';
import { PlatformElement } from '@platform/lib/platform-element/index.js';
import '@platform/lib/components/platform-icon.js';
import './office-catalog-context-menu.js';

function _groupByParent(items, parentKey, idKey) {
    const map = new Map();
    for (const item of items) {
        const parentId = item[parentKey];
        const bucketKey = typeof parentId === 'string' && parentId.length > 0 ? parentId : '';
        if (!map.has(bucketKey)) {
            map.set(bucketKey, []);
        }
        map.get(bucketKey).push(item);
    }
    return map;
}

export class OfficeExplorerTree extends PlatformElement {
    static i18nNamespace = 'documents';

    static properties = {
        catalogs: { type: Array },
        activeCatalogId: { type: String, attribute: 'active-catalog-id' },
        expandedCatalogIds: { type: Array, attribute: false },
    };

    static styles = [
        PlatformElement.styles,
        css`
            :host {
                display: flex;
                flex-direction: column;
                min-height: 0;
                height: 100%;
                position: relative;
            }
            .head {
                display: flex;
                align-items: center;
                justify-content: space-between;
                padding: var(--space-3) var(--space-3) var(--space-2);
            }
            .head-title {
                font-size: var(--text-xs);
                font-weight: 700;
                text-transform: uppercase;
                letter-spacing: 0.04em;
                color: var(--text-tertiary);
            }
            .head-actions {
                display: inline-flex;
                gap: var(--space-1);
            }
            .head-btn {
                display: inline-flex;
                align-items: center;
                justify-content: center;
                width: 1.75rem;
                height: 1.75rem;
                border: 1px solid var(--glass-border-medium);
                border-radius: var(--radius-md);
                background: var(--glass-solid-subtle);
                color: var(--text-secondary);
                cursor: pointer;
            }
            .head-btn:hover {
                color: var(--accent);
                border-color: var(--accent);
            }
            .list {
                flex: 1;
                min-height: 0;
                overflow: auto;
                padding: 0 var(--space-2) var(--space-2);
            }
            .tree-row {
                display: flex;
                align-items: center;
                gap: var(--space-1);
                width: 100%;
                margin-bottom: var(--space-1);
            }
            .toggle {
                display: inline-flex;
                align-items: center;
                justify-content: center;
                width: 1.25rem;
                height: 1.75rem;
                border: none;
                background: transparent;
                color: var(--text-tertiary);
                cursor: pointer;
                flex-shrink: 0;
            }
            .toggle:disabled {
                visibility: hidden;
                cursor: default;
            }
            .toggle.expanded platform-icon {
                transform: rotate(90deg);
            }
            .item {
                display: flex;
                align-items: center;
                gap: var(--space-2);
                flex: 1;
                min-width: 0;
                padding: var(--space-2) var(--space-3);
                border: 1px solid transparent;
                border-radius: var(--radius-lg);
                background: transparent;
                color: var(--text-primary);
                font-size: var(--text-sm);
                font-weight: 500;
                text-align: left;
                cursor: pointer;
                transition: var(--motion-transition-interactive);
            }
            .item:hover {
                background: var(--glass-solid-subtle);
            }
            .item.active {
                background: var(--documents-selected-bg, var(--accent-subtle));
                border-color: var(--documents-selected-stroke, var(--accent));
                color: var(--documents-selected-text, var(--accent));
                font-weight: 600;
            }
            .item.drop-target {
                border-color: var(--accent);
                background: var(--accent-subtle);
            }
            .item-label {
                flex: 1;
                min-width: 0;
                overflow: hidden;
                text-overflow: ellipsis;
                white-space: nowrap;
            }
            .count {
                font-size: var(--text-xs);
                color: var(--text-tertiary);
                flex-shrink: 0;
            }
            .item.active .count {
                color: inherit;
                opacity: 0.8;
            }
            .rag-badge {
                display: inline-flex;
                color: var(--accent);
                flex-shrink: 0;
            }
            .row-actions {
                display: inline-flex;
                gap: var(--space-1);
                opacity: 0;
                flex-shrink: 0;
            }
            .tree-row:hover .row-actions {
                opacity: 1;
            }
            .mini-btn {
                display: inline-flex;
                align-items: center;
                justify-content: center;
                width: 1.5rem;
                height: 1.5rem;
                border: 1px solid var(--glass-border-medium);
                border-radius: var(--radius-md);
                background: var(--glass-solid-subtle);
                color: var(--text-secondary);
                cursor: pointer;
            }
            .mini-btn:hover {
                color: var(--accent);
                border-color: var(--accent);
            }
            .children {
                margin-left: var(--documents-tree-indent, 0.75rem);
            }
            .empty-tree {
                padding: var(--space-3) var(--space-3) var(--space-2);
                font-size: var(--text-sm);
                color: var(--text-tertiary);
            }
        `,
    ];

    constructor() {
        super();
        this.catalogs = [];
        this.activeCatalogId = '';
        this.expandedCatalogIds = [];
        this._dropTargetCatalogId = '';
        this._contextMenu = null;
        this._onDocumentClick = this._onDocumentClick.bind(this);
    }

    connectedCallback() {
        super.connectedCallback();
        document.addEventListener('click', this._onDocumentClick);
    }

    disconnectedCallback() {
        document.removeEventListener('click', this._onDocumentClick);
        super.disconnectedCallback();
    }

    _onDocumentClick() {
        this._hideContextMenu();
    }

    _catalogExpanded(catalogId) {
        return Array.isArray(this.expandedCatalogIds) && this.expandedCatalogIds.includes(catalogId);
    }

    _toggleCatalog(catalogId, hasChildren) {
        if (!hasChildren) return;
        this.emit('toggle-catalog', {
            catalogId,
            expanded: !this._catalogExpanded(catalogId),
        });
    }

    _selectCatalog(catalogId) {
        if (typeof catalogId !== 'string' || catalogId.length === 0) return;
        this.emit('select-catalog', { catalogId });
    }

    _createCatalog(parentCatalogId) {
        this.emit('create-catalog', { parentCatalogId: parentCatalogId || null });
    }

    _showContextMenu(clientX, clientY, catalog, hasChildCatalogs) {
        const hostRect = this.getBoundingClientRect();
        const menuWidth = 200;
        const menuHeight = 180;
        const x = Math.min(Math.max(clientX - hostRect.left, 8), hostRect.width - menuWidth);
        const y = Math.min(Math.max(clientY - hostRect.top, 8), hostRect.height - menuHeight);
        this._contextMenu = { x, y, catalog, hasChildCatalogs };
        this.requestUpdate();
    }

    _hideContextMenu() {
        if (this._contextMenu !== null) {
            this._contextMenu = null;
            this.requestUpdate();
        }
    }

    _openContextMenuFromEvent(e, catalog, hasChildCatalogs) {
        e.preventDefault();
        e.stopPropagation();
        this._showContextMenu(e.clientX, e.clientY, catalog, hasChildCatalogs);
    }

    _openContextMenuFromButton(e, catalog, hasChildCatalogs) {
        e.preventDefault();
        e.stopPropagation();
        const rect = e.currentTarget.getBoundingClientRect();
        this._showContextMenu(rect.right, rect.bottom, catalog, hasChildCatalogs);
    }

    _onContextAction(e) {
        const action = e.detail && e.detail.action;
        const catalog = e.detail && e.detail.catalog;
        this._hideContextMenu();
        if (typeof action !== 'string' || !catalog) {
            return;
        }
        this.emit('catalog-action', { action, catalog });
    }

    _onCatalogDragOver(e, catalogId) {
        e.preventDefault();
        this._dropTargetCatalogId = catalogId;
        this.requestUpdate();
    }

    _onCatalogDragLeave(e, catalogId) {
        e.preventDefault();
        if (this._dropTargetCatalogId === catalogId) {
            this._dropTargetCatalogId = '';
            this.requestUpdate();
        }
    }

    _onCatalogDrop(e, catalog) {
        e.preventDefault();
        e.stopPropagation();
        this._dropTargetCatalogId = '';
        const bindingId = e.dataTransfer && e.dataTransfer.getData('application/x-office-binding-id');
        if (typeof bindingId !== 'string' || bindingId.length === 0) return;
        this.emit('move-to-catalog', {
            bindingId,
            catalogId: catalog.catalog_id,
        });
    }

    _renderCatalogNode(catalog, catalogChildrenMap, depth) {
        const childCatalogs = catalogChildrenMap.get(catalog.catalog_id) || [];
        const hasChildren = childCatalogs.length > 0;
        const expanded = this._catalogExpanded(catalog.catalog_id);
        const active = catalog.catalog_id === this.activeCatalogId;
        const dropTarget = this._dropTargetCatalogId === catalog.catalog_id;
        const ragEnabled = catalog.rag_index_enabled === true;
        return html`
            <div class="tree-row" style="padding-left: ${depth * 12}px">
                <button
                    class="toggle ${expanded ? 'expanded' : ''}"
                    type="button"
                    ?disabled=${!hasChildren}
                    @click=${() => this._toggleCatalog(catalog.catalog_id, hasChildren)}
                >
                    <platform-icon name="chevron-right" size="12"></platform-icon>
                </button>
                <button
                    class="item ${active ? 'active' : ''} ${dropTarget ? 'drop-target' : ''}"
                    type="button"
                    role="treeitem"
                    @click=${() => this._selectCatalog(catalog.catalog_id)}
                    @contextmenu=${(e) => this._openContextMenuFromEvent(e, catalog, hasChildren)}
                    @dragover=${(e) => this._onCatalogDragOver(e, catalog.catalog_id)}
                    @dragleave=${(e) => this._onCatalogDragLeave(e, catalog.catalog_id)}
                    @drop=${(e) => this._onCatalogDrop(e, catalog)}
                >
                    <platform-icon name="folder" size="16"></platform-icon>
                    <span class="item-label">${catalog.title}</span>
                    ${ragEnabled ? html`
                        <span class="rag-badge" title=${this.t('catalog_context_menu.rag')}>
                            <platform-icon name="search" size="12"></platform-icon>
                        </span>
                    ` : null}
                    <span class="count">${catalog.file_count}</span>
                </button>
                <div class="row-actions">
                    <button
                        class="mini-btn"
                        type="button"
                        title=${this.t('tree.newSubcatalog')}
                        @click=${(e) => { e.stopPropagation(); this._createCatalog(catalog.catalog_id); }}
                    >
                        <platform-icon name="plus" size="12"></platform-icon>
                    </button>
                    ${catalog.is_owner === true ? html`
                        <button
                            class="mini-btn"
                            type="button"
                            title=${this.t('tree.catalogMenu')}
                            @click=${(e) => this._openContextMenuFromButton(e, catalog, hasChildren)}
                        >
                            <platform-icon name="more-vertical" size="12"></platform-icon>
                        </button>
                    ` : null}
                </div>
            </div>
            ${expanded ? html`
                <div class="children">
                    ${childCatalogs.map((child) => this._renderCatalogNode(child, catalogChildrenMap, depth + 1))}
                </div>
            ` : null}
        `;
    }

    render() {
        const items = Array.isArray(this.catalogs) ? this.catalogs : [];
        const catalogChildrenMap = _groupByParent(items, 'parent_catalog_id', 'catalog_id');
        const roots = catalogChildrenMap.get('') || [];
        const menu = this._contextMenu;
        return html`
            <div class="head">
                <span class="head-title">${this.t('explorer.catalogsTitle')}</span>
                <div class="head-actions">
                    <button class="head-btn" type="button" title=${this.t('catalogs.create')} @click=${() => this._createCatalog(null)}>
                        <platform-icon name="plus" size="14"></platform-icon>
                    </button>
                </div>
            </div>
            <div class="list" role="tree">
                ${roots.length === 0 ? html`
                    <div class="empty-tree">${this.t('explorer.noCatalogsInline')}</div>
                ` : roots.map((catalog) => this._renderCatalogNode(catalog, catalogChildrenMap, 0))}
            </div>
            <office-catalog-context-menu
                .x=${menu ? menu.x : 0}
                .y=${menu ? menu.y : 0}
                .catalog=${menu ? menu.catalog : null}
                ?has-child-catalogs=${menu ? menu.hasChildCatalogs : false}
                .visible=${menu !== null}
                @ctx-action=${this._onContextAction}
            ></office-catalog-context-menu>
        `;
    }
}

customElements.define('office-explorer-tree', OfficeExplorerTree);
