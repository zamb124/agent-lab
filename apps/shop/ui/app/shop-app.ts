/**
 * ShopApp — корневой компонент конструктора витрин (`/shop`).
 *
 * Разделы: магазины компании (home), меню/товары, внешний вид витрины,
 * заказы, настройки и домены. Всё адресуется `:shopId` в маршруте.
 */

import { html, css } from 'lit';
import { PlatformApp } from '@platform/lib/base/PlatformApp.js';
import { createRouterEffect } from '@platform/lib/events/effects/router.effect.js';
import { platformFileCreateOp } from '@platform/lib/events/factories/platform-file-create.js';

import {
    shopShopsResource,
    shopCreateOp,
    shopUpdateOp,
    shopPublishOp,
    shopSuspendOp,
    shopBadgeIconsListOp,
    shopCategoriesListOp,
    shopCategoriesReorderOp,
    shopCategoryCreateOp,
    shopCategoryUpdateOp,
    shopCategoryRemoveOp,
    shopProductsListOp,
    shopProductCreateOp,
    shopProductUpdateOp,
    shopProductRemoveOp,
    shopProductsImportOp,
    shopProductsReorderOp,
    shopOrdersListOp,
    shopOrderSetStatusOp,
    shopDomainAddOp,
    shopDomainProvisionOp,
    shopAiDescribeOp,
    shopAiDescribeBatchOp,
    shopAiAutofillOp,
    shopAiDescribeShopOp,
    shopAiEnhancePhotoOp,
    shopAiGenerateCoverOp,
    shopAiGenerateLogoOp,
    shopAiGeneratePhotoOp,
    shopAiParseMenuOp,
    shopAiSuggestOptionsOp,
    shopModifierGroupCreateOp,
    shopModifierGroupUpdateOp,
    shopModifierGroupRemoveOp,
    shopModifierOptionCreateOp,
    shopModifierOptionUpdateOp,
    shopModifierOptionRemoveOp,
    shopProductModifierAttachOp,
    shopProductModifierDetachOp,
    shopPromoCreateOp,
    shopPromoUpdateOp,
    shopPromoRemoveOp,
    shopTelegramConnectOp,
    shopTelegramDisconnectOp,
} from '../events/resources/shop.resource.js';

import '@platform/lib/components/layout/platform-island.js';
import '../components/shop-sidebar.js';
import '../pages/shop-home-page.js';
import '../pages/shop-menu-page.js';
import '../pages/shop-builder-page.js';
import '../pages/shop-orders-page.js';
import '../pages/shop-promos-page.js';
import '../pages/shop-settings-page.js';
import '../modals/shop-modifiers-modal.js';

const SHOP_ROUTES = [
    { key: 'shop_home',      path: '',                  titleKey: 'routes.shop_home' },
    { key: 'shop_menu',      path: ':shopId/menu',      parent: 'shop_home', titleKey: 'routes.shop_menu' },
    { key: 'shop_builder',   path: ':shopId/builder',   parent: 'shop_home', titleKey: 'routes.shop_builder' },
    { key: 'shop_orders',    path: ':shopId/orders',    parent: 'shop_home', titleKey: 'routes.shop_orders' },
    { key: 'shop_promos',    path: ':shopId/promos',    parent: 'shop_home', titleKey: 'routes.shop_promos' },
    { key: 'shop_settings',  path: ':shopId/settings',  parent: 'shop_home', titleKey: 'routes.shop_settings' },
];

const SHOP_BOTTOM_NAV_ITEMS = [
    { key: 'home',      routeKey: 'shop_home',   icon: 'store',    labelKey: 'bottom_nav.home' },
    { key: 'menu',      routeKey: 'shop_menu',   icon: 'tag',      labelKey: 'bottom_nav.menu' },
    { key: 'orders',    routeKey: 'shop_orders', icon: 'receipt',  labelKey: 'bottom_nav.orders' },
    { key: 'profile',   sheet: 'platform.service_switcher', icon: 'user', labelKey: 'bottom_nav.profile' },
];

export class ShopApp extends PlatformApp {
    static defaultI18nNamespace = 'shop';
    static bottomNavItems = SHOP_BOTTOM_NAV_ITEMS;
    static platformAssistant = {
        branchId: 'shop',
        serviceId: 'shop',
        showLauncher: true,
    };

    static factories = [
        shopShopsResource,
        shopCreateOp,
        shopUpdateOp,
        shopPublishOp,
        shopSuspendOp,
        shopBadgeIconsListOp,
        shopCategoriesListOp,
        shopCategoryCreateOp,
        shopCategoryUpdateOp,
        shopCategoryRemoveOp,
        shopCategoriesReorderOp,
        shopProductsListOp,
        shopProductCreateOp,
        shopProductUpdateOp,
        shopProductRemoveOp,
        shopProductsImportOp,
        shopProductsReorderOp,
        shopOrdersListOp,
        shopOrderSetStatusOp,
        shopDomainAddOp,
        shopDomainProvisionOp,
        shopAiDescribeOp,
        shopAiDescribeBatchOp,
        shopAiAutofillOp,
        shopAiDescribeShopOp,
        shopAiEnhancePhotoOp,
        shopAiGenerateCoverOp,
        shopAiGenerateLogoOp,
        shopAiGeneratePhotoOp,
        shopAiParseMenuOp,
        shopAiSuggestOptionsOp,
        shopModifierGroupCreateOp,
        shopModifierGroupUpdateOp,
        shopModifierGroupRemoveOp,
        shopModifierOptionCreateOp,
        shopModifierOptionUpdateOp,
        shopModifierOptionRemoveOp,
        shopProductModifierAttachOp,
        shopProductModifierDetachOp,
        shopPromoCreateOp,
        shopPromoUpdateOp,
        shopPromoRemoveOp,
        shopTelegramConnectOp,
        shopTelegramDisconnectOp,
        platformFileCreateOp,
    ];

    static override styles = [
        PlatformApp.styles,
        css`
            :host {
                display: flex;
                flex-direction: row;
                width: var(--app-vw, 100vw);
                height: var(--app-vh, 100vh);
                overflow: hidden;
                background: var(--bg-gradient);
            }
            .sidebar {
                height: var(--app-vh, 100vh);
                flex-shrink: 0;
            }
            .main {
                flex: 1;
                height: 100%;
                min-width: 0;
                display: flex;
                flex-direction: column;
                overflow: hidden;
                padding: var(--space-4);
                box-sizing: border-box;
            }
            platform-island {
                flex: 1;
                min-height: 0;
                min-width: 0;
            }
            @media (max-width: 767px) {
                .main { padding: 0; }
                .sidebar {
                    position: absolute;
                    width: 0;
                    height: 0;
                    overflow: visible;
                }
            }
        `,
    ];

    override getBaseUrl() { return '/shop'; }

    override getRoutes() { return []; }

    override getServiceEffects() {
        return [createRouterEffect({ baseUrl: '/shop', routes: SHOP_ROUTES })];
    }

    override async getPlatformAssistantContextVariables(routeKey: string, params: Record<string, string>) {
        return {
            shop_route: routeKey,
            shop_id: typeof params.shopId === 'string' ? params.shopId : '',
        };
    }

    override renderRoute(routeKey: string | null, params: Record<string, string>) {
        return html`
            <div class="sidebar"><shop-sidebar></shop-sidebar></div>
            <div class="main">
                <platform-island padding="none" ?content-no-scroll=${true}>
                    ${this._renderPage(routeKey, params)}
                </platform-island>
            </div>
        `;
    }

    private _renderPage(routeKey: string | null, params: Record<string, string>) {
        const shopId = typeof params.shopId === 'string' ? params.shopId : '';
        switch (routeKey) {
            case 'shop_menu':
                return html`<shop-menu-page shop-id=${shopId}></shop-menu-page>`;
            case 'shop_builder':
                return html`<shop-builder-page shop-id=${shopId}></shop-builder-page>`;
            case 'shop_orders':
                return html`<shop-orders-page shop-id=${shopId}></shop-orders-page>`;
            case 'shop_promos':
                return html`<shop-promos-page shop-id=${shopId}></shop-promos-page>`;
            case 'shop_settings':
                return html`<shop-settings-page shop-id=${shopId}></shop-settings-page>`;
            case 'shop_home':
            default:
                return html`<shop-home-page></shop-home-page>`;
        }
    }
}

customElements.define('shop-app', ShopApp);
