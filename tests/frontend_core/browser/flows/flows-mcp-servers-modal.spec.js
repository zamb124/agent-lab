import { fixture, fixtureCleanup, html, expect, aTimeout, waitUntil } from '../helpers/render.js';
import { resetPlatformState, bootstrapTestBus } from '../helpers/reset.js';
import { collectFactories, registerFactory } from '@platform/lib/events/index.js';
import {
    mcpServersResource,
    mcpServerUpdateOp,
    mcpServerSyncOp,
    mcpServerTestOp,
    mcpServerResetCatalogDefaultsOp,
    mcpBrandingLoadOp,
    mcpBrandingUpsertOp,
    mcpBrandingRemoveOp,
    mcpCatalogStoreLoadOp,
    mcpCatalogInstallOp,
    mcpCatalogUninstallOp,
} from '../../../../apps/flows/ui/events/resources/mcp.resource.js';
import '../../../../apps/flows/ui/modals/flows-mcp-servers-modal.js';

const FACTORIES = [
    mcpServersResource,
    mcpServerUpdateOp,
    mcpServerSyncOp,
    mcpServerTestOp,
    mcpServerResetCatalogDefaultsOp,
    mcpBrandingLoadOp,
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

function jsonResponse(body) {
    return new Response(JSON.stringify(body), {
        status: 200,
        headers: { 'content-type': 'application/json' },
    });
}

describe('flows mcp servers modal', () => {
    let originalFetch;

    beforeEach(() => {
        originalFetch = window.fetch;
        resetPlatformState();
        bootstrap();
    });

    afterEach(() => {
        window.fetch = originalFetch;
        fixtureCleanup();
    });

    it('loads catalog when switching to Catalog tab', async () => {
        const requests = [];
        window.fetch = async (url, init) => {
            const href = String(url);
            requests.push(href);
            if (href.includes('/flows/api/v1/mcp/servers') && (!init || init.method === undefined || init.method === 'GET')) {
                return jsonResponse({
                    items: [
                        {
                            server_id: 'browser',
                            name: 'Browser',
                            url: 'https://example.test/browser/mcp',
                            transport_type: 'http',
                            source: 'platform',
                            is_active: true,
                            cached_tools: [],
                            headers: {},
                            catalog_auto_provisioned: false,
                            override_locked: false,
                        },
                    ],
                    total: 1,
                    limit: 200,
                    offset: 0,
                });
            }
            if (href.includes('/flows/api/v1/mcp/catalog')) {
                return jsonResponse({
                    items: [{
                        catalog_id: 'store_demo',
                        registry_name: 'demo/store',
                        title: 'Store Demo',
                        upstream_url: 'https://example.test/mcp',
                        transport_type: 'http',
                        auth_policy: 'none',
                        verify_status: 'verified',
                        tool_count_snapshot: 1,
                        installed: false,
                    }],
                    total: 1,
                    limit: 100,
                    offset: 0,
                });
            }
            throw new Error(`unexpected fetch: ${href}`);
        };

        const modal = await fixture(html`
            <flows-mcp-servers-modal ?open=${true}></flows-mcp-servers-modal>
        `);
        await modal.updateComplete;
        await waitUntil(() => requests.some((href) => href.includes('/mcp/servers')), 'servers load');

        await modal._switchListTab('catalog');
        await modal.updateComplete;
        await waitUntil(() => requests.some((href) => href.includes('/mcp/catalog')), 'catalog load');

        expect(modal._listTab).to.equal('catalog');
        expect(modal._catalogItems).to.have.length(1);
        expect(modal._catalogTotal).to.equal(1);
    });

    it('installs catalog entry and refreshes servers list', async () => {
        let installCalls = 0;
        window.fetch = async (url, init) => {
            const href = String(url);
            const method = init?.method || 'GET';
            if (href.includes('/flows/api/v1/mcp/servers') && method === 'GET') {
                return jsonResponse({
                    items: installCalls > 0
                        ? [{
                            server_id: 'mcp_store_demo',
                            name: 'Store Demo',
                            url: 'https://example.test/mcp',
                            transport_type: 'http',
                            source: 'catalog',
                            catalog_id: 'store_demo',
                            catalog_auto_provisioned: false,
                            is_active: true,
                            cached_tools: ['mcp:mcp_store_demo:echo'],
                            headers: {},
                            override_locked: false,
                        }]
                        : [],
                    total: installCalls > 0 ? 1 : 0,
                    limit: 200,
                    offset: 0,
                });
            }
            if (href.includes('/flows/api/v1/mcp/catalog') && method === 'GET') {
                return jsonResponse({
                    items: [{
                        catalog_id: 'store_demo',
                        title: 'Store Demo',
                        upstream_url: 'https://example.test/mcp',
                        transport_type: 'http',
                        installed: installCalls > 0,
                        tool_count_snapshot: 1,
                    }],
                    total: 1,
                    limit: 100,
                    offset: 0,
                });
            }
            if (href.includes('/flows/api/v1/mcp/catalog/store_demo/install') && method === 'POST') {
                installCalls += 1;
                return jsonResponse({
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
                });
            }
            throw new Error(`unexpected fetch: ${method} ${href}`);
        };

        const modal = await fixture(html`
            <flows-mcp-servers-modal ?open=${true}></flows-mcp-servers-modal>
        `);
        await modal.updateComplete;
        await modal._switchListTab('catalog');
        await modal.updateComplete;

        await modal._installCatalogEntry({ catalog_id: 'store_demo', title: 'Store Demo' });
        await modal.updateComplete;

        expect(installCalls).to.equal(1);
        expect(modal._catalogItems[0].installed).to.equal(true);
    });
});
