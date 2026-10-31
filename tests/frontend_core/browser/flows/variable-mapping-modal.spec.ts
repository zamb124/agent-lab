import { fixture, fixtureCleanup, html, expect, elementUpdated } from '../helpers/render.js';
import { resetPlatformState } from '../helpers/reset.js';
import { registerFactory } from '@platform/lib/events/factory-registry.js';
import { editorResource } from '../../../../apps/flows/ui/events/resources/editor.resource.js';
import {
    bootstrapFlowsEditor,
    seedEditorDataflow,
    SAMPLE_DATAFLOW_NODES,
} from '../../helpers/flows-dataflow-fixtures.js';
import '../../../../apps/flows/ui/modals/flows-variable-mapping-modal.js';

describe('flows-variable-mapping-modal', () => {
    beforeEach(() => resetPlatformState());
    afterEach(() => fixtureCleanup());

    it('renders summary and suggestions from target dataflow', async () => {
        const { bus } = bootstrapFlowsEditor();
        seedEditorDataflow(bus);

        const el = await fixture(html`
            <flows-variable-mapping-modal
                .open=${true}
                .fromNodeId=${'code_1'}
                .fromNodeName=${'Code'}
                .targetNodeId=${'llm_1'}
                .targetNodeName=${'LLM'}
                .sourcePath=${'topic'}
                .sourceType=${'string'}
                .pathExists=${true}
            ></flows-variable-mapping-modal>
        `);
        await elementUpdated(el);

        const summary = el.shadowRoot.querySelector('.summary');
        expect(summary.textContent).to.include('Code');
        expect(summary.textContent).to.include('topic');
        expect(summary.textContent).to.include('LLM');
        const suggestions = el.shadowRoot.querySelectorAll('.suggestion');
        expect(suggestions.length).to.be.greaterThan(0);
    });

    it('shows edge note when pathExists is false', async () => {
        bootstrapFlowsEditor();
        const el = await fixture(html`
            <flows-variable-mapping-modal
                .open=${true}
                .fromNodeId=${'code_1'}
                .targetNodeId=${'broken_1'}
                .sourcePath=${'topic'}
                .pathExists=${false}
            ></flows-variable-mapping-modal>
        `);
        await elementUpdated(el);
        expect(el.shadowRoot.querySelector('.edge-note')).to.not.equal(null);
    });

    it('confirm writes input_mapping and optional edge', async () => {
        const { bus, getState } = bootstrapFlowsEditor();
        bus.dispatch('flows/editor/flow_loaded', {
            branchId: 'default',
            flow: {
                flow_id: 'flow_test',
                name: 'Test',
                entry: 'code_1',
                nodes: {
                    code_1: { type: 'code', name: 'Code', input_mapping: {} },
                    orphan: { type: 'llm_node', name: 'Orphan', input_mapping: {} },
                },
                edges: [],
            },
        });

        const el = await fixture(html`
            <flows-variable-mapping-modal
                .open=${true}
                .fromNodeId=${'code_1'}
                .targetNodeId=${'orphan'}
                .sourcePath=${'topic'}
                .pathExists=${false}
            ></flows-variable-mapping-modal>
        `);
        await elementUpdated(el);
        el._targetParam = 'topic';
        el._createEdge = true;
        el.close = () => {};
        el._confirm();
        await elementUpdated(el);

        const branchData = getState().flowsEditor.branchData;
        expect(branchData.nodes.orphan.input_mapping.topic).to.equal('@state:topic');
        expect(branchData.edges.some((e) => e.from_node === 'code_1' && e.to_node === 'orphan')).to.equal(true);
        expect(getState().flowsEditor.isDirty).to.equal(true);
    });
});
