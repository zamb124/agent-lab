/**
 * CRMSidebar — навигация и namespace-селектор сервиса CRM на event-driven каноне.
 *
 * Namespace-селектор: фабрика `crm/namespaces`, выбор через `setPlatformNamespaceSelection`.
 * При выбранном конкретном пространстве основное меню — дерево из
 * `crm_settings.sidebar_navigation`: дети секций заметок / задач / сущностей
 * каждый рендер синхронизируются с каноном (`buildDefaultSidebarNav`), чтобы
 * новые типы и иерархия `parent_type_id` не терялись в старом снимке.
 * Порядок «Все …» — `ensureCrmSidebarNavAllLeavesFirst`, иконки —
 * `enrichSidebarNavWithEntityTypeIcons`.
 * Режим «Все пространства» — плоский список пунктов (notes / entities / tasks / graph).
 * Типы для дерева: GET `crm/entity_types` с `?namespace=…`, если в селекторе выбрано
 * конкретное пространство; в режиме «Все пространства» — без фильтра (типы компании).
 */

import { html, css } from 'lit';
import { PlatformElement } from '@platform/lib/platform-element/index.js';
import { CoreEvents } from '@platform/lib/events/index.js';
import { sidebarStyles, sidebarNavItemStyles } from '@platform/lib/styles/shared/sidebar.styles.js';
import { readShellSidebarCollapsed } from '@platform/lib/utils/shell-sidebar-preference.js';
import {
    getPlatformNamespaceSidebarSelection,
    setPlatformNamespaceSelection,
} from '@platform/lib/utils/platform-namespace.js';
import { PlatformServiceSidebar } from '@platform/lib/components/layout/platform-service-sidebar.js';
import { isPlainRecord } from '@platform/lib/events/payload.js';
import '@platform/lib/components/layout/platform-sidebar-nav-tree.js';
import '@platform/lib/components/platform-icon.js';
import '@platform/lib/components/platform-user.js';
import '@platform/lib/components/platform-deployment-version.js';
import '@platform/lib/components/platform-notification-manager.js';
import '@platform/lib/components/layout/platform-sidebar-namespace-select.js';
import {
    buildDefaultSidebarNav,
    dropCrmSidebarLegacyTopLevelNodes,
    enrichSidebarNavWithEntityTypeIcons,
    ensureCrmSidebarNavAllLeavesFirst,
    mapSidebarNavFromApi,
    mergeCrmSidebarNavMissingGroups,
    replaceCrmSidebarGroupChildrenFromCanonical,
} from '../_helpers/build-default-sidebar-nav.js';
import type {
    CSSResultGroup,
    PropertyDeclarations,
    TemplateResult,
} from 'lit';
import type {
    ResourceController,
} from '@platform/lib/base/use-resource.js';
import type { SelectController } from '@platform/lib/events/select-controller.js';

const PRIMARY_NAV = [
    { route: 'notes', icon: 'list', label_key: 'sidebar.nav.notes' },
    { route: 'entities', icon: 'database', label_key: 'sidebar.nav.entities' },
    { route: 'graph', icon: 'share', label_key: 'sidebar.nav.graph', search: '?view=mindmap' },
];

const ORG_NAV = [
    { route: 'suggests', icon: 'sparkle', label_key: 'sidebar.nav.suggests' },
    { route: 'access_requests', icon: 'lock', label_key: 'sidebar.nav.access_requests' },
    { route: 'namespace_imports', icon: 'ai', label_key: 'sidebar.nav.ai_analysis' },
    { route: 'settings', icon: 'settings', label_key: 'sidebar.nav.settings' },
];

const SETTINGS_ALIASES = new Set(['settings', 'namespaces', 'templates', 'relationship_types']);

/**
 * @param {unknown} user
 * @param {Record<string, string>} selectionByCompany
 * @returns {'all' | string}
 */
function resolveCrmSidebarNamespaceSelection(user: { company_id?: unknown } | null | undefined, selectionByCompany: Record<string, string> | null | undefined): string {
    if (!user || typeof user.company_id !== 'string') {
        return 'all';
    }
    const companyId = user.company_id.trim();
    if (companyId.length === 0) {
        return 'all';
    }
    if (selectionByCompany != null && Object.prototype.hasOwnProperty.call(selectionByCompany, companyId)) {
        const entry = selectionByCompany[companyId];
        if (entry === undefined) {
            throw new Error('crm sidebar: namespace selection missing');
        }
        return entry === 'all' ? 'all' : entry;
    }
    return getPlatformNamespaceSidebarSelection(companyId);
}

/**
 * @param {string} namespaceName
 * @param {Array<Record<string, unknown>>} entityTypesItems
 * @returns {string[]}
 */
function allowedTypeIdsForNamespace(namespaceName: unknown, entityTypesItems: unknown): string[] {
    if (typeof namespaceName !== 'string' || namespaceName.length === 0) {
        throw new Error('allowedTypeIdsForNamespace: namespaceName required');
    }
    const items = Array.isArray(entityTypesItems) ? entityTypesItems : [];
    const out: string[] = [];
    for (const t of items) {
        if (!isPlainRecord(t) || typeof t.type_id !== 'string' || t.type_id.length === 0) {
            continue;
        }
        if (t.namespace !== namespaceName) {
            continue;
        }
        out.push(t.type_id);
    }
    return out;
}

/**
 * @param {string} routeKey
 * @param {string} locationSearch
 * @returns {string}
 */
function crmNavActiveTail(routeKey: unknown, locationSearch: unknown): string {
    if (typeof routeKey !== 'string' || routeKey.length === 0) {
        return '';
    }
    let q = typeof locationSearch === 'string' ? locationSearch : '';
    if (q === '?') {
        q = '';
    }
    if (q.length > 0 && !q.startsWith('?')) {
        throw new Error('crmNavActiveTail: locationSearch must start with ?');
    }
    if (q.length === 0) {
        return routeKey;
    }
    return `${routeKey}${q}`;
}

/**
 * @param {Array<Record<string, unknown>>} nodes
 * @param {string} routeKey
 * @param {string} searchNormalized
 * @returns {string}
 */
function findNavLeafId(nodes: unknown, routeKey: string, searchNormalized: string): string {
    const list = Array.isArray(nodes) ? nodes : [];
    for (const n of list) {
        if (!isPlainRecord(n)) {
            continue;
        }
        const ch = n.children;
        if (Array.isArray(ch) && ch.length > 0) {
            const id = findNavLeafId(ch, routeKey, searchNormalized);
            if (typeof id === 'string' && id.length > 0) {
                return id;
            }
            continue;
        }
        if (typeof n.routeKey !== 'string') {
            continue;
        }
        if (n.routeKey !== routeKey) {
            continue;
        }
        const sch = typeof n.search === 'string' ? n.search : '';
        if (sch === searchNormalized) {
            return typeof n.id === 'string' ? n.id : '';
        }
    }
    return '';
}

export class CRMSidebar extends PlatformElement {
    static i18nNamespace = 'crm';
    declare collapsed: boolean;
    declare mobileOpen: boolean;

    static override styles: CSSResultGroup = [
        PlatformElement.styles,
        sidebarStyles,
        sidebarNavItemStyles,
        css`
            :host { display: block; height: 100%; }

            platform-service-sidebar {
                --sidebar-logo-text-weight: 700;
                --sidebar-logo-text-gradient: var(--crm-main-gradient);
                --sidebar-logo-text-clip: text;
                --sidebar-logo-text-fill: transparent;
                --platform-namespace-add-background: var(--crm-main-gradient);
                --platform-namespace-edit-stroke: var(--crm-stroke);
                --platform-namespace-edit-fg: var(--text-secondary);
                --platform-namespace-edit-hover-bg: var(--crm-selected-bg);
                --platform-namespace-edit-hover-fg: var(--crm-selected-text);
                --platform-namespace-edit-hover-stroke: var(--crm-selected-stroke);
                --sidebar-nav-tree-children-border: none;
            }

            .nav-section { margin-bottom: var(--space-6); }
            .nav-title {
                font-size: 12px;
                font-weight: 600;
                text-transform: uppercase;
                letter-spacing: 0.08em;
                color: var(--text-tertiary);
                margin-bottom: var(--space-3);
                padding: 0 var(--space-3);
            }
            .nav-item {
                display: flex;
                align-items: center;
                gap: var(--space-3);
                padding: var(--space-3);
                margin-bottom: var(--space-1);
                background: transparent;
                border: none;
                border-radius: var(--radius-lg);
                color: var(--text-primary);
                font-size: var(--text-base);
                font-weight: 500;
                cursor: pointer;
                transition: background var(--duration-fast), border-color var(--duration-fast), color var(--duration-fast);
                width: 100%;
                text-align: left;
            }
            .nav-item:hover { background: var(--glass-solid-subtle); }
            .nav-item.active {
                background: var(--crm-selected-bg);
                border: 1px solid var(--crm-selected-stroke);
                color: var(--crm-selected-text);
            }

            .nav-icon-wrapper {
                width: 32px;
                height: 32px;
                display: flex;
                align-items: center;
                justify-content: center;
                border-radius: var(--radius-md);
                border: 1px solid var(--crm-stroke);
                background: var(--crm-surface-muted);
                color: var(--text-secondary);
                flex-shrink: 0;
            }
            .nav-item.active .nav-icon-wrapper {
                border-color: var(--crm-selected-stroke);
                color: var(--crm-selected-text);
                background: var(--crm-selected-bg);
            }
            .nav-label { flex: 1; font-size: var(--text-base); }

            .user-section {
                display: flex;
                flex-direction: column;
                align-items: stretch;
                gap: var(--space-2);
                width: 100%;
                min-width: 0;
            }

            platform-service-sidebar[collapsed] platform-sidebar-namespace-select,
            platform-service-sidebar[collapsed] .nav-label,
            platform-service-sidebar[collapsed] .nav-title { display: none; }
            platform-service-sidebar[collapsed] .nav-item {
                justify-content: center;
                padding: var(--space-2);
            }
            platform-service-sidebar[collapsed] .nav-item:hover { transform: none; }
            platform-service-sidebar[collapsed] .user-section {
                align-items: center;
            }
        `,
    ];

    static override properties: PropertyDeclarations = {
        collapsed: { type: Boolean, reflect: true },
        mobileOpen: { type: Boolean, reflect: true, attribute: 'mobile-open' },
    };

    private _routeKeySel: SelectController<string | null>;
    private _onPopState: () => void;
    private _authSel: SelectController<{ company_id?: unknown } | null | undefined>;
    private _namespaceSelectionByCompany: SelectController<Record<string, string> | undefined>;
    private _namespaces: ResourceController;
    private _entityTypes: ResourceController;

    constructor() {
        super();
        this.collapsed = readShellSidebarCollapsed();
        this.mobileOpen = false;
        this._onPopState = () => this.requestUpdate();
        this._routeKeySel = this.select((s: Record<string, any>) => s.router.routeKey);
        this._authSel = this.select((s: Record<string, any>) => s.auth.user);
        this._namespaceSelectionByCompany = this.select((s: Record<string, any>) => s.ui.namespace.selectionByCompany);
        this._namespaces = this.useResource('crm/namespaces', { autoload: true });
        this._entityTypes = this.useResource('crm/entity_types', { autoload: false });
    }

    override connectedCallback(): void {
        super.connectedCallback();
        if (typeof window !== 'undefined') {
            this.useDomEvent(window, 'popstate', this._onPopState);
        }
        this.useEvent(CoreEvents.ROUTER_ROUTE_CHANGED, () => this.requestUpdate());
        this.useEvent(CoreEvents.UI_NAMESPACE_CHANGED, () => {
            this._reloadEntityTypesForSidebar();
            this.requestUpdate();
        });
        this.useEvent(CoreEvents.AUTH_USER_LOADED, () => this._reloadEntityTypesForSidebar());
        this.useEvent(CoreEvents.AUTH_COMPANY_SWITCHED, () => this._reloadEntityTypesForSidebar());
        this._reloadEntityTypesForSidebar();
    }


    _closeMobileNav() {
        const shell = this.renderRoot.querySelector('platform-service-sidebar');
        if (shell === null) return;
        if (!(shell instanceof PlatformServiceSidebar)) {
            throw new Error('crm sidebar: platform-service-sidebar required');
        }
        shell.closeMobile();
    }

    _navigate(routeKey: string, navigationOptions?: { search?: string }) {
        this.navigate(routeKey, {}, navigationOptions);
        this._closeMobileNav();
    }

    _onNavTreePick(e: CustomEvent) {
        const d = isPlainRecord(e.detail) ? e.detail : null;
        if (!d || typeof d.routeKey !== 'string' || d.routeKey.length === 0) {
            throw new Error('CRMSidebar: pick requires routeKey');
        }
        const rawSearch = typeof d.search === 'string' ? d.search : '';
        if (rawSearch.length > 0 && !rawSearch.startsWith('?')) {
            throw new Error('CRMSidebar: pick.search must start with ?');
        }
        const opts: { search?: string } = {};
        if (rawSearch.length > 0) {
            opts.search = rawSearch;
        }
        this.navigate(d.routeKey, {}, Object.keys(opts).length > 0 ? opts : undefined);
        this._closeMobileNav();
    }

    _namespaceDropdownConfig(items: unknown): { values: { value: string; label: string }[] } {
        if (!Array.isArray(items)) {
            throw new Error('CRMSidebar._namespaceDropdownConfig: items must be an array');
        }
        const values = [{ value: '', label: this.t('sidebar.all_namespaces') }];
        for (const ns of items) {
            if (!isPlainRecord(ns) || typeof ns.name !== 'string' || ns.name.length === 0) {
                throw new Error('CRMSidebar._namespaceDropdownConfig: namespace name required');
            }
            const title = typeof ns.title === 'string' && ns.title.length > 0 ? ns.title : ns.name;
            values.push({ value: ns.name, label: title });
        }
        return { values };
    }

    _onNamespaceChange(event: CustomEvent) {
        const user = this._authSel.value;
        if (!user || typeof user.company_id !== 'string') {
            throw new Error('CRMSidebar: cannot change namespace without active company_id');
        }
        if (!event.detail || typeof event.detail.value !== 'string') {
            throw new Error('CRMSidebar: namespace field expects change detail.value string');
        }
        const value = event.detail.value;
        setPlatformNamespaceSelection(user.company_id, value === '' ? null : value);
    }

    _reloadEntityTypesForSidebar() {
        const user = this._authSel.value;
        const map = this._namespaceSelectionByCompany.value;
        const resolved = resolveCrmSidebarNamespaceSelection(user, map);
        if (resolved === 'all') {
            this._entityTypes.load(null);
            return;
        }
        this._entityTypes.load({ namespace: resolved });
    }

    _openCreateNamespace() {
        this.openModal('crm.namespace', { mode: 'create' });
    }

    _openEditNamespace(name: unknown) {
        if (typeof name !== 'string' || name.length === 0) {
            throw new Error('CRMSidebar._openEditNamespace: name required');
        }
        this.openModal('crm.namespace', { mode: 'edit', name });
    }

    _isActive(route: string) {
        const current = this._routeKeySel.value;
        if (route === 'settings') {
            return typeof current === 'string' && SETTINGS_ALIASES.has(current);
        }
        return current === route;
    }

    _renderNavItem(item: { search?: unknown; route: string; icon: string; label_key: string }) {
        const opts = typeof item.search === 'string' && item.search.length > 0
            ? { search: item.search }
            : undefined;
        return html`
            <button
                class="nav-item ${this._isActive(item.route) ? 'active' : ''}"
                @click=${() => this._navigate(item.route, opts)}
            >
                <span class="nav-icon-wrapper">
                    <platform-icon name=${item.icon} size="18"></platform-icon>
                </span>
                <span class="nav-label">${this.t(item.label_key)}</span>
            </button>
        `;
    }

    /**
     * @param {string} namespaceName
     * @returns {Array<Record<string, unknown>>}
     */
    _sidebarTreeNodesForNamespace(namespaceName: string): Record<string, any>[] {
        const items = this._namespaces.items;
        const nsRow = items.find((row: Record<string, any> | null) => row && row.name === namespaceName);
        const settings = nsRow && isPlainRecord(nsRow.crm_settings) ? nsRow.crm_settings : null;
        const navigation = settings === null ? undefined : settings.sidebar_navigation;
        const rawNav = Array.isArray(navigation) ? navigation : null;
        const fromApi = mapSidebarNavFromApi(rawNav);
        const allowed = allowedTypeIdsForNamespace(namespaceName, this._entityTypes.items);
        const labels = {
            groupNotes: this.t('sidebar.nav_group_notes'),
            groupTasks: this.t('sidebar.nav_group_tasks'),
            groupEntities: this.t('sidebar.nav_group_entities'),
            allNotes: this.t('sidebar.nav_all_notes'),
            allTasks: this.t('sidebar.nav_all_tasks'),
            allEntities: this.t('sidebar.nav_all_entities'),
            groupGraph: this.t('sidebar.nav_group_graph'),
            graphView3d: this.t('graph.view_mode_3d'),
            graphViewMindmap: this.t('graph.view_mode_mindmap'),
        };
        const entityTypesItems = this._entityTypes.items;
        const canonical = buildDefaultSidebarNav({
            allowedTypeIds: allowed,
            entityTypes: entityTypesItems,
            labels,
        });
        let base;
        if (fromApi !== null && fromApi.length > 0) {
            const cleaned = dropCrmSidebarLegacyTopLevelNodes(fromApi);
            const patched = replaceCrmSidebarGroupChildrenFromCanonical(cleaned, canonical);
            base = mergeCrmSidebarNavMissingGroups(patched, canonical);
        } else {
            base = canonical;
        }
        return enrichSidebarNavWithEntityTypeIcons(
            ensureCrmSidebarNavAllLeavesFirst(base, labels),
            entityTypesItems,
        );
    }

    override render(): TemplateResult {
        const user = this._authSel.value;
        const map = this._namespaceSelectionByCompany.value;
        const resolved = resolveCrmSidebarNamespaceSelection(user, map);
        const selectValue = resolved === 'all' ? '' : resolved;
        const items = this._namespaces.items;

        const routeKey = this._routeKeySel.value;
        const locSearch = typeof window !== 'undefined' ? window.location.search : '';
        const searchNorm = typeof locSearch === 'string' ? locSearch : '';
        const activeTail = typeof routeKey === 'string' && routeKey.length > 0
            ? crmNavActiveTail(routeKey, searchNorm)
            : '';

        const treeNodes = selectValue !== ''
            ? this._sidebarTreeNodesForNamespace(selectValue)
            : null;
        const activeItemId = treeNodes !== null && typeof routeKey === 'string' && routeKey.length > 0
            ? findNavLeafId(treeNodes, routeKey, searchNorm)
            : '';
        const navTreeStorageScope =
            selectValue !== '' &&
            user &&
            typeof user.company_id === 'string' &&
            user.company_id.trim().length > 0
                ? `crm:${user.company_id.trim()}:${selectValue}`
                : '';

        return html`
            <platform-service-sidebar
                logo-src="/crm/ui/static/assets/icons/networkle_logo.svg"
                logo-text="NetWorkle"
                ?logo-opens-services=${true}
                ?collapsed=${this.collapsed}
                ?mobile-open=${this.mobileOpen}
                @collapse-change=${(e: CustomEvent<{ collapsed: boolean }>) => { this.collapsed = e.detail.collapsed; }}
                @mobile-change=${(e: CustomEvent<{ open: boolean }>) => { this.mobileOpen = e.detail.open; }}
            >
                <div slot="header">
                    <platform-sidebar-namespace-select
                        .label=${this.t('sidebar.namespace_label')}
                        .value=${selectValue}
                        .config=${this._namespaceDropdownConfig(items)}
                        ?show-edit=${selectValue !== ''}
                        edit-title=${this.t('sidebar.edit_namespace_tooltip')}
                        add-title=${this.t('sidebar.create_namespace_tooltip')}
                        @change=${this._onNamespaceChange}
                        @edit-request=${() => this._openEditNamespace(selectValue)}
                        @add-request=${this._openCreateNamespace}
                    ></platform-sidebar-namespace-select>
                </div>

                ${treeNodes === null ? html`
                    <div class="nav-section">
                        ${PRIMARY_NAV.map((item) => this._renderNavItem(item))}
                    </div>
                ` : html`
                    <div class="nav-section">
                        <platform-sidebar-nav-tree
                            .nodes=${treeNodes}
                            active-item-id=${activeItemId}
                            active-path=${activeTail}
                            storage-scope=${navTreeStorageScope}
                            ?collapsed=${this.collapsed}
                            @pick=${this._onNavTreePick}
                        ></platform-sidebar-nav-tree>
                    </div>
                `}

                <div class="nav-section">
                    <div class="nav-title">${this.t('sidebar.org_section')}</div>
                    ${ORG_NAV.map((item) => this._renderNavItem(item))}
                </div>

                <div slot="footer" class="user-section">
                    <platform-user block>
                        <platform-notification-manager slot="user-toolbar"></platform-notification-manager>
                    </platform-user>
                    <platform-deployment-version base-url="/crm" footer></platform-deployment-version>
                </div>
            </platform-service-sidebar>
        `;
    }
}

customElements.define('crm-sidebar', CRMSidebar);
