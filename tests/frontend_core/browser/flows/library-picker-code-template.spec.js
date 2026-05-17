import { fixture, fixtureCleanup, html, expect, aTimeout } from '../helpers/render.js';
import { resetPlatformState, bootstrapTestBus } from '../helpers/reset.js';
import { collectFactories, registerFactory } from '@platform/lib/events/index.js';
import { toolsAllOp, toolsResource } from '../../../../apps/flows/ui/events/resources/tools.resource.js';
import {
    codeCompletionsOp,
    codeTemplatesOp,
    codeParseSignatureOp,
    codeValidateOp,
} from '../../../../apps/flows/ui/events/resources/code.resource.js';
import '../../../../apps/flows/ui/modals/flows-library-picker-modal.js';
import '../../../../apps/flows/ui/modals/flows-tool-create-modal.js';

const FACTORIES = [toolsAllOp, toolsResource, codeCompletionsOp, codeTemplatesOp, codeParseSignatureOp, codeValidateOp];

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

describe('flows library picker code templates', () => {
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

    it('commits catalog code template with inferred args_schema', async () => {
        window.fetch = async (url, options) => {
            const href = String(url);
            if (href.endsWith('/flows/api/v1/code/parse-signature')) {
                const body = JSON.parse(String(options.body));
                expect(body.func_name).to.equal(undefined);
                expect(body.code).to.include('async def run');
                return jsonResponse({
                    success: true,
                    func_name: 'run',
                    parameters: {},
                    args_schema: {
                        url: {
                            type: 'string',
                            description: 'Параметр url',
                            required: true,
                        },
                        data: {
                            type: 'object',
                            description: 'Параметр data',
                            required: false,
                            default: null,
                        },
                    },
                });
            }
            throw new Error(`unexpected fetch: ${href}`);
        };

        const modal = await fixture(html`<flows-library-picker-modal></flows-library-picker-modal>`);
        modal._modalId = 'test_modal';
        let committed = null;
        modal.onCommit = (detail) => {
            committed = detail;
        };

        await modal._commitTemplate({
            id: 'http_post',
            name: 'HTTP POST запрос',
            language: 'python',
            code: 'async def run(url: str, data: dict = None, state: dict = None):\n    return {}',
        });
        await aTimeout(0);

        expect(committed.config.args_schema.url.type).to.equal('string');
        expect(committed.config.args_schema.url.required).to.equal(true);
        expect(committed.config.args_schema.data.type).to.equal('object');
        expect(committed.config.args_schema.data.required).to.equal(false);
        expect(committed.config.args_schema.data.default).to.equal(null);
    });

    it('commits non-python catalog template without python signature parsing', async () => {
        window.fetch = async (url) => {
            throw new Error(`unexpected fetch: ${String(url)}`);
        };

        const modal = await fixture(html`<flows-library-picker-modal></flows-library-picker-modal>`);
        modal._modalId = 'test_modal';
        let committed = null;
        modal.onCommit = (detail) => {
            committed = detail;
        };

        await modal._commitTemplate({
            id: 'ts_transform',
            name: 'TS transform',
            language: 'typescript',
            code: 'async function run(args: Record<string, unknown>, state: Record<string, unknown>) {\n  return {};\n}',
        });
        await aTimeout(0);

        expect(committed.config.language).to.equal('typescript');
        expect(committed.config.code).to.include('async function run');
        expect(committed.config.args_schema).to.equal(undefined);
    });

    it('creates inline tool with selected language and JSON Schema parameters', async () => {
        const modal = await fixture(html`<flows-tool-create-modal></flows-tool-create-modal>`);
        let created = null;
        modal._tools = {
            create: (payload) => {
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

        expect(created.tool_id).to.equal('ts_tool');
        expect(created.title).to.equal('TypeScript tool');
        expect(created.language).to.equal('typescript');
        expect(created.parameters_schema).to.deep.equal({ type: 'object', properties: {} });
    });

    it('creates generated code-node template from registry-only platform tool', async () => {
        const modal = await fixture(html`<flows-library-picker-modal></flows-library-picker-modal>`);
        modal._modalId = 'test_modal';
        let committed = null;
        modal.onCommit = (detail) => {
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
        expect(modal._pickModeRows().map((row) => row.tool_id)).to.include('browser_page_markdown');

        modal._modalKind = 'flows.code_node_templates';
        modal._codeLanguage = 'javascript';
        expect(modal._toolRegistryRows().map((row) => row.tool_id)).to.include('browser_page_markdown');

        modal._commitTool(platformTool);
        await aTimeout(0);

        expect(committed.config.language).to.equal('javascript');
        expect(committed.config.tool_id).to.equal('browser_page_markdown');
        expect(committed.config.code).to.include('await tools.browser_page_markdown');
        expect(committed.config.args_schema.url.required).to.equal(true);
    });
});
