import { fixture, fixtureCleanup, html, expect, aTimeout, waitUntil } from '../helpers/render.js';
import { resetPlatformState, bootstrapTestBus } from '../helpers/reset.js';
import { collectFactories, registerFactory, getPlatformBus, CoreEvents } from '@platform/lib/events/index.js';
import { platformWs } from '@platform/lib/events/effects/ws.effect.js';
import {
    mcpServersResource,
    mcpServersListOp,
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
import {q, qs, qsa, shadow, type TestEl} from '../helpers/dom.js';

const FACTORIES = [
    mcpServersResource,
    mcpServersListOp,
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

function createMcpWsStub(handlers: any) {
    const calls: any[] = [];
    const original = platformWs.request;
    platformWs.request = async (opts) => {
        if (!opts || typeof opts.type !== 'string') {
            throw new Error('mcp ws stub: opts.type required');
        }
        calls.push({ type: opts.type, payload: opts.payload });
        const handler = handlers[opts.type];
        if (handler === undefined) {
            throw new Error(`unexpected ws: ${opts.type}`);
        }
        return typeof handler === 'function' ? handler(opts.payload) : handler;
    };
    return {
        calls,
        uninstall() {
            platformWs.request = original;
        },
    };
}

function offsetPage(items: any, total: any, limit: any, offset: any) {
    return { items, total, limit, offset };
}

function modalRoot(modal: any) {
    return shadow(modal);
}

function segmentedSegments(control: any) {
    return [...qsa(shadow(control), '.segment')];
}

function clickPlatformButton(buttonEl: any) {
    const inner = qs(shadow(buttonEl), 'button');
    (inner as TestEl).click();
}

async function clickListTab(modal: any, tab: any) {
    const tabs = qs(modalRoot(modal), 'platform-segmented-control.mcp-list-tabs');
    expect(tabs).to.exist;
    const segments = segmentedSegments(tabs);
    const targetIndex = tab === 'catalog' ? 1 : 0;
    segments[targetIndex]!.click();
    await modal.updateComplete;
    await waitUntil(() => modal._listTab === tab, `list tab ${tab}`);
}

async function dispatchSearch(modal: any, value: any) {
    const search = qs(modalRoot(modal), 'platform-modal-search-field');
    expect(search).to.exist;
    search.dispatchEvent(new CustomEvent('change', {
        detail: { value },
        bubbles: true,
        composed: true,
    }));
    await aTimeout(280);
    await modal.updateComplete;
}

async function clickLoadMore(modal: any) {
    const loadMore = qs(modalRoot(modal), '.mcp-load-more platform-button');
    expect(loadMore).to.exist;
    clickPlatformButton(loadMore);
    await modal.updateComplete;
}

function switchToSystemCompany() {
    getPlatformBus().dispatch(CoreEvents.AUTH_COMPANY_SWITCHED, { company_id: 'system' });
}

async function openBrandingView(modal: any) {
    switchToSystemCompany();
    await modal.requestUpdate();
    await modal.updateComplete;
    await waitUntil(
        () => q(modalRoot(modal), '.mcp-list-toolbar > platform-button') !== null,
        'branding nav button',
    );
    const brandingButton = qs(modalRoot(modal), '.mcp-list-toolbar > platform-button');
    clickPlatformButton(brandingButton);
    await modal.updateComplete;
    await waitUntil(() => modal._view === 'branding', 'branding view');
}

function installedServerStub(serverId: any, overrides: any = {}) {
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

function catalogItemStub(catalogId: any, overrides: any = {}) {
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
    /** @type {ReturnType<typeof createMcpWsStub> | null} */
    let wsStub: any;

    beforeEach(() => {
        resetPlatformState();
        bootstrap();
    });

    afterEach(() => {
        wsStub?.uninstall();
        wsStub = null;
        fixtureCleanup();
    });

    it('switches to catalog via segmented control and loads catalog', async () => {
        wsStub = createMcpWsStub({
            'flows/mcp_servers/list_requested': offsetPage(
                [installedServerStub('browser', { source: 'platform' })],
                1,
                50,
                0,
            ),
            'flows/mcp_catalog/list_requested': offsetPage(
                [catalogItemStub('store_demo')],
                1,
                50,
                0,
            ),
        });

        const modal = await fixture<TestEl>(html`
            <flows-mcp-servers-modal ?open=${true}></flows-mcp-servers-modal>
        `);
        await modal.updateComplete;
        await waitUntil(() => modal._installedItems.length === 1, 'installed load');

        await clickListTab(modal, 'catalog');
        await waitUntil(() => modal._catalogItems.length === 1, 'catalog load');

        expect(qsa(modalRoot(modal), '.mcp-card-shell')).to.have.length(1);
    });

    it('installs catalog entry via Install button and refreshes servers list', async () => {
        const state = { installCalls: 0 };
        wsStub = createMcpWsStub({
            'flows/mcp_servers/list_requested': () => offsetPage(
                state.installCalls > 0
                    ? [installedServerStub('mcp_store_demo', {
                        source: 'catalog',
                        catalog_id: 'store_demo',
                        cached_tools: ['mcp:mcp_store_demo:echo'],
                    })]
                    : [],
                state.installCalls > 0 ? 1 : 0,
                50,
                0,
            ),
            'flows/mcp_catalog/list_requested': () => offsetPage(
                [catalogItemStub('store_demo', { installed: state.installCalls > 0 })],
                1,
                50,
                0,
            ),
            'flows/mcp_catalog/install_requested': (payload: any) => {
                if (!payload || payload.catalog_id !== 'store_demo') {
                    throw new Error('mcp ws stub: catalog_id store_demo required');
                }
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
        });

        const modal = await fixture<TestEl>(html`
            <flows-mcp-servers-modal ?open=${true}></flows-mcp-servers-modal>
        `);
        await modal.updateComplete;
        await clickListTab(modal, 'catalog');
        await waitUntil(() => q(modalRoot(modal), '.mcp-card-actions platform-button'), 'catalog card');

        const installButton = qs(modalRoot(modal), '.mcp-card-actions platform-button[variant="primary"]');
        clickPlatformButton(installButton);
        await waitUntil(() => state.installCalls === 1, 'install request');
        await modal.updateComplete;

        expect(qs(modalRoot(modal), '.mcp-chip')).to.exist;
    });

    it('loads branding with backend search query from header search field', async () => {
        wsStub = createMcpWsStub({
            'flows/mcp_servers/list_requested': offsetPage([], 0, 50, 0),
            'flows/mcp_branding/slug_suggest_requested': { slugs: ['context7_catalog'] },
            'flows/mcp_branding/list_requested': (payload: any) => {
                if (payload && payload.search === 'context7') {
                    return offsetPage(
                        [{
                            server_id: 'context7_catalog',
                            icon_file_id: 'file_context7',
                            icon_url: '/frontend/api/v1/files/download/file_context7',
                            updated_at: '2026-01-01T00:00:00Z',
                            updated_by_user_id: 'user_test',
                        }],
                        1,
                        40,
                        0,
                    );
                }
                return offsetPage([], 0, 40, 0);
            },
        });

        switchToSystemCompany();
        const modal = await fixture<TestEl>(html`
            <flows-mcp-servers-modal ?open=${true}></flows-mcp-servers-modal>
        `);
        await modal.updateComplete;
        await openBrandingView(modal);
        await dispatchSearch(modal, 'context7');

        expect(
            wsStub.calls.some((call: any) => (
                call.type === 'flows/mcp_branding/list_requested'
                && call.payload
                && call.payload.search === 'context7'
            )),
        ).to.equal(true);
        expect(qsa(modalRoot(modal), '.mcp-branding-card')).to.have.length(1);
    });

    it('catalog search debounces and sends search query param', async () => {
        wsStub = createMcpWsStub({
            'flows/mcp_servers/list_requested': offsetPage([], 0, 50, 0),
            'flows/mcp_catalog/list_requested': offsetPage(
                [catalogItemStub('store_demo')],
                1,
                50,
                0,
            ),
        });

        const modal = await fixture<TestEl>(html`
            <flows-mcp-servers-modal ?open=${true}></flows-mcp-servers-modal>
        `);
        await modal.updateComplete;
        await clickListTab(modal, 'catalog');
        await dispatchSearch(modal, 'store_demo');

        expect(
            wsStub.calls.some((call: any) => (
                call.type === 'flows/mcp_catalog/list_requested'
                && call.payload
                && call.payload.search === 'store_demo'
            )),
        ).to.equal(true);
    });

    it('load more appends installed servers page', async () => {
        const firstPage = [
            installedServerStub('browser', { source: 'platform' }),
            installedServerStub('search', { source: 'platform' }),
            ...Array.from({ length: 48 }, (_, index) => installedServerStub(`srv_${index}`)),
        ];
        const secondPage = [installedServerStub('srv_48')];
        wsStub = createMcpWsStub({
            'flows/mcp_servers/list_requested': (payload: any) => {
                const offset = payload && typeof payload.offset === 'number' ? payload.offset : 0;
                if (offset === 50) {
                    return offsetPage(secondPage, 51, 50, 50);
                }
                return offsetPage(firstPage, 51, 50, 0);
            },
        });

        const modal = await fixture<TestEl>(html`
            <flows-mcp-servers-modal ?open=${true}></flows-mcp-servers-modal>
        `);
        await modal.updateComplete;
        await waitUntil(() => modal._installedItems.length === 50, 'first page');

        await clickLoadMore(modal);
        await waitUntil(() => modal._installedItems.length === 51, 'second page');

        expect(
            wsStub.calls.some((call: any) => (
                call.type === 'flows/mcp_servers/list_requested'
                && call.payload
                && call.payload.offset === 50
            )),
        ).to.equal(true);
    });

    it('renders platform_curated chip on catalog card', async () => {
        wsStub = createMcpWsStub({
            'flows/mcp_servers/list_requested': offsetPage([], 0, 50, 0),
            'flows/mcp_catalog/list_requested': offsetPage(
                [catalogItemStub('context7_catalog', { platform_curated: true, title: 'Context7' })],
                1,
                50,
                0,
            ),
        });

        const modal = await fixture<TestEl>(html`
            <flows-mcp-servers-modal ?open=${true}></flows-mcp-servers-modal>
        `);
        await modal.updateComplete;
        await clickListTab(modal, 'catalog');
        await waitUntil(() => modal._catalogItems.length === 1, 'catalog item');

        const chips = [...qsa(modalRoot(modal), '.mcp-card-meta .mcp-chip')];
        expect(chips.some((chip) => chip.textContent.toLowerCase().includes('curated'))).to.equal(true);
    });

    it('slug typeahead requests suggest endpoint', async () => {
        wsStub = createMcpWsStub({
            'flows/mcp_servers/list_requested': offsetPage([], 0, 50, 0),
            'flows/mcp_branding/slug_suggest_requested': { slugs: ['context7_catalog'] },
            'flows/mcp_branding/list_requested': offsetPage([], 0, 40, 0),
        });

        switchToSystemCompany();
        const modal = await fixture<TestEl>(html`
            <flows-mcp-servers-modal ?open=${true}></flows-mcp-servers-modal>
        `);
        await modal.updateComplete;
        await openBrandingView(modal);
        await waitUntil(
            () => q(modalRoot(modal), '.mcp-branding-form platform-field') !== null,
            'branding slug field',
        );

        const slugField = qs(modalRoot(modal), '.mcp-branding-form platform-field');
        slugField.dispatchEvent(new CustomEvent('change', {
            detail: { value: 'context7' },
            bubbles: true,
            composed: true,
        }));
        await aTimeout(220);
        await modal.updateComplete;

        expect(
            wsStub.calls.some((call: any) => (
                call.type === 'flows/mcp_branding/slug_suggest_requested'
                && call.payload
                && call.payload.search === 'context7'
            )),
        ).to.equal(true);
        expect(qs(modalRoot(modal), '.mcp-branding-slugs platform-button')).to.exist;
    });

    it('branding gallery card selects on click', async () => {
        wsStub = createMcpWsStub({
            'flows/mcp_servers/list_requested': offsetPage([], 0, 50, 0),
            'flows/mcp_branding/slug_suggest_requested': { slugs: [] },
            'flows/mcp_branding/list_requested': offsetPage(
                [{
                    server_id: 'browser',
                    icon_file_id: 'file_browser',
                    icon_url: '/frontend/api/v1/files/download/file_browser',
                    updated_at: '2026-01-01T00:00:00Z',
                    updated_by_user_id: 'user_test',
                }],
                1,
                40,
                0,
            ),
        });

        switchToSystemCompany();
        const modal = await fixture<TestEl>(html`
            <flows-mcp-servers-modal ?open=${true}></flows-mcp-servers-modal>
        `);
        await modal.updateComplete;
        await openBrandingView(modal);
        await waitUntil(() => modal._brandingItems.length === 1, 'branding gallery');

        const card = qs(modalRoot(modal), '.mcp-branding-card');
        expect(card).to.exist;
        (card as TestEl).click();
        await modal.updateComplete;

        expect(card.getAttribute('aria-selected')).to.equal('true');
    });

    it('shows installed cards without both platform defaults', async () => {
        wsStub = createMcpWsStub({
            'flows/mcp_servers/list_requested': offsetPage(
                [
                    installedServerStub('browser', { source: 'platform' }),
                    installedServerStub('mcp_store_demo', {
                        source: 'catalog',
                        catalog_id: 'store_demo',
                    }),
                ],
                2,
                50,
                0,
            ),
        });

        const modal = await fixture<TestEl>(html`
            <flows-mcp-servers-modal ?open=${true}></flows-mcp-servers-modal>
        `);
        await modal.updateComplete;
        await waitUntil(() => modal._installedItems.length === 2, 'installed load');

        expect(modal._listTab).to.equal('installed');
        expect(qsa(modalRoot(modal), '.mcp-card-shell')).to.have.length(2);
    });

    it('catalog then installed roundtrip reloads and shows cards', async () => {
        let installedCalls = 0;
        wsStub = createMcpWsStub({
            'flows/mcp_servers/list_requested': () => {
                installedCalls += 1;
                return offsetPage(
                    [
                        installedServerStub('browser', { source: 'platform' }),
                        installedServerStub('search', { source: 'platform' }),
                    ],
                    2,
                    50,
                    0,
                );
            },
            'flows/mcp_catalog/list_requested': offsetPage(
                [catalogItemStub('store_demo')],
                1,
                50,
                0,
            ),
        });

        const modal = await fixture<TestEl>(html`
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

        expect(qsa(modalRoot(modal), '.mcp-card-shell')).to.have.length(2);
    });
});
