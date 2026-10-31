/**
 * ShopSidebar — навигация конструктора витрин.
 *
 * Пункты разделов адресуются `:shopId` текущего маршрута; пока магазин не
 * выбран — активен только «Магазины».
 */

import { html, css } from 'lit';
import { PlatformElement } from '@platform/lib/platform-element/index.js';
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
    { route: 'shop_menu',     icon: 'tag',     label_key: 'sidebar.nav.shop_menu' },
    { route: 'shop_builder',  icon: 'brush',   label_key: 'sidebar.nav.shop_builder' },
    { route: 'shop_orders',   icon: 'receipt', label_key: 'sidebar.nav.shop_orders' },
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
        `,
    ];
    declare collapsed: boolean;
    declare mobileOpen: boolean;
    private _routeKeySel: SelectController<unknown>;
    private _routeParamsSel: SelectController<unknown>;

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
                title=${this.t('sidebar.title')}
                service-id="shop"
                ?collapsed=${this.collapsed}
                ?mobile-open=${this.mobileOpen}
            >
                ${NAV_ITEMS.map((item) => {
                    const needsShop = item.route !== 'shop_home';
                    const disabled = needsShop && shopId === '';
                    return html`
                        <button
                            class="nav-item ${this._isActive(item.route) ? 'active' : ''} ${disabled ? 'disabled' : ''}"
                            @click=${() => this._navigate(item.route, needsShop ? { shopId } : {})}
                        >
                            <platform-icon name=${item.icon}></platform-icon>
                            <span class="nav-label">${this.t(item.label_key)}</span>
                        </button>
                    `;
                })}
            </platform-service-sidebar>
        `;
    }
}

customElements.define('shop-sidebar', ShopSidebar);
