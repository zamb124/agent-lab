/**
 * StockApp — корневой компонент склада (`/stock`).
 *
 * Разделы первого среза: пульс склада (остатки + стоимость), переводы,
 * продукты, локации, журнал оценки.
 */

import { html, css } from 'lit';
import { PlatformApp } from '@platform/lib/base/PlatformApp.js';
import { createRouterEffect } from '@platform/lib/events/effects/router.effect.js';

import {
    stockProductsResource,
    stockLocationsResource,
    stockWarehousesResource,
    stockTransfersResource,
    stockQuantsResource,
    stockValuationLayersListOp,
    stockProductCreateOp,
    stockProductUpdateOp,
    stockLocationCreateOp,
    stockLocationUpdateOp,
    stockWarehouseCreateOp,
    stockWarehousePulseOp,
    stockOperationTypesListOp,
    stockOperationTypeUpdateOp,
    stockTransferCreateOp,
    stockTransferItemOp,
    stockTransferConfirmOp,
    stockTransferAssignOp,
    stockTransferValidateOp,
    stockTransferCancelOp,
    stockTransferReturnOp,
    stockMoveLineUpdateOp,
    stockMoveApplyDecisionOp,
    stockQuantInventorySetOp,
    stockQuantInventoryApplyOp,
    stockValuationProductValueOp,
    stockValuationRevalueOp,
    stockValuationCorrectionOp,
    stockBarcodeResolveOp,
    stockLotsListOp,
    stockLotCreateOp,
    stockUomsListOp,
} from '../events/resources/stock.resource.js';

import '@platform/lib/components/layout/platform-island.js';
import '../components/stock-sidebar.js';
import '../pages/stock-home-page.js';
import '../pages/stock-transfers-page.js';
import '../pages/stock-transfer-page.js';
import '../pages/stock-products-page.js';
import '../pages/stock-locations-page.js';
import '../pages/stock-valuation-page.js';

const STOCK_ROUTES = [
    { key: 'stock_home',      path: '',                    titleKey: 'routes.stock_home' },
    { key: 'stock_transfers', path: 'transfers',           parent: 'stock_home', titleKey: 'routes.stock_transfers' },
    { key: 'stock_transfer',  path: 'transfers/:transferId', parent: 'stock_transfers', titleKey: 'routes.stock_transfer' },
    { key: 'stock_products',  path: 'products',            parent: 'stock_home', titleKey: 'routes.stock_products' },
    { key: 'stock_locations', path: 'locations',           parent: 'stock_home', titleKey: 'routes.stock_locations' },
    { key: 'stock_valuation', path: 'valuation',           parent: 'stock_home', titleKey: 'routes.stock_valuation' },
];

const STOCK_BOTTOM_NAV_ITEMS = [
    { key: 'home',      routeKey: 'stock_home',      icon: 'box',       labelKey: 'bottom_nav.home' },
    { key: 'transfers', routeKey: 'stock_transfers', icon: 'truck',     labelKey: 'bottom_nav.transfers' },
    { key: 'products',  routeKey: 'stock_products',  icon: 'tag',       labelKey: 'bottom_nav.products' },
    { key: 'profile',   sheet: 'platform.service_switcher', icon: 'user', labelKey: 'bottom_nav.profile' },
];

export class StockApp extends PlatformApp {
    static defaultI18nNamespace = 'stock';
    static bottomNavItems = STOCK_BOTTOM_NAV_ITEMS;
    static platformAssistant = {
        branchId: 'stock',
        serviceId: 'stock',
        showLauncher: true,
    };

    static factories = [
        stockProductsResource,
        stockLocationsResource,
        stockWarehousesResource,
        stockTransfersResource,
        stockQuantsResource,
        stockValuationLayersListOp,
        stockProductCreateOp,
        stockProductUpdateOp,
        stockLocationCreateOp,
        stockLocationUpdateOp,
        stockWarehouseCreateOp,
        stockWarehousePulseOp,
        stockOperationTypesListOp,
        stockOperationTypeUpdateOp,
        stockTransferCreateOp,
        stockTransferItemOp,
        stockTransferConfirmOp,
        stockTransferAssignOp,
        stockTransferValidateOp,
        stockTransferCancelOp,
        stockTransferReturnOp,
        stockMoveLineUpdateOp,
        stockMoveApplyDecisionOp,
        stockQuantInventorySetOp,
        stockQuantInventoryApplyOp,
        stockValuationProductValueOp,
        stockValuationRevalueOp,
        stockValuationCorrectionOp,
        stockBarcodeResolveOp,
        stockLotsListOp,
        stockLotCreateOp,
        stockUomsListOp,
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

    override getBaseUrl() { return '/stock'; }

    override getRoutes() { return []; }

    override getServiceEffects() {
        return [createRouterEffect({ baseUrl: '/stock', routes: STOCK_ROUTES })];
    }

    override async getPlatformAssistantContextVariables(routeKey: string, params: Record<string, string>) {
        return {
            stock_route: routeKey,
            stock_transfer_id: typeof params.transferId === 'string' ? params.transferId : '',
        };
    }

    override renderRoute(routeKey: string | null, params: Record<string, string>) {
        return html`
            <div class="sidebar"><stock-sidebar></stock-sidebar></div>
            <div class="main">
                <platform-island padding="none" ?content-no-scroll=${true}>
                    ${this._renderPage(routeKey, params)}
                </platform-island>
            </div>
        `;
    }

    private _renderPage(routeKey: string | null, params: Record<string, string>) {
        switch (routeKey) {
            case 'stock_transfers':
                return html`<stock-transfers-page></stock-transfers-page>`;
            case 'stock_transfer':
                return html`<stock-transfer-page transfer-id=${params.transferId}></stock-transfer-page>`;
            case 'stock_products':
                return html`<stock-products-page></stock-products-page>`;
            case 'stock_locations':
                return html`<stock-locations-page></stock-locations-page>`;
            case 'stock_valuation':
                return html`<stock-valuation-page></stock-valuation-page>`;
            case 'stock_home':
            default:
                return html`<stock-home-page></stock-home-page>`;
        }
    }
}

customElements.define('stock-app', StockApp);
