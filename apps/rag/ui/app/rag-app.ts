/**
 * RagApp — корневой компонент сервиса RAG.
 *
 * Полностью event-driven canon: все доменные сущности описаны фабриками
 * в `@platform/lib/events/resources/rag-*.resource.js` и регистрируются через `static factories`.
 * Никаких ручных slice/effect/reducer/selectors. Маршрутизация — через
 * core router.effect (`createRouterEffect`), SPA сервится по `/rag`.
 *
 * Маршруты:
 *   /rag                                  → namespaces
 *   /rag/namespaces/:namespaceId          → namespace_detail
 *   /rag/search                           → search
 *   /rag/settings                         → settings
 */

import { html, css } from 'lit';
import type { PropertyValues } from '@platform/lib/lit-shim.js';
import { PlatformApp } from '@platform/lib/base/PlatformApp.js';
import type { SelectController } from '@platform/lib/events/select-controller.js';
import { createRouterEffect } from '@platform/lib/events/effects/router.effect.js';
import { platformFileCreateOp } from '@platform/lib/events/factories/platform-file-create.js';

import { providersResource } from '@platform/lib/events/resources/rag-providers.resource.js';
import { namespacesResource, namespaceCreateForm } from '@platform/lib/events/resources/rag-namespaces.resource.js';
import {
    documentsResource,
    documentUploadOp,
    documentRemoveOp,
} from '@platform/lib/events/resources/rag-documents.resource.js';
import { documentStatusResource } from '@platform/lib/events/resources/rag-document-status.resource.js';
import { searchOp, searchDefaultsOp } from '@platform/lib/events/resources/rag-search.resource.js';
import { applyCompanyHostRedirectIfNeeded } from '@platform/lib/utils/company-host-guard.js';
import { COMPANIES_EVENTS } from '@platform/lib/events/reducers/companies.js';
import type { CompaniesState } from '@platform/lib/events/reducers/companies.js';
import type { CompanyListEntry } from '@platform/lib/utils/company-host-guard.js';
import { buildRagAssistantContext } from '../_helpers/platform-assistant-context.js';

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
import '../components/rag-sidebar.js';
import '../pages/namespaces-page.js';
import '../pages/namespace-page.js';
import '../pages/search-page.js';
import '../pages/settings-page.js';
import '../modals/namespace-create-modal.js';

const RAG_ROUTES = [
    { key: 'namespaces',        path: '',                              titleKey: 'routes.namespaces' },
    { key: 'platform_services', path: 'services',                      parent: 'namespaces',  titleKey: 'routes.platform_services' },
    { key: 'namespace_detail',  path: 'namespaces/:namespaceId',       parent: 'namespaces',  titleKey: 'routes.namespace_detail' },
    { key: 'search',            path: 'search',                                                titleKey: 'routes.search' },
    { key: 'settings',          path: 'settings',                                              titleKey: 'routes.settings' },
];

/**
 * Нижняя навигация (mobile shell 2026): базы знаний, поиск, настройки, профиль.
 */
const RAG_BOTTOM_NAV_ITEMS = [
    { key: 'namespaces', routeKey: 'namespaces', icon: 'box',      labelKey: 'bottom_nav.namespaces' },
    { key: 'search',     routeKey: 'search',     icon: 'search',   labelKey: 'bottom_nav.search' },
    { key: 'settings',   routeKey: 'settings',   icon: 'settings', labelKey: 'bottom_nav.settings' },
    { key: 'profile',    sheet: 'platform.service_switcher', icon: 'user', labelKey: 'bottom_nav.profile' },
];

export class RagApp extends PlatformApp {
    static defaultI18nNamespace = 'rag';
    static bottomNavItems = RAG_BOTTOM_NAV_ITEMS;
    static bottomNavHideOnRoutes = [];
    static platformAssistant = {
        branchId: 'documents',
        serviceId: 'rag',
        showLauncher: true,
    };

    private _companiesListSel: SelectController<readonly CompanyListEntry[]>;
    private _companiesLoadingSel: SelectController<boolean>;

    constructor() {
        super();
        this._companiesListSel = this.select((s) => companyListEntries((s.companies as CompaniesState).list));
        this._companiesLoadingSel = this.select((s) => Boolean((s.companies as CompaniesState).loading));
    }

    static factories = [
        providersResource,
        namespacesResource,
        namespaceCreateForm,
        documentsResource,
        documentUploadOp,
        documentRemoveOp,
        documentStatusResource,
        searchOp,
        searchDefaultsOp,
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

    override getBaseUrl() { return '/rag'; }

    override getRoutes() { return []; }

    override getServiceEffects() {
        return [
            createRouterEffect({ baseUrl: '/rag', routes: RAG_ROUTES }),
        ];
    }

    override shouldRenderPlatformAssistant(_routeKey: string | null) {
        return true;
    }

    override async getPlatformAssistantContextVariables(routeKey: string | null, params: Record<string, string>) {
        return buildRagAssistantContext(routeKey === undefined || routeKey === null ? '' : routeKey, params);
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

    override renderRoute(routeKey: string | null, params: Record<string, string>) {
        let content;
        switch (routeKey) {
            case 'platform_services':
                content = html`<platform-services-page></platform-services-page>`;
                break;
            case 'namespaces':
                content = html`<rag-namespaces-page></rag-namespaces-page>`;
                break;
            case 'namespace_detail':
                content = html`<rag-namespace-page .namespaceId=${params.namespaceId}></rag-namespace-page>`;
                break;
            case 'search':
                content = html`<rag-search-page></rag-search-page>`;
                break;
            case 'settings':
                content = html`<rag-settings-page></rag-settings-page>`;
                break;
            default:
                content = html`<rag-namespaces-page></rag-namespaces-page>`;
                break;
        }
        return html`
            <div class="sidebar"><rag-sidebar></rag-sidebar></div>
            <div class="main">
                <platform-island>${content}</platform-island>
            </div>
        `;
    }
}

customElements.define('rag-app', RagApp);
