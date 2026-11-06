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
import { isPlainRecord } from '@platform/lib/events/payload.js';
interface FrontendCookieConsentState {
    hydrated: boolean;
    analyticsAllowed: boolean;
    consentTextVersion: string;
}

function requireCookieConsent(value: unknown): FrontendCookieConsentState {
    if (!isPlainRecord(value)
        || typeof value.hydrated !== 'boolean'
        || typeof value.analyticsAllowed !== 'boolean'
        || typeof value.consentTextVersion !== 'string') {
        throw new Error('FrontendApp: cookie consent state required');
    }
    return {
        hydrated: value.hydrated,
        analyticsAllowed: value.analyticsAllowed,
        consentTextVersion: value.consentTextVersion,
    };
}

function companyListEntries(list: readonly CompanyRecord[]): CompanyListEntry[] {
    const entries: CompanyListEntry[] = [];
    for (const company of list) {
        if (typeof company.company_id !== 'string' || company.company_id.length === 0) {
            throw new Error('FrontendApp: company_id required');
        }
        const entry: CompanyListEntry = { company_id: company.company_id };
        if (typeof company.subdomain === 'string') {
            entry.subdomain = company.subdomain;
        }
        entries.push(entry);
    }
    return entries;
}
import { PlatformApp } from '@platform/lib/base/PlatformApp.js';
import { createRouterEffect } from '@platform/lib/events/effects/router.effect.js';
import { CoreAuthEvents } from '@platform/lib/events/effects/auth.effect.js';
import type { CompanyRecord } from '@platform/lib/events/reducers/companies.js';
import { applyCompanyHostRedirectIfNeeded, type CompanyListEntry } from '@platform/lib/utils/company-host-guard.js';
import { COMPANIES_EVENTS } from '@platform/lib/events/reducers/companies.js';
import { platformFileCreateOp } from '@platform/lib/events/factories/platform-file-create.js';

import { apiKeysResource } from '../events/resources/api-keys.resource.js';
import { secretsVariablesResource } from '@platform/lib/events/resources/secrets-variables.resource.js';
import { secretsVariablesResolveOp } from '@platform/lib/events/resources/secrets-variables-resolve.resource.js';
import { secretsVariableVersionsLoadOp } from '@platform/lib/events/resources/secrets-variable-versions.resource.js';
import {
    companyVoiceProvidersCatalogLoadOp,
    companyVoiceProvidersLoadOp,
    companyVoiceProvidersUpsertOp,
    companyVoiceProvidersRemoveOp,
} from '@platform/lib/events/resources/voice-company-providers.resource.js';
import {
    companyPronunciationRulesLoadOp,
    companyPronunciationRuleCreateOp,
    companyPronunciationRuleUpdateOp,
    companyPronunciationRuleDeleteOp,
    companyPronunciationRuleTestOp,
} from '@platform/lib/events/resources/voice-company-pronunciation-rules.resource.js';
import { teamMembersResource, inviteGenerateOp } from '../events/resources/team.resource.js';
import {
    authzExplorerByUserOp,
    authzExplorerByObjectOp,
    authzExplorerWhyOp,
    authzExplorerObjectsOp,
    authzExplorerRevokeOp,
    authzExplorerUiSlice,
} from '../events/resources/authz-explorer.resource.js';
import {
    consoleNamespacesResource,
    consoleNamespaceCreateForm,
} from '../events/resources/namespaces.resource.js';
import { embedConfigsResource, embedCodeLoadOp } from '../events/resources/embed.resource.js';
import { landingAgentsLoadOp, landingDemoSessionOp } from '../events/resources/landing-demo.resource.js';
import {
    publicSearchRunOp,
    publicSearchSerpClickOp,
    publicSearchSerpMoreOp,
    publicSearchSourceDescribeOp,
} from '../events/resources/public-search.resource.js';
import { flowsListOp } from '@platform/lib/events/resources/flows-flows-list.resource.js';
import {
    schedulerTasksResource,
    schedulerPauseOp,
    schedulerResumeOp,
    schedulerCancelOp,
    schedulerRunNowOp,
    schedulerRedisOp,
} from '@platform/lib/events/resources/scheduler-schedules.resource.js';
import {
    billingSubscriptionLoadOp,
    billingUsageLoadOp,
    billingHistoryLoadOp,
    billingPlanChangeOp,
    billingTopupOp,
} from '../events/resources/billing.resource.js';
import {
    settingsLoadOp,
    settingsUpdateOp,
    aiProvidersLoadOp,
    aiProviderCapabilityPutOp,
    aiProviderCapabilityDeleteOp,
    aiProviderLlmContextPutOp,
    aiProviderLlmContextDeleteOp,
    aiCustomProviderCreateOp,
    aiCustomProviderUpdateOp,
    aiCustomProviderDeleteOp,
} from '../events/resources/settings.resource.js';
import {
    companyStoragesLoadOp,
    companyStoragesProbeOp,
    companyStoragesCreateOp,
    companyStoragesRotateOp,
    companyStoragesDeleteOp,
    companyStorageCreateForm,
    companyStorageRoutesSetOp,
    companyStorageMigrationsStartOp,
    companyStorageMigrationSlice,
} from '../events/resources/company-storages.resource.js';
import {
    searchProvidersLoadOp,
    searchProviderPutOp,
    searchProviderOrderPutOp,
    searchProviderDeleteOp,
} from '@platform/lib/events/resources/search-providers.resource.js';
import { leadSubmitOp, leadRequestsList } from '../events/resources/leads.resource.js';
import { tracingSpansList, tracingFacets, tracingTraceLoadOp } from '../events/resources/tracing.resource.js';
import {
    crawlProfilesLoadOp,
    crawlSummaryLoadOp,
    crawlDomainsResource,
    crawlUrlsResource,
    crawlJobsResource,
    crawlQueueTickOp,
    crawlDomainRunOp,
    crawlUrlDetailOp,
    crawlProfilePatchOp,
    crawlDomainCreateOp,
    crawlDomainPatchOp,
    crawlDomainDeleteOp,
    crawlUrlAddOp,
    crawlUrlRecrawlOp,
} from '@platform/lib/events/resources/search-crawl-report.resource.js';
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
    balanceGrantOp,
    systemAccessEnterOp,
    systemAccessLeaveOp,
} from '../events/resources/billing-admin.resource.js';
import {
    llmModelScoresLoadOp,
    llmModelScoreUpsertOp,
    llmModelScoreDeleteOp,
    llmModelScoresRefreshCacheOp,
    llmModelScoresProbeProvidersOp,
} from '../events/resources/llm-model-scores.resource.js';
import { acceptInviteOp, previewInviteOp } from '../events/resources/invites.resource.js';
import { servicesStatusLoadOp } from '../events/resources/services-status.resource.js';
import {
    dashboardStatsOp,
} from '../events/resources/dashboard-stats.resource.js';
import {
    publicSiteBundleOp,
    publicBlogListOp,
    publicBlogPostOp,
} from '../events/resources/public-site.resource.js';
import {
    cookieConsentRecordOp,
    cookieConsentSlice,
} from '../events/resources/cookie-consent.resource.js';
import { applyPublicDocumentMeta } from '../_helpers/public-document-meta.js';
import { buildFrontendAssistantContext } from '../_helpers/platform-assistant-context.js';
import { canInjectPublicAnalytics, shouldFetchPublicSiteBundle } from '../_helpers/cookie-consent-analytics.js';

import '@platform/lib/components/layout/platform-island.js';
import '../components/frontend-sidebar.js';
import '../pages/landing-page.js';
import '../pages/search-page.js';
import '../pages/products/product-agents-page.js';
import '../pages/products/product-rag-page.js';
import '../pages/products/product-crm-page.js';
import '../pages/products/product-sync-page.js';
import '../pages/products/product-documents-page.js';
import '../pages/products/product-geo-page.js';
import '../pages/products/product-wiki-page.js';
import '../pages/products/product-shop-page.js';
import '../pages/legal-page.js';
import '../components/landing/cookie-consent-banner.js';
import '../pages/support-page.js';
import '../pages/landing-digital-workers-page.js';
import '../pages/blog-list-page.js';
import '../pages/blog-post-page.js';
import '../pages/about-page.js';
import '../pages/roadmap-page.js';
import '../pages/login-page.js';
import '../pages/join-page.js';
import '../pages/select-company-page.js';
import '../pages/dashboard-page.js';
import '../pages/team/team-page.js';
import '../pages/access/access-page.js';
import '../components/sheets/access-why-sheet.js';
import '../pages/namespaces/namespaces-page.js';
import '../pages/api-keys/api-keys-page.js';
import '../pages/company-variables/company-variables-page.js';
import '../pages/company-voice-providers/company-voice-providers-page.js';
import '../pages/embed-configs-page.js';
import '../pages/billing/billing-page.js';
import '../pages/scheduler-tasks-page.js';
import '../pages/settings/settings-page.js';
import '../pages/leads-requests-page.js';
import '../pages/admin/tracing-page.js';
import '../pages/admin/crawl-report-page.js';
import '../pages/admin/billing-admin-page.js';
import type {CSSResultGroup, PropertyValues} from 'lit';
import type { OpController } from '@platform/lib/base/use-resource.js';
import type { SelectController } from '@platform/lib/events/select-controller.js';
import '@platform/lib/components/platform-empty-state.js';

const FRONTEND_ROUTES = [
    { key: 'landing',                 path: '',                                                titleKey: 'routes.landing' },
    { key: 'search',                  path: 'search',                   parent: 'landing',     titleKey: 'routes.search' },
    { key: 'product-agents',          path: 'products/agents',          parent: 'landing',     titleKey: 'routes.product-agents' },
    { key: 'product-rag',             path: 'products/rag',             parent: 'landing',     titleKey: 'routes.product-rag' },
    { key: 'product-crm',             path: 'products/crm',             parent: 'landing',     titleKey: 'routes.product-crm' },
    { key: 'product-sync',            path: 'products/sync',            parent: 'landing',     titleKey: 'routes.product-sync' },
    { key: 'product-documents',       path: 'products/documents',       parent: 'landing',     titleKey: 'routes.product-documents' },
    { key: 'product-geo',             path: 'products/geo',             parent: 'landing',     titleKey: 'routes.product-geo' },
    { key: 'product-wiki',            path: 'products/wiki',            parent: 'landing',     titleKey: 'routes.product-wiki' },
    { key: 'product-shop',            path: 'products/shop',            parent: 'landing',     titleKey: 'routes.product-shop' },
    { key: 'policy',                  path: 'policy',                   parent: 'landing',     titleKey: 'routes.policy' },
    { key: 'terms',                   path: 'terms',                    parent: 'landing',     titleKey: 'routes.terms' },
    { key: 'cookies',                 path: 'cookies',                  parent: 'landing',     titleKey: 'routes.cookies' },
    { key: 'cookie-consent',          path: 'consent/cookies',          parent: 'landing',     titleKey: 'routes.cookie-consent' },
    { key: 'support',                 path: 'support',                  parent: 'landing',     titleKey: 'routes.support' },
    { key: 'digital-workers',         path: 'demo/digital-workers',     parent: 'landing',     titleKey: 'routes.digital-workers' },
    { key: 'blog',                    path: 'blog',                     parent: 'landing',     titleKey: 'routes.blog' },
    { key: 'blog-post',               path: 'blog/:slug',               parent: 'blog',        titleKey: 'routes.blog-post' },
    { key: 'about',                   path: 'about',                    parent: 'landing',     titleKey: 'routes.about' },
    { key: 'roadmap',                 path: 'roadmap',                  parent: 'landing',     titleKey: 'routes.roadmap' },
    { key: 'login',                   path: 'login',                                           titleKey: 'routes.login' },
    { key: 'join',                    path: 'join',                                            titleKey: 'routes.join' },
    { key: 'select-company',          path: 'select-company',                                  titleKey: 'routes.select-company' },
    { key: 'dashboard',               path: 'dashboard',                                       titleKey: 'routes.dashboard' },
    { key: 'platform_services',       path: 'services',                 parent: 'dashboard',   titleKey: 'routes.platform_services' },
    { key: 'team',                    path: 'team',                     parent: 'dashboard',   titleKey: 'routes.team' },
    { key: 'access',                  path: 'access',                   parent: 'dashboard',   titleKey: 'routes.access' },
    { key: 'namespaces',              path: 'namespaces',               parent: 'dashboard',   titleKey: 'routes.namespaces' },
    { key: 'api-keys',                path: 'api-keys',                 parent: 'dashboard',   titleKey: 'routes.api-keys' },
    { key: 'company-variables',       path: 'company-variables',        parent: 'dashboard',   titleKey: 'routes.company-variables' },
    { key: 'company-voice-providers', path: 'company-voice-providers',  parent: 'dashboard',   titleKey: 'routes.company-voice-providers' },
    { key: 'embed-configs',           path: 'embed-configs',            parent: 'dashboard',   titleKey: 'routes.embed-configs' },
    { key: 'billing',                 path: 'billing',                  parent: 'dashboard',   titleKey: 'routes.billing' },
    { key: 'scheduler-tasks',         path: 'scheduler-tasks',          parent: 'dashboard',   titleKey: 'routes.scheduler-tasks' },
    { key: 'settings',                path: 'settings',                 parent: 'dashboard',   titleKey: 'routes.settings' },
    { key: 'lead-requests',           path: 'lead-requests',            parent: 'dashboard',   titleKey: 'routes.lead-requests' },
    { key: 'platform-tracing',        path: 'platform-tracing',         parent: 'dashboard',   titleKey: 'routes.platform-tracing' },
    { key: 'crawl-report',            path: 'crawl-report',             parent: 'dashboard',   titleKey: 'routes.crawl-report' },
    { key: 'platform-billing',        path: 'platform-billing',         parent: 'dashboard',   titleKey: 'routes.platform-billing' },
];

const PUBLIC_ROUTE_KEYS = new Set([
    'landing',
    'search',
    'product-agents', 'product-rag', 'product-crm', 'product-sync', 'product-documents',
    'product-geo', 'product-wiki', 'product-shop',
    'policy', 'terms', 'cookies', 'cookie-consent', 'support',
    'digital-workers',
    'blog', 'blog-post', 'about', 'roadmap',
    'login', 'join', 'select-company',
]);

const LANDING_ROUTE_KEYS = new Set([
    'landing',
    'search',
    'product-agents', 'product-rag', 'product-crm', 'product-sync', 'product-documents',
    'product-geo', 'product-wiki', 'product-shop',
    'policy', 'terms', 'cookies', 'cookie-consent', 'support',
    'digital-workers',
    'blog', 'blog-post', 'about', 'roadmap',
]);

/** Публичные страницы с собственным sync meta (продукты, пост блога). */
const DOCUMENT_META_SKIP = new Set([
    'product-agents',
    'product-rag',
    'product-crm',
    'product-sync',
    'product-documents',
    'product-geo',
    'product-wiki',
    'product-shop',
    'blog-post',
]);

/**
 * Нижняя навигация (mobile shell 2026): консоль панели управления.
 * Скрыта на всех public-маршрутах (landing, login, blog и т.п.) — туда mobile shell
 * платформы не подключается, лендинг рендерит свой собственный layout.
 */
const FRONTEND_BOTTOM_NAV_ITEMS = [
    { key: 'dashboard',  routeKey: 'dashboard',  icon: 'apps',     labelKey: 'bottom_nav.dashboard' },
    { key: 'team',       routeKey: 'team',       icon: 'users',    labelKey: 'bottom_nav.team' },
    { key: 'access',     routeKey: 'access',     icon: 'shield',   labelKey: 'bottom_nav.access' },
    { key: 'billing',    routeKey: 'billing',    icon: 'chart',    labelKey: 'bottom_nav.billing' },
    { key: 'profile',    sheet: 'platform.service_switcher', icon: 'user', labelKey: 'bottom_nav.profile' },
];

const FRONTEND_BOTTOM_NAV_HIDE_ON_ROUTES = [
    'landing',
    'search',
    'product-agents', 'product-rag', 'product-crm', 'product-sync', 'product-documents',
    'product-geo', 'product-wiki', 'product-shop',
    'policy', 'terms', 'cookies', 'cookie-consent', 'support',
    'digital-workers',
    'blog', 'blog-post', 'about', 'roadmap',
    'login', 'join', 'select-company',
];

export class FrontendApp extends PlatformApp {
    static defaultI18nNamespace = 'frontend';
    static bottomNavItems = FRONTEND_BOTTOM_NAV_ITEMS;
    static bottomNavHideOnRoutes = FRONTEND_BOTTOM_NAV_HIDE_ON_ROUTES;
    static platformAssistant = {
        branchId: 'console',
        serviceId: 'frontend',
        showLauncher: true,
    };

    static factories = [
        apiKeysResource,
        secretsVariablesResource,
        secretsVariablesResolveOp,
        secretsVariableVersionsLoadOp,
        companyVoiceProvidersCatalogLoadOp,
        companyVoiceProvidersLoadOp,
        companyVoiceProvidersUpsertOp,
        companyVoiceProvidersRemoveOp,
        companyPronunciationRulesLoadOp,
        companyPronunciationRuleCreateOp,
        companyPronunciationRuleUpdateOp,
        companyPronunciationRuleDeleteOp,
        companyPronunciationRuleTestOp,
        teamMembersResource,
        inviteGenerateOp,
        authzExplorerByUserOp,
        authzExplorerByObjectOp,
        authzExplorerWhyOp,
        authzExplorerObjectsOp,
        authzExplorerRevokeOp,
        authzExplorerUiSlice,
        consoleNamespacesResource,
        consoleNamespaceCreateForm,
        embedConfigsResource,
        embedCodeLoadOp,
        landingAgentsLoadOp,
        landingDemoSessionOp,
        publicSearchRunOp,
        publicSearchSerpClickOp,
        publicSearchSerpMoreOp,
        publicSearchSourceDescribeOp,
        flowsListOp,
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
        companyStoragesLoadOp,
        companyStoragesProbeOp,
        companyStoragesCreateOp,
        companyStoragesRotateOp,
        companyStoragesDeleteOp,
        companyStorageCreateForm,
        companyStorageRoutesSetOp,
        companyStorageMigrationsStartOp,
        companyStorageMigrationSlice,
        settingsUpdateOp,
        aiProvidersLoadOp,
        aiProviderCapabilityPutOp,
        aiProviderCapabilityDeleteOp,
        aiProviderLlmContextPutOp,
        aiProviderLlmContextDeleteOp,
        aiCustomProviderCreateOp,
        aiCustomProviderUpdateOp,
        aiCustomProviderDeleteOp,
        searchProvidersLoadOp,
        searchProviderPutOp,
        searchProviderOrderPutOp,
        searchProviderDeleteOp,
        leadSubmitOp,
        leadRequestsList,
        tracingSpansList,
        tracingFacets,
        tracingTraceLoadOp,
        crawlProfilesLoadOp,
        crawlSummaryLoadOp,
        crawlDomainsResource,
        crawlUrlsResource,
        crawlJobsResource,
        crawlQueueTickOp,
        crawlDomainRunOp,
        crawlUrlDetailOp,
        crawlProfilePatchOp,
        crawlDomainCreateOp,
        crawlDomainPatchOp,
        crawlDomainDeleteOp,
        crawlUrlAddOp,
        crawlUrlRecrawlOp,
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
        balanceGrantOp,
        systemAccessEnterOp,
        systemAccessLeaveOp,
        llmModelScoresLoadOp,
        llmModelScoreUpsertOp,
        llmModelScoreDeleteOp,
        llmModelScoresRefreshCacheOp,
        llmModelScoresProbeProvidersOp,
        acceptInviteOp,
        previewInviteOp,
        servicesStatusLoadOp,
        dashboardStatsOp,
        publicSiteBundleOp,
        publicBlogListOp,
        publicBlogPostOp,
        cookieConsentRecordOp,
        cookieConsentSlice,
        platformFileCreateOp,
    ];

    constructor() {
        super();
        this._deferredAuthMeRequested = false;
        this._lastPublicMetaSig = '';
        this._publicSiteBundle = this.useOp('frontend/public_site_bundle');
        this._cookieConsentSel = this.select((state) => requireCookieConsent(state.frontendCookieConsent));
        this._companiesSel = this.select((state) => state.companies.list);
        this._companiesLoadingSel = this.select((state) => state.companies.loading);
        this._i18nPublicMetaSel = this.select((state) => {
            const bundle = state.i18n.translations[state.i18n.locale];
            const landing = bundle === undefined ? undefined : bundle.landing;
            return {
                locale: state.i18n.locale,
                hasBundle: !state.i18n.loading && isPlainRecord(landing),
            };
        });
        this._frontendMobile =
            typeof window !== 'undefined' &&
            typeof window.matchMedia === 'function' &&
            window.matchMedia('(max-width: 767px)').matches;
    }
    private _deferredAuthMeRequested: boolean;
    private _lastPublicMetaSig: string;
    private _publicSiteBundle: OpController;
    private _cookieConsentSel: SelectController<FrontendCookieConsentState>;
    private _companiesSel: SelectController<CompanyRecord[]>;
    private _companiesLoadingSel: SelectController<boolean>;
    private _i18nPublicMetaSel: SelectController<{ locale: string; hasBundle: boolean }>;
    private _frontendMobile: unknown;


    override async connectedCallback(): Promise<void> {
        await super.connectedCallback();
        if (typeof window === 'undefined' || typeof window.matchMedia !== 'function') {
            return;
        }
        const mql = window.matchMedia('(max-width: 767px)');
        const onFrontendMobileMql = () => {
            const next = mql.matches;
            if (next !== this._frontendMobile) {
                this._frontendMobile = next;
                this.requestUpdate();
            }
        };
        this.useDomEvent(mql, 'change', onFrontendMobileMql);
        const next = mql.matches;
        if (next !== this._frontendMobile) {
            this._frontendMobile = next;
            this.requestUpdate();
        }
    }

    static override styles: CSSResultGroup = [
        PlatformApp.styles,
        css`
            :host {
                display: block;
                width: 100%;
                min-height: 100vh;
                background: var(--bg-gradient);
            }
            :host([landing]) { background: var(--marketing-page-bg); }
            .console {
                display: flex;
                width: 100%;
                height: var(--app-vh, 100vh);
                overflow: hidden;
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
                .sidebar { position: absolute; width: 0; height: 0; overflow: visible; }
                .main { padding: 0; }
            }
        `,
    ];

    override getBaseUrl() { return '/frontend'; }

    override getRoutes() { return []; }

    override getServiceEffects() {
        return [
            createRouterEffect({ baseUrl: '', routes: FRONTEND_ROUTES }),
        ];
    }

    override rendersUnauthenticated() { return true; }

    override shouldRenderPlatformAssistant(routeKey: string) {
        return !PUBLIC_ROUTE_KEYS.has(routeKey);
    }

    override async getPlatformAssistantContextVariables(routeKey: string, _params: Record<string, string>): Promise<Record<string, unknown>> {
        return buildFrontendAssistantContext(routeKey);
    }

    override shouldRequestUserLoadOnConnect() {
        if (typeof window === 'undefined') return true;
        const path = window.location.pathname.replace(/\/+$/, '') || '/';
        if (path === '/') return false;
        if (path === '/search') return false;
        if (/^\/demo\/digital-workers(\/|$)/.test(path)) return false;
        if (path.startsWith('/products/')) return false;
        if (path === '/policy' || path === '/terms' || path === '/support') return false;
        if (path === '/cookies' || path === '/consent/cookies') return false;
        if (path === '/blog' || path.startsWith('/blog/')) return false;
        if (path === '/about' || path === '/roadmap') return false;
        return true;
    }

    override updated(changed: PropertyValues<this>): void {
        super.updated && super.updated(changed);

        const route = this._routerSelect ? this._routerSelect.value : null;
        const routeKey = route ? route.routeKey : null;
        const auth = this._authSelect ? this._authSelect.value : null;

        if (
            auth &&
            auth.status === 'unauthenticated' &&
            auth.sessionEndCause === null &&
            routeKey &&
            !PUBLIC_ROUTE_KEYS.has(routeKey) &&
            !this._deferredAuthMeRequested
        ) {
            this._deferredAuthMeRequested = true;
            this.dispatch(CoreAuthEvents.USER_LOAD_REQUESTED, null);
        }

        const landingPublic = !!routeKey && LANDING_ROUTE_KEYS.has(routeKey);
        this.toggleAttribute('landing', landingPublic);
        if (typeof document !== 'undefined' && document.documentElement) {
            document.documentElement.classList.toggle('frontend-landing-public', landingPublic);
            if (landingPublic) {
                document.documentElement.setAttribute('data-platform-theme-lock', 'dark');
            } else {
                document.documentElement.removeAttribute('data-platform-theme-lock');
            }
        }

        if (
            auth && auth.status === 'unauthenticated'
            && auth.sessionEndCause !== 'logout'
            && routeKey && !PUBLIC_ROUTE_KEYS.has(routeKey)
        ) {
            if (typeof window !== 'undefined') {
                const href = window.location.origin + window.location.pathname + window.location.search;
                this.navigate('login', {}, { search: `?redirect_uri=${encodeURIComponent(href)}` });
            } else {
                this.navigate('login');
            }
        }

        if (
            auth && auth.status === 'authenticated'
            && routeKey && !PUBLIC_ROUTE_KEYS.has(routeKey)
        ) {
            const companies = this._companiesSel ? this._companiesSel.value : [];
            const loading = this._companiesLoadingSel ? this._companiesLoadingSel.value : false;
            applyCompanyHostRedirectIfNeeded(auth, companyListEntries(companies), loading, {
                loadCompanies: () => this.dispatch(COMPANIES_EVENTS.LOAD_REQUESTED, null),
            });
        }

        if (typeof window !== 'undefined' && routeKey && PUBLIC_ROUTE_KEYS.has(routeKey)) {
            this._syncPublicHtmlMeta(routeKey);
            this._maybeBootstrapPublicAnalytics();
        }
    }

    override disconnectedCallback(): void {
        super.disconnectedCallback();
        if (typeof document !== 'undefined' && document.documentElement) {
            document.documentElement.classList.remove('frontend-landing-public');
            document.documentElement.removeAttribute('data-platform-theme-lock');
        }
    }

    override renderRoute(routeKey: string, params: Record<string, string>) {
        if (!routeKey) {
            return html`<platform-empty-state class="loading-container" loading></platform-empty-state>`;
        }
        if (PUBLIC_ROUTE_KEYS.has(routeKey)) {
            return this._renderPublic(routeKey, params);
        }
        return this._renderConsole(routeKey);
    }

    _syncPublicHtmlMeta(routeKey: string) {
        if (typeof window === 'undefined') return;
        if (!routeKey) return;
        if (DOCUMENT_META_SKIP.has(routeKey)) return;

        const i18nMeta = this._i18nPublicMetaSel.value;
        if (!i18nMeta || !i18nMeta.hasBundle) {
            // Бандл ещё не в state — не трогаем title и не lock'аем sig.
            // После I18N_LOCALE_LOADED select триггерит override updated() → повторный sync.
            return;
        }

        const rawPath = window.location.pathname.replace(/\/+$/, '') || '/';
        const sig = `${routeKey}|${rawPath}|${i18nMeta.locale}`;
        if (this._lastPublicMetaSig === sig) return;

        const origin = window.location.origin;
        const canonicalUrl = `${origin}${rawPath.startsWith('/') ? rawPath : `/${rawPath}`}`;
        const ogImageUrl = `${origin}/static/frontend/assets/images/main_img.png`;

        let titleKey;
        let descriptionKey;
        let titleNs;
        let descriptionNs;
        switch (routeKey) {
            case 'landing':
                titleKey = 'meta.home_title';
                descriptionKey = 'meta.home_description';
                titleNs = 'landing';
                descriptionNs = 'landing';
                break;
            case 'search':
                titleKey = 'meta.search_title';
                descriptionKey = 'meta.search_description';
                titleNs = 'landing';
                descriptionNs = 'landing';
                break;
            case 'blog':
                titleKey = 'meta.blog_title';
                descriptionKey = 'meta.blog_description';
                titleNs = 'landing';
                descriptionNs = 'landing';
                break;
            case 'about':
                titleKey = 'meta.about_title';
                descriptionKey = 'meta.about_description';
                titleNs = 'landing';
                descriptionNs = 'landing';
                break;
            case 'roadmap':
                titleKey = 'meta.roadmap_title';
                descriptionKey = 'meta.roadmap_description';
                titleNs = 'landing';
                descriptionNs = 'landing';
                break;
            case 'digital-workers':
                titleKey = 'meta.digital_workers_title';
                descriptionKey = 'meta.digital_workers_description';
                titleNs = 'landing';
                descriptionNs = 'landing';
                break;
            case 'support':
                titleKey = 'meta.support_title';
                descriptionKey = 'meta.support_description';
                titleNs = 'landing';
                descriptionNs = 'landing';
                break;
            case 'policy':
                titleKey = 'title';
                descriptionKey = 'meta.policy_description';
                titleNs = 'privacy';
                descriptionNs = 'landing';
                break;
            case 'terms':
                titleKey = 'title';
                descriptionKey = 'meta.terms_description';
                titleNs = 'terms';
                descriptionNs = 'landing';
                break;
            case 'cookies':
                titleKey = 'title';
                descriptionKey = 'meta.cookies_description';
                titleNs = 'cookies';
                descriptionNs = 'landing';
                break;
            case 'cookie-consent':
                titleKey = 'title';
                descriptionKey = 'meta.cookie_consent_description';
                titleNs = 'cookie_consent';
                descriptionNs = 'landing';
                break;
            default:
                return;
        }

        const title = this.t(titleKey, {}, titleNs);
        const description = this.t(descriptionKey, {}, descriptionNs);
        if (title === titleKey) {
            throw new Error(
                `FrontendApp._syncPublicHtmlMeta: missing i18n key ${titleNs}:${titleKey} for route "${routeKey}"`,
            );
        }
        if (description === descriptionKey) {
            throw new Error(
                `FrontendApp._syncPublicHtmlMeta: missing i18n key ${descriptionNs}:${descriptionKey} for route "${routeKey}"`,
            );
        }

        this._lastPublicMetaSig = sig;
        applyPublicDocumentMeta({ title, description, canonicalUrl, ogImageUrl });
    }

    _maybeBootstrapPublicAnalytics() {
        if (typeof window === 'undefined') return;
        if (Reflect.get(window, '__linnexAnalyticsInjected') === true) return;
        const route = this._routerSelect ? this._routerSelect.value : null;
        const routeKey = route ? route.routeKey : null;
        if (!routeKey || !LANDING_ROUTE_KEYS.has(routeKey)) return;

        const consent = this._cookieConsentSel.value;
        if (shouldFetchPublicSiteBundle({
            busy: this._publicSiteBundle.busy,
            error: this._publicSiteBundle.error,
            lastResult: this._publicSiteBundle.lastResult,
        })) {
            void this._publicSiteBundle.run();
            return;
        }
        const bundleRes = this._publicSiteBundle.lastResult;
        if (!isPlainRecord(bundleRes)) {
            return;
        }
        const version = bundleRes.cookie_consent_text_version;
        if (typeof version !== 'string' || version === '') {
            throw new Error('FrontendApp: cookie_consent_text_version required');
        }
        const analyticsConfigured = bundleRes.analytics_configured;
        if (typeof analyticsConfigured !== 'boolean') {
            throw new Error('FrontendApp: analytics_configured boolean required');
        }
        if (!canInjectPublicAnalytics({
            routeKey,
            isLandingRoute: true,
            hydrated: consent.hydrated,
            analyticsAllowed: consent.analyticsAllowed,
            consentTextVersion: consent.consentTextVersion,
            bundleVersion: version,
            analyticsConfigured,
        })) {
            return;
        }

        const marketing = bundleRes.marketing;
        if (!isPlainRecord(marketing)) {
            throw new Error('FrontendApp: marketing required');
        }

        const ymId = marketing.yandex_metrika_id;
        const gaId = marketing.google_analytics_measurement_id;

        let injected = false;
        if (typeof ymId === 'string' && ymId !== '') {
            const s = document.createElement('script');
            const metrikaQueue = '||' + '[]';
            s.textContent = [
                `(function(m,e,t,r,i,k,a){m[i]=m[i]||function(){(m[i].a=m[i].a${metrikaQueue}).push(arguments)};`,
                'm[i].l=1*new Date();',
                'for (var j = 0; j < document.scripts.length; j++) { if (document.scripts[j].src === r) { return; } }',
                'k=e.createElement(t),a=e.getElementsByTagName(t)[0],k.async=1,k.src=r,a.parentNode.insertBefore(k,a)}',
                '(window, document, "script", "https://mc.yandex.ru/metrika/tag.js", "ym");',
                `ym(${JSON.stringify(ymId)}, "init", { clickmap:true, trackLinks:true, accurateTrackBounce:true, webvisor:true });`,
            ].join('');
            document.head.appendChild(s);
            injected = true;
        }

        if (typeof gaId === 'string' && gaId !== '') {
            const gtagSrc = document.createElement('script');
            gtagSrc.async = true;
            gtagSrc.src = `https://www.googletagmanager.com/gtag/js?id=${encodeURIComponent(gaId)}`;
            document.head.appendChild(gtagSrc);
            const inline = document.createElement('script');
            const dataLayerEmpty = '||' + ' []';
            inline.textContent = [
                `window.dataLayer = window.dataLayer ${dataLayerEmpty};`,
                'function gtag(){dataLayer.push(arguments);}',
                "gtag('js', new Date());",
                `gtag('config', ${JSON.stringify(gaId)});`,
            ].join('');
            document.head.appendChild(inline);
            injected = true;
        }

        if (injected) {
            Reflect.set(window, '__linnexAnalyticsInjected', true);
        }
    }

    _renderPublic(routeKey: string, params: Record<string, string>) {
        const slug = typeof params.slug === 'string' ? params.slug : '';
        let page;
        switch (routeKey) {
            case 'landing':            page = html`<landing-page></landing-page>`; break;
            case 'search':             page = html`<public-search-page></public-search-page>`; break;
            case 'product-agents':     page = html`<product-agents-page></product-agents-page>`; break;
            case 'product-rag':        page = html`<product-rag-page></product-rag-page>`; break;
            case 'product-crm':        page = html`<product-crm-page></product-crm-page>`; break;
            case 'product-sync':       page = html`<product-sync-page></product-sync-page>`; break;
            case 'product-documents':  page = html`<product-documents-page></product-documents-page>`; break;
            case 'product-geo':        page = html`<product-geo-page></product-geo-page>`; break;
            case 'product-wiki':       page = html`<product-wiki-page></product-wiki-page>`; break;
            case 'product-shop':       page = html`<product-shop-page></product-shop-page>`; break;
            case 'policy':             page = html`<legal-page kind="policy"></legal-page>`; break;
            case 'terms':              page = html`<legal-page kind="terms"></legal-page>`; break;
            case 'cookies':            page = html`<legal-page kind="cookies"></legal-page>`; break;
            case 'cookie-consent':     page = html`<legal-page kind="cookie_consent"></legal-page>`; break;
            case 'support':            page = html`<support-page></support-page>`; break;
            case 'digital-workers':    page = html`<landing-digital-workers-page></landing-digital-workers-page>`; break;
            case 'blog':               page = html`<blog-list-page></blog-list-page>`; break;
            case 'blog-post':          page = html`<blog-post-page .slug=${slug}></blog-post-page>`; break;
            case 'about':              page = html`<about-page></about-page>`; break;
            case 'roadmap':            page = html`<roadmap-page></roadmap-page>`; break;
            case 'login':              page = html`<login-page></login-page>`; break;
            case 'join':               page = html`<join-page></join-page>`; break;
            case 'select-company':     page = html`<select-company-page></select-company-page>`; break;
            default:                   page = html`<landing-page></landing-page>`; break;
        }
        return html`${page}<cookie-consent-banner></cookie-consent-banner>`;
    }

    _renderConsole(routeKey: string) {
        let content;
        switch (routeKey) {
            case 'dashboard':         content = html`<dashboard-page></dashboard-page>`; break;
            case 'platform_services': content = html`<platform-services-page></platform-services-page>`; break;
            case 'team':              content = html`<frontend-team-page></frontend-team-page>`; break;
            case 'access':            content = html`<frontend-access-page></frontend-access-page>`; break;
            case 'namespaces':        content = html`<frontend-namespaces-page></frontend-namespaces-page>`; break;
            case 'api-keys':          content = html`<frontend-api-keys-page></frontend-api-keys-page>`; break;
            case 'company-variables': content = html`<frontend-company-variables-page></frontend-company-variables-page>`; break;
            case 'company-voice-providers': content = html`<frontend-company-voice-providers-page></frontend-company-voice-providers-page>`; break;
            case 'embed-configs':     content = html`<frontend-embed-configs-page></frontend-embed-configs-page>`; break;
            case 'billing':           content = html`<frontend-billing-page></frontend-billing-page>`; break;
            case 'scheduler-tasks':   content = html`<frontend-scheduler-tasks-page></frontend-scheduler-tasks-page>`; break;
            case 'settings':          content = html`<frontend-settings-page></frontend-settings-page>`; break;
            case 'lead-requests':     content = html`<frontend-leads-requests-page></frontend-leads-requests-page>`; break;
            case 'platform-tracing':  content = html`<frontend-tracing-page></frontend-tracing-page>`; break;
            case 'crawl-report':      content = html`<frontend-crawl-report-page></frontend-crawl-report-page>`; break;
            case 'platform-billing':  content = html`<frontend-billing-admin-page></frontend-billing-admin-page>`; break;
            default:                  content = html`<dashboard-page></dashboard-page>`; break;
        }
        return html`
            <div class="console">
                <div class="sidebar"><frontend-sidebar></frontend-sidebar></div>
                <div class="main">
                    <platform-island
                        padding=${this._frontendMobile ? 'none' : 'md'}
                        ?safe-bottom=${this._frontendMobile}
                    >${content}</platform-island>
                </div>
            </div>
        `;
    }
}

customElements.define('frontend-app', FrontendApp);
