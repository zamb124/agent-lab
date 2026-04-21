/**
 * FrontendApp — корневой компонент сервиса frontend (landing + console + admin).
 *
 * Полностью event-driven. Маршрутизация — через core router.effect:
 * dispatch ROUTER_NAVIGATE_REQUESTED → state.router.routeKey → renderRoute().
 *
 * baseUrl сервиса (`/frontend`) используется только для HTTP-эндпоинтов; UI
 * сервис серверится с корня домена, поэтому router-effect регистрируется здесь
 * вручную с пустым baseUrl.
 */

import { html, css } from 'lit';
import { PlatformApp } from '@platform/lib/base/PlatformApp.js';
import { createRouterEffect } from '@platform/lib/events/effects/router.effect.js';

import { apiKeysResource } from '../events/resources/api-keys.resource.js';
import { teamMembersResource, inviteGenerateOp } from '../events/resources/team.resource.js';
import { embedConfigsResource, embedCodeLoadOp } from '../events/resources/embed.resource.js';
import { flowsCatalogOp } from '../events/resources/flows-catalog.resource.js';
import {
    schedulerTasksResource,
    schedulerPauseOp,
    schedulerResumeOp,
    schedulerCancelOp,
    schedulerRunNowOp,
    schedulerRedisOp,
} from '../events/resources/scheduler.resource.js';
import {
    billingSubscriptionLoadOp,
    billingUsageLoadOp,
    billingHistoryLoadOp,
    billingPlanChangeOp,
    billingTopupOp,
} from '../events/resources/billing.resource.js';
import { settingsLoadOp, settingsUpdateOp } from '../events/resources/settings.resource.js';
import { leadSubmitOp, leadRequestsList } from '../events/resources/leads.resource.js';
import { tracingSpansList, tracingFacets, tracingTraceLoadOp } from '../events/resources/tracing.resource.js';
import {
    companiesOverviewLoadOp,
    companyResolveOp,
    pricesGlobalLoadOp,
    pricesGlobalUpdateOp,
    companyPricesLoadOp,
    companyPricesUpdateOp,
    settlementRulesLoadOp,
    settlementRulesUpdateOp,
    defaultSettlementRulesLoadOp,
    usageReportLoadOp,
    billingAdminFacets,
    systemAccessEnterOp,
    systemAccessLeaveOp,
} from '../events/resources/billing-admin.resource.js';
import { acceptInviteOp } from '../events/resources/invites.resource.js';
import { servicesStatusLoadOp } from '../events/resources/services-status.resource.js';
import {
    dashboardFlowsCountOp,
    dashboardCrmNamespacesCountOp,
    dashboardRagNamespacesCountOp,
    dashboardSyncSpacesCountOp,
    dashboardDocumentsFilesCountOp,
} from '../events/resources/dashboard-stats.resource.js';

import '@platform/lib/components/layout/platform-island.js';
import '../components/frontend-sidebar.js';
import '../pages/landing-page.js';
import '../pages/products/product-agents-page.js';
import '../pages/products/product-rag-page.js';
import '../pages/products/product-crm-page.js';
import '../pages/products/product-sync-page.js';
import '../pages/products/product-documents-page.js';
import '../pages/legal-page.js';
import '../pages/login-page.js';
import '../pages/join-page.js';
import '../pages/select-company-page.js';
import '../pages/dashboard-page.js';
import '../pages/team/team-page.js';
import '../pages/api-keys/api-keys-page.js';
import '../pages/embed-configs-page.js';
import '../pages/billing/billing-page.js';
import '../pages/scheduler-tasks-page.js';
import '../pages/settings/settings-page.js';
import '../pages/leads-requests-page.js';
import '../pages/admin/tracing-page.js';
import '../pages/admin/billing-admin-page.js';

const FRONTEND_ROUTES = [
    { key: 'landing',           path: '' },
    { key: 'product-agents',    path: 'products/agents' },
    { key: 'product-rag',       path: 'products/rag' },
    { key: 'product-crm',       path: 'products/crm' },
    { key: 'product-sync',      path: 'products/sync' },
    { key: 'product-documents', path: 'products/documents' },
    { key: 'policy',            path: 'policy' },
    { key: 'terms',             path: 'terms' },
    { key: 'login',             path: 'login' },
    { key: 'join',              path: 'join' },
    { key: 'select-company',    path: 'select-company' },
    { key: 'dashboard',         path: 'dashboard' },
    { key: 'team',              path: 'team' },
    { key: 'api-keys',          path: 'api-keys' },
    { key: 'embed-configs',     path: 'embed-configs' },
    { key: 'billing',           path: 'billing' },
    { key: 'scheduler-tasks',   path: 'scheduler-tasks' },
    { key: 'settings',          path: 'settings' },
    { key: 'lead-requests',     path: 'lead-requests' },
    { key: 'platform-tracing',  path: 'platform-tracing' },
    { key: 'platform-billing',  path: 'platform-billing' },
];

const PUBLIC_ROUTE_KEYS = new Set([
    'landing',
    'product-agents', 'product-rag', 'product-crm', 'product-sync', 'product-documents',
    'policy', 'terms',
    'login', 'join', 'select-company',
]);

const LANDING_ROUTE_KEYS = new Set([
    'landing',
    'product-agents', 'product-rag', 'product-crm', 'product-sync', 'product-documents',
    'policy', 'terms',
]);

export class FrontendApp extends PlatformApp {
    static defaultI18nNamespace = 'frontend';

    static factories = [
        apiKeysResource,
        teamMembersResource,
        inviteGenerateOp,
        embedConfigsResource,
        embedCodeLoadOp,
        flowsCatalogOp,
        schedulerTasksResource,
        schedulerPauseOp,
        schedulerResumeOp,
        schedulerCancelOp,
        schedulerRunNowOp,
        schedulerRedisOp,
        billingSubscriptionLoadOp,
        billingUsageLoadOp,
        billingHistoryLoadOp,
        billingPlanChangeOp,
        billingTopupOp,
        settingsLoadOp,
        settingsUpdateOp,
        leadSubmitOp,
        leadRequestsList,
        tracingSpansList,
        tracingFacets,
        tracingTraceLoadOp,
        companiesOverviewLoadOp,
        companyResolveOp,
        pricesGlobalLoadOp,
        pricesGlobalUpdateOp,
        companyPricesLoadOp,
        companyPricesUpdateOp,
        settlementRulesLoadOp,
        settlementRulesUpdateOp,
        defaultSettlementRulesLoadOp,
        usageReportLoadOp,
        billingAdminFacets,
        systemAccessEnterOp,
        systemAccessLeaveOp,
        acceptInviteOp,
        servicesStatusLoadOp,
        dashboardFlowsCountOp,
        dashboardCrmNamespacesCountOp,
        dashboardRagNamespacesCountOp,
        dashboardSyncSpacesCountOp,
        dashboardDocumentsFilesCountOp,
    ];

    static styles = [
        PlatformApp.styles,
        css`
            :host {
                display: block;
                width: 100%;
                min-height: 100vh;
                background: var(--bg-gradient);
            }
            :host([landing]) { background: var(--landing-bg, var(--bg-gradient)); }
            .console {
                display: flex;
                width: 100%;
                height: 100vh;
                overflow: hidden;
            }
            .sidebar {
                height: 100vh;
                flex-shrink: 0;
                background: transparent;
            }
            .main {
                flex: 1;
                height: 100vh;
                overflow-y: auto;
                display: flex;
                padding: var(--space-4);
            }
            platform-island { flex: 1; min-height: calc(100vh - 2rem); }
            @media (max-width: 767px) {
                .sidebar { position: absolute; width: 0; height: 0; overflow: visible; }
                .main { padding: 0; }
            }
        `,
    ];

    getBaseUrl() { return '/frontend'; }

    getRoutes() { return []; }

    getServiceEffects() {
        return [
            createRouterEffect({ baseUrl: '', routes: FRONTEND_ROUTES }),
        ];
    }

    rendersUnauthenticated() { return true; }

    updated(changed) {
        super.updated && super.updated(changed);

        const route = this._routerSelect ? this._routerSelect.value : null;
        const routeKey = route ? route.routeKey : null;
        const landingPublic = !!routeKey && LANDING_ROUTE_KEYS.has(routeKey);
        this.toggleAttribute('landing', landingPublic);
        if (typeof document !== 'undefined' && document.documentElement) {
            document.documentElement.classList.toggle('frontend-landing-public', landingPublic);
        }

        const auth = this._authSelect ? this._authSelect.value : null;
        if (
            auth && auth.status === 'unauthenticated'
            && routeKey && !PUBLIC_ROUTE_KEYS.has(routeKey)
        ) {
            this.navigate('login');
        }
    }

    disconnectedCallback() {
        super.disconnectedCallback();
        if (typeof document !== 'undefined' && document.documentElement) {
            document.documentElement.classList.remove('frontend-landing-public');
        }
    }

    renderRoute(routeKey, params) {
        if (!routeKey) {
            return html`<div class="loading-container"><div class="loading-spinner"></div></div>`;
        }
        if (PUBLIC_ROUTE_KEYS.has(routeKey)) {
            return this._renderPublic(routeKey, params);
        }
        return this._renderConsole(routeKey, params);
    }

    _renderPublic(routeKey) {
        switch (routeKey) {
            case 'landing':            return html`<landing-page></landing-page>`;
            case 'product-agents':     return html`<product-agents-page></product-agents-page>`;
            case 'product-rag':        return html`<product-rag-page></product-rag-page>`;
            case 'product-crm':        return html`<product-crm-page></product-crm-page>`;
            case 'product-sync':       return html`<product-sync-page></product-sync-page>`;
            case 'product-documents':  return html`<product-documents-page></product-documents-page>`;
            case 'policy':             return html`<legal-page kind="policy"></legal-page>`;
            case 'terms':              return html`<legal-page kind="terms"></legal-page>`;
            case 'login':              return html`<login-page></login-page>`;
            case 'join':               return html`<join-page></join-page>`;
            case 'select-company':     return html`<select-company-page></select-company-page>`;
            default:                   return html`<landing-page></landing-page>`;
        }
    }

    _renderConsole(routeKey) {
        let content;
        switch (routeKey) {
            case 'dashboard':         content = html`<dashboard-page></dashboard-page>`; break;
            case 'team':              content = html`<frontend-team-page></frontend-team-page>`; break;
            case 'api-keys':          content = html`<frontend-api-keys-page></frontend-api-keys-page>`; break;
            case 'embed-configs':     content = html`<frontend-embed-configs-page></frontend-embed-configs-page>`; break;
            case 'billing':           content = html`<frontend-billing-page></frontend-billing-page>`; break;
            case 'scheduler-tasks':   content = html`<frontend-scheduler-tasks-page></frontend-scheduler-tasks-page>`; break;
            case 'settings':          content = html`<frontend-settings-page></frontend-settings-page>`; break;
            case 'lead-requests':     content = html`<frontend-leads-requests-page></frontend-leads-requests-page>`; break;
            case 'platform-tracing':  content = html`<frontend-tracing-page></frontend-tracing-page>`; break;
            case 'platform-billing':  content = html`<frontend-billing-admin-page></frontend-billing-admin-page>`; break;
            default:                  content = html`<dashboard-page></dashboard-page>`; break;
        }
        return html`
            <div class="console">
                <div class="sidebar"><frontend-sidebar></frontend-sidebar></div>
                <div class="main">
                    <platform-island>${content}</platform-island>
                </div>
            </div>
        `;
    }
}

customElements.define('frontend-app', FrontendApp);
