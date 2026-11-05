/**
 * ShopSidebar — навигация конструктора витрин.
 *
 * Пункты разделов адресуются `:shopId` текущего маршрута; пока магазин не
 * выбран — активен только «Магазины».
 */

import { html, css, nothing } from 'lit';
import type { PropertyValues } from 'lit';
import { PlatformElement } from '@platform/lib/platform-element/index.js';
import type { OpController } from '@platform/lib/base/use-resource.js';
import type { SelectController } from '@platform/lib/events/select-controller.js';
import { sidebarStyles, sidebarNavItemStyles } from '@platform/lib/styles/shared/sidebar.styles.js';
import { readShellSidebarCollapsed } from '@platform/lib/utils/shell-sidebar-preference.js';
import { PlatformServiceSidebar } from '@platform/lib/components/layout/platform-service-sidebar.js';
import '@platform/lib/components/platform-icon.js';
import '@platform/lib/components/platform-user.js';
import '@platform/lib/components/platform-deployment-version.js';
import '@platform/lib/components/platform-notification-manager.js';

const NAV_ITEMS = [
    { route: 'shop_home',     icon: 'store',   label_key: 'sidebar.nav.shop_home' },
    { route: 'shop_menu',     icon: 'book-open', label_key: 'sidebar.nav.shop_menu' },
    { route: 'shop_builder',  icon: 'edit',    label_key: 'sidebar.nav.shop_builder' },
    { route: 'shop_orders',   icon: 'scroll-text', label_key: 'sidebar.nav.shop_orders' },
    { route: 'shop_promos',   icon: 'tag',     label_key: 'sidebar.nav.shop_promos' },
    { route: 'shop_settings', icon: 'settings', label_key: 'sidebar.nav.shop_settings' },
];

export class ShopSidebar extends PlatformElement {
    static i18nNamespace = 'shop';

    static override styles = [
        PlatformElement.styles,
        sidebarStyles,
        sidebarNavItemStyles,
        css`
            :host { display: block; height: 100%; }
            .nav-item {
                margin-bottom: var(--space-1);
            }
            platform-service-sidebar[collapsed] .nav-label { display: none; }
            platform-service-sidebar[collapsed] .nav-item {
                justify-content: center;
                padding: var(--space-2);
            }
            .nav-item.disabled {
                opacity: 0.4;
                pointer-events: none;
            }
            .nav-badge {
                margin-left: auto;
                min-width: 20px;
                height: 20px;
                padding: 0 var(--space-1);
                border-radius: var(--radius-full, 10px);
                background: var(--color-primary, var(--text-secondary));
                color: var(--text-on-primary, var(--bg-surface));
                font-size: var(--text-2xs, 10px);
                font-weight: var(--font-semibold);
                display: inline-flex;
                align-items: center;
                justify-content: center;
            }
            platform-service-sidebar[collapsed] .nav-badge {
                position: absolute;
                top: 2px;
                right: 2px;
                margin-left: 0;
            }
            platform-service-sidebar[collapsed] .nav-item { position: relative; }
        `,
    ];
    declare collapsed: boolean;
    declare mobileOpen: boolean;
    private _routeKeySel: SelectController<unknown>;
    private _routeParamsSel: SelectController<unknown>;
    private _ordersOp: OpController;
    private _ordersShopId = '';

    static override properties = {
        collapsed: { type: Boolean, reflect: true },
        mobileOpen: { type: Boolean, reflect: true, attribute: 'mobile-open' },
    };

    constructor() {
        super();
        this.collapsed = readShellSidebarCollapsed();
        this.mobileOpen = false;
        this._routeKeySel = this.select((s) => s.router.routeKey);
        this._routeParamsSel = this.select((s) => s.router.params);
        this._ordersOp = this.useOp('shop/orders_list');
    }

    override updated(changed: PropertyValues<this>): void {
        super.updated(changed);
        const shopId = this._shopId();
        // Бейдж активных заказов держится на том же op — push shop/order/*
        // перезапускает его в фабрике, счётчик живой на любом маршруте.
        if (shopId !== '' && shopId !== this._ordersShopId) {
            this._ordersShopId = shopId;
            void this._ordersOp.run({ shop_id: shopId, limit: 200 });
        }
    }

    private _activeOrderCount(): number {
        const result = this._ordersOp.lastResult as { items?: { status?: string }[] } | null;
        const items = result !== null && result !== undefined && Array.isArray(result.items) ? result.items : [];
        return items.filter((o) => o.status === 'new' || o.status === 'accepted' || o.status === 'preparing' || o.status === 'delivering').length;
    }

    private _shell(): PlatformServiceSidebar | null {
        if (!this.renderRoot) return null;
        const shell = this.renderRoot.querySelector('platform-service-sidebar');
        if (shell === null) return null;
        if (!(shell instanceof PlatformServiceSidebar)) {
            throw new Error('shop-sidebar: service sidebar required');
        }
        return shell;
    }

    closeMobile() {
        this._shell()?.closeMobile();
    }

    private _shopId(): string {
        const params = this._routeParamsSel.value as Record<string, string> | undefined;
        return params && typeof params.shopId === 'string' ? params.shopId : '';
    }

    private _navigate(routeKey: string, params?: Record<string, string>) {
        this.navigate(routeKey, params === undefined ? {} : params);
        this.closeMobile();
    }

    private _isActive(route: string) {
        return this._routeKeySel.value === route;
    }

    override render() {
        const shopId = this._shopId();
        return html`
            <platform-service-sidebar
                logo-src="/static/core/assets/service_logos/shop_logo.svg"
                logo-text=${this.t('sidebar.title')}
                ?logo-opens-services=${true}
                ?collapsed=${this.collapsed}
                ?mobile-open=${this.mobileOpen}
                @collapse-change=${(e: CustomEvent<{ collapsed?: boolean }>) => { this.collapsed = e.detail.collapsed === true; }}
                @mobile-change=${(e: CustomEvent<{ open?: boolean }>) => { this.mobileOpen = e.detail.open === true; }}
            >
                <nav>
                    ${NAV_ITEMS.map((item) => {
                        const needsShop = item.route !== 'shop_home';
                        const disabled = needsShop && shopId === '';
                        const badge = item.route === 'shop_orders' && !disabled ? this._activeOrderCount() : 0;
                        return html`
                            <button
                                class="nav-item ${this._isActive(item.route) ? 'active' : ''} ${disabled ? 'disabled' : ''}"
                                @click=${() => this._navigate(item.route, needsShop ? { shopId } : {})}
                            >
                                <platform-icon name=${item.icon}></platform-icon>
                                <span class="nav-label">${this.t(item.label_key)}</span>
                                ${badge > 0 ? html`<span class="nav-badge">${badge}</span>` : nothing}
                            </button>
                        `;
                    })}
                </nav>
                <div slot="footer">
                    <platform-user block>
                        <platform-notification-manager slot="user-toolbar"></platform-notification-manager>
                    </platform-user>
                    <platform-deployment-version base-url="/shop" footer></platform-deployment-version>
                </div>
            </platform-service-sidebar>
        `;
    }
}

customElements.define('shop-sidebar', ShopSidebar);
