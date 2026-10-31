/**
 * Боковая панель базы знаний: выбор пространства и дерево страниц.
 *
 * NS-селектор — `useResource('wiki/namespaces', { autoload: true })`.
 * Режим «все пространства» запрещён (как в Documents): при `all` или
 * неизвестном имени автоматически выбирается первый workspace.
 *
 * Дерево строит `platform-tree`; здесь только доменная часть — превращение
 * страниц в узлы, фильтр по названию, создание и перемещение.
 *
 * Поиск фильтрует дерево, а не заменяет его списком: так видно, в каком
 * разделе лежит найденная страница. Поэтому вместе с совпадениями
 * показываются их родители.
 */

import { html, css } from 'lit';
import { PlatformElement } from '@platform/lib/platform-element/index.js';
import { isPlainRecord } from '@platform/lib/events/payload.js';
import type { SelectController } from '@platform/lib/events/select-controller.js';
import type { OpController, ResourceController } from '@platform/lib/base/use-resource.js';
import type { ResourceItem } from '@platform/lib/events/factories/resource-collection.js';

interface WikiPageItem extends ResourceItem {
    wiki_page_id?: unknown;
    parent_page_id?: unknown;
    title?: unknown;
    icon?: unknown;
    has_children?: unknown;
    updated_at?: unknown;
    namespace?: unknown;
}

interface WikiTreeNode {
    id: unknown;
    parent_id: unknown;
    label: unknown;
    emoji: unknown;
    icon: string;
    has_children: unknown;
}

interface WikiSidebarMenuItem {
    id: string;
    label?: string;
    icon?: string;
    kind?: string;
    danger?: boolean;
}

import { CoreEvents } from '@platform/lib/events/contract.js';
import {
    getPlatformNamespaceSidebarSelection,
    setPlatformNamespaceSelection,
} from '@platform/lib/utils/platform-namespace.js';
import { readShellSidebarCollapsed } from '@platform/lib/utils/shell-sidebar-preference.js';
import { platformStorageKey } from '@platform/lib/utils/storage-keys.js';
import { storageGet, storageSetJson } from '@platform/lib/utils/platform-storage.js';
import { platformConfirm } from '@platform/lib/components/platform-confirm-modal.js';
import '@platform/lib/components/layout/platform-service-sidebar.js';
import '@platform/lib/components/layout/platform-sidebar-namespace-select.js';
import '@platform/lib/components/platform-deployment-version.js';
import '@platform/lib/components/platform-icon.js';
import '@platform/lib/components/platform-empty-state.js';
import '@platform/lib/components/platform-notification-manager.js';
import '@platform/lib/components/platform-tree.js';
import '@platform/lib/components/platform-user.js';

function missingAsEmpty(value: unknown): string {
    if (value === undefined || value === null) return '';
    return String(value);
}

function isWikiPageItem(value: unknown): value is WikiPageItem {
    return isPlainRecord(value);
}

function recentCollapsed(stored: string): boolean {
    const parsed: unknown = JSON.parse(stored);
    if (!isPlainRecord(parsed)) {
        throw new Error(`wiki-sidebar: битое состояние recent ${stored}`);
    }
    const collapsed = parsed.collapsed;
    if (typeof collapsed !== 'boolean') {
        throw new Error(`wiki-sidebar: битое состояние recent ${stored}`);
    }
    return collapsed;
}

function createdPageId(value: unknown): string | null {
    if (!isPlainRecord(value)) {
        return null;
    }
    const page = value.page;
    if (!isPlainRecord(page)) {
        return null;
    }
    const pageId = page.wiki_page_id;
    return typeof pageId === 'string' && pageId !== '' ? pageId : null;
}


const RECENT_LIMIT = 5;
const RECENT_STORAGE_KEY = platformStorageKey('wiki', 'sidebar.recent');

export class WikiSidebar extends PlatformElement {
    static i18nNamespace = 'wiki';

    declare activePageId: string;
    declare collapsed: boolean;
    declare mobileOpen: boolean;
    declare _filter: string;
    declare _recentCollapsed: boolean;
    private _pages: ResourceController;
    private _createPage: OpController;
    private _movePage: OpController;
    private _deletePage: OpController;
    private _namespaces: ResourceController;
    private _authSelect: SelectController<{ company_id?: unknown } | null | undefined>;

    static override properties = {
        activePageId: { type: String, attribute: 'active-page-id' },
        collapsed: { type: Boolean, reflect: true },
        mobileOpen: { type: Boolean, attribute: 'mobile-open' },
        _filter: { state: true },
        _recentCollapsed: { state: true },
    };

    static override styles = [
        PlatformElement.styles,
        css`
            :host {
                display: block;
                height: 100%;
            }

            .tools {
                display: flex;
                align-items: center;
                gap: var(--space-2);
                padding: var(--space-2) var(--space-3);
            }

            .search {
                flex: 1;
                min-width: 0;
                min-height: 30px;
                padding: 0 var(--space-2);
                border: 1px solid var(--glass-border-subtle);
                border-radius: var(--radius-sm);
                background: var(--wiki-surface-muted);
                color: var(--text-primary);
                font-family: inherit;
                font-size: var(--text-sm);
            }

            .search:focus {
                outline: none;
                border-color: var(--wiki-accent);
            }

            .create-btn {
                flex-shrink: 0;
                display: inline-flex;
                align-items: center;
                justify-content: center;
                width: 30px;
                height: 30px;
                border: 1px solid var(--glass-border-subtle);
                border-radius: var(--radius-sm);
                background: var(--wiki-accent-soft);
                color: var(--wiki-accent);
                cursor: pointer;
            }

            .create-btn:hover {
                border-color: var(--wiki-accent);
            }

            .section-title {
                padding: var(--space-3) var(--space-3) var(--space-1);
                color: var(--text-tertiary);
                font-size: var(--text-xs);
                font-weight: var(--font-semibold);
                letter-spacing: var(--tracking-wide);
                text-transform: uppercase;
            }

            .section-toggle {
                display: flex;
                align-items: center;
                gap: var(--space-1);
                width: 100%;
                margin: 0;
                padding: var(--space-3) var(--space-3) var(--space-1);
                border: none;
                background: transparent;
                color: var(--text-tertiary);
                font-family: inherit;
                font-size: var(--text-xs);
                font-weight: var(--font-semibold);
                letter-spacing: var(--tracking-wide);
                text-transform: uppercase;
                text-align: left;
                cursor: pointer;
            }

            .section-toggle:hover {
                color: var(--text-secondary);
            }

            .section-toggle platform-icon {
                flex-shrink: 0;
                transition: transform var(--motion-duration-micro) ease;
            }

            .section-toggle[aria-expanded='false'] platform-icon {
                transform: rotate(-90deg);
            }

            .recent {
                display: flex;
                flex-direction: column;
                padding: 0 var(--space-2);
            }

            .recent-item {
                display: flex;
                align-items: center;
                gap: var(--space-2);
                padding: 5px var(--space-2);
                border: none;
                border-radius: var(--radius-sm);
                background: transparent;
                color: var(--text-secondary);
                font-family: inherit;
                font-size: var(--text-sm);
                text-align: left;
                cursor: pointer;
                overflow: hidden;
                text-overflow: ellipsis;
                white-space: nowrap;
            }

            .recent-item:hover {
                background: var(--wiki-surface-muted);
                color: var(--text-primary);
            }

            .tree-wrap {
                flex: 1;
                min-height: 0;
                overflow-y: auto;
                padding: 0 var(--space-2) var(--space-4);
            }

            platform-empty-state { padding: var(--space-4) var(--space-3); }

            /* В свёрнутой полосе 72px дерево и селектор пространства не читаются:
               оставляем только логотип, пользователя и кнопку разворота. */
            platform-service-sidebar[collapsed] platform-sidebar-namespace-select,
            platform-service-sidebar[collapsed] .tools,
            platform-service-sidebar[collapsed] .section-title,
            platform-service-sidebar[collapsed] .section-toggle,
            platform-service-sidebar[collapsed] .recent,
            platform-service-sidebar[collapsed] .tree-wrap,
            platform-service-sidebar[collapsed] .empty,
            platform-service-sidebar[collapsed] platform-deployment-version {
                display: none;
            }
        `,
    ];

    constructor() {
        super();
        this.activePageId = '';
        this.collapsed = readShellSidebarCollapsed();
        this.mobileOpen = false;
        this._filter = '';
        this._recentCollapsed = this._readRecentCollapsed();
        this._pages = this.useResource('wiki/pages', { autoload: true });
        this._createPage = this.useOp('wiki/page_create');
        this._movePage = this.useOp('wiki/page_move');
        this._deletePage = this.useOp('wiki/page_delete');
        this._authSelect = this.select((state) => state.auth.user);
        this._namespaces = this.useResource('wiki/namespaces', { autoload: true });
        this._treeMenuItems = this._treeMenuItems.bind(this);
        this.useEvent(CoreEvents.UI_NAMESPACE_CHANGED, () => {
            this._pages.load();
        });
    }

    private _readRecentCollapsed(): boolean {
        const stored = storageGet(RECENT_STORAGE_KEY);
        if (stored === null) {
            return false;
        }
        const parsedCollapsed = recentCollapsed(stored);
        return parsedCollapsed;
    }

    private _persistRecentCollapsed() {
        storageSetJson(RECENT_STORAGE_KEY, { collapsed: this._recentCollapsed });
    }

    private _toggleRecent() {
        this._recentCollapsed = !this._recentCollapsed;
        this._persistRecentCollapsed();
    }

    private _companyId(): string {
        const user = this._authSelect.value;
        return user && typeof user.company_id === 'string' ? user.company_id : '';
    }

    /** Страницы пространства как узлы дерева. */
    private _nodes(): WikiTreeNode[] {
        const pages: WikiPageItem[] = [];
        for (const item of this._pages.items) {
            if (!isWikiPageItem(item)) {
                throw new Error('wiki-sidebar: page item must be an object');
            }
            pages.push(item);
        }
        const visible = this._filter.trim() === '' ? pages : this._filteredPages(pages);
        return visible.map((page: WikiPageItem) => ({
            id: page.wiki_page_id,
            parent_id: page.parent_page_id,
            label: page.title === '' ? this.t('page.untitled') : page.title,
            emoji: page.icon === '' ? undefined : page.icon,
            icon: 'file',
            has_children: page.has_children,
        }));
    }

    /** Совпадения плюс их предки: иначе найденная страница потеряет ветку. */
    private _filteredPages(pages: WikiPageItem[]): WikiPageItem[] {
        const query = this._filter.trim().toLowerCase();
        const byId = new Map(pages.map((page) => [page.wiki_page_id, page]));
        const keep = new Set<unknown>();
        for (const page of pages) {
            if (!missingAsEmpty(page.title).toLowerCase().includes(query)) {
                continue;
            }
            keep.add(page.wiki_page_id);
            let parentId: unknown = page.parent_page_id;
            while (parentId && !keep.has(parentId)) {
                keep.add(parentId);
                const parent = byId.get(parentId);
                parentId = parent ? parent.parent_page_id : null;
            }
        }
        return pages.filter((page) => keep.has(page.wiki_page_id));
    }

    private _recentPages(): WikiPageItem[] {
        return [...this._pages.items]
            .sort((left, right) => String(right.updated_at).localeCompare(String(left.updated_at)))
            .slice(0, RECENT_LIMIT);
    }

    private _namespaceConfig(): { values: { value: string; label: string }[] } {
        const items = this._namespaces.items;
        const values = items.map((namespace: ResourceItem) => ({ value: missingAsEmpty(namespace.name), label: missingAsEmpty(namespace.name) }));
        return { values };
    }

    private _namespaceValue(): string {
        const selection = getPlatformNamespaceSidebarSelection(this._companyId());
        const items = this._namespaces.items;
        if (selection !== 'all' && items.some((namespace: ResourceItem) => namespace.name === selection)) {
            return selection;
        }
        const first = items[0];
        return first ? missingAsEmpty(first.name) : '';
    }

    /**
     * Wiki не умеет режим «все пространства»: страница всегда в одном NS.
     * Если в storage `all` или чужой namespace (из CRM), фиксируем workspace из списка.
     */
    private _ensureExplicitNamespace(items: readonly ResourceItem[], sidebarSel: string, companyId: string): void {
        if (companyId === '') {
            return;
        }
        if (!Array.isArray(items) || items.length === 0) {
            return;
        }
        const first = items[0];
        if (!first || typeof first.name !== 'string' || first.name.length === 0) {
            return;
        }
        if (sidebarSel === 'all') {
            setPlatformNamespaceSelection(companyId, first.name);
            return;
        }
        if (!items.some((namespace: ResourceItem) => namespace.name === sidebarSel)) {
            setPlatformNamespaceSelection(companyId, first.name);
        }
    }

    private _onNamespaceChange(event: CustomEvent<{ value?: unknown }>) {
        const companyId = this._companyId();
        const name = missingAsEmpty(event.detail.value).trim();
        if (companyId === '' || name === '') {
            return;
        }
        setPlatformNamespaceSelection(companyId, name);
    }

    private _onFilterInput(event: Event) {
        const target = event.target;
        if (!(target instanceof HTMLInputElement)) {
            throw new Error('wiki-sidebar: filter input required');
        }
        this._filter = target.value;
    }

    private async _createRootPage(): Promise<void> {
        const pageId = createdPageId(await this._createPage.run({ title: '' }));
        if (typeof pageId !== 'string' || pageId === '') {
            return;
        }
        await this._pages.load();
        this.navigate('wiki_page', { pageId });
    }

    private async _createChildPage(parentPageId: string): Promise<void> {
        const pageId = createdPageId(await this._createPage.run({ title: '', parent_page_id: parentPageId }));
        if (typeof pageId !== 'string' || pageId === '') {
            return;
        }
        await this._pages.load();
        this.navigate('wiki_page', { pageId });
    }

    private _treeMenuItems(): WikiSidebarMenuItem[] {
        return [
            { id: 'open', label: this.t('tree_menu.open'), icon: 'external-link' },
            { id: 'create_child', label: this.t('tree_menu.create_child'), icon: 'plus' },
            { id: 'sep', kind: 'separator' },
            { id: 'move', label: this.t('tree_menu.move'), icon: 'swap-horiz' },
            { id: 'access', label: this.t('tree_menu.access'), icon: 'lock' },
            { id: 'history', label: this.t('tree_menu.history'), icon: 'history' },
            { id: 'sep2', kind: 'separator' },
            { id: 'delete', label: this.t('tree_menu.delete'), icon: 'trash', danger: true },
        ];
    }

    private async _onTreeAction(event: CustomEvent<{ action?: string; id?: unknown }>): Promise<void> {
        const { action } = event.detail;
        const id = missingAsEmpty(event.detail.id);
        if (action === 'open') {
            this.navigate('wiki_page', { pageId: id });
            return;
        }
        if (action === 'create_child') {
            await this._createChildPage(id);
            return;
        }
        if (action === 'move') {
            this.openModal('wiki.move_page', { pageId: id });
            return;
        }
        if (action === 'access') {
            this.openModal('wiki.page_access', { pageId: id });
            return;
        }
        if (action === 'history') {
            this.navigate('wiki_page_history', { pageId: id });
            return;
        }
        if (action === 'delete') {
            const confirmed = await platformConfirm(this.t('page.delete_confirm_body'), {
                title: this.t('page.delete_confirm_title'),
                variant: 'danger',
                confirmVariant: 'danger',
            });
            if (!confirmed) {
                return;
            }
            await this._deletePage.run({ wiki_page_id: id });
            await this._pages.load();
            return;
        }
        throw new Error(`wiki-sidebar: неизвестное действие дерева ${action}`);
    }

    private async _onTreeMove(event: CustomEvent<{ id?: unknown; parent_id?: unknown; position?: string; target_id?: unknown }>): Promise<void> {
        const { id, parent_id: parentId, position, target_id: targetId } = event.detail;
        // «Внутрь» кладёт страницу первой в разделе, «между» — рядом с целью.
        const siblings = this._pages.items.filter((page: WikiPageItem) => page.parent_page_id === parentId);
        const targetIndex = siblings.findIndex((page: WikiPageItem) => page.wiki_page_id === targetId);
        const nextPosition = position === 'inside'
            ? 0
            : Math.max(0, position === 'after' ? targetIndex + 1 : targetIndex);
        await this._movePage.run({
            wiki_page_id: id,
            parent_page_id: parentId,
            position: nextPosition,
        });
        await this._pages.load();
    }

    override render() {
        const items = this._namespaces.items;
        const companyId = this._companyId();
        const sidebarSel = getPlatformNamespaceSidebarSelection(companyId);
        this._ensureExplicitNamespace(items, sidebarSel, companyId);
        const nodes = this._nodes();
        const recent = this._recentPages();
        return html`
            <platform-service-sidebar
                logo-src="/static/core/assets/service_logos/wiki_logo.svg"
                logo-text=${this.t('sidebar.title')}
                width="100%"
                ?logo-opens-services=${true}
                ?collapsed=${this.collapsed}
                ?mobile-open=${this.mobileOpen}
                @collapse-change=${(event: CustomEvent<{ collapsed: boolean }>) => { this.collapsed = event.detail.collapsed; }}
                @mobile-change=${(event: CustomEvent<{ open: boolean }>) => { this.mobileOpen = event.detail.open; }}
            >
                <div slot="header">
                    <platform-sidebar-namespace-select
                        .label=${this.t('sidebar.namespace_label')}
                        .value=${this._namespaceValue()}
                        .config=${this._namespaceConfig()}
                        ?show-edit=${false}
                        @change=${(event: CustomEvent<{ value?: unknown }>) => this._onNamespaceChange(event)}
                    ></platform-sidebar-namespace-select>
                    <div class="tools">
                        <input
                            class="search"
                            type="text"
                            data-canon="search-as-you-type"
                            spellcheck="false"
                            autocomplete="off"
                            aria-label=${this.t('sidebar.search_placeholder')}
                            placeholder=${this.t('sidebar.search_placeholder')}
                            .value=${this._filter}
                            @input=${(event: Event) => this._onFilterInput(event)}
                        />
                        <button
                            class="create-btn"
                            type="button"
                            data-wiki-create-page
                            title=${this.t('sidebar.create_page')}
                            aria-label=${this.t('sidebar.create_page')}
                            @click=${() => this._createRootPage()}
                        >
                            <platform-icon name="plus" size="16"></platform-icon>
                        </button>
                    </div>
                </div>

                ${recent.length > 0 && this._filter === '' ? html`
                    <button
                        class="section-toggle"
                        type="button"
                        data-wiki-recent-toggle
                        aria-expanded=${this._recentCollapsed ? 'false' : 'true'}
                        aria-label=${this._recentCollapsed
                            ? this.t('sidebar.recent_expand')
                            : this.t('sidebar.recent_collapse')}
                        @click=${() => this._toggleRecent()}
                    >
                        <platform-icon name="chevron-down" size="12"></platform-icon>
                        <span>${this.t('sidebar.recent')}</span>
                    </button>
                    ${this._recentCollapsed ? '' : html`
                        <div class="recent">
                            ${recent.map((page) => html`
                                <button
                                    class="recent-item"
                                    type="button"
                                    data-recent-page=${page.wiki_page_id}
                                    @click=${() => this.navigate('wiki_page', { pageId: missingAsEmpty(page.wiki_page_id) })}
                                >
                                    <platform-icon name="clock" size="13"></platform-icon>
                                    <span>${page.title === '' ? this.t('page.untitled') : page.title}</span>
                                </button>
                            `)}
                        </div>
                    `}
                ` : ''}

                <div class="section-title">${this.t('sidebar.pages')}</div>
                <div class="tree-wrap">
                    ${nodes.length === 0
                        ? html`<platform-empty-state
                              icon="book-open"
                              title=${this._filter === '' ? this.t('sidebar.empty') : this.t('sidebar.no_matches')}
                              hint=${this._filter === '' ? this.t('sidebar.empty_hint') : ''}
                          ></platform-empty-state>`
                        : html`<platform-tree
                              .nodes=${nodes}
                              selected-id=${this.activePageId}
                              draggable-nodes
                              aria-label=${this.t('sidebar.pages')}
                              .menuItems=${this._treeMenuItems}
                              @tree-select=${(event: CustomEvent<{ id?: unknown }>) => this.navigate('wiki_page', { pageId: missingAsEmpty(event.detail.id) })}
                              @tree-action=${(event: CustomEvent<{ action?: string; id?: unknown }>) => this._onTreeAction(event)}
                              @tree-move=${(event: CustomEvent<{ id?: unknown; parent_id?: unknown; position?: string; target_id?: unknown }>) => this._onTreeMove(event)}
                          ></platform-tree>`}
                </div>

                <div slot="footer">
                    <platform-user block>
                        <platform-notification-manager slot="user-toolbar"></platform-notification-manager>
                    </platform-user>
                    <platform-deployment-version base-url="/wiki" footer></platform-deployment-version>
                </div>
            </platform-service-sidebar>
        `;
    }
}

customElements.define('wiki-sidebar', WikiSidebar);
