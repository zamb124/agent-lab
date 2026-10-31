import { fixture, fixtureCleanup, html, expect, aTimeout } from '../helpers/render.js';
import { resetPlatformState, bootstrapTestBus } from '../helpers/reset.js';
import { collectFactories, registerFactory } from '@platform/lib/events/index.js';
import { platformWs } from '@platform/lib/events/effects/ws.effect.js';
import { toolsAllOp, toolsResource } from '../../../../apps/flows/ui/events/resources/tools.resource.js';
import { toolTagGroupsOp } from '../../../../apps/flows/ui/events/resources/tool-tag-groups.resource.js';
import {
    codeLspSessionOp,
    codeTemplatesOp,
    codeParseSignatureOp,
    codeValidateOp,
} from '../../../../apps/flows/ui/events/resources/code.resource.js';
import { mcpServersResource, mcpServerSyncOp, mcpServerTestOp } from '../../../../apps/flows/ui/events/resources/mcp.resource.js';
import '../../../../apps/flows/ui/modals/flows-library-picker-modal.js';
import '../../../../apps/flows/ui/modals/flows-tool-create-modal.js';
import type { TestEl } from '../helpers/dom.js';

const FACTORIES = [
    toolsAllOp,
    toolsResource,
    toolTagGroupsOp,
    codeLspSessionOp,
    codeTemplatesOp,
    codeParseSignatureOp,
    codeValidateOp,
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

describe('flows library picker code templates', () => {
    let originalFetch: any;
    let originalWsRequest: any;

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

    it('commits catalog code template with inferred parameters_schema', async () => {
        window.fetch = async (url: RequestInfo | URL) => {
            throw new Error(`unexpected fetch: ${String(url)}`);
        };
        platformWs.request = async (opts) => {
            if (opts.type === 'flows/code/parse_signature_requested') {
                expect((opts.payload as Record<string, any>).func_name).to.equal(undefined);
                expect((opts.payload as Record<string, any>).code).to.include('async def run');
                return {
                    success: true,
                    func_name: 'run',
                    parameters: {},
                    parameters_schema: {
                        type: 'object',
                        properties: {
                            url: {
                                type: 'string',
                                description: 'Параметр url',
                            },
                            data: {
                                type: 'object',
                                description: 'Параметр data',
                                default: null,
                            },
                        },
                        required: ['url'],
                    },
                };
            }
            throw new Error(`unexpected WS command ${opts.type}`);
        };

        const modal = await fixture<TestEl>(html`<flows-library-picker-modal></flows-library-picker-modal>`);
        modal._modalId = 'test_modal';
        let committed = null;
        modal.onCommit = (detail: any) => {
            committed = detail;
        };

        await modal._commitTemplate({
            id: 'http_post',
            name: 'HTTP POST запрос',
            language: 'python',
            code: 'async def run(url: str, data: dict = None, state: dict = None):\n    return {}',
        });
        await aTimeout(0);

        expect(committed!.config.parameters_schema.properties.url.type).to.equal('string');
        expect(committed!.config.parameters_schema.required).to.deep.equal(['url']);
        expect(committed!.config.parameters_schema.properties.data.type).to.equal('object');
        expect(committed!.config.parameters_schema.properties.data.default).to.equal(null);
    });

    it('commits non-python catalog template without python signature parsing', async () => {
        window.fetch = async (url: RequestInfo | URL) => {
            throw new Error(`unexpected fetch: ${String(url)}`);
        };

        const modal = await fixture<TestEl>(html`<flows-library-picker-modal></flows-library-picker-modal>`);
        modal._modalId = 'test_modal';
        let committed = null;
        modal.onCommit = (detail: any) => {
            committed = detail;
        };

        await modal._commitTemplate({
            id: 'ts_transform',
            name: 'TS transform',
            language: 'typescript',
            code: 'async function run(args: Record<string, unknown>, state: Record<string, unknown>) {\n  return {};\n}',
        });
        await aTimeout(0);

        expect(committed!.config.language).to.equal('typescript');
        expect(committed!.config.code).to.include('async function run');
        expect(committed!.config.parameters_schema).to.deep.equal({ type: 'object', properties: {}, required: [] });
    });

    it('creates inline tool with selected language and JSON Schema parameters', async () => {
        const modal = await fixture<TestEl>(html`<flows-tool-create-modal></flows-tool-create-modal>`);
        let created = null;
        modal._tools = {
            create: (payload: any) => {
                created = payload;
            },
        };
        modal.closeAfterSave = () => {};
        modal._toolId = 'ts_tool';
        modal._name = 'TypeScript tool';
        modal._description = 'runs in node runner';
        modal._language = 'typescript';
        modal._code = 'async function run(args: Record<string, unknown>, state: Record<string, unknown>) {\n  return {};\n}';
        modal._schemaJson = JSON.stringify({ type: 'object', properties: {} });

        modal._save();

        expect(created!.tool_id).to.equal('ts_tool');
        expect(created!.title).to.equal('TypeScript tool');
        expect(created!.language).to.equal('typescript');
        expect(created!.parameters_schema).to.deep.equal({ type: 'object', properties: {} });
    });

    it('creates generated code-node template from registry-only platform tool', async () => {
        const modal = await fixture<TestEl>(html`<flows-library-picker-modal></flows-library-picker-modal>`);
        modal._modalId = 'test_modal';
        let committed = null;
        modal.onCommit = (detail: any) => {
            committed = detail;
        };
        const platformTool = {
            tool_id: 'browser_page_markdown',
            title: 'browser_page_markdown',
            item_type: 'tool',
            code: null,
            language: 'python',
            parameters_schema: {
                type: 'object',
                properties: {
                    url: { type: 'string', description: 'Page URL' },
                },
                required: ['url'],
            },
            tags: ['browser'],
        };
        modal._toolsAll = {
            busy: false,
            lastResult: {
                items: [
                    platformTool,
                    {
                        tool_id: 'py_transform',
                        title: 'Python transform',
                        item_type: 'tool',
                        language: 'python',
                        code: 'async def run(args, state):\n    return {}',
                        tags: ['sandbox'],
                    },
                ],
            },
        };

        modal._modalKind = 'flows.tool_picker';
        expect(modal._pickModeRows().map((row: any) => row.tool_id)).to.include('browser_page_markdown');

        modal.pickMode = 'code_node';
        modal._modalKind = 'flows.tool_picker';
        modal._codeLanguage = 'javascript';
        modal._pickerItemsByCategory = new Map([
            ['code', modal._toolsAll.lastResult.items],
        ]);
        expect(modal._codeNodePickRows().map((row: any) => row.tool_id)).to.include('browser_page_markdown');

        modal._commitTool(platformTool);
        await aTimeout(0);

        expect(committed!.config.language).to.equal('javascript');
        expect(committed!.config.tool_id).to.equal('browser_page_markdown');
        expect(committed!.config.code).to.include('await tools.browser_page_markdown');
        expect(committed!.config.parameters_schema.required).to.include('url');
    });
});
