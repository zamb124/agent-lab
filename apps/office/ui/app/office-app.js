/**
 * OfficeApp — корневой компонент сервиса Документы (`/documents`).
 *
 * Полностью event-driven canon: все доменные сущности — в фабриках
 * `events/resources/*.resource.js`, регистрируются через `static factories`.
 * Маршрутизация — через core router.effect (`createRouterEffect`),
 * SPA сервится по `/documents`. i18n — единственный бандл `documents`
 * (см. `core/i18n/translations/{ru,en}/documents.json`).
 *
 * Маршруты:
 *   /documents                                   → documents_list
 *   /documents/catalogs                          → redirect → documents_list (legacy)
 *   /documents/edit/:bindingId                   → document_editor
 *   /documents/embed/edit/:bindingId             → document_editor_embed
 */

import { html, css } from 'lit';
import { PlatformApp } from '@platform/lib/base/PlatformApp.js';
import { createRouterEffect } from '@platform/lib/events/effects/router.effect.js';

import { integrationStatusOp } from '../events/resources/integration.resource.js';
import {
    namespacesResource,
    namespaceCreateForm,
    namespaceTemplatesOp,
} from '../events/resources/namespaces.resource.js';
import {
    catalogsResource,
    catalogCreateForm,
    catalogEditForm,
} from '../events/resources/catalogs.resource.js';
import {
    catalogMembersOp,
    catalogMemberAddOp,
    catalogMemberRemoveOp,
} from '../events/resources/catalog-members.resource.js';
import {
    catalogRagStatusOp,
    catalogRagEnableOp,
    catalogRagDisableOp,
    catalogRagRebuildOp,
    catalogRagSettingsOp,
} from '../events/resources/catalog-rag.resource.js';
import { catalogRagSearchOp } from '../events/resources/catalog-rag-search.resource.js';
import { createOfficeCatalogsLegacyRoutesEffect } from '../events/office-catalogs-legacy-routes.effect.js';
import { companyMembersOp } from '../events/resources/company-members.resource.js';
import {
    documentsOp,
    buildDocumentsListPayload,
    documentCreateEmptyOp,
    documentUploadOp,
    documentRenameOp,
    documentRemoveOp,
    documentRenameForm,
    deletedDocumentsOp,
    documentRestoreOp,
    documentPermanentDeleteOp,
    documentMoveOp,
    documentShareCreateOp,
} from '../events/resources/documents.resource.js';
import {
    catalogAccessGetOp,
    catalogAccessPatchOp,
    catalogAccessRotateLinkOp,
    documentAccessGetOp,
    documentAccessPatchOp,
    documentAccessRotateLinkOp,
    publicResolveOp,
    publicOpenOp,
    publicCatalogItemsOp,
    publicCatalogBindingOpenOp,
} from '../events/resources/access.resource.js';
import { documentEditorConfigOp } from '../events/resources/editor.resource.js';
import { applyCompanyHostRedirectIfNeeded } from '@platform/lib/utils/company-host-guard.js';
import { COMPANIES_EVENTS } from '@platform/lib/events/reducers/companies.js';

import '@platform/lib/components/layout/platform-island.js';
import '../components/office-sidebar.js';
import '../components/sheets/office-workspace-picker-sheet.js';
import '@platform/lib/components/platform-onlyoffice-host.js';
import '../components/office-integration-banner.js';
import '../pages/documents-explorer-page.js';
import '../components/sheets/office-catalog-picker-sheet.js';
import '@platform/lib/components/platform-file-table.js';
import '@platform/lib/components/platform-file-row.js';
import '@platform/lib/components/platform-file-card.js';
import '../pages/document-editor-page.js';
import '../modals/namespace-create-modal.js';
import '../modals/catalog-create-modal.js';
import '../modals/catalog-edit-modal.js';
import '../modals/catalog-members-modal.js';
import '../modals/catalog-rag-modal.js';
import '../modals/document-rename-modal.js';
import '../modals/document-create-empty-modal.js';
import '../modals/document-upload-modal.js';
import '../modals/office-access-modal.js';
import '../pages/office-public-preview-page.js';

const OFFICE_ROUTES = [
    { key: 'documents_list',     path: '',                                           titleKey: 'routes.documents_list' },
    { key: 'documents_recent',   path: 'recent',           parent: 'documents_list', titleKey: 'routes.documents_recent' },
    { key: 'platform_services',  path: 'services',           parent: 'documents_list', titleKey: 'routes.platform_services' },
    { key: 'documents_catalogs', path: 'catalogs',           parent: 'documents_list', titleKey: 'routes.documents_catalogs' },
    { key: 'documents_public_preview', path: 'p/:token', titleKey: 'routes.documents_public_preview' },
    { key: 'document_editor',    path: 'edit/:bindingId',    parent: 'documents_list', titleKey: 'routes.document_editor' },
    { key: 'document_editor_embed', path: 'embed/edit/:bindingId', titleKey: 'routes.document_editor' },
];

/**
 * Нижняя навигация (mobile shell 2026): Documents, Recent, Profile.
 */
const OFFICE_BOTTOM_NAV_ITEMS = [
    { key: 'documents', routeKey: 'documents_list',     icon: 'doc-detail', labelKey: 'bottom_nav.documents' },
    { key: 'recent',    routeKey: 'documents_recent',   icon: 'clock',      labelKey: 'bottom_nav.recent' },
    { key: 'profile',   sheet: 'platform.service_switcher', icon: 'user',   labelKey: 'bottom_nav.profile' },
];

const OFFICE_BOTTOM_NAV_HIDE_ON_ROUTES = ['document_editor', 'documents_public_preview'];

export class OfficeApp extends PlatformApp {
    static defaultI18nNamespace = 'documents';
    static bottomNavItems = OFFICE_BOTTOM_NAV_ITEMS;
    static bottomNavHideOnRoutes = OFFICE_BOTTOM_NAV_HIDE_ON_ROUTES;

    constructor() {
        super();
        this._companiesListSel = this.select((s) => s.companies.list);
        this._companiesLoadingSel = this.select((s) => s.companies.loading);
    }

    static factories = [
        integrationStatusOp,
        namespacesResource,
        namespaceCreateForm,
        namespaceTemplatesOp,
        catalogsResource,
        catalogCreateForm,
        catalogEditForm,
        catalogMembersOp,
        catalogMemberAddOp,
        catalogMemberRemoveOp,
        catalogRagStatusOp,
        catalogRagEnableOp,
        catalogRagDisableOp,
        catalogRagRebuildOp,
        catalogRagSettingsOp,
        catalogRagSearchOp,
        companyMembersOp,
        documentsOp,
        documentCreateEmptyOp,
        documentUploadOp,
        documentRenameOp,
        documentRemoveOp,
        documentRenameForm,
        deletedDocumentsOp,
        documentRestoreOp,
        documentPermanentDeleteOp,
    documentMoveOp,
    documentShareCreateOp,
    documentEditorConfigOp,
    catalogAccessGetOp,
    catalogAccessPatchOp,
    catalogAccessRotateLinkOp,
    documentAccessGetOp,
    documentAccessPatchOp,
    documentAccessRotateLinkOp,
    publicResolveOp,
    publicOpenOp,
    publicCatalogItemsOp,
    publicCatalogBindingOpenOp,
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
                --documents-title-gradient: linear-gradient(
                    135deg,
                    rgba(180, 140, 255, 0.95) 0%,
                    rgba(140, 180, 255, 0.95) 50%,
                    rgba(110, 200, 240, 0.95) 100%
                );
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
            .main--bleed {
                padding: 0;
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

    getBaseUrl() { return '/documents'; }

    getRoutes() { return []; }

    getServiceEffects() {
        return [
            createRouterEffect({ baseUrl: '/documents', routes: OFFICE_ROUTES }),
            createOfficeCatalogsLegacyRoutesEffect(),
        ];
    }

    updated(changed) {
        super.updated(changed);
        const auth = this._authSelect.value;
        applyCompanyHostRedirectIfNeeded(
            auth,
            this._companiesListSel.value,
            this._companiesLoadingSel.value,
            { loadCompanies: () => this.dispatch(COMPANIES_EVENTS.LOAD_REQUESTED, null) },
        );
    }

    renderRoute(routeKey, params) {
        let content;
        let editorMode = false;
        let explorerFullBleed = false;
        switch (routeKey) {
            case 'platform_services':
                content = html`<platform-services-page></platform-services-page>`;
                break;
            case 'documents_list':
            case 'documents_recent':
                explorerFullBleed = true;
                content = html`<office-documents-explorer-page
                    .initialExplorerView=${routeKey === 'documents_recent' ? 'recent' : 'catalog'}
                ></office-documents-explorer-page>`;
                break;
            case 'document_editor':
                editorMode = true;
                content = html`<office-document-editor-page
                    .bindingId=${params.bindingId}
                ></office-document-editor-page>`;
                break;
            case 'document_editor_embed':
                editorMode = true;
                content = html`<office-document-editor-page
                    .bindingId=${params.bindingId}
                    ?embedded=${true}
                ></office-document-editor-page>`;
                return html`
                    <div class="main main--bleed">
                        <platform-island
                            padding="none"
                            ?content-no-scroll=${true}
                        >${content}</platform-island>
                    </div>
                `;
            case 'documents_public_preview':
                editorMode = true;
                return html`
                    <div class="main main--bleed">
                        <platform-island padding="none" ?content-no-scroll=${true}>
                            <office-public-preview-page .token=${params.token}></office-public-preview-page>
                        </platform-island>
                    </div>
                `;
            default:
                content = html`<office-documents-explorer-page></office-documents-explorer-page>`;
        }
        /** Редактор и explorer: остров без inset + без скролла у `.island-content`. Остальные маршруты — `padding="md"`. */
        const islandContentNoScroll = editorMode || explorerFullBleed;
        const mainBleed = editorMode || explorerFullBleed;
        return html`
            <div class="sidebar"><office-sidebar></office-sidebar></div>
            <div class="main ${mainBleed ? 'main--bleed' : ''}">
                <platform-island
                    padding=${islandContentNoScroll ? 'none' : 'md'}
                    ?content-no-scroll=${islandContentNoScroll}
                >${content}</platform-island>
            </div>
        `;
    }
}

customElements.define('office-app', OfficeApp);
