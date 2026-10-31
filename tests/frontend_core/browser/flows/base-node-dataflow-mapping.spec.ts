import { fixture, fixtureCleanup, html, expect, elementUpdated } from '../helpers/render.js';
import { resetPlatformState, bootstrapTestBus } from '../helpers/reset.js';
import { registerFactory, collectFactories } from '@platform/lib/events/index.js';

import { editorResource } from '../../../../apps/flows/ui/events/resources/editor.resource.js';
import { resourcesBundleResource } from '../../../../apps/flows/ui/events/resources/resources-bundle.resource.js';
import { platformFileCreateOp } from '@platform/lib/events/factories/platform-file-create.js';
import {
    codeLspSessionOp,
    codeDocumentationOp,
    codeTemplatesOp,
    codeEditorStateOp,
    codeSourceOp,
    codeFlowFunctionsOp,
    codeToolSourceOp,
    codeParseSignatureOp,
    codeValidateOp,
    codeExecuteOp,
} from '../../../../apps/flows/ui/events/resources/code.resource.js';
import { exceptionAbsorbAllowNamesOp, executionLimitsOp } from '../../../../apps/flows/ui/events/resources/metadata.resource.js';
import '../../../../apps/flows/ui/components/nodes/flows-base-node-editor.js';
import { qs, shadow, type TestEl } from '../helpers/dom.js';

const FACTORIES = [
    editorResource,
    resourcesBundleResource,
    platformFileCreateOp,
    codeLspSessionOp,
    codeDocumentationOp,
    codeTemplatesOp,
    codeEditorStateOp,
    codeSourceOp,
    codeFlowFunctionsOp,
    codeToolSourceOp,
    codeParseSignatureOp,
    codeValidateOp,
    codeExecuteOp,
    exceptionAbsorbAllowNamesOp,
    executionLimitsOp,
];

function bootstrap() {
    for (const f of FACTORIES) registerFactory(f);
    const collected = collectFactories(FACTORIES);
    return bootstrapTestBus({ slices: collected.slices, effects: [] });
}

describe('flows-base-node-editor dataflow mapping shortcuts', () => {
    beforeEach(() => {
        resetPlatformState();
        bootstrap();
    });
    afterEach(() => fixtureCleanup());

    it('clicks read/write dataflow chips into matching mapping tabs', async () => {
        const node = { node_id: 'n1', type: 'llm_node', name: 'N1', input_mapping: {}, output_mapping: {} };
        const dataflowNode = {
            incoming_state: [{ path: 'content', type: 'string', source: 'previous' }],
            writes: [{ path: 'response', type: 'string', source: 'node' }],
            result_keys: ['response'],
        };
        const el = await fixture<TestEl>(html`
            <flows-base-node-editor
                .nodeId=${'n1'}
                .flowId=${'demo'}
                .branchId=${'base'}
                .nodeConfig=${node}
                .flowNodeType=${'llm_node'}
                .flowVariables=${{}}
                .graphNodes=${[]}
                .dataflowNode=${dataflowNode}
            ></flows-base-node-editor>
        `);
        await elementUpdated(el);

        let lastPatch: Record<string, unknown> | null = null;
        el.addEventListener('change', (e) => { lastPatch = (e as CustomEvent).detail.patch; });

        const readButton = qs(shadow(el), '.dataflow-lane:first-child article.dataflow-chip');
        (readButton as TestEl).click();
        expect(lastPatch).to.deep.equal({ input_mapping: { content: '@state:content' } });

        el.nodeConfig = { ...node, ...(lastPatch as unknown as Record<string, unknown>) };
        await elementUpdated(el);

        const writeButton = qs(shadow(el), '.dataflow-lane:nth-child(2) article.dataflow-chip');
        (writeButton as TestEl).click();
        expect(lastPatch).to.deep.equal({ output_mapping: { response: 'response' } });
    });
});
