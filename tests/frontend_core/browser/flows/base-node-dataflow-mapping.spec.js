import { fixture, fixtureCleanup, html, expect, elementUpdated } from '../helpers/render.js';
import { resetPlatformState, bootstrapTestBus } from '../helpers/reset.js';
import { registerFactory, collectFactories } from '@platform/lib/events/index.js';

import { editorResource } from '../../../../apps/flows/ui/events/resources/editor.resource.js';
import { resourcesBundleResource } from '../../../../apps/flows/ui/events/resources/resources-bundle.resource.js';
import { fileUploadOp } from '../../../../apps/flows/ui/events/resources/files.resource.js';
import {
    codeCompletionsOp,
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

const FACTORIES = [
    editorResource,
    resourcesBundleResource,
    fileUploadOp,
    codeCompletionsOp,
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
        const el = await fixture(html`
            <flows-base-node-editor
                .nodeId=${'n1'}
                .flowId=${'demo'}
                .branchId=${'base'}
                .nodeConfig=${node}
                .nodeType=${'llm_node'}
                .flowVariables=${{}}
                .graphNodes=${[]}
                .dataflowNode=${dataflowNode}
            ></flows-base-node-editor>
        `);
        await elementUpdated(el);

        let lastPatch = null;
        el.addEventListener('change', (e) => { lastPatch = e.detail.patch; });

        const readButton = el.shadowRoot.querySelector('.dataflow-lane:first-child button.dataflow-chip');
        readButton.click();
        expect(lastPatch).to.deep.equal({ input_mapping: { content: '@state:content' } });

        el.nodeConfig = { ...node, ...lastPatch };
        await elementUpdated(el);

        const writeButton = el.shadowRoot.querySelector('.dataflow-lane:nth-child(2) button.dataflow-chip');
        writeButton.click();
        expect(lastPatch).to.deep.equal({ output_mapping: { response: 'response' } });
    });
});
