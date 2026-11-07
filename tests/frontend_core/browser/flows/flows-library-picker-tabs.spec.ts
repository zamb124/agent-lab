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
import {ensureTokensLoaded, q, qs, qsa, shadow, type TestEl} from '../helpers/dom.js';

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

function jsonResponse(body: any) {
    return new Response(JSON.stringify(body), {
        status: 200,
        headers: { 'content-type': 'application/json' },
    });
}

describe('flows library picker tabs', () => {
    let originalFetch: any;
    let originalWsRequest: any;

    beforeEach(async () => {
        originalFetch = window.fetch;
        originalWsRequest = platformWs.request;
        resetPlatformState();
        bootstrap();
        await ensureTokensLoaded();
    });

    afterEach(() => {
        window.fetch = originalFetch;
        platformWs.request = originalWsRequest;
        fixtureCleanup();
    });

    it('loads picker_category per active tab', async () => {
        const requests: any[] = [];
        window.fetch = async (url: RequestInfo | URL) => {
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
                const limit = (opts.payload as Record<string, any>).limit;
                expect(limit).to.be.at.most(20);
                expect((opts.payload as Record<string, any>).offset).to.equal(0);
                return {
                    items: [],
                    total: 0,
                    limit,
                    offset: 0,
                };
            }
            throw new Error(`unexpected WS command ${opts.type}`);
        };

        const modal = await fixture<TestEl>(html`
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
        window.fetch = async (url: RequestInfo | URL) => {
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

        const modal = await fixture<TestEl>(html`
            <flows-library-picker-modal pick-mode="all" ?open=${true}></flows-library-picker-modal>
        `);
        modal._modalKind = 'flows.tool_picker';
        await modal.updateComplete;
        await aTimeout(0);

        expect(q(shadow(modal), '.lib-load-error')).to.not.equal(null);

        const retryButton = qs(shadow(modal), '.lib-load-error platform-button');
        qs(shadow(retryButton), 'button').click();
        await waitUntil(
            () => modal._pickModeRows().some((row: any) => row.tool_id === 'calculator'),
            'picker rows after retry',
            { timeout: 3000 },
        );

        expect(modal._pickModeRows().map((row: any) => row.tool_id)).to.include('calculator');
    });

    it('wraps MCP server tools in content-panel-body', async () => {
        const modal = await fixture<TestEl>(html`
            <flows-library-picker-modal pick-mode="mcp_only"></flows-library-picker-modal>
        `);
        modal._modalKind = 'flows.tool_picker';
        const host = await fixture<TestEl>(html`
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

        const panelBody = q(host!, '.mcp-picker-server .content-panel-body');
        expect(panelBody).to.not.equal(null);
        expect(q(panelBody!, '.mcp-picker-tools-grid')).to.not.equal(null);

        const card = qs(panelBody!, 'platform-picker-card');
        expect(card).to.not.equal(null);
        const cardInner = qs(shadow(card)!, '.picker-card');
        expect(getComputedStyle(cardInner).paddingTop).to.not.equal('0px')!;
    });

    it('shows MCP bulk-add control when onPickBatch is provided', async () => {
        let batchPayload = null;
        const modal = await fixture<TestEl>(html`
            <flows-library-picker-modal pick-mode="all"></flows-library-picker-modal>
        `);
        modal._modalKind = 'flows.tool_picker';
        modal._modalId = 'picker-test';
        modal.onPickBatch = (detail: any) => {
            batchPayload = detail;
        };
        const host = await fixture<TestEl>(html`
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

        const bulkButtons = qsa(host!, '.mcp-picker-server-actions platform-button');
        expect(bulkButtons.length).to.be.greaterThan(0);
        qs(shadow(bulkButtons[0]!), 'button').click();
        await aTimeout(0);
        expect(batchPayload).to.not.equal(null);
        expect(Array.isArray(batchPayload!.items)).to.equal(true);
        expect(batchPayload!.items).to.have.length(2);
    });

    it('flat MCP search finds tool by name across servers', async () => {
        const modal = await fixture<TestEl>(html`
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

        const host = await fixture<TestEl>(html`<div>${modal._renderMcpFlatSearchResults()}</div>`);
        expect(q(host!, '.mcp-picker-flat-hint')).to.not.equal(null);
        expect(qsa(host!, 'platform-picker-card')).to.have.length(1);
    });

    function pickerSearchInput(modal: TestEl): HTMLInputElement {
        const search = qs(shadow(modal), 'platform-modal-search-field');
        expect(search).to.not.equal(null);
        const field = qs(shadow(search!), 'platform-field');
        const inner = qs(shadow(field!), 'platform-field-string');
        const input = qs(shadow(inner!), 'input.field-pill-input');
        expect(input).to.not.equal(null);
        return input as HTMLInputElement;
    }

    it('keeps search focus and caret while intermediate search results reload', async () => {
        const responses: Array<{ q: string | undefined; items: Array<Record<string, unknown>> }> = [];
        let releaseSecond: ((value?: unknown) => void) | null = null;
        const secondGate = new Promise((resolve) => {
            releaseSecond = resolve;
        });
        window.fetch = async (url: RequestInfo | URL) => {
            throw new Error(`unexpected fetch: ${String(url)}`);
        };
        platformWs.request = async (opts) => {
            if (opts.type === 'flows/tools/tag_groups_requested') {
                return { items: [], total: 0, limit: 200, offset: 0 };
            }
            if (opts.type === 'flows/tools/list_all_requested') {
                const payload = opts.payload as Record<string, unknown>;
                const q = typeof payload.q === 'string' ? payload.q : undefined;
                if (q === 'read_f') {
                    await secondGate;
                    responses.push({
                        q,
                        items: [{
                            tool_id: 'read_file',
                            title: 'read_file',
                            item_type: 'tool',
                            tags: ['files'],
                            description: 'Reads files',
                        }],
                    });
                    return { items: responses[responses.length - 1]!.items, total: 1, limit: 20, offset: 0 };
                }
                responses.push({
                    q,
                    items: [
                        {
                            tool_id: 'read_file',
                            title: 'read_file',
                            item_type: 'tool',
                            tags: ['files'],
                            description: 'Reads files',
                        },
                        {
                            tool_id: 'fill_docx_template',
                            title: 'fill_docx_template',
                            item_type: 'tool',
                            tags: ['files'],
                            description: 'Fills docx',
                        },
                    ],
                });
                return { items: responses[responses.length - 1]!.items, total: 2, limit: 20, offset: 0 };
            }
            throw new Error(`unexpected WS command ${opts.type}`);
        };

        const modal = await fixture<TestEl>(html`
            <flows-library-picker-modal pick-mode="all" ?open=${true}></flows-library-picker-modal>
        `);
        modal._modalKind = 'flows.tool_picker';
        await waitUntil(
            () => modal._pickModeRows().some((row: { tool_id?: string }) => row.tool_id === 'read_file'),
            'initial picker rows',
            { timeout: 3000 },
        );

        const input = pickerSearchInput(modal);
        input.focus();
        input.value = 'read_f';
        input.setSelectionRange(6, 6);
        input.dispatchEvent(new Event('input', { bubbles: true, composed: true }));
        await modal.updateComplete;
        expect(document.activeElement === input || modal.contains(document.activeElement)).to.equal(true);

        // Debounce → reload: результаты приходят при удержанном фокусе.
        await aTimeout(320);
        releaseSecond!();
        await waitUntil(
            () => responses.some((entry) => entry.q === 'read_f'),
            'search response for read_f',
            { timeout: 3000 },
        );
        await modal.updateComplete;
        await aTimeout(0);

        const inputAfter = pickerSearchInput(modal);
        expect(inputAfter).to.equal(input);
        expect(shadow(modal).activeElement === inputAfter
            || document.activeElement === inputAfter
            || inputAfter.matches(':focus')).to.equal(true);
        expect(inputAfter.value).to.equal('read_f');
        expect(inputAfter.selectionStart).to.equal(6);
        expect(inputAfter.selectionEnd).to.equal(6);
    });

    it('shows manage MCP CTA when MCP servers and tools are empty', async () => {
        const modal = await fixture<TestEl>(html`
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
        const host = await fixture<TestEl>(html`<div>${modal._renderMcpEmptyState()}</div>`);
        expect(host.textContent).to.include('tool_picker_modal.action_manage_mcp');
        expect(q(host!, 'platform-button')).to.not.equal(null);
    });
});
