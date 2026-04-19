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
 *   /documents/catalogs                          → documents_catalogs
 *   /documents/catalog/:catalogId                → documents_catalogs (legacy alias)
 *   /documents/edit/:bindingId                   → document_editor
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
import { companyMembersOp } from '../events/resources/company-members.resource.js';
import {
    documentsOp,
    documentCreateEmptyOp,
    documentUploadOp,
    documentRenameOp,
    documentRemoveOp,
    documentRenameForm,
} from '../events/resources/documents.resource.js';
import { documentEditorConfigOp } from '../events/resources/editor.resource.js';

import '@platform/lib/components/layout/platform-island.js';
import '../components/office-sidebar.js';
import '../components/onlyoffice-host.js';
import '../components/office-document-row.js';
import '../components/office-catalog-card.js';
import '../components/office-integration-banner.js';
import '../pages/documents-list-page.js';
import '../pages/documents-catalogs-page.js';
import '../pages/document-editor-page.js';
import '../modals/namespace-create-modal.js';
import '../modals/catalog-create-modal.js';
import '../modals/catalog-edit-modal.js';
import '../modals/catalog-members-modal.js';
import '../modals/document-rename-modal.js';
import '../modals/document-create-empty-modal.js';
import '../modals/document-upload-modal.js';

const OFFICE_ROUTES = [
    { key: 'documents_list',     path: '' },
    { key: 'documents_catalogs', path: 'catalogs',                parent: 'documents_list' },
    { key: 'documents_catalogs', path: 'catalog/:catalogId',      parent: 'documents_list' },
    { key: 'document_editor',    path: 'edit/:bindingId',         parent: 'documents_list' },
];

export class OfficeApp extends PlatformApp {
    static defaultI18nNamespace = 'documents';

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
        companyMembersOp,
        documentsOp,
        documentCreateEmptyOp,
        documentUploadOp,
        documentRenameOp,
        documentRemoveOp,
        documentRenameForm,
        documentEditorConfigOp,
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
        ];
    }

    renderRoute(routeKey, params) {
        let content;
        let editorMode = false;
        switch (routeKey) {
            case 'documents_list':
                content = html`<office-documents-list-page></office-documents-list-page>`;
                break;
            case 'documents_catalogs':
                content = html`<office-documents-catalogs-page
                    .focusCatalogId=${typeof params.catalogId === 'string' ? params.catalogId : ''}
                ></office-documents-catalogs-page>`;
                break;
            case 'document_editor':
                editorMode = true;
                content = html`<office-document-editor-page
                    .bindingId=${params.bindingId}
                ></office-document-editor-page>`;
                break;
            default:
                content = html`<office-documents-list-page></office-documents-list-page>`;
        }
        const islandPadding = editorMode ? 'none' : '';
        const islandContentNoScroll = editorMode;
        return html`
            <div class="sidebar"><office-sidebar></office-sidebar></div>
            <div class="main ${editorMode ? 'main--bleed' : ''}">
                <platform-island
                    padding=${islandPadding}
                    ?content-no-scroll=${islandContentNoScroll}
                >${content}</platform-island>
            </div>
        `;
    }
}

customElements.define('office-app', OfficeApp);
