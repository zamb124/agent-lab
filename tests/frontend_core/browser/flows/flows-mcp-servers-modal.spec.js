import { fixture, fixtureCleanup, html, expect, aTimeout, waitUntil } from '../helpers/render.js';
import { resetPlatformState, bootstrapTestBus } from '../helpers/reset.js';
import { collectFactories, registerFactory, getPlatformBus, CoreEvents } from '@platform/lib/events/index.js';
import {
    mcpServersResource,
    mcpServersListOp,
    mcpServerUpdateOp,
    mcpServerSyncOp,
    mcpServerTestOp,
    mcpServerResetCatalogDefaultsOp,
    mcpBrandingLoadOp,
    mcpBrandingSlugSuggestOp,
    mcpBrandingUpsertOp,
    mcpBrandingRemoveOp,
    mcpCatalogStoreLoadOp,
    mcpCatalogInstallOp,
    mcpCatalogUninstallOp,
} from '../../../../apps/flows/ui/events/resources/mcp.resource.js';
import '../../../../apps/flows/ui/modals/flows-mcp-servers-modal.js';

const FACTORIES = [
    mcpServersResource,
    mcpServersListOp,
    mcpServerUpdateOp,
    mcpServerSyncOp,
    mcpServerTestOp,
    mcpServerResetCatalogDefaultsOp,
    mcpBrandingLoadOp,
    mcpBrandingSlugSuggestOp,
    mcpBrandingUpsertOp,
    mcpBrandingRemoveOp,
    mcpCatalogStoreLoadOp,
    mcpCatalogInstallOp,
    mcpCatalogUninstallOp,
];

function bootstrap() {
    for (const factory of FACTORIES) {
        registerFactory(factory);
    }
    const collected = collectFactories(FACTORIES);
    bootstrapTestBus({ slices: collected.slices, effects: collected.effects });
}

function createMcpModalFetchStub(routes) {
    const calls = [];
    const prevFetch = window.fetch;
    window.fetch = async (url, init = {}) => {
        const href = String(url);
        const method = (init.method || 'GET').toUpperCase();
        calls.push({ url: href, method, init });
        for (const route of routes) {
            if (route.method !== method) {
                continue;
            }
            if (!route.match(href)) {
                continue;
            }
            const body = typeof route.body === 'function' ? route.body(href, init) : route.body;
            return new Response(JSON.stringify(body), {
                status: route.status || 200,
                headers: { 'content-type': 'application/json' },
            });
        }
        throw new Error(`unexpected fetch: ${method} ${href}`);
    };
    return {
        calls,
        uninstall() {
            window.fetch = prevFetch;
        },
    };
}

function modalRoot(modal) {
    return modal.shadowRoot;
}

function segmentedSegments(control) {
    return [...control.shadowRoot.querySelectorAll('.segment')];
}

function clickPlatformButton(buttonEl) {
    const inner = buttonEl.shadowRoot.querySelector('button');
    inner.click();
}

async function clickListTab(modal, tab) {
    const tabs = modalRoot(modal).querySelector('platform-segmented-control.mcp-list-tabs');
    expect(tabs).to.exist;
    const segments = segmentedSegments(tabs);
    const targetIndex = tab === 'catalog' ? 1 : 0;
    segments[targetIndex].click();
    await modal.updateComplete;
    await waitUntil(() => modal._listTab === tab, `list tab ${tab}`);
}

async function dispatchSearch(modal, value) {
    const search = modalRoot(modal).querySelector('platform-modal-search-field');
    expect(search).to.exist;
    search.dispatchEvent(new CustomEvent('change', {
        detail: { value },
        bubbles: true,
        composed: true,
    }));
    await aTimeout(280);
    await modal.updateComplete;
}

async function clickLoadMore(modal) {
    const loadMore = modalRoot(modal).querySelector('.mcp-load-more platform-button');
    expect(loadMore).to.exist;
    clickPlatformButton(loadMore);
    await modal.updateComplete;
}

function switchToSystemCompany() {
    getPlatformBus().dispatch(CoreEvents.AUTH_COMPANY_SWITCHED, { company_id: 'system' });
}

async function openBrandingView(modal) {
    switchToSystemCompany();
    await modal.requestUpdate();
    await modal.updateComplete;
    await waitUntil(
        () => modalRoot(modal).querySelector('.mcp-list-toolbar > platform-button') !== null,
        'branding nav button',
    );
    const brandingButton = modalRoot(modal).querySelector('.mcp-list-toolbar > platform-button');
    clickPlatformButton(brandingButton);
    await modal.updateComplete;
    await waitUntil(() => modal._view === 'branding', 'branding view');
}

function installedServerStub(serverId, overrides = {}) {
    return {
        server_id: serverId,
        name: `Server ${serverId}`,
        url: 'https://example.test/mcp',
        transport_type: 'http',
        source: 'manual',
        is_active: true,
        cached_tools: [],
        headers: {},
        catalog_auto_provisioned: false,
        override_locked: false,
        ...overrides,
    };
}

function catalogItemStub(catalogId, overrides = {}) {
    return {
        catalog_id: catalogId,
        registry_name: `demo/${catalogId}`,
        title: `Title ${catalogId}`,
        upstream_url: 'https://example.test/mcp',
        transport_type: 'http',
        auth_policy: 'none',
        verify_status: 'verified',
        tool_count_snapshot: 1,
        installed: false,
        platform_curated: false,
        ...overrides,
    };
}

describe('flows mcp servers modal', () => {
    /** @type {ReturnType<typeof createMcpModalFetchStub> | null} */
    let fetchStub;

    beforeEach(() => {
        resetPlatformState();
        bootstrap();
    });

    afterEach(() => {
        fetchStub?.uninstall();
        fetchStub = null;
        fixtureCleanup();
    });

    it('switches to catalog via segmented control and loads catalog', async () => {
        fetchStub = createMcpModalFetchStub([
            {
                method: 'GET',
                match: (href) => href.includes('/flows/api/v1/mcp/servers'),
                body: {
                    items: [installedServerStub('browser', { source: 'platform' })],
                    total: 1,
                    limit: 50,
                    offset: 0,
                },
            },
            {
                method: 'GET',
                match: (href) => href.includes('/flows/api/v1/mcp/catalog'),
                body: {
                    items: [catalogItemStub('store_demo')],
                    total: 1,
                    limit: 50,
                    offset: 0,
                },
            },
        ]);

        const modal = await fixture(html`
            <flows-mcp-servers-modal ?open=${true}></flows-mcp-servers-modal>
        `);
        await modal.updateComplete;
        await waitUntil(() => modal._installedItems.length === 1, 'installed load');

        await clickListTab(modal, 'catalog');
        await waitUntil(() => modal._catalogItems.length === 1, 'catalog load');

        expect(modalRoot(modal).querySelectorAll('.mcp-card-shell')).to.have.length(1);
    });

    it('installs catalog entry via Install button and refreshes servers list', async () => {
        const state = { installCalls: 0 };
        fetchStub = createMcpModalFetchStub([
            {
                method: 'GET',
                match: (href) => href.includes('/flows/api/v1/mcp/servers'),
                body: () => ({
                    items: state.installCalls > 0
                        ? [installedServerStub('mcp_store_demo', {
                            source: 'catalog',
                            catalog_id: 'store_demo',
                            cached_tools: ['mcp:mcp_store_demo:echo'],
                        })]
                        : [],
                    total: state.installCalls > 0 ? 1 : 0,
                    limit: 50,
                    offset: 0,
                }),
            },
            {
                method: 'GET',
                match: (href) => href.includes('/flows/api/v1/mcp/catalog'),
                body: () => ({
                    items: [catalogItemStub('store_demo', { installed: state.installCalls > 0 })],
                    total: 1,
                    limit: 50,
                    offset: 0,
                }),
            },
            {
                method: 'POST',
                match: (href) => href.includes('/flows/api/v1/mcp/catalog/store_demo/install'),
                body: () => {
                    state.installCalls += 1;
                    return {
                        server_id: 'mcp_store_demo',
                        name: 'Store Demo',
                        url: 'https://example.test/mcp',
                        transport_type: 'http',
                        source: 'catalog',
                        catalog_id: 'store_demo',
                        catalog_auto_provisioned: false,
                        is_active: true,
                        cached_tools: [],
                        headers: {},
                        override_locked: false,
                    };
                },
            },
        ]);

        const modal = await fixture(html`
            <flows-mcp-servers-modal ?open=${true}></flows-mcp-servers-modal>
        `);
        await modal.updateComplete;
        await clickListTab(modal, 'catalog');
        await waitUntil(() => modalRoot(modal).querySelector('.mcp-card-actions platform-button'), 'catalog card');

        const installButton = modalRoot(modal).querySelector('.mcp-card-actions platform-button[variant="primary"]');
        clickPlatformButton(installButton);
        await waitUntil(() => state.installCalls === 1, 'install request');
        await modal.updateComplete;

        expect(modalRoot(modal).querySelector('.mcp-chip')).to.exist;
    });

    it('loads branding with backend search query from header search field', async () => {
        fetchStub = createMcpModalFetchStub([
            {
                method: 'GET',
                match: (href) => href.includes('/flows/api/v1/mcp/servers'),
                body: { items: [], total: 0, limit: 50, offset: 0 },
            },
            {
                method: 'GET',
                match: (href) => href.includes('/flows/api/v1/mcp/branding/slug-suggest'),
                body: { slugs: ['context7_catalog'] },
            },
            {
                method: 'GET',
                match: (href) => href.includes('/flows/api/v1/mcp/branding') && href.includes('search=context7'),
                body: {
                    items: [{
                        server_id: 'context7_catalog',
                        icon_file_id: 'file_context7',
                        icon_url: '/frontend/api/v1/files/download/file_context7',
                        updated_at: '2026-01-01T00:00:00Z',
                        updated_by_user_id: 'user_test',
                    }],
                    total: 1,
                    limit: 40,
                    offset: 0,
                },
            },
            {
                method: 'GET',
                match: (href) => href.includes('/flows/api/v1/mcp/branding'),
                body: { items: [], total: 0, limit: 40, offset: 0 },
            },
        ]);

        switchToSystemCompany();
        const modal = await fixture(html`
            <flows-mcp-servers-modal ?open=${true}></flows-mcp-servers-modal>
        `);
        await modal.updateComplete;
        await openBrandingView(modal);
        await dispatchSearch(modal, 'context7');

        expect(
            fetchStub.calls.some((call) => call.url.includes('/mcp/branding?') && call.url.includes('search=context7')),
        ).to.equal(true);
        expect(modalRoot(modal).querySelectorAll('.mcp-branding-card')).to.have.length(1);
    });

    it('catalog search debounces and sends search query param', async () => {
        fetchStub = createMcpModalFetchStub([
            {
                method: 'GET',
                match: (href) => href.includes('/flows/api/v1/mcp/servers'),
                body: { items: [], total: 0, limit: 50, offset: 0 },
            },
            {
                method: 'GET',
                match: (href) => href.includes('/flows/api/v1/mcp/catalog'),
                body: {
                    items: [catalogItemStub('store_demo')],
                    total: 1,
                    limit: 50,
                    offset: 0,
                },
            },
        ]);

        const modal = await fixture(html`
            <flows-mcp-servers-modal ?open=${true}></flows-mcp-servers-modal>
        `);
        await modal.updateComplete;
        await clickListTab(modal, 'catalog');
        await dispatchSearch(modal, 'store_demo');

        expect(
            fetchStub.calls.some((call) => call.url.includes('/mcp/catalog') && call.url.includes('search=store_demo')),
        ).to.equal(true);
    });

    it('load more appends installed servers page', async () => {
        const firstPage = [
            installedServerStub('browser', { source: 'platform' }),
            installedServerStub('search', { source: 'platform' }),
            ...Array.from({ length: 48 }, (_, index) => installedServerStub(`srv_${index}`)),
        ];
        const secondPage = [installedServerStub('srv_48')];
        fetchStub = createMcpModalFetchStub([
            {
                method: 'GET',
                match: (href) => href.includes('/flows/api/v1/mcp/servers') && href.includes('offset=50'),
                body: { items: secondPage, total: 51, limit: 50, offset: 50 },
            },
            {
                method: 'GET',
                match: (href) => href.includes('/flows/api/v1/mcp/servers'),
                body: { items: firstPage, total: 51, limit: 50, offset: 0 },
            },
        ]);

        const modal = await fixture(html`
            <flows-mcp-servers-modal ?open=${true}></flows-mcp-servers-modal>
        `);
        await modal.updateComplete;
        await waitUntil(() => modal._installedItems.length === 50, 'first page');

        await clickLoadMore(modal);
        await waitUntil(() => modal._installedItems.length === 51, 'second page');

        expect(
            fetchStub.calls.some((call) => call.url.includes('/mcp/servers') && call.url.includes('offset=50')),
        ).to.equal(true);
    });

    it('renders platform_curated chip on catalog card', async () => {
        fetchStub = createMcpModalFetchStub([
            {
                method: 'GET',
                match: (href) => href.includes('/flows/api/v1/mcp/servers'),
                body: { items: [], total: 0, limit: 50, offset: 0 },
            },
            {
                method: 'GET',
                match: (href) => href.includes('/flows/api/v1/mcp/catalog'),
                body: {
                    items: [catalogItemStub('context7_catalog', { platform_curated: true, title: 'Context7' })],
                    total: 1,
                    limit: 50,
                    offset: 0,
                },
            },
        ]);

        const modal = await fixture(html`
            <flows-mcp-servers-modal ?open=${true}></flows-mcp-servers-modal>
        `);
        await modal.updateComplete;
        await clickListTab(modal, 'catalog');
        await waitUntil(() => modal._catalogItems.length === 1, 'catalog item');

        const chips = [...modalRoot(modal).querySelectorAll('.mcp-card-meta .mcp-chip')];
        expect(chips.some((chip) => chip.textContent.toLowerCase().includes('curated'))).to.equal(true);
    });

    it('slug typeahead requests suggest endpoint', async () => {
        fetchStub = createMcpModalFetchStub([
            {
                method: 'GET',
                match: (href) => href.includes('/flows/api/v1/mcp/servers'),
                body: { items: [], total: 0, limit: 50, offset: 0 },
            },
            {
                method: 'GET',
                match: (href) => href.includes('/flows/api/v1/mcp/branding/slug-suggest'),
                body: { slugs: ['context7_catalog'] },
            },
            {
                method: 'GET',
                match: (href) => href.includes('/flows/api/v1/mcp/branding'),
                body: { items: [], total: 0, limit: 40, offset: 0 },
            },
        ]);

        switchToSystemCompany();
        const modal = await fixture(html`
            <flows-mcp-servers-modal ?open=${true}></flows-mcp-servers-modal>
        `);
        await modal.updateComplete;
        await openBrandingView(modal);
        await waitUntil(
            () => modalRoot(modal).querySelector('.mcp-branding-form platform-field') !== null,
            'branding slug field',
        );

        const slugField = modalRoot(modal).querySelector('.mcp-branding-form platform-field');
        slugField.dispatchEvent(new CustomEvent('change', {
            detail: { value: 'context7' },
            bubbles: true,
            composed: true,
        }));
        await aTimeout(220);
        await modal.updateComplete;

        expect(
            fetchStub.calls.some((call) => call.url.includes('/mcp/branding/slug-suggest') && call.url.includes('search=context7')),
        ).to.equal(true);
        expect(modalRoot(modal).querySelector('.mcp-branding-slugs platform-button')).to.exist;
    });

    it('branding gallery card selects on click', async () => {
        fetchStub = createMcpModalFetchStub([
            {
                method: 'GET',
                match: (href) => href.includes('/flows/api/v1/mcp/servers'),
                body: { items: [], total: 0, limit: 50, offset: 0 },
            },
            {
                method: 'GET',
                match: (href) => href.includes('/flows/api/v1/mcp/branding/slug-suggest'),
                body: { slugs: [] },
            },
            {
                method: 'GET',
                match: (href) => href.includes('/flows/api/v1/mcp/branding'),
                body: {
                    items: [{
                        server_id: 'browser',
                        icon_file_id: 'file_browser',
                        icon_url: '/frontend/api/v1/files/download/file_browser',
                        updated_at: '2026-01-01T00:00:00Z',
                        updated_by_user_id: 'user_test',
                    }],
                    total: 1,
                    limit: 40,
                    offset: 0,
                },
            },
        ]);

        switchToSystemCompany();
        const modal = await fixture(html`
            <flows-mcp-servers-modal ?open=${true}></flows-mcp-servers-modal>
        `);
        await modal.updateComplete;
        await openBrandingView(modal);
        await waitUntil(() => modal._brandingItems.length === 1, 'branding gallery');

        const card = modalRoot(modal).querySelector('.mcp-branding-card');
        expect(card).to.exist;
        card.click();
        await modal.updateComplete;

        expect(card.getAttribute('aria-selected')).to.equal('true');
    });

    it('shows installed cards without both platform defaults', async () => {
        fetchStub = createMcpModalFetchStub([
            {
                method: 'GET',
                match: (href) => href.includes('/flows/api/v1/mcp/servers'),
                body: {
                    items: [
                        installedServerStub('browser', { source: 'platform' }),
                        installedServerStub('mcp_store_demo', {
                            source: 'catalog',
                            catalog_id: 'store_demo',
                        }),
                    ],
                    total: 2,
                    limit: 50,
                    offset: 0,
                },
            },
        ]);

        const modal = await fixture(html`
            <flows-mcp-servers-modal ?open=${true}></flows-mcp-servers-modal>
        `);
        await modal.updateComplete;
        await waitUntil(() => modal._installedItems.length === 2, 'installed load');

        expect(modal._listTab).to.equal('installed');
        expect(modalRoot(modal).querySelectorAll('.mcp-card-shell')).to.have.length(2);
    });

    it('catalog then installed roundtrip reloads and shows cards', async () => {
        let installedCalls = 0;
        fetchStub = createMcpModalFetchStub([
            {
                method: 'GET',
                match: (href) => href.includes('/flows/api/v1/mcp/servers'),
                body: () => {
                    installedCalls += 1;
                    return {
                        items: [
                            installedServerStub('browser', { source: 'platform' }),
                            installedServerStub('search', { source: 'platform' }),
                        ],
                        total: 2,
                        limit: 50,
                        offset: 0,
                    };
                },
            },
            {
                method: 'GET',
                match: (href) => href.includes('/flows/api/v1/mcp/catalog'),
                body: {
                    items: [catalogItemStub('store_demo')],
                    total: 1,
                    limit: 50,
                    offset: 0,
                },
            },
        ]);

        const modal = await fixture(html`
            <flows-mcp-servers-modal ?open=${true}></flows-mcp-servers-modal>
        `);
        await modal.updateComplete;
        await waitUntil(() => modal._installedItems.length === 2, 'initial installed');
        const callsAfterOpen = installedCalls;

        await clickListTab(modal, 'catalog');
        await waitUntil(() => modal._catalogItems.length === 1, 'catalog load');
        expect(modal._listTab).to.equal('catalog');

        await clickListTab(modal, 'installed');
        await waitUntil(() => modal._listTab === 'installed', 'back to installed');
        await waitUntil(() => installedCalls > callsAfterOpen, 'installed reload');
        await waitUntil(() => modal._installedItems.length === 2, 'installed after roundtrip');

        expect(modalRoot(modal).querySelectorAll('.mcp-card-shell')).to.have.length(2);
    });
});
