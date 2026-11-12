/**
 * StockTsdApp — терминал сбора данных склада (`/stock/tsd`).
 *
 * Второе приложение сервиса stock из того же ui-dist: один бандл для
 * браузера, планшета, ТСД и Capacitor WebView. Операторский слой без
 * административной навигации: светлая тема (lock в tsd.html), крупные
 * тач-цели, экраны, подчинённые backend-контексту задания.
 */

import { html, css } from 'lit';
import { PlatformApp } from '@platform/lib/base/PlatformApp.js';
import { createRouterEffect } from '@platform/lib/events/effects/router.effect.js';
import { platformFileCreateOp } from '@platform/lib/events/factories/platform-file-create.js';

import {
    stockContainerItemOp,
    stockContainerMoveOp,
    stockLocationCountDueOp,
    stockLocationsResource,
    stockProductsResource,
    stockQuantsResource,
    stockQueueResource,
    stockTransferItemOp,
    stockWarehousesResource,
    stockWavesResource,
} from '../events/resources/stock.resource.js';
import {
    stockLocationItemOp,
    stockMoveLinesAssignOp,
    stockMoveLinesClaimOp,
    stockMoveLinesExceptionOp,
    stockMoveLinesNextOp,
    stockMoveLinesReleaseOp,
    stockOperatorLoginOp,
    stockOperatorPulseOp,
    stockProductItemOp,
    stockPutawaySuggestOp,
    stockResourceLoginOp,
    stockScanAdhocCommitOp,
    stockScanCommitOp,
    stockScanCountCommitOp,
    stockScanOpenOp,
    stockScanQuantityOp,
    stockScanStepOp,
    stockTsdContextSlice,
    stockTsdOutboxSlice,
    stockTsdSessionSlice,
} from '../events/resources/stock-tsd.resource.js';
import { createTsdPersistEffect } from '../events/tsd-persist.effect.js';

import '../pages/tsd/stock-tsd-home-page.js';
import '../pages/tsd/stock-tsd-login-page.js';
import { tsdTokens } from '../pages/tsd/tsd-tokens.js';

const TSD_ROUTES = [
    { key: 'tsd_home', path: '', titleKey: 'routes.tsd_home' },
];

const TSD_BOTTOM_NAV_ITEMS = [
    { key: 'home',    routeKey: 'tsd_home', icon: 'box',  labelKey: 'bottom_nav.home' },
    { key: 'profile', sheet: 'platform.service_switcher', icon: 'user', labelKey: 'bottom_nav.profile' },
];

export class StockTsdApp extends PlatformApp {
    static defaultI18nNamespace = 'stock_tsd';
    static bottomNavItems = TSD_BOTTOM_NAV_ITEMS;
    static platformAssistant = {
        branchId: 'stock',
        serviceId: 'stock',
        showLauncher: false,
    };

    static factories = [
        stockWarehousesResource,
        stockQueueResource,
        stockProductsResource,
        stockLocationsResource,
        stockQuantsResource,
        stockContainerItemOp,
        stockContainerMoveOp,
        stockLocationCountDueOp,
        stockWavesResource,
        stockTransferItemOp,
        stockTsdContextSlice,
        stockTsdOutboxSlice,
        stockTsdSessionSlice,
        stockOperatorLoginOp,
        stockOperatorPulseOp,
        stockResourceLoginOp,
        stockScanOpenOp,
        stockProductItemOp,
        stockLocationItemOp,
        stockMoveLinesNextOp,
        stockMoveLinesClaimOp,
        stockMoveLinesReleaseOp,
        stockMoveLinesAssignOp,
        stockMoveLinesExceptionOp,
        platformFileCreateOp,
        stockScanStepOp,
        stockScanQuantityOp,
        stockScanAdhocCommitOp,
        stockScanCommitOp,
        stockScanCountCommitOp,
        stockPutawaySuggestOp,
    ];

    static override styles = [
        PlatformApp.styles,
        tsdTokens,
        css`
            :host {
                display: flex;
                flex-direction: column;
                width: var(--app-vw, 100vw);
                height: var(--app-vh, 100vh);
                overflow: hidden;
                background: var(--bg-gradient);
            }
            .tsd-main {
                flex: 1;
                min-height: 0;
                display: flex;
                flex-direction: column;
                overflow: hidden;
            }
        `,
    ];

    /**
     * Ingress-сегмент сервиса, а не маунт приложения: платформенные эффекты
     * строят API-URL как `${baseUrl}/api/...` → `/stock/api/...`. Путь
     * приложения `/stock/tsd` знает только router-эффект в getServiceEffects.
     */
    override getBaseUrl() { return '/stock'; }

    override getRoutes() { return []; }

    override getServiceEffects() {
        return [
            createRouterEffect({ baseUrl: '/stock/tsd', routes: TSD_ROUTES }),
            createTsdPersistEffect(),
        ];
    }

    override shouldRenderPlatformAssistant() { return false; }

    /** ТСД живёт и без сессии — экран бейджа показывается до логина. */
    override rendersUnauthenticated() { return true; }

    override renderRoute(routeKey: string | null, params: Record<string, string>) {
        return html`<div class="tsd-main">${this._renderPage(routeKey, params)}</div>`;
    }

    private _renderPage(routeKey: string | null, _params: Record<string, string>) {
        const auth = this._authSelect ? this._authSelect.value : null;
        if (auth !== null && auth.status === 'unauthenticated') {
            return html`<stock-tsd-login-page></stock-tsd-login-page>`;
        }
        switch (routeKey) {
            case 'tsd_home':
            default:
                return html`<stock-tsd-home-page></stock-tsd-home-page>`;
        }
    }
}

customElements.define('stock-tsd-app', StockTsdApp);
