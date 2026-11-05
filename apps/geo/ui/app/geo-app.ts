/**
 * GeoApp — корневой компонент сервиса Geo.
 *
 * Event-driven canon: слои и реестр покрытия — фабрики
 * `@platform/lib/events/resources/geo-*.resource.js`; маршрутизация —
 * `createRouterEffect`, SPA сервится по `/geo`.
 *
 * Маршруты:
 *   /geo                → overview (карта канонических слоёв)
 *   /geo/sources        → sources (регионы, источники, статистика)
 *   /geo/route-lab      → route_lab (маршрутная лаборатория)
 */

import { html, css } from 'lit';
import type { PropertyValues } from 'lit';
import { PlatformApp } from '@platform/lib/base/PlatformApp.js';
import type { SelectController } from '@platform/lib/events/select-controller.js';
import { createRouterEffect } from '@platform/lib/events/effects/router.effect.js';
import { applyCompanyHostRedirectIfNeeded } from '@platform/lib/utils/company-host-guard.js';
import { COMPANIES_EVENTS } from '@platform/lib/events/reducers/companies.js';
import type { CompanyListEntry } from '@platform/lib/utils/company-host-guard.js';

import '@platform/lib/events/resources/geo-layers.resource.js';
import '@platform/lib/events/resources/geo-coverage.resource.js';
import '@platform/lib/events/resources/geo-route.resource.js';
import { geoLayersOp, geoLayerFeaturesOp, geoMapSlice } from '@platform/lib/events/resources/geo-layers.resource.js';
import {
    geoRegionsResource,
    geoSourcesOp,
    geoStatsOp,
    geoCursorsOp,
    geoImportStatusOp,
    geoImportRunOp,
} from '@platform/lib/events/resources/geo-coverage.resource.js';
import { geoRouteOp, geoIsochroneOp } from '@platform/lib/events/resources/geo-route.resource.js';

function companyListEntries(list: readonly { company_id?: unknown; subdomain?: unknown }[]): readonly CompanyListEntry[] {
    return list.map((company) => {
        if (typeof company.company_id !== 'string' || company.company_id.length === 0) {
            throw new Error('companies.list: company_id required');
        }
        const entry: CompanyListEntry = { company_id: company.company_id };
        if (typeof company.subdomain === 'string') entry.subdomain = company.subdomain;
        return entry;
    });
}

import '@platform/lib/components/layout/platform-island.js';
import '../components/geo-sidebar.js';
import '../pages/geo-overview-page.js';
import '../pages/geo-sources-page.js';
import '../pages/geo-route-lab-page.js';

const GEO_ROUTES = [
    { key: 'overview',  path: '',            titleKey: 'routes.overview' },
    { key: 'sources',   path: 'sources',     titleKey: 'routes.sources' },
    { key: 'route_lab', path: 'route-lab',   titleKey: 'routes.route_lab' },
];

export class GeoApp extends PlatformApp {
    static defaultI18nNamespace = 'geo';
    static bottomNavItems = [];
    static bottomNavHideOnRoutes = [];
    static platformAssistant = {
        branchId: 'geo',
        serviceId: 'geo',
        showLauncher: false,
    };

    private _companiesListSel: SelectController<readonly CompanyListEntry[]>;
    private _companiesLoadingSel: SelectController<boolean>;

    constructor() {
        super();
        this._companiesListSel = this.select((s) => companyListEntries(s.companies.list));
        this._companiesLoadingSel = this.select((s) => s.companies.loading);
    }

    static factories = [
        geoLayersOp,
        geoLayerFeaturesOp,
        geoMapSlice,
        geoRegionsResource,
        geoSourcesOp,
        geoStatsOp,
        geoCursorsOp,
        geoImportStatusOp,
        geoImportRunOp,
        geoRouteOp,
        geoIsochroneOp,
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
                background: transparent;
            }
            .main {
                flex: 1;
                min-width: 0;
                height: var(--app-vh, 100vh);
                display: flex;
                flex-direction: column;
                padding: var(--space-4);
                overflow: hidden;
            }
            platform-island {
                flex: 1;
                min-height: 0;
                min-width: 0;
            }
            @media (max-width: 767px) {
                .main { padding: 0; }
                .sidebar { position: absolute; width: 0; height: 0; overflow: visible; }
            }
        `,
    ];

    override getBaseUrl() { return '/geo'; }

    override getRoutes() { return []; }

    override getServiceEffects() {
        return [
            createRouterEffect({ baseUrl: '/geo', routes: GEO_ROUTES }),
        ];
    }

    override updated(changed: PropertyValues<this>) {
        super.updated(changed);
        const auth = this._authSelect.value;
        applyCompanyHostRedirectIfNeeded(
            auth,
            this._companiesListSel.value,
            Boolean(this._companiesLoadingSel.value),
            { loadCompanies: () => this.dispatch(COMPANIES_EVENTS.LOAD_REQUESTED, null) },
        );
    }

    override renderRoute(routeKey: string | null) {
        let content;
        switch (routeKey) {
            case 'sources':
                content = html`<geo-sources-page></geo-sources-page>`;
                break;
            case 'route_lab':
                content = html`<geo-route-lab-page></geo-route-lab-page>`;
                break;
            case 'overview':
            default:
                content = html`<geo-overview-page></geo-overview-page>`;
                break;
        }
        return html`
            <div class="sidebar"><geo-sidebar></geo-sidebar></div>
            <div class="main">
                <platform-island>${content}</platform-island>
            </div>
        `;
    }
}

customElements.define('geo-app', GeoApp);
