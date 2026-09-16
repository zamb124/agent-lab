/**
 * Documents explorer: «Все документы» = корень namespace (каталоги, без GET /documents).
 */

import { fixture, fixtureCleanup, html, expect, elementUpdated, waitUntil } from '../helpers/render.js';
import { resetPlatformState, bootstrapTestBus } from '../helpers/reset.js';
import { getPlatformBus, CoreEvents } from '@platform/lib/events/index.js';
import { setDefaultI18nNamespace } from '@platform/lib/utils/i18n-namespace.js';
import { integrationStatusOp } from '../../../../apps/office/ui/events/resources/integration.resource.js';
import { namespacesResource } from '../../../../apps/office/ui/events/resources/namespaces.resource.js';
import { catalogsResource } from '../../../../apps/office/ui/events/resources/catalogs.resource.js';
import {
    documentsOp,
    deletedDocumentsOp,
    documentUploadOp,
    documentRemoveOp,
    documentRestoreOp,
    documentPermanentDeleteOp,
    documentShareCreateOp,
    documentMoveOp,
} from '../../../../apps/office/ui/events/resources/documents.resource.js';
import { catalogRagSearchOp } from '../../../../apps/office/ui/events/resources/catalog-rag-search.resource.js';
import documentsEn from '../../../../core/i18n/translations/en/documents.json' with { type: 'json' };
import platformEn from '../../../../core/i18n/translations/en/platform.json' with { type: 'json' };
import '../../../../apps/office/ui/pages/documents-explorer-page.js';
import '../../../../apps/office/ui/components/office-sidebar.js';

const FACTORIES = [
    integrationStatusOp,
    namespacesResource,
    catalogsResource,
    documentsOp,
    deletedDocumentsOp,
    documentUploadOp,
    documentRemoveOp,
    documentRestoreOp,
    documentPermanentDeleteOp,
    documentShareCreateOp,
    documentMoveOp,
    catalogRagSearchOp,
];

const CATALOGS = [
    {
        catalog_id: 'cat-lara',
        title: 'lara',
        parent_catalog_id: null,
        file_count: 3,
        is_owner: true,
        company_visible: true,
        owner_user_id: 'u1',
        rag_index_enabled: false,
    },
    {
        catalog_id: 'cat-flows',
        title: 'Flows',
        parent_catalog_id: null,
        file_count: 1,
        is_owner: true,
        company_visible: true,
        owner_user_id: 'u1',
        rag_index_enabled: false,
    },
    {
        catalog_id: 'cat-flow-child',
        title: 'my-flow',
        parent_catalog_id: 'cat-flows',
        file_count: 1,
        is_owner: true,
        company_visible: true,
        owner_user_id: 'u1',
        rag_index_enabled: false,
    },
];

const FLOWS_DOC = {
    file_id: 'file-in-flows',
    catalog_id: 'cat-flows',
    title: 'Data table.sqlite',
    file_category: 'data_table',
    file_size: 2048,
    created_at: '2026-01-01T00:00:00Z',
    updated_at: '2026-01-01T00:00:00Z',
    created_by_user_id: 'u1',
    created_by_display_name: 'Tester',
    created_by_avatar_url: null,
    file_availability: 'available',
};

function asUrl(raw) {
    return new URL(String(raw), 'http://local.test');
}

function isDocumentsList(raw) {
    const pathname = asUrl(raw).pathname;
    return pathname === '/documents/api/v1/documents' || pathname === '/documents/api/v1/documents/';
}

function jsonResponse(body) {
    return new Response(JSON.stringify(body), {
        status: 200,
        headers: { 'content-type': 'application/json' },
    });
}

function installOfficeFetch() {
    const calls = [];
    const prevFetch = window.fetch;
    window.fetch = async (url, init = {}) => {
        const method = (init.method || 'GET').toUpperCase();
        const raw = String(url);
        calls.push({ url: raw, method, init });
        const pathname = asUrl(raw).pathname;
        if (raw.includes('/static/core/assets/') || raw.includes('jsdelivr.net') || raw.startsWith('blob:')) {
            return new Response('<svg xmlns="http://www.w3.org/2000/svg"></svg>', {
                status: 200,
                headers: { 'content-type': 'image/svg+xml' },
            });
        }
        if (method === 'GET' && (pathname === '/documents/api/v1/catalogs' || pathname === '/documents/api/v1/catalogs/')) {
            return jsonResponse({ items: CATALOGS });
        }
        if (method === 'GET' && pathname.includes('/documents/api/v1/namespaces')) {
            return jsonResponse({
                items: [{ name: 'default', is_default: true }],
                total: 1,
                limit: 200,
                offset: 0,
            });
        }
        if (method === 'GET' && pathname.includes('/integration/status')) {
            return jsonResponse({ configured: true });
        }
        if (method === 'GET' && isDocumentsList(raw)) {
            const ids = asUrl(raw).searchParams.getAll('catalog_ids');
            if (ids.length === 0 && !asUrl(raw).searchParams.get('catalog_id')) {
                throw new Error(`documents list without catalog_ids: ${raw}`);
            }
            const items = ids.includes('cat-flows') ? [FLOWS_DOC] : [];
            return jsonResponse({ items });
        }
        throw new Error(`fake fetch: no handler for ${method} ${raw}`);
    };
    return {
        calls,
        uninstall() {
            window.fetch = prevFetch;
        },
    };
}

function seedTranslations() {
    const bus = getPlatformBus();
    const prevEn = bus.getState().i18n.translations.en;
    bus.dispatch(
        CoreEvents.I18N_LOCALE_LOADED,
        {
            locale: 'en',
            bundle: {
                ...prevEn,
                platform: platformEn,
                documents: documentsEn,
            },
        },
        { source: 'system' },
    );
    bus.dispatch(
        CoreEvents.I18N_LOCALE_CHANGED,
        { locale: 'en', default_namespace: 'documents' },
        { source: 'system' },
    );
}

function seedAuth() {
    getPlatformBus().dispatch(
        CoreEvents.AUTH_USER_LOADED,
        {
            user: {
                user_id: 'u1',
                name: 'Tester',
                company_id: 'c1',
                raw: { user_id: 'u1', emails: ['tester@example.com'] },
            },
        },
        { source: 'system' },
    );
}

function documentsListCalls(fetchMock) {
    return fetchMock.calls.filter((call) => call.method === 'GET' && isDocumentsList(call.url));
}

describe('office documents explorer root', () => {
    let fetchMock;

    beforeEach(() => {
        window.localStorage.clear();
        resetPlatformState();
        setDefaultI18nNamespace('documents');
        fetchMock = installOfficeFetch();
        bootstrapTestBus({ factories: FACTORIES });
        seedAuth();
        seedTranslations();
    });

    afterEach(() => {
        fetchMock.uninstall();
        document.querySelectorAll('office-documents-explorer-page, office-sidebar').forEach((node) => node.remove());
        fixtureCleanup();
    });

    it('корень показывает каталоги, без GET /documents; Flows и хлебная крошка корня', async () => {
        const host = await fixture(html`
            <div>
                <office-sidebar></office-sidebar>
                <office-documents-explorer-page></office-documents-explorer-page>
            </div>
        `);
        const page = host.querySelector('office-documents-explorer-page');
        const sidebar = host.querySelector('office-sidebar');
        await waitUntil(
            () => page.shadowRoot.querySelectorAll('platform-file-row[item-kind="catalog"]').length >= 2,
            { timeout: 4000 },
        );
        await elementUpdated(page);

        expect(page._documents.state.activeCatalogId).to.equal(null);
        const rootRows = [...page.shadowRoot.querySelectorAll('platform-file-row[item-kind="catalog"]')];
        const rootNames = rootRows.map((row) => row.getAttribute('file-name'));
        expect(rootNames).to.include('Flows');
        expect(rootNames).to.include('lara');
        expect(rootNames).to.not.include('my-flow');
        expect(page.shadowRoot.querySelector('platform-file-row[file-name="Data table.sqlite"]')).to.equal(null);
        expect(documentsListCalls(fetchMock)).to.have.length(0);

        const toolbar = page.shadowRoot.querySelector('office-file-toolbar');
        expect(toolbar.actionsDisabled).to.equal(true);
        const uploadBtn = toolbar.shadowRoot.querySelector('.actions .btn-primary');
        expect(uploadBtn.disabled).to.equal(true);

        const flowsRow = rootRows.find((row) => row.getAttribute('file-name') === 'Flows');
        flowsRow.shadowRoot.querySelector('.row').dispatchEvent(new MouseEvent('dblclick', { bubbles: true }));
        await waitUntil(
            () => page.shadowRoot.querySelector('platform-file-row[file-name="Data table.sqlite"]'),
            { timeout: 4000 },
        );
        await elementUpdated(page);

        expect(page._documents.state.activeCatalogId).to.equal('cat-flows');
        const listCalls = documentsListCalls(fetchMock);
        expect(listCalls.length).to.be.greaterThan(0);
        expect(listCalls.every((call) => asUrl(call.url).searchParams.getAll('catalog_ids').includes('cat-flows'))).to.equal(true);
        expect(page.shadowRoot.querySelector('platform-file-row[file-name="Data table.sqlite"]')).to.exist;
        expect(page.shadowRoot.querySelector('platform-file-row[file-name="lara"]')).to.equal(null);

        const crumbs = [...toolbar.shadowRoot.querySelectorAll('button.crumb')];
        expect(crumbs[0].disabled).to.equal(false);
        crumbs[0].click();
        await waitUntil(
            () => page._documents.state.activeCatalogId === null
                && page.shadowRoot.querySelector('platform-file-row[file-name="lara"]'),
            { timeout: 4000 },
        );
        expect(page.shadowRoot.querySelector('platform-file-row[file-name="Data table.sqlite"]')).to.equal(null);

        const flowsAgain = page.shadowRoot.querySelector('platform-file-row[file-name="Flows"]');
        flowsAgain.shadowRoot.querySelector('.row').dispatchEvent(new MouseEvent('dblclick', { bubbles: true }));
        await waitUntil(
            () => page._documents.state.activeCatalogId === 'cat-flows',
            { timeout: 4000 },
        );

        const rail = sidebar.shadowRoot.querySelector('office-explorer-nav-rail');
        const allBtn = rail.shadowRoot.querySelector('button.item');
        expect(allBtn).to.exist;
        allBtn.click();
        await waitUntil(
            () => page._documents.state.activeCatalogId === null
                && page.shadowRoot.querySelector('platform-file-row[file-name="lara"]'),
            { timeout: 4000 },
        );
        expect(documentsListCalls(fetchMock).every((call) => {
            const ids = asUrl(call.url).searchParams.getAll('catalog_ids');
            const catalogId = asUrl(call.url).searchParams.get('catalog_id');
            return ids.length > 0 || Boolean(catalogId);
        })).to.equal(true);
    });

    it('query catalog_id opens nested catalog after catalogs load', async () => {
        getPlatformBus().dispatch(
            CoreEvents.ROUTER_ROUTE_CHANGED,
            {
                routeKey: 'documents_list',
                params: {},
                pathname: '/documents',
                search: '?namespace=default&catalog_id=cat-flow-child',
            },
            { source: 'system' },
        );
        const host = await fixture(html`
            <div>
                <office-sidebar></office-sidebar>
                <office-documents-explorer-page></office-documents-explorer-page>
            </div>
        `);
        const page = host.querySelector('office-documents-explorer-page');
        await waitUntil(
            () => page._documents.state.activeCatalogId === 'cat-flow-child',
            { timeout: 4000 },
        );
        await elementUpdated(page);
        expect(page.shadowRoot.querySelector('platform-file-row[file-name="lara"]')).to.equal(null);
        expect(page.shadowRoot.querySelector('platform-file-row[file-name="Flows"]')).to.equal(null);
        const toolbar = page.shadowRoot.querySelector('office-file-toolbar');
        const crumbs = [...toolbar.shadowRoot.querySelectorAll('button.crumb')];
        const crumbLabels = crumbs.map((crumb) => crumb.textContent.trim());
        expect(crumbLabels).to.include('my-flow');
    });

    it('query catalog_id without namespace opens catalog in default workspace', async () => {
        getPlatformBus().dispatch(
            CoreEvents.ROUTER_ROUTE_CHANGED,
            {
                routeKey: 'documents_list',
                params: {},
                pathname: '/documents',
                search: '?catalog_id=cat-flow-child',
            },
            { source: 'system' },
        );
        const host = await fixture(html`
            <div>
                <office-sidebar></office-sidebar>
                <office-documents-explorer-page></office-documents-explorer-page>
            </div>
        `);
        const page = host.querySelector('office-documents-explorer-page');
        await waitUntil(
            () => page._documents.state.activeCatalogId === 'cat-flow-child',
            { timeout: 4000 },
        );
        await elementUpdated(page);
        expect(page.shadowRoot.querySelector('platform-file-row[file-name="lara"]')).to.equal(null);
        const toolbar = page.shadowRoot.querySelector('office-file-toolbar');
        const crumbs = [...toolbar.shadowRoot.querySelectorAll('button.crumb')];
        const crumbLabels = crumbs.map((crumb) => crumb.textContent.trim());
        expect(crumbLabels).to.include('my-flow');
    });
});
