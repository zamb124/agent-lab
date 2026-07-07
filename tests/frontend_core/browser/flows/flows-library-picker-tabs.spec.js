import { fixture, fixtureCleanup, html, expect, aTimeout, waitUntil } from '../helpers/render.js';
import { resetPlatformState, bootstrapTestBus } from '../helpers/reset.js';
import { collectFactories, registerFactory } from '@platform/lib/events/index.js';
import { toolsAllOp, toolsResource } from '../../../../apps/flows/ui/events/resources/tools.resource.js';
import {
    codeCompletionsOp,
    codeTemplatesOp,
    codeParseSignatureOp,
} from '../../../../apps/flows/ui/events/resources/code.resource.js';
import { mcpServersResource, mcpServerSyncOp, mcpServerTestOp } from '../../../../apps/flows/ui/events/resources/mcp.resource.js';
import '../../../../apps/flows/ui/modals/flows-library-picker-modal.js';

const FACTORIES = [
    toolsAllOp,
    toolsResource,
    codeCompletionsOp,
    codeTemplatesOp,
    codeParseSignatureOp,
    mcpServersResource,
    mcpServerSyncOp,
    mcpServerTestOp,
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

describe('flows library picker tabs', () => {
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

    it('loads picker_category per active tab', async () => {
        const requests = [];
        window.fetch = async (url) => {
            const href = String(url);
            requests.push(href);
            if (href.includes('/flows/api/v1/tools/all')) {
                const parsed = new URL(href, 'http://localhost');
                const category = parsed.searchParams.get('picker_category');
                return jsonResponse({
                    items: [],
                    total: 0,
                    limit: 2000,
                    offset: 0,
                    category,
                });
            }
            if (href.includes('/flows/api/v1/mcp/servers')) {
                return jsonResponse({ items: [] });
            }
            throw new Error(`unexpected fetch: ${href}`);
        };

        const modal = await fixture(html`
            <flows-library-picker-modal pick-mode="all" ?open=${true}></flows-library-picker-modal>
        `);
        modal._modalKind = 'flows.tool_picker';
        await modal.updateComplete;
        await aTimeout(0);

        expect(requests.some((href) => href.includes('picker_category=all'))).to.equal(true);

        modal._onToolCategoryTabChange('flow');
        await aTimeout(0);
        expect(requests.some((href) => href.includes('picker_category=flow'))).to.equal(true);
    });

    it('shows inline error and retry on tools_all failure', async () => {
        let attempts = 0;
        window.fetch = async (url) => {
            const href = String(url);
            if (href.includes('/flows/api/v1/tools/all')) {
                attempts += 1;
                if (attempts === 1) {
                    return new Response(JSON.stringify({ detail: 'tools unavailable' }), {
                        status: 503,
                        headers: { 'content-type': 'application/json' },
                    });
                }
                return jsonResponse({
                    items: [{ tool_id: 'calculator', title: 'calculator', item_type: 'tool' }],
                    total: 1,
                    limit: 2000,
                    offset: 0,
                });
            }
            throw new Error(`unexpected fetch: ${href}`);
        };

        const modal = await fixture(html`
            <flows-library-picker-modal pick-mode="all" ?open=${true}></flows-library-picker-modal>
        `);
        modal._modalKind = 'flows.tool_picker';
        await modal.updateComplete;
        await aTimeout(0);

        expect(modal.shadowRoot.querySelector('.lib-load-error')).to.not.equal(null);

        const retryButton = modal.shadowRoot.querySelector('.lib-load-error platform-button');
        retryButton.shadowRoot.querySelector('button').click();
        await waitUntil(
            () => modal._pickModeRows().some((row) => row.tool_id === 'calculator'),
            'picker rows after retry',
            { timeout: 3000 },
        );

        expect(modal._pickModeRows().map((row) => row.tool_id)).to.include('calculator');
    });

    it('wraps MCP server tools in content-panel-body', async () => {
        const modal = await fixture(html`
            <flows-library-picker-modal pick-mode="mcp_only"></flows-library-picker-modal>
        `);
        modal._modalKind = 'flows.tool_picker';
        const host = await fixture(html`
            <div>
                ${modal._renderMcpServerSection({
                    server: {
                        server_id: 'test-server',
                        name: 'Test MCP',
                        url: 'https://example.test/mcp',
                        transport_type: 'http',
                        source: 'manual',
                    },
                    tools: [{
                        tool_id: 'mcp:test-server:echo',
                        title: 'echo',
                        item_type: 'tool',
                        code_mode: 'mcp_tool',
                        mcp_server_id: 'test-server',
                        description: 'Echo tool',
                    }],
                })}
            </div>
        `);

        const panelBody = host.querySelector('.mcp-picker-server .content-panel-body');
        expect(panelBody).to.not.equal(null);
        expect(panelBody.querySelector('.mcp-picker-tools-grid')).to.not.equal(null);
    });
});
