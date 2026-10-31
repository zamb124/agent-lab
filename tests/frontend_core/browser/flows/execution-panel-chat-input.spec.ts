/**
 * flows-execution-panel hosts unified platform-flow-ui in Run workspace
 * and relays A2A frames into editor slice / canvas.
 */
import { fixture, fixtureCleanup, html, expect, elementUpdated } from '../helpers/render.js';
import { resetPlatformState, bootstrapTestBus } from '../helpers/reset.js';
import { getPlatformBus } from '@platform/lib/events/index.js';
import { executionUiSlice } from '../../../../apps/flows/ui/events/resources/execution-ui.resource.js';
import {
    FLOW_CANVAS_FACTORIES,
    SAMPLE_BRANCH_NODES,
    flowsEditorBus,
} from '../../helpers/flows-dataflow-fixtures.js';
import '../../../../apps/flows/ui/components/editor/flows-execution-panel.js';
import '../../../../apps/flows/ui/components/flow-canvas/flows-flow-canvas.js';
import {q, qs, shadow, type TestEl} from '../helpers/dom.js';

const CONTEXT_ID = 'context:65b4c118-763f-4080-bf46-ee4dc5b01cd6';
const TASK_ID = 'c44ce807-e69c-5d1d-bbcf-b557e00f1c39';

function rpcFrame(result: any) {
    return { jsonrpc: '2.0', id: 'rpc:test', result };
}

function nodeStartFrame(nodeId: any, nodeType: any) {
    return rpcFrame({
        artifactUpdate: {
            taskId: TASK_ID,
            contextId: CONTEXT_ID,
            artifact: {
                artifactId: `start-${nodeId}`,
                name: `node_start_${nodeId}`,
                parts: [{ data: { event: 'node_start', node_id: nodeId, node_type: nodeType } }],
            },
        },
    });
}

const NODE_START_FRAME = nodeStartFrame('main', 'llm_node');

const NODE_ERROR_FRAME = rpcFrame({
    artifactUpdate: {
        taskId: TASK_ID,
        contextId: CONTEXT_ID,
        artifact: {
            artifactId: '97e82012-e333-4de3-91ca-4be46178cda4',
            name: 'node_error_main',
            parts: [{
                data: {
                    event: 'node_error',
                    node_id: 'main',
                    node_type: 'llm_node',
                    error: "LLM node 'main' returned empty final response after 1 iteration(s)",
                    duration_ms: 2058.0,
                    run_index: 0.0,
                },
            }],
        },
    },
});

const NODE_COMPLETE_FRAME = rpcFrame({
    artifactUpdate: {
        taskId: TASK_ID,
        contextId: CONTEXT_ID,
        artifact: {
            artifactId: 'complete-main',
            name: 'node_complete_main',
            parts: [{
                data: {
                    event: 'node_complete',
                    node_id: 'main',
                    node_type: 'llm_node',
                    result_preview: 'hello from node',
                    duration_ms: 12,
                    run_index: 0,
                },
            }],
        },
    },
});

const EDGE_EXECUTED_FRAME = rpcFrame({
    artifactUpdate: {
        taskId: TASK_ID,
        contextId: CONTEXT_ID,
        artifact: {
            artifactId: 'edge-0',
            name: 'edge_executed_0',
            parts: [{
                data: {
                    event: 'edge_executed',
                    edge_index: 0,
                    from_node: 'code_1',
                    to_node: 'llm_1',
                },
            }],
        },
    },
});

const FAILED_STATUS_FRAME = rpcFrame({
    statusUpdate: {
        taskId: TASK_ID,
        contextId: CONTEXT_ID,
        status: {
            state: 'TASK_STATE_FAILED',
            message: {
                messageId: `status:${TASK_ID}:failed`,
                role: 'ROLE_AGENT',
                parts: [{ text: "LLM node 'main' returned empty final response after 1 iteration(s)" }],
            },
        },
    },
});

function dispatchHostFrame(host: any, frame: any) {
    host.dispatchEvent(new CustomEvent('flow-ui-a2a-frame', {
        detail: { frame, contextId: CONTEXT_ID, taskId: TASK_ID },
    }));
}

async function mountRunWorkspace(flow: any) {
    const bus = flowsEditorBus();
    bus.dispatch('flows/editor/flow_loaded', {
        branchId: 'base',
        flow,
    });
    const wrap = await fixture<TestEl>(html`
        <div>
            <flows-flow-canvas flow-id=${flow.flow_id} branch-id="base"></flows-flow-canvas>
            <flows-execution-panel flow-id=${flow.flow_id} branch-id="base"></flows-execution-panel>
        </div>
    `);
    const panel = qs(wrap!, 'flows-execution-panel');
    const canvas = qs(wrap!, 'flows-flow-canvas');
    panel._editor.setExecutionPanelOpen({ open: true });
    await elementUpdated(panel);
    await elementUpdated(canvas);
    const host = q(panel.renderRoot, 'platform-flow-ui');
    expect(host).to.not.equal(null);
    return { wrap, panel, canvas, host, bus };
}

describe('flows-execution-panel Flow UI host', () => {
    beforeEach(async () => {
        await resetPlatformState();
        bootstrapTestBus({ factories: [...FLOW_CANVAS_FACTORIES, executionUiSlice] });
    });

    afterEach(() => {
        fixtureCleanup();
    });

    it('execution panel module exposes platform-flow-ui host contract', async () => {
        const defined = customElements.get('flows-execution-panel');
        expect(defined).to.not.equal(undefined);
        const el = await fixture<TestEl>(html`<flows-execution-panel></flows-execution-panel>`);
        await elementUpdated(el);
        expect(el.tagName.toLowerCase()).to.equal('flows-execution-panel');
    });

    it('submit + node_start highlights canvas orbit, running pill, START wire and running badge', async () => {
        const { panel, canvas, host, bus } = await mountRunWorkspace({
            flow_id: 'lara',
            name: 'Lara',
            entry: 'main',
            nodes: {
                main: { ...SAMPLE_BRANCH_NODES.llm_1, name: 'Lara', pos_x: 0, pos_y: 0 },
            },
            edges: [],
        });

        host!.dispatchEvent(new CustomEvent('flow-ui-submit-start', {
            detail: { contextId: CONTEXT_ID, surfaceId: 'main', componentId: 'submit' },
        }));
        await elementUpdated(panel);
        expect(bus.getState().flowsEditor.agentExecutionRunning).to.equal(true);
        const badge = q(panel.renderRoot, '.status-badge');
        expect(badge).to.not.equal(null);
        expect(badge!.getAttribute('data-status')).to.equal('running');

        dispatchHostFrame(host, NODE_START_FRAME);
        await elementUpdated(panel);
        await elementUpdated(canvas);

        expect(bus.getState().flowsEditor.runningNodeIds).to.deep.equal(['main']);
        const runningNode = q(shadow(canvas), 'g.node[data-node-id="main"][data-state="running"]');
        expect(runningNode).to.not.equal(null);
        expect(q(runningNode!, '.node-run-orbit')).to.not.equal(null);
        expect(q(runningNode!, '.node-run-result-pill[data-tone="running"]')).to.not.equal(null);
        const startWire = q(shadow(canvas), 'g.terminal-marker--start path.edge[data-run-state="running"]');
        expect(startWire).to.not.equal(null);
    });

    it('node_error + TASK_STATE_FAILED shows error pill, failed START and failed badge', async () => {
        const { panel, canvas, host, bus } = await mountRunWorkspace({
            flow_id: 'lara',
            name: 'Lara',
            entry: 'main',
            nodes: {
                main: { ...SAMPLE_BRANCH_NODES.llm_1, name: 'Lara', pos_x: 0, pos_y: 0 },
            },
            edges: [],
        });

        host!.dispatchEvent(new CustomEvent('flow-ui-submit-start', {
            detail: { contextId: CONTEXT_ID, surfaceId: 'main', componentId: 'submit' },
        }));
        dispatchHostFrame(host, NODE_START_FRAME);
        dispatchHostFrame(host, NODE_ERROR_FRAME);
        dispatchHostFrame(host, FAILED_STATUS_FRAME);
        await elementUpdated(panel);
        await elementUpdated(canvas);

        const editor = bus.getState().flowsEditor;
        expect(editor!.runningNodeIds).to.deep.equal([]);
        expect(editor!.erroredNodes!.main).to.equal(
            "LLM node 'main' returned empty final response after 1 iteration(s)",
        );
        expect((editor!.nodeRunResults!.main![0] as Record<string, unknown>).kind).to.equal('error');
        expect(editor!.agentExecutionRunning).to.equal(false);

        const errorNode = q(shadow(canvas), 'g.node[data-node-id="main"][data-state="error"]');
        expect(errorNode).to.not.equal(null);
        const errorPill = q(errorNode!, '.node-run-result-pill[data-tone="error"]');
        expect(errorPill).to.not.equal(null);
        expect(errorPill!.textContent).to.include("empty final response");
        expect(q(shadow(canvas), 'g.terminal-marker--start path.edge[data-run-state="failed"]')).to.not.equal(null);
        expect(qs(panel.renderRoot, '.status-badge').getAttribute('data-status')).to.equal('failed');
    });

    it('keeps platform-flow-ui mounted while collapsed and still applies frames', async () => {
        const { panel, canvas, host, bus } = await mountRunWorkspace({
            flow_id: 'lara',
            name: 'Lara',
            entry: 'main',
            nodes: {
                main: { ...SAMPLE_BRANCH_NODES.llm_1, name: 'Lara', pos_x: 0, pos_y: 0 },
            },
            edges: [],
        });

        host!.dispatchEvent(new CustomEvent('flow-ui-submit-start', {
            detail: { contextId: CONTEXT_ID, surfaceId: 'main', componentId: 'submit' },
        }));
        dispatchHostFrame(host, NODE_START_FRAME);
        await elementUpdated(panel);

        const minimizeIcon = q(panel.renderRoot, 'platform-icon[name="minimize"]');
        expect(minimizeIcon).to.not.equal(null);
        (minimizeIcon!.closest('platform-button') as HTMLElement)!.click();
        await elementUpdated(panel);

        const hostAfterCollapse = qs(panel.renderRoot, 'platform-flow-ui');
        expect(hostAfterCollapse).to.equal(host);

        dispatchHostFrame(hostAfterCollapse, NODE_ERROR_FRAME);
        await elementUpdated(panel);
        await elementUpdated(canvas);
        expect(bus.getState().flowsEditor.erroredNodes!.main).to.equal(
            "LLM node 'main' returned empty final response after 1 iteration(s)",
        );
        expect(q(shadow(canvas), 'g.node[data-node-id="main"][data-state="error"]')).to.not.equal(null);
    });

    it('node_complete shows completed state and ok pill with preview', async () => {
        const { panel, canvas, host, bus } = await mountRunWorkspace({
            flow_id: 'lara',
            name: 'Lara',
            entry: 'main',
            nodes: {
                main: { ...SAMPLE_BRANCH_NODES.llm_1, name: 'Lara', pos_x: 0, pos_y: 0 },
            },
            edges: [],
        });

        host!.dispatchEvent(new CustomEvent('flow-ui-submit-start', {
            detail: { contextId: CONTEXT_ID, surfaceId: 'main', componentId: 'submit' },
        }));
        dispatchHostFrame(host, NODE_START_FRAME);
        dispatchHostFrame(host, NODE_COMPLETE_FRAME);
        await elementUpdated(panel);
        await elementUpdated(canvas);

        expect(bus.getState().flowsEditor.completedNodeIds).to.deep.equal(['main']);
        const done = q(shadow(canvas), 'g.node[data-node-id="main"][data-state="completed"]');
        expect(done).to.not.equal(null);
        const pill = q(done!, '.node-run-result-pill[data-tone="ok"]');
        expect(pill).to.not.equal(null);
        expect(pill!.textContent).to.include('hello from node');
        expect(q(shadow(canvas), 'g.terminal-marker--start path.edge[data-run-state="completed"]')).to.not.equal(null);
        expect(q(shadow(canvas), 'g.terminal-marker--end path.edge[data-run-state="completed"]')).to.not.equal(null);
    });

    it('edge_executed then next node_started marks real edge running then completed', async () => {
        const { panel, canvas, host, bus } = await mountRunWorkspace({
            flow_id: 'two',
            name: 'Two',
            entry: 'code_1',
            nodes: {
                code_1: { ...SAMPLE_BRANCH_NODES.code_1, pos_x: 0, pos_y: 0 },
                llm_1: { ...SAMPLE_BRANCH_NODES.llm_1, pos_x: 280, pos_y: 0 },
            },
            edges: [{ from_node: 'code_1', to_node: 'llm_1' }],
        });

        host!.dispatchEvent(new CustomEvent('flow-ui-submit-start', {
            detail: { contextId: CONTEXT_ID, surfaceId: 'main', componentId: 'submit' },
        }));
        dispatchHostFrame(host, nodeStartFrame('code_1', 'code'));
        dispatchHostFrame(host, rpcFrame({
            artifactUpdate: {
                taskId: TASK_ID,
                contextId: CONTEXT_ID,
                artifact: {
                    artifactId: 'complete-code',
                    name: 'node_complete_code_1',
                    parts: [{
                        data: {
                            event: 'node_complete',
                            node_id: 'code_1',
                            node_type: 'code',
                            result_preview: 'step-1',
                            run_index: 0,
                        },
                    }],
                },
            },
        }));
        dispatchHostFrame(host, EDGE_EXECUTED_FRAME);
        await elementUpdated(panel);
        await elementUpdated(canvas);
        expect(bus.getState().flowsEditor.runningEdgeIndices).to.deep.equal([0]);
        expect(q(shadow(canvas), 'path.edge[data-run-state="running"]')).to.not.equal(null);

        dispatchHostFrame(host, nodeStartFrame('llm_1', 'llm_node'));
        await elementUpdated(panel);
        await elementUpdated(canvas);
        expect(bus.getState().flowsEditor.completedEdgeIndices).to.deep.equal([0]);
        expect(q(shadow(canvas), 'g.edge-group:not(.terminal-marker) path.edge[data-run-state="completed"]')).to.not.equal(null);
        expect(q(shadow(canvas), 'g.node[data-node-id="llm_1"][data-state="running"]')).to.not.equal(null);
    });
});
