/**
 * RagApp — корневой компонент сервиса RAG.
 *
 * Полностью event-driven canon: все доменные сущности описаны фабриками
 * в `events/resources/*.resource.js` и регистрируются через `static factories`.
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
import { PlatformApp } from '@platform/lib/base/PlatformApp.js';
import { createRouterEffect } from '@platform/lib/events/effects/router.effect.js';

import { providersResource, providerSwitchOp } from '../events/resources/providers.resource.js';
import { namespacesResource, namespaceCreateForm } from '../events/resources/namespaces.resource.js';
import {
    documentsResource,
    documentUploadOp,
    documentRemoveOp,
    documentIngestTextOp,
} from '../events/resources/documents.resource.js';
import { documentStatusResource } from '../events/resources/document-status.resource.js';
import { searchOp } from '../events/resources/search.resource.js';
import { applyTenantHostRedirectIfNeeded } from '@platform/lib/utils/tenant-host-guard.js';
import { COMPANIES_EVENTS } from '@platform/lib/events/reducers/companies.js';

import '@platform/lib/components/layout/platform-island.js';
import '../components/rag-sidebar.js';
import '../pages/namespaces-page.js';
import '../pages/namespace-page.js';
import '../pages/search-page.js';
import '../pages/settings-page.js';
import '../modals/namespace-create-modal.js';

const RAG_ROUTES = [
    { key: 'namespaces',       path: '' },
    { key: 'platform_services', path: 'services', parent: 'namespaces' },
    { key: 'namespace_detail', path: 'namespaces/:namespaceId', parent: 'namespaces' },
    { key: 'search',           path: 'search' },
    { key: 'settings',         path: 'settings' },
];

export class RagApp extends PlatformApp {
    static defaultI18nNamespace = 'rag';

    constructor() {
        super();
        this._companiesListSel = this.select((s) => s.companies.list);
        this._companiesLoadingSel = this.select((s) => s.companies.loading);
    }

    static factories = [
        providersResource,
        providerSwitchOp,
        namespacesResource,
        namespaceCreateForm,
        documentsResource,
        documentUploadOp,
        documentRemoveOp,
        documentIngestTextOp,
        documentStatusResource,
        searchOp,
    ];

    static styles = [
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

    getBaseUrl() { return '/rag'; }

    getRoutes() { return []; }

    getServiceEffects() {
        return [
            createRouterEffect({ baseUrl: '/rag', routes: RAG_ROUTES }),
        ];
    }

    updated(changed) {
        super.updated(changed);
        const auth = this._authSelect.value;
        applyTenantHostRedirectIfNeeded(
            auth,
            this._companiesListSel.value,
            this._companiesLoadingSel.value,
            { loadCompanies: () => this.dispatch(COMPANIES_EVENTS.LOAD_REQUESTED, null) },
        );
    }

    renderRoute(routeKey, params) {
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
