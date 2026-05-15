import { fixture, fixtureCleanup, html, expect, aTimeout } from '../helpers/render.js';
import { resetPlatformState, bootstrapTestBus } from '../helpers/reset.js';
import { collectFactories, registerFactory } from '@platform/lib/events/index.js';
import { toolsAllOp } from '../../../../apps/flows/ui/events/resources/tools.resource.js';
import {
    codeTemplatesOp,
    codeParseSignatureOp,
} from '../../../../apps/flows/ui/events/resources/code.resource.js';
import '../../../../apps/flows/ui/modals/flows-library-picker-modal.js';

const FACTORIES = [toolsAllOp, codeTemplatesOp, codeParseSignatureOp];

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
                expect(body.func_name).to.equal('execute');
                expect(body.code).to.include('async def execute');
                return jsonResponse({
                    success: true,
                    func_name: 'execute',
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
            code: 'async def execute(url: str, data: dict = None, state: dict = None):\n    return {}',
        });
        await aTimeout(0);

        expect(committed.config.args_schema.url.type).to.equal('string');
        expect(committed.config.args_schema.url.required).to.equal(true);
        expect(committed.config.args_schema.data.type).to.equal('object');
        expect(committed.config.args_schema.data.required).to.equal(false);
        expect(committed.config.args_schema.data.default).to.equal(null);
    });
});
