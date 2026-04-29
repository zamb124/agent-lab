/**
 * CRMSidebar — навигация и SPACE-селектор сервиса CRM на event-driven каноне.
 *
 * SPACE-селектор: фабрика `crm/namespaces`, выбор через `setPlatformNamespaceSelection`.
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
import '@platform/lib/components/layout/platform-service-sidebar.js';
import '@platform/lib/components/layout/platform-sidebar-nav-tree.js';
import '@platform/lib/components/platform-icon.js';
import '@platform/lib/components/platform-user.js';
import '@platform/lib/components/platform-deployment-version.js';
import '@platform/lib/components/platform-notification-manager.js';
import {
    buildDefaultSidebarNav,
    enrichSidebarNavWithEntityTypeIcons,
    ensureCrmSidebarNavAllLeavesFirst,
    mapSidebarNavFromApi,
    mergeCrmSidebarNavMissingGroups,
    replaceCrmSidebarGroupChildrenFromCanonical,
} from '../utils/build-default-sidebar-nav.js';

const PRIMARY_NAV = [
    { route: 'notes', icon: 'list', label_key: 'sidebar.nav.notes' },
    { route: 'entities', icon: 'database', label_key: 'sidebar.nav.entities' },
    { route: 'tasks', icon: 'check', label_key: 'sidebar.nav.tasks' },
    { route: 'graph', icon: 'share', label_key: 'sidebar.nav.graph' },
];

const ORG_NAV = [
    { route: 'access_requests', icon: 'lock', label_key: 'sidebar.nav.access_requests' },
    { route: 'namespace_imports', icon: 'ai', label_key: 'sidebar.nav.ai_analysis' },
    { route: 'settings', icon: 'settings', label_key: 'sidebar.nav.settings' },
];

const SETTINGS_ALIASES = new Set(['settings', 'spaces', 'templates', 'relationship_types']);

/**
 * @param {unknown} user
 * @param {Record<string, string>} selectionByCompany
 * @returns {'all' | string}
 */
function resolveCrmSidebarNamespaceSelection(user, selectionByCompany) {
    if (!user || typeof user.company_id !== 'string') {
        return 'all';
    }
    const companyId = user.company_id.trim();
    if (companyId.length === 0) {
        return 'all';
    }
    if (Object.prototype.hasOwnProperty.call(selectionByCompany, companyId)) {
        const entry = selectionByCompany[companyId];
        return entry === 'all' ? 'all' : entry;
    }
    return getPlatformNamespaceSidebarSelection(companyId);
}

/**
 * @param {string} nsName
 * @param {Array<Record<string, unknown>>} entityTypesItems
 * @returns {string[]}
 */
function allowedTypeIdsForSpace(nsName, entityTypesItems) {
    if (typeof nsName !== 'string' || nsName.length === 0) {
        throw new Error('allowedTypeIdsForSpace: nsName required');
    }
    const items = Array.isArray(entityTypesItems) ? entityTypesItems : [];
    const out = [];
    for (const t of items) {
        if (!t || typeof t.type_id !== 'string' || t.type_id.length === 0) {
            continue;
        }
        if (t.namespace !== nsName) {
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
function crmNavActiveTail(routeKey, locationSearch) {
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
function findNavLeafId(nodes, routeKey, searchNormalized) {
    const list = Array.isArray(nodes) ? nodes : [];
    for (const n of list) {
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

    static styles = [
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
            }

            .ns-section {
                display: flex;
                align-items: center;
                gap: var(--space-2);
                padding: var(--space-2);
                margin-bottom: var(--space-4);
                background: var(--crm-surface-muted);
                border: 1px solid var(--crm-stroke);
                border-radius: var(--radius-lg);
                width: 100%;
                box-sizing: border-box;
            }
            .ns-label {
                font-size: 10px;
                font-weight: 600;
                text-transform: uppercase;
                letter-spacing: 0.05em;
                color: var(--text-tertiary);
                white-space: nowrap;
                flex-shrink: 0;
            }
            .ns-select {
                flex: 1;
                min-width: 0;
                background: transparent;
                border: none;
                color: var(--text-primary);
                font-size: var(--text-sm);
                font-weight: 500;
                cursor: pointer;
                outline: none;
                padding: var(--space-1) var(--space-2);
                overflow: hidden;
                text-overflow: ellipsis;
            }
            .ns-select option {
                background: var(--crm-surface-elevated);
                color: var(--text-primary);
            }
            .ns-add-btn {
                display: flex;
                align-items: center;
                justify-content: center;
                width: 24px;
                height: 24px;
                border: none;
                background: var(--crm-main-gradient);
                color: var(--text-inverse);
                border-radius: var(--radius-md);
                cursor: pointer;
                transition: transform var(--duration-fast);
                flex-shrink: 0;
            }
            .ns-add-btn:hover { transform: scale(1.05); }
            .ns-edit-btn {
                display: flex;
                align-items: center;
                justify-content: center;
                width: 24px;
                height: 24px;
                border: 1px solid var(--crm-stroke);
                background: transparent;
                color: var(--text-secondary);
                border-radius: var(--radius-md);
                cursor: pointer;
                transition: background var(--duration-fast),
                            color var(--duration-fast),
                            border-color var(--duration-fast);
                flex-shrink: 0;
            }
            .ns-edit-btn:hover {
                background: var(--crm-selected-bg);
                color: var(--crm-selected-text);
                border-color: var(--crm-selected-stroke);
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

            platform-service-sidebar[collapsed] .ns-section,
            platform-service-sidebar[collapsed] .nav-label,
            platform-service-sidebar[collapsed] .nav-title { display: none; }
            platform-service-sidebar[collapsed] .nav-item { justify-content: center; padding: var(--space-3); }
        `,
    ];

    static properties = {
        collapsed: { type: Boolean, reflect: true },
        mobileOpen: { type: Boolean, reflect: true, attribute: 'mobile-open' },
    };

    constructor() {
        super();
        this.collapsed = readShellSidebarCollapsed();
        this.mobileOpen = false;
        this._onPopState = () => this.requestUpdate();
        this._routeKeySel = this.select((s) => s.router.routeKey);
        this._authSel = this.select((s) => s.auth.user);
        this._namespaceSelectionByCompany = this.select((s) => s.ui.namespace.selectionByCompany);
        this._namespaces = this.useResource('crm/namespaces', { autoload: true });
        this._entityTypes = this.useResource('crm/entity_types', { autoload: false });
    }

    connectedCallback() {
        super.connectedCallback();
        if (typeof window !== 'undefined') {
            window.addEventListener('popstate', this._onPopState);
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

    disconnectedCallback() {
        if (typeof window !== 'undefined') {
            window.removeEventListener('popstate', this._onPopState);
        }
        super.disconnectedCallback();
    }

    _navigate(routeKey, navigationOptions) {
        this.navigate(routeKey, {}, navigationOptions);
        this.renderRoot?.querySelector('platform-service-sidebar')?.closeMobile?.();
    }

    _onNavTreePick(e) {
        const d = e.detail;
        if (!d || typeof d.routeKey !== 'string' || d.routeKey.length === 0) {
            throw new Error('CRMSidebar: pick requires routeKey');
        }
        const rawSearch = typeof d.search === 'string' ? d.search : '';
        if (rawSearch.length > 0 && !rawSearch.startsWith('?')) {
            throw new Error('CRMSidebar: pick.search must start with ?');
        }
        const opts = {};
        if (rawSearch.length > 0) {
            opts.search = rawSearch;
        }
        this.navigate(d.routeKey, {}, Object.keys(opts).length > 0 ? opts : undefined);
        this.renderRoot?.querySelector('platform-service-sidebar')?.closeMobile?.();
    }

    _onNamespaceChange(event) {
        const user = this._authSel.value;
        if (!user || typeof user.company_id !== 'string') {
            throw new Error('CRMSidebar: cannot change namespace without active company_id');
        }
        const value = event.target.value;
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

    _openEditNamespace(name) {
        if (typeof name !== 'string' || name.length === 0) {
            throw new Error('CRMSidebar._openEditNamespace: name required');
        }
        this.openModal('crm.namespace', { mode: 'edit', name });
    }

    _isActive(route) {
        const current = this._routeKeySel.value;
        if (route === 'settings') {
            return SETTINGS_ALIASES.has(current);
        }
        return current === route;
    }

    _renderNavItem(item) {
        return html`
            <button
                class="nav-item ${this._isActive(item.route) ? 'active' : ''}"
                @click=${() => this._navigate(item.route)}
            >
                <span class="nav-icon-wrapper">
                    <platform-icon name=${item.icon} size="18"></platform-icon>
                </span>
                <span class="nav-label">${this.t(item.label_key)}</span>
            </button>
        `;
    }

    /**
     * @param {string} spaceName
     * @returns {Array<Record<string, unknown>>}
     */
    _sidebarTreeNodesForSpace(spaceName) {
        const items = this._namespaces.items;
        const nsRow = items.find((row) => row && row.name === spaceName);
        const rawSettings = nsRow && nsRow.crm_settings && typeof nsRow.crm_settings === 'object'
            ? nsRow.crm_settings
            : null;
        const rawNav = rawSettings && Array.isArray(rawSettings.sidebar_navigation)
            ? rawSettings.sidebar_navigation
            : null;
        const fromApi = mapSidebarNavFromApi(rawNav);
        const allowed = allowedTypeIdsForSpace(spaceName, this._entityTypes.items);
        const labels = {
            groupNotes: this.t('sidebar.nav_group_notes'),
            groupTasks: this.t('sidebar.nav_group_tasks'),
            groupEntities: this.t('sidebar.nav_group_entities'),
            allNotes: this.t('sidebar.nav_all_notes'),
            allTasks: this.t('sidebar.nav_all_tasks'),
            allEntities: this.t('sidebar.nav_all_entities'),
            graph: this.t('sidebar.nav.graph'),
        };
        const entityTypesItems = this._entityTypes.items;
        const canonical = buildDefaultSidebarNav({
            allowedTypeIds: allowed,
            entityTypes: entityTypesItems,
            labels,
        });
        let base;
        if (fromApi !== null && fromApi.length > 0) {
            const patched = replaceCrmSidebarGroupChildrenFromCanonical(fromApi, canonical);
            base = mergeCrmSidebarNavMissingGroups(patched, canonical);
        } else {
            base = canonical;
        }
        return enrichSidebarNavWithEntityTypeIcons(
            ensureCrmSidebarNavAllLeavesFirst(base, labels),
            entityTypesItems,
        );
    }

    render() {
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
            ? this._sidebarTreeNodesForSpace(selectValue)
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
                @collapse-change=${(e) => { this.collapsed = e.detail.collapsed; }}
                @mobile-change=${(e) => { this.mobileOpen = e.detail.open; }}
            >
                <div slot="header">
                    <div class="ns-section">
                        <span class="ns-label">${this.t('sidebar.namespace_label')}</span>
                        <select class="ns-select" .value=${selectValue} @change=${this._onNamespaceChange}>
                            <option value="">${this.t('sidebar.all_namespaces')}</option>
                            ${items.map((ns) => html`
                                <option value=${ns.name} ?selected=${ns.name === selectValue}>
                                    ${typeof ns.title === 'string' && ns.title.length > 0 ? ns.title : ns.name}
                                </option>
                            `)}
                        </select>
                        ${selectValue !== '' ? html`
                            <button
                                class="ns-edit-btn"
                                type="button"
                                title=${this.t('sidebar.edit_space_tooltip')}
                                @click=${() => this._openEditNamespace(selectValue)}
                            >
                                <platform-icon name="edit" size="14"></platform-icon>
                            </button>
                        ` : ''}
                        <button
                            class="ns-add-btn"
                            type="button"
                            title=${this.t('sidebar.create_space_tooltip')}
                            @click=${this._openCreateNamespace}
                        >
                            <platform-icon name="plus" size="14"></platform-icon>
                        </button>
                    </div>
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
