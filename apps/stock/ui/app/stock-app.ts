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
    stockValuationReportOp,
    stockValuationRevalueForm,
    stockValuationCorrectionForm,
    stockProductCreateOp,
    stockProductUpdateOp,
    stockCatalogProductsSuggestOp,
    stockCatalogProductUpdateOp,
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
    stockMovesList,
    stockContainersListOp,
    stockContainerItemOp,
    stockContainerCreateOp,
    stockContainerMoveOp,
    stockLocationCountDueOp,
    stockStorageTypesListOp,
    stockStorageTypeCreateOp,
    stockStorageTypeUpdateOp,
    stockContainerTypesListOp,
    stockContainerTypeCreateOp,
    stockContainerTypeUpdateOp,
    stockResourceTypesListOp,
    stockResourceTypeCreateOp,
    stockResourceTypeUpdateOp,
    stockResourcesListOp,
    stockResourceCreateOp,
    stockResourceUpdateOp,
    stockPutawayRulesListOp,
    stockPutawayRuleCreateOp,
    stockPutawayRuleUpdateOp,
    stockPutawayRuleDeleteOp,
    stockReorderRulesListOp,
    stockReorderRuleCreateOp,
    stockReorderRuleUpdateOp,
    stockRoutesListOp,
    stockRouteCreateOp,
    stockWarehouseUpdateOp,
    stockLocationCreateForm,
    stockLocationUpdateForm,
} from '../events/resources/stock.resource.js';

import '@platform/lib/components/layout/platform-island.js';
import '../components/stock-sidebar.js';
import '../pages/stock-home-page.js';
import '../pages/stock-transfers-page.js';
import '../pages/stock-transfer-page.js';
import '../pages/stock-products-page.js';
import '../pages/stock-locations-page.js';
import '../pages/stock-stock-report-page.js';
import '../pages/stock-moves-page.js';
import '../pages/stock-packages-page.js';
import '../pages/stock-inventory-page.js';
import '../pages/stock-settings-pages.js';
import '../modals/stock-location-modal.js';
import '../pages/stock-valuation-page.js';
import '../pages/stock-valuation-journal-page.js';
import '../pages/stock-valuation-batches-page.js';
import '../modals/stock-valuation-revalue-modal.js';
import '../modals/stock-valuation-correction-modal.js';

const STOCK_ROUTES = [
    { key: 'stock_home',      path: '',                    titleKey: 'routes.stock_home' },
    { key: 'stock_transfers', path: 'transfers',           parent: 'stock_home', titleKey: 'routes.stock_transfers' },
    { key: 'stock_transfer',  path: 'transfers/:transferId', parent: 'stock_transfers', titleKey: 'routes.stock_transfer' },
    { key: 'stock_products',  path: 'products',            parent: 'stock_home', titleKey: 'routes.stock_products' },
    { key: 'stock_locations', path: 'locations',           parent: 'stock_home', titleKey: 'routes.stock_locations' },
    { key: 'stock_stock_report', path: 'locations/report', parent: 'stock_locations', titleKey: 'routes.stock_stock_report' },
    { key: 'stock_moves',     path: 'locations/moves',     parent: 'stock_locations', titleKey: 'routes.stock_moves' },
    { key: 'stock_packages',  path: 'locations/packages',  parent: 'stock_locations', titleKey: 'routes.stock_packages' },
    { key: 'stock_inventory', path: 'locations/inventory', parent: 'stock_locations', titleKey: 'routes.stock_inventory' },
    { key: 'stock_location',  path: 'locations/:locationId', parent: 'stock_locations', titleKey: 'routes.stock_location' },
    { key: 'stock_warehouses', path: 'settings/warehouses', parent: 'stock_home', titleKey: 'routes.stock_warehouses' },
    { key: 'stock_storage_types', path: 'settings/storage-types', parent: 'stock_home', titleKey: 'routes.stock_storage_types' },
    { key: 'stock_container_types', path: 'settings/container-types', parent: 'stock_home', titleKey: 'routes.stock_container_types' },
    { key: 'stock_resources', path: 'settings/resources',  parent: 'stock_home', titleKey: 'routes.stock_resources' },
    { key: 'stock_putaway_rules', path: 'settings/putaway-rules', parent: 'stock_home', titleKey: 'routes.stock_putaway_rules' },
    { key: 'stock_reorder_rules', path: 'settings/reorder-rules', parent: 'stock_home', titleKey: 'routes.stock_reorder_rules' },
    { key: 'stock_routes',    path: 'settings/routes',     parent: 'stock_home', titleKey: 'routes.stock_routes' },
    { key: 'stock_valuation', path: 'valuation',           parent: 'stock_home', titleKey: 'routes.stock_valuation' },
    { key: 'stock_valuation_journal', path: 'valuation/journal', parent: 'stock_valuation', titleKey: 'routes.stock_valuation_journal' },
    { key: 'stock_valuation_batches', path: 'valuation/batches', parent: 'stock_valuation', titleKey: 'routes.stock_valuation_batches' },
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
        stockValuationReportOp,
        stockValuationRevalueForm,
        stockValuationCorrectionForm,
        stockProductCreateOp,
        stockProductUpdateOp,
        stockCatalogProductsSuggestOp,
        stockCatalogProductUpdateOp,
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
        stockMovesList,
        stockContainersListOp,
        stockContainerItemOp,
        stockContainerCreateOp,
        stockContainerMoveOp,
        stockLocationCountDueOp,
        stockStorageTypesListOp,
        stockStorageTypeCreateOp,
        stockStorageTypeUpdateOp,
        stockContainerTypesListOp,
        stockContainerTypeCreateOp,
        stockContainerTypeUpdateOp,
        stockResourceTypesListOp,
        stockResourceTypeCreateOp,
        stockResourceTypeUpdateOp,
        stockResourcesListOp,
        stockResourceCreateOp,
        stockResourceUpdateOp,
        stockPutawayRulesListOp,
        stockPutawayRuleCreateOp,
        stockPutawayRuleUpdateOp,
        stockPutawayRuleDeleteOp,
        stockReorderRulesListOp,
        stockReorderRuleCreateOp,
        stockReorderRuleUpdateOp,
        stockRoutesListOp,
        stockRouteCreateOp,
        stockWarehouseUpdateOp,
        stockLocationCreateForm,
        stockLocationUpdateForm,
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
            case 'stock_location':
                return html`<stock-locations-page location-id=${params.locationId || ''}></stock-locations-page>`;
            case 'stock_stock_report':
                return html`<stock-stock-report-page></stock-stock-report-page>`;
            case 'stock_moves':
                return html`<stock-moves-page></stock-moves-page>`;
            case 'stock_packages':
                return html`<stock-packages-page></stock-packages-page>`;
            case 'stock_inventory':
                return html`<stock-inventory-page></stock-inventory-page>`;
            case 'stock_warehouses':
                return html`<stock-warehouses-page></stock-warehouses-page>`;
            case 'stock_storage_types':
                return html`<stock-storage-types-page></stock-storage-types-page>`;
            case 'stock_container_types':
                return html`<stock-container-types-page></stock-container-types-page>`;
            case 'stock_resources':
                return html`<stock-resources-page></stock-resources-page>`;
            case 'stock_putaway_rules':
                return html`<stock-putaway-rules-page></stock-putaway-rules-page>`;
            case 'stock_reorder_rules':
                return html`<stock-reorder-rules-page></stock-reorder-rules-page>`;
            case 'stock_routes':
                return html`<stock-routes-page></stock-routes-page>`;
            case 'stock_valuation':
                return html`<stock-valuation-page></stock-valuation-page>`;
            case 'stock_valuation_journal':
                return html`<stock-valuation-journal-page></stock-valuation-journal-page>`;
            case 'stock_valuation_batches':
                return html`<stock-valuation-batches-page></stock-valuation-batches-page>`;
            case 'stock_home':
            default:
                return html`<stock-home-page></stock-home-page>`;
        }
    }
}

customElements.define('stock-app', StockApp);
