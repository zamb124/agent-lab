/**
 * Documents explorer: «Все документы» = корень namespace (каталоги, без GET /documents).
 */

import { fixture, fixtureCleanup, html, expect, elementUpdated, waitUntil } from '../helpers/render.js';
import { resetPlatformState, bootstrapTestBus } from '../helpers/reset.js';
import { getPlatformBus, CoreEvents } from '@platform/lib/events/index.js';
import { platformWs } from '@platform/lib/events/effects/ws.effect.js';
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
import {q, qs, qsa, shadow, type TestEl} from '../helpers/dom.js';

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

function asUrl(raw: any) {
    return new URL(String(raw), 'http://local.test');
}

function installOfficeFetch() {
    const prevFetch = window.fetch;
    window.fetch = async (url, init: any = {}) => {
        const method = (init.method || 'GET').toUpperCase();
        const raw = String(url);
        const pathname = asUrl(raw).pathname;
        if (
            pathname.startsWith('/api/i18n/')
            || pathname.startsWith('/api/platform/')
            || pathname === '/health'
        ) {
            return prevFetch(url, init);
        }
        if (raw.includes('/static/core/assets/') || raw.includes('jsdelivr.net') || raw.startsWith('blob:')) {
            return new Response('<svg xmlns="http://www.w3.org/2000/svg"></svg>', {
                status: 200,
                headers: { 'content-type': 'image/svg+xml' },
            });
        }
        throw new Error(`fake fetch: no handler for ${method} ${raw}`);
    };
    return {
        uninstall() {
            window.fetch = prevFetch;
        },
    };
}

function installOfficeWs() {
    const calls: any[] = [];
    const original = platformWs.request;
    platformWs.request = async (opts) => {
        if (!opts || typeof opts.type !== 'string') {
            throw new Error('office ws stub: opts.type required');
        }
        calls.push({ type: opts.type, payload: opts.payload });
        if (opts.type === 'office/catalogs/list_requested') {
            return { items: CATALOGS };
        }
        if (opts.type === 'office/namespaces/list_requested') {
            return {
                items: [{ name: 'default', is_default: true }],
                total: 1,
                limit: 200,
                offset: 0,
            };
        }
        if (opts.type === 'office/integration/status_requested') {
            return { configured: true };
        }
        if (opts.type === 'office/documents/list_requested') {
            const payload = opts.payload;
            if (!payload || typeof payload !== 'object') {
                throw new Error('documents list without payload');
            }
            const catalogIds = (payload as Record<string, unknown>).catalog_ids;
            const ids: unknown[] = Array.isArray(catalogIds) ? catalogIds : [];
            if (ids.length === 0) {
                throw new Error('documents list without catalog_ids');
            }
            const items = ids.includes('cat-flows') ? [FLOWS_DOC] : [];
            return { items };
        }
        throw new Error(`unexpected ws: ${opts.type}`);
    };
    return {
        calls,
        uninstall() {
            platformWs.request = original;
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

function documentsListCalls(wsMock: any) {
    return wsMock.calls.filter((call: any) => call.type === 'office/documents/list_requested');
}

describe('office documents explorer root', () => {
    let fetchMock: any;
    let wsMock: any;

    beforeEach(() => {
        window.localStorage.clear();
        resetPlatformState();
        setDefaultI18nNamespace('documents');
        fetchMock = installOfficeFetch();
        bootstrapTestBus({ factories: FACTORIES });
        wsMock = installOfficeWs();
        seedAuth();
        seedTranslations();
    });

    afterEach(() => {
        fetchMock.uninstall();
        wsMock.uninstall();
        qsa(document!, 'office-documents-explorer-page, office-sidebar').forEach((node) => node.remove());
        fixtureCleanup();
    });

    it('корень показывает каталоги, без GET /documents; Flows и хлебная крошка корня', async () => {
        const host = await fixture<TestEl>(html`
            <div>
                <office-sidebar></office-sidebar>
                <office-documents-explorer-page></office-documents-explorer-page>
            </div>
        `);
        const page = qs(host!, 'office-documents-explorer-page');
        const sidebar = qs(host!, 'office-sidebar');
        await waitUntil(
            () => qsa(shadow(page), 'platform-file-row[item-kind="catalog"]').length >= 2,
            'root catalog rows',
            { timeout: 4000 },
        );
        await elementUpdated(page);

        expect(page._documents.state.activeCatalogId).to.equal(null);
        const rootRows = [...qsa(shadow(page), 'platform-file-row[item-kind="catalog"]')];
        const rootNames = rootRows.map((row) => row.getAttribute('file-name'));
        expect(rootNames).to.include('Flows');
        expect(rootNames).to.include('lara');
        expect(rootNames).to.not.include('my-flow');
        expect(q(shadow(page), 'platform-file-row[file-name="Data table.sqlite"]')).to.equal(null);
        expect(documentsListCalls(wsMock)).to.have.length(0);

        const toolbar = qs(shadow(page), 'office-file-toolbar');
        expect(toolbar.actionsDisabled).to.equal(true);
        const uploadBtn = qs(shadow(toolbar), '.actions .btn-primary');
        expect(uploadBtn.disabled).to.equal(true);

        const flowsRow = rootRows.find((row) => row.getAttribute('file-name') === 'Flows');
        qs(shadow(flowsRow!), '.row').dispatchEvent(new MouseEvent('dblclick', { bubbles: true }));
        await waitUntil(
            () => q(shadow(page), 'platform-file-row[file-name="Data table.sqlite"]'),
            'flows catalog file row',
            { timeout: 4000 },
        );
        await elementUpdated(page);

        expect(page._documents.state.activeCatalogId).to.equal('cat-flows');
        const listCalls = documentsListCalls(wsMock);
        expect(listCalls.length).to.be.greaterThan(0);
        expect(listCalls.every((call: any) => Array.isArray(call.payload.catalog_ids) && call.payload.catalog_ids.includes('cat-flows'))).to.equal(true);
        expect(q(shadow(page), 'platform-file-row[file-name="Data table.sqlite"]')).to.exist;
        expect(q(shadow(page), 'platform-file-row[file-name="lara"]')).to.equal(null);

        const crumbs = [...qsa(shadow(toolbar), 'button.crumb')];
        expect(crumbs[0]!.disabled).to.equal(false);
        crumbs[0]!.click();
        await waitUntil(
            () => page._documents.state.activeCatalogId === null
                && q(shadow(page), 'platform-file-row[file-name="lara"]'),
            'breadcrumb back to root',
            { timeout: 4000 },
        );
        expect(q(shadow(page), 'platform-file-row[file-name="Data table.sqlite"]')).to.equal(null);

        const flowsAgain = qs(shadow(page), 'platform-file-row[file-name="Flows"]');
        qs(shadow(flowsAgain), '.row').dispatchEvent(new MouseEvent('dblclick', { bubbles: true }));
        await waitUntil(
            () => page._documents.state.activeCatalogId === 'cat-flows',
            'reopen flows catalog',
            { timeout: 4000 },
        );

        const rail = qs(shadow(sidebar), 'office-explorer-nav-rail');
        const allBtn = qs(shadow(rail), 'button.item');
        expect(allBtn).to.exist;
        (allBtn as TestEl).click();
        await waitUntil(
            () => page._documents.state.activeCatalogId === null
                && q(shadow(page), 'platform-file-row[file-name="lara"]'),
            'nav rail all documents',
            { timeout: 4000 },
        );
        expect(documentsListCalls(wsMock).every((call: any) => {
            const ids = call.payload && Array.isArray(call.payload.catalog_ids) ? call.payload.catalog_ids : [];
            return ids.length > 0;
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
        const host = await fixture<TestEl>(html`
            <div>
                <office-sidebar></office-sidebar>
                <office-documents-explorer-page></office-documents-explorer-page>
            </div>
        `);
        const page = qs(host!, 'office-documents-explorer-page');
        await waitUntil(
            () => page._documents.state.activeCatalogId === 'cat-flow-child',
            'deep link nested catalog',
            { timeout: 4000 },
        );
        await elementUpdated(page);
        expect(q(shadow(page), 'platform-file-row[file-name="lara"]')).to.equal(null);
        expect(q(shadow(page), 'platform-file-row[file-name="Flows"]')).to.equal(null);
        const toolbar = qs(shadow(page), 'office-file-toolbar');
        const crumbs = [...qsa(shadow(toolbar), 'button.crumb')];
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
        const host = await fixture<TestEl>(html`
            <div>
                <office-sidebar></office-sidebar>
                <office-documents-explorer-page></office-documents-explorer-page>
            </div>
        `);
        const page = qs(host!, 'office-documents-explorer-page');
        await waitUntil(
            () => page._documents.state.activeCatalogId === 'cat-flow-child',
            'deep link catalog without namespace',
            { timeout: 4000 },
        );
        await elementUpdated(page);
        expect(q(shadow(page), 'platform-file-row[file-name="lara"]')).to.equal(null);
        const toolbar = qs(shadow(page), 'office-file-toolbar');
        const crumbs = [...qsa(shadow(toolbar), 'button.crumb')];
        const crumbLabels = crumbs.map((crumb) => crumb.textContent.trim());
        expect(crumbLabels).to.include('my-flow');
    });
});
