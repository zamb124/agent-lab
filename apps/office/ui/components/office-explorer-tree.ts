/**
 * office-explorer-tree — nested catalogs for Documents explorer.
 */

import { html, css } from 'lit';
import { PlatformElement } from '@platform/lib/platform-element/index.js';
import '@platform/lib/components/platform-icon.js';
import './office-catalog-context-menu.js';
import type {CSSResultGroup, PropertyDeclarations, TemplateResult} from 'lit';
import '@platform/lib/components/platform-empty-state.js';

interface CatalogRecord {
    catalog_id: string;
    parent_catalog_id?: string | null;
    title?: unknown;
    file_count?: unknown;
    is_owner?: unknown;
    rag_index_enabled?: unknown;
    [key: string]: unknown;
}

function _groupByParent(items: CatalogRecord[], parentKey: string, idKey: string): Map<string, CatalogRecord[]> {
    const map = new Map<string, CatalogRecord[]>();
    for (const item of items) {
        const parentId = item[parentKey];
        const bucketKey = typeof parentId === 'string' && parentId.length > 0 ? parentId : '';
        if (!map.has(bucketKey)) {
            map.set(bucketKey, []);
        }
        const bucket = map.get(bucketKey);
        if (bucket === undefined) {
            throw new Error('office-explorer-tree: catalog bucket missing');
        }
        bucket.push(item);
    }
    return map;
}

export class OfficeExplorerTree extends PlatformElement {
    static i18nNamespace = 'documents';

    static override properties: PropertyDeclarations = {
        catalogs: { type: Array },
        activeCatalogId: { type: String, attribute: 'active-catalog-id' },
        expandedCatalogIds: { type: Array, attribute: false },
    }
    declare catalogs: CatalogRecord[];
    declare activeCatalogId: string;
    declare expandedCatalogIds: string[];

    static override styles: CSSResultGroup = [
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
                width: 1.5rem;
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
            .treeitem {
                display: flex;
                align-items: center;
                gap: var(--space-1);
                flex: 1;
                min-width: 0;
                padding: var(--space-2) var(--space-3);
                border: 1px solid transparent;
                border-radius: var(--radius-lg);
                background: transparent;
                color: var(--text-primary);
                font-size: var(--text-sm);
                font-weight: 500;
                transition: var(--motion-transition-interactive);
            }
            .treeitem:hover {
                background: var(--glass-solid-subtle);
            }
            .treeitem.active {
                background: var(--documents-selected-bg);
                border-color: var(--documents-selected-stroke);
                color: var(--documents-selected-text);
                font-weight: 600;
            }
            .treeitem.drop-target {
                border-color: var(--accent);
                background: var(--accent-subtle);
            }
            .item-main {
                display: flex;
                align-items: center;
                gap: var(--space-2);
                flex: 1;
                min-width: 0;
                padding: 0;
                border: none;
                background: transparent;
                color: inherit;
                font-size: inherit;
                font-weight: inherit;
                text-align: left;
                cursor: pointer;
            }
            .item-label {
                flex: 1;
                min-width: 0;
                overflow: hidden;
                text-overflow: ellipsis;
                white-space: nowrap;
            }
            .item-main .count {
                font-size: var(--text-xs);
                color: var(--text-tertiary);
                flex-shrink: 0;
            }
            .treeitem.active .item-main .count {
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
            .treeitem:hover .row-actions,
            .treeitem:focus-within .row-actions {
                opacity: 1;
            }
            .mini-btn {
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
            .mini-btn:hover {
                color: var(--accent);
                border-color: var(--accent);
            }
            .children {
                margin-left: var(--documents-tree-indent, 0.75rem);
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
        this._onDocumentClick = () => this._hideContextMenu();
    }
    private _dropTargetCatalogId: string;
    private _contextMenu: { x: number; y: number; catalog: CatalogRecord; hasChildCatalogs: boolean } | null;
    private _onDocumentClick: () => void;


    override connectedCallback(): void {
        super.connectedCallback();
        this.useDomEvent(document, 'click', this._onDocumentClick);
    }


    private _onDocumentClickHandler() {
        this._hideContextMenu();
    }

    private _catalogExpanded(catalogId: string) {
        return Array.isArray(this.expandedCatalogIds) && this.expandedCatalogIds.includes(catalogId);
    }

    private _toggleCatalog(catalogId: string, hasChildren: boolean) {
        if (!hasChildren) return;
        this.emit('toggle-catalog', {
            catalogId,
            expanded: !this._catalogExpanded(catalogId),
        });
    }

    private _selectCatalog(catalogId: string) {
        if (typeof catalogId !== 'string' || catalogId.length === 0) return;
        this.emit('select-catalog', { catalogId });
    }

    private _createCatalog(parentCatalogId: string | null) {
        const parentId = parentCatalogId === null || parentCatalogId.length === 0 ? null : parentCatalogId;
        this.emit('create-catalog', { parentCatalogId: parentId });
    }

    private _showContextMenu(clientX: number, clientY: number, catalog: CatalogRecord, hasChildCatalogs: boolean) {
        const hostRect = this.getBoundingClientRect();
        const menuWidth = 200;
        const menuHeight = 180;
        const x = Math.min(Math.max(clientX - hostRect.left, 8), hostRect.width - menuWidth);
        const y = Math.min(Math.max(clientY - hostRect.top, 8), hostRect.height - menuHeight);
        this._contextMenu = { x, y, catalog, hasChildCatalogs };
        this.requestUpdate();
    }

    private _hideContextMenu() {
        if (this._contextMenu !== null) {
            this._contextMenu = null;
            this.requestUpdate();
        }
    }

    private _openContextMenuFromEvent(e: MouseEvent, catalog: CatalogRecord, hasChildCatalogs: boolean) {
        e.preventDefault();
        e.stopPropagation();
        this._showContextMenu(e.clientX, e.clientY, catalog, hasChildCatalogs);
    }

    private _openContextMenuFromButton(e: MouseEvent, catalog: CatalogRecord, hasChildCatalogs: boolean) {
        e.preventDefault();
        e.stopPropagation();
        const target = e.currentTarget;
        if (!(target instanceof HTMLElement)) {
            throw new Error('office-explorer-tree: context menu target required');
        }
        const rect = target.getBoundingClientRect();
        this._showContextMenu(rect.right, rect.bottom, catalog, hasChildCatalogs);
    }

    private _onContextAction(e: CustomEvent<{ action?: unknown; catalog?: unknown }>) {
        const action = e.detail && e.detail.action;
        const catalog = e.detail && e.detail.catalog;
        this._hideContextMenu();
        if (typeof action !== 'string' || !catalog) {
            return;
        }
        this.emit('catalog-action', { action, catalog });
    }

    private _onCatalogDragOver(e: DragEvent, catalogId: string) {
        e.preventDefault();
        this._dropTargetCatalogId = catalogId;
        this.requestUpdate();
    }

    private _onCatalogDragLeave(e: DragEvent, catalogId: string) {
        e.preventDefault();
        if (this._dropTargetCatalogId === catalogId) {
            this._dropTargetCatalogId = '';
            this.requestUpdate();
        }
    }

    private _onCatalogDrop(e: DragEvent, catalog: CatalogRecord) {
        e.preventDefault();
        e.stopPropagation();
        this._dropTargetCatalogId = '';
        const fileId = e.dataTransfer && e.dataTransfer.getData('application/x-office-file-id');
        if (typeof fileId !== 'string' || fileId.length === 0) return;
        this.emit('move-to-catalog', {
            fileId,
            catalogId: catalog.catalog_id,
        });
    }

    private _renderCatalogNode(catalog: CatalogRecord, catalogChildrenMap: Map<string, CatalogRecord[]>, depth: number): TemplateResult {
        const storedChildren = catalogChildrenMap.get(catalog.catalog_id);
        const childCatalogs = storedChildren === undefined ? [] : storedChildren;
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
                    <platform-icon name="chevron-right" size="14"></platform-icon>
                </button>
                <div
                    class="treeitem ${active ? 'active' : ''} ${dropTarget ? 'drop-target' : ''}"
                    role="treeitem"
                    @contextmenu=${(e: MouseEvent) => this._openContextMenuFromEvent(e, catalog, hasChildren)}
                    @dragover=${(e: DragEvent) => this._onCatalogDragOver(e, catalog.catalog_id)}
                    @dragleave=${(e: DragEvent) => this._onCatalogDragLeave(e, catalog.catalog_id)}
                    @drop=${(e: DragEvent) => this._onCatalogDrop(e, catalog)}
                >
                    <button
                        class="item-main"
                        type="button"
                        @click=${() => this._selectCatalog(catalog.catalog_id)}
                    >
                        <platform-icon name="folder" size="16"></platform-icon>
                        <span class="item-label">${catalog.title}</span>
                        ${ragEnabled ? html`
                            <span class="rag-badge" title=${this.t('catalog_context_menu.rag')}>
                                <platform-icon name="search" size="12"></platform-icon>
                            </span>
                        ` : null}
                        <span class="count">${typeof catalog.file_count === 'number' ? catalog.file_count : 0}</span>
                    </button>
                    <div class="row-actions">
                        <button
                            class="mini-btn"
                            type="button"
                            title=${this.t('tree.newSubcatalog')}
                            @click=${(e: MouseEvent) => { e.stopPropagation(); this._createCatalog(catalog.catalog_id); }}
                        >
                            <platform-icon name="plus" size="14"></platform-icon>
                        </button>
                        ${catalog.is_owner === true ? html`
                            <button
                                class="mini-btn"
                                type="button"
                                title=${this.t('tree.catalogMenu')}
                                @click=${(e: MouseEvent) => this._openContextMenuFromButton(e, catalog, hasChildren)}
                            >
                                <platform-icon name="more-vertical" size="14"></platform-icon>
                            </button>
                        ` : null}
                    </div>
                </div>
            </div>
            ${expanded ? html`
                <div class="children">
                    ${childCatalogs.map((child: CatalogRecord) => this._renderCatalogNode(child, catalogChildrenMap, depth + 1))}
                </div>
            ` : null}
        `;
    }

    override render(): TemplateResult {
        const items = Array.isArray(this.catalogs) ? this.catalogs : [];
        const catalogChildrenMap = _groupByParent(items, 'parent_catalog_id', 'catalog_id');
        const storedRoots = catalogChildrenMap.get('');
        const roots = storedRoots === undefined ? [] : storedRoots;
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
                    <platform-empty-state icon="folder" title=${this.t('explorer.noCatalogsInline')}></platform-empty-state>
                ` : roots.map((catalog: CatalogRecord) => this._renderCatalogNode(catalog, catalogChildrenMap, 0))}
            </div>
            <office-catalog-context-menu
                .x=${menu ? menu.x : 0}
                .y=${menu ? menu.y : 0}
                .catalog=${menu ? menu.catalog : null}
                ?has-child-catalogs=${menu ? menu.hasChildCatalogs : false}
                .visible=${menu !== null}
                @ctx-action=${this._onContextAction}
                @ctx-dismiss=${() => this._hideContextMenu()}
            ></office-catalog-context-menu>
        `;
    }
}

customElements.define('office-explorer-tree', OfficeExplorerTree);
