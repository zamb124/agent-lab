/**
 * StockSidebar — навигация сервиса склада.
 *
 * Иерархия — `platform-sidebar-nav-tree`: раздел «Оценка» раскрывается в
 * отчёт / журнал / FIFO-партии, развёрнутость групп хранится per-scope.
 */

import { html, css } from 'lit';
import { PlatformElement } from '@platform/lib/platform-element/index.js';
import type { SelectController } from '@platform/lib/events/select-controller.js';
import { isPlainRecord } from '@platform/lib/events/payload.js';
import { sidebarStyles, sidebarNavItemStyles } from '@platform/lib/styles/shared/sidebar.styles.js';
import { readShellSidebarCollapsed } from '@platform/lib/utils/shell-sidebar-preference.js';
import { PlatformServiceSidebar } from '@platform/lib/components/layout/platform-service-sidebar.js';
import '@platform/lib/components/layout/platform-sidebar-nav-tree.js';
import '@platform/lib/components/platform-icon.js';
import '@platform/lib/components/platform-user.js';
import '@platform/lib/components/platform-deployment-version.js';
import '@platform/lib/components/platform-notification-manager.js';

interface NavNodeSpec {
    id: string;
    label_key: string;
    icon?: string;
    route?: string;
    children?: NavNodeSpec[];
}

const NAV_TREE: NavNodeSpec[] = [
    { id: 'stock_home', icon: 'box', label_key: 'sidebar.nav.stock_home', route: 'stock_home' },
    { id: 'stock_transfers', icon: 'truck', label_key: 'sidebar.nav.stock_transfers', route: 'stock_transfers' },
    { id: 'stock_products', icon: 'tag', label_key: 'sidebar.nav.stock_products', route: 'stock_products' },
    {
        id: 'stock_locations',
        icon: 'pin',
        label_key: 'sidebar.nav.stock_locations',
        children: [
            { id: 'stock_locations_map', label_key: 'sidebar.nav.stock_locations_map', route: 'stock_locations' },
            { id: 'stock_stock_report', label_key: 'sidebar.nav.stock_stock_report', route: 'stock_stock_report' },
            { id: 'stock_moves', label_key: 'sidebar.nav.stock_moves', route: 'stock_moves' },
            { id: 'stock_packages', label_key: 'sidebar.nav.stock_packages', route: 'stock_packages' },
            { id: 'stock_inventory', label_key: 'sidebar.nav.stock_inventory', route: 'stock_inventory' },
        ],
    },
    {
        id: 'stock_settings',
        icon: 'settings',
        label_key: 'sidebar.nav.stock_settings',
        children: [
            { id: 'stock_warehouses', label_key: 'sidebar.nav.stock_warehouses', route: 'stock_warehouses' },
            { id: 'stock_storage_types', label_key: 'sidebar.nav.stock_storage_types', route: 'stock_storage_types' },
            { id: 'stock_container_types', label_key: 'sidebar.nav.stock_container_types', route: 'stock_container_types' },
            { id: 'stock_resources', label_key: 'sidebar.nav.stock_resources', route: 'stock_resources' },
            { id: 'stock_putaway_rules', label_key: 'sidebar.nav.stock_putaway_rules', route: 'stock_putaway_rules' },
            { id: 'stock_reorder_rules', label_key: 'sidebar.nav.stock_reorder_rules', route: 'stock_reorder_rules' },
            { id: 'stock_routes', label_key: 'sidebar.nav.stock_routes', route: 'stock_routes' },
        ],
    },
    {
        id: 'stock_valuation',
        icon: 'chart',
        label_key: 'sidebar.nav.stock_valuation',
        children: [
            { id: 'stock_valuation_report', label_key: 'sidebar.nav.stock_valuation_report', route: 'stock_valuation' },
            { id: 'stock_valuation_journal', label_key: 'sidebar.nav.stock_valuation_journal', route: 'stock_valuation_journal' },
            { id: 'stock_valuation_batches', label_key: 'sidebar.nav.stock_valuation_batches', route: 'stock_valuation_batches' },
        ],
    },
];

/** Активный пункт дерева: дочерние роуты подсвечивают свой лист. */
function activeItemId(routeKey: string): string {
    switch (routeKey) {
        case 'stock_transfer':
            return 'stock_transfers';
        case 'stock_locations':
        case 'stock_location':
            return 'stock_locations_map';
        case 'stock_valuation':
            return 'stock_valuation_report';
        case 'stock_valuation_journal':
            return 'stock_valuation_journal';
        case 'stock_valuation_batches':
            return 'stock_valuation_batches';
        default:
            return routeKey;
    }
}

export class StockSidebar extends PlatformElement {
    static i18nNamespace = 'stock';

    static override styles = [
        PlatformElement.styles,
        sidebarStyles,
        sidebarNavItemStyles,
        css`
            :host { display: block; height: 100%; }
            .nav-section { margin-bottom: var(--space-2); }
            platform-sidebar-nav-tree {
                --sidebar-nav-tree-children-border: none;
            }
        `,
    ];
    declare collapsed: boolean;
    declare mobileOpen: boolean;
    private _routeKeySel: SelectController<unknown>;

    static override properties = {
        collapsed: { type: Boolean, reflect: true },
        mobileOpen: { type: Boolean, reflect: true, attribute: 'mobile-open' },
    };

    constructor() {
        super();
        this.collapsed = readShellSidebarCollapsed();
        this.mobileOpen = false;
        this._routeKeySel = this.select((s) => s.router.routeKey);
    }

    private _shell(): PlatformServiceSidebar | null {
        if (!this.renderRoot) return null;
        const shell = this.renderRoot.querySelector('platform-service-sidebar');
        if (shell === null) return null;
        if (!(shell instanceof PlatformServiceSidebar)) {
            throw new Error('stock-sidebar: service sidebar required');
        }
        return shell;
    }

    closeMobile() {
        this._shell()?.closeMobile();
    }

    private _onNavTreePick(e: CustomEvent) {
        const d = isPlainRecord(e.detail) ? e.detail : null;
        if (!d || typeof d.routeKey !== 'string' || d.routeKey.length === 0) {
            throw new Error('stock-sidebar: pick requires routeKey');
        }
        const rawSearch = typeof d.search === 'string' ? d.search : '';
        if (rawSearch.length > 0 && !rawSearch.startsWith('?')) {
            throw new Error('stock-sidebar: pick.search must start with ?');
        }
        this.navigate(d.routeKey, {}, rawSearch.length > 0 ? { search: rawSearch } : undefined);
        this.closeMobile();
    }

    private _navNodes() {
        const toNode = (spec: NavNodeSpec): Record<string, unknown> => {
            const node: Record<string, unknown> = { id: spec.id, label: this.t(spec.label_key) };
            if (typeof spec.icon === 'string' && spec.icon !== '') {
                node.icon = spec.icon;
            }
            if (spec.children !== undefined && spec.children.length > 0) {
                node.children = spec.children.map(toNode);
            } else {
                if (typeof spec.route !== 'string' || spec.route === '') {
                    throw new Error(`stock-sidebar: nav node ${spec.id} requires route`);
                }
                node.routeKey = spec.route;
            }
            return node;
        };
        return NAV_TREE.map(toNode);
    }

    override render() {
        const routeKey = typeof this._routeKeySel.value === 'string' ? this._routeKeySel.value : '';
        return html`
            <platform-service-sidebar
                logo-src="/static/core/assets/service_logos/stock_logo.svg"
                logo-text=${this.t('sidebar.title')}
                ?logo-opens-services=${true}
                ?collapsed=${this.collapsed}
                ?mobile-open=${this.mobileOpen}
                @collapse-change=${(e: CustomEvent<{ collapsed?: boolean }>) => { this.collapsed = e.detail.collapsed === true; }}
                @mobile-change=${(e: CustomEvent<{ open?: boolean }>) => { this.mobileOpen = e.detail.open === true; }}
            >
                <nav>
                    <div class="nav-section">
                        <platform-sidebar-nav-tree
                            .nodes=${this._navNodes()}
                            active-item-id=${activeItemId(routeKey)}
                            storage-scope="stock-nav"
                            ?collapsed=${this.collapsed}
                            @pick=${this._onNavTreePick}
                        ></platform-sidebar-nav-tree>
                    </div>
                </nav>
                <div slot="footer">
                    <platform-user block>
                        <platform-notification-manager slot="user-toolbar"></platform-notification-manager>
                    </platform-user>
                    <platform-deployment-version base-url="/stock" footer></platform-deployment-version>
                </div>
            </platform-service-sidebar>
        `;
    }
}

customElements.define('stock-sidebar', StockSidebar);
