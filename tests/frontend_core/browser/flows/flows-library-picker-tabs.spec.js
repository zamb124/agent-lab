import { fixture, fixtureCleanup, html, expect, aTimeout, waitUntil } from '../helpers/render.js';
import { resetPlatformState, bootstrapTestBus } from '../helpers/reset.js';
import { collectFactories, registerFactory } from '@platform/lib/events/index.js';
import { platformWs, WsTransportError } from '@platform/lib/events/effects/ws.effect.js';
import { toolsAllOp, toolsResource } from '../../../../apps/flows/ui/events/resources/tools.resource.js';
import { toolTagGroupsOp } from '../../../../apps/flows/ui/events/resources/tool-tag-groups.resource.js';
import {
    codeLspSessionOp,
    codeTemplatesOp,
    codeParseSignatureOp,
} from '../../../../apps/flows/ui/events/resources/code.resource.js';
import { mcpServersResource, mcpServerSyncOp, mcpServerTestOp } from '../../../../apps/flows/ui/events/resources/mcp.resource.js';
import '../../../../apps/flows/ui/modals/flows-library-picker-modal.js';

const FACTORIES = [
    toolsAllOp,
    toolsResource,
    toolTagGroupsOp,
    codeLspSessionOp,
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
    let originalWsRequest;

    beforeEach(() => {
        originalFetch = window.fetch;
        originalWsRequest = platformWs.request;
        resetPlatformState();
        bootstrap();
    });

    afterEach(() => {
        window.fetch = originalFetch;
        platformWs.request = originalWsRequest;
        fixtureCleanup();
    });

    it('loads picker_category per active tab', async () => {
        const requests = [];
        window.fetch = async (url) => {
            const href = String(url);
            if (href.includes('/flows/api/v1/mcp/servers')) {
                return jsonResponse({ items: [] });
            }
            throw new Error(`unexpected fetch: ${href}`);
        };
        platformWs.request = async (opts) => {
            if (opts.type === 'flows/tools/tag_groups_requested') {
                return { items: [], total: 0, limit: 200, offset: 0 };
            }
            if (opts.type === 'flows/tools/list_all_requested') {
                requests.push(opts.payload);
                const limit = opts.payload.limit;
                expect(limit).to.be.at.most(20);
                expect(opts.payload.offset).to.equal(0);
                return {
                    items: [],
                    total: 0,
                    limit,
                    offset: 0,
                };
            }
            throw new Error(`unexpected WS command ${opts.type}`);
        };

        const modal = await fixture(html`
            <flows-library-picker-modal pick-mode="all" ?open=${true}></flows-library-picker-modal>
        `);
        modal._modalKind = 'flows.tool_picker';
        await modal.updateComplete;
        await aTimeout(0);

        expect(requests.some((payload) => payload.picker_category === 'all')).to.equal(true);

        modal._onToolCategoryTabChange('flow');
        await aTimeout(0);
        expect(requests.some((payload) => payload.picker_category === 'flow')).to.equal(true);
    });

    it('shows inline error and retry on tools_all failure', async () => {
        let attempts = 0;
        window.fetch = async (url) => {
            throw new Error(`unexpected fetch: ${String(url)}`);
        };
        platformWs.request = async (opts) => {
            if (opts.type === 'flows/tools/tag_groups_requested') {
                return { items: [], total: 0, limit: 200, offset: 0 };
            }
            if (opts.type === 'flows/tools/list_all_requested') {
                attempts += 1;
                if (attempts === 1) {
                    throw new WsTransportError('tools unavailable', 'ws_command_failed');
                }
                return {
                    items: [{ tool_id: 'calculator', title: 'calculator', item_type: 'tool' }],
                    total: 1,
                    limit: 20,
                    offset: 0,
                };
            }
            throw new Error(`unexpected WS command ${opts.type}`);
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

        const card = panelBody.querySelector('platform-picker-card');
        expect(card).to.not.equal(null);
        const cardInner = card.shadowRoot.querySelector('.picker-card');
        expect(getComputedStyle(cardInner).paddingTop).to.not.equal('0px');
    });

    it('shows MCP bulk-add control when onPickBatch is provided', async () => {
        let batchPayload = null;
        const modal = await fixture(html`
            <flows-library-picker-modal pick-mode="all"></flows-library-picker-modal>
        `);
        modal._modalKind = 'flows.tool_picker';
        modal._modalId = 'picker-test';
        modal.onPickBatch = (detail) => {
            batchPayload = detail;
        };
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
                    tools: [
                        {
                            tool_id: 'mcp:test-server:echo',
                            title: 'echo',
                            item_type: 'tool',
                            code_mode: 'mcp_tool',
                            mcp_server_id: 'test-server',
                            description: 'Echo tool',
                        },
                        {
                            tool_id: 'mcp:test-server:ping',
                            title: 'ping',
                            item_type: 'tool',
                            code_mode: 'mcp_tool',
                            mcp_server_id: 'test-server',
                            description: 'Ping tool',
                        },
                    ],
                })}
            </div>
        `);

        const bulkButtons = host.querySelectorAll('.mcp-picker-server-actions platform-button');
        expect(bulkButtons.length).to.be.greaterThan(0);
        bulkButtons[0].shadowRoot.querySelector('button').click();
        await aTimeout(0);
        expect(batchPayload).to.not.equal(null);
        expect(Array.isArray(batchPayload.items)).to.equal(true);
        expect(batchPayload.items).to.have.length(2);
    });

    it('flat MCP search finds tool by name across servers', async () => {
        const modal = await fixture(html`
            <flows-library-picker-modal pick-mode="mcp_only"></flows-library-picker-modal>
        `);
        modal._modalKind = 'flows.tool_picker';
        modal._toolsAllItems = () => ([
            {
                tool_id: 'mcp:alpha:find_me',
                title: 'find_me',
                item_type: 'tool',
                code_mode: 'mcp_tool',
                mcp_server_id: 'alpha',
                description: 'Alpha tool',
            },
            {
                tool_id: 'mcp:beta:other',
                title: 'other',
                item_type: 'tool',
                code_mode: 'mcp_tool',
                mcp_server_id: 'beta',
                description: 'Beta tool',
            },
        ]);
        modal._mcpServers = {
            items: [
                {
                    server_id: 'alpha',
                    name: 'Alpha Server',
                    url: 'https://alpha.test/mcp',
                    transport_type: 'http',
                    source: 'catalog',
                    is_active: true,
                },
                {
                    server_id: 'beta',
                    name: 'Beta Server',
                    url: 'https://beta.test/mcp',
                    transport_type: 'http',
                    source: 'manual',
                    is_active: true,
                },
            ],
            loading: false,
            error: null,
            load: async () => {},
        };
        modal._search = 'find_me';
        const flat = modal._buildMcpFlatSearchTools();
        expect(flat).to.have.length(1);
        expect(flat[0].tool.tool_id).to.equal('mcp:alpha:find_me');
        expect(flat[0].server.server_id).to.equal('alpha');

        const host = await fixture(html`<div>${modal._renderMcpFlatSearchBody(false)}</div>`);
        expect(host.querySelector('.mcp-picker-flat-hint')).to.not.equal(null);
        expect(host.querySelectorAll('platform-picker-card')).to.have.length(1);
    });

    it('shows manage MCP CTA when MCP servers and tools are empty', async () => {
        const modal = await fixture(html`
            <flows-library-picker-modal pick-mode="mcp_only"></flows-library-picker-modal>
        `);
        modal._modalKind = 'flows.tool_picker';
        modal._toolsAllItems = () => [];
        modal._mcpServers = {
            items: [],
            loading: false,
            error: null,
            load: async () => {},
        };
        const host = await fixture(html`<div>${modal._renderMcpEmptyState()}</div>`);
        expect(host.textContent).to.include('tool_picker_modal.action_manage_mcp');
        expect(host.querySelector('platform-button')).to.not.equal(null);
    });
});
