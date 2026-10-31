/**
 * flows/editor — UI-only фабрика состояния редактора.
 *
 * extraReducer: flow_loaded / node_selected / panel_closed /
 * execution_panel_set / agent_execution_set /
 * active_tool_set / dirty_set / saving_set / preview_state_set /
 * history_pushed / history_undone / history_redone / history_cleared.
 */

import { describe, it, expect, beforeEach, afterEach } from 'vitest';
import { collectFactories } from '@platform/lib/events/factories/register.js';
import { editorResource } from '../../../../apps/flows/ui/events/resources/editor.resource.js';
import { resetFactories } from '../../helpers/factory-fixtures.js';
import { buildBus } from '../../helpers/bus-fixtures.js';
import { installFakeStorage } from '../../helpers/fake-storage.js';
import { dig, digOr, prop } from '../../helpers/prop.js';
import { registerFactory } from '@platform/lib/events/factory-registry.js';

let storage: ReturnType<typeof installFakeStorage>;

beforeEach(() => {
    resetFactories();
    storage = installFakeStorage();
});
afterEach(() => {
    storage.uninstall();
    resetFactories();
});

function build() {
    registerFactory(editorResource);
    return buildBus({ slices: { flowsEditor: editorResource.slice } });
}

describe('flows/editor extraReducer', () => {
    it('initial slice имеет дефолты', () => {
        const { getState } = build();
        const s = getState().flowsEditor;
        expect(s.flowId).toBeNull();
        expect(s.activeTool).toBe('select');
        expect(s.canUndo).toBe(false);
        expect(s.canRedo).toBe(false);
        expect(s.historyStack).toEqual([]);
    });

    it('flow_loaded заполняет flowConfig и branchData', () => {
        const { bus, getState } = build();
        bus.dispatch('flows/editor/flow_loaded', {
            flow: { flow_id: 'demo', name: 'Demo', nodes: { a: { type: 'code' } }, edges: [], variables: {} },
            branchId: 'base',
        });
        const s = getState().flowsEditor;
        expect(s.flowId).toBe('demo');
        expect(dig(s, 'flowConfig', 'name')).toBe('Demo');
        expect(dig(s, 'branchData', 'nodes', 'a', 'type')).toBe('code');
        expect(s.isDirty).toBe(false);
        expect(s.historyStack).toEqual([]);
    });

    it('branch_data_updated сохраняет dataflow до нового inspect результата', () => {
        const { bus, getState } = build();
        bus.dispatch('flows/editor/flow_loaded', {
            flow: { flow_id: 'demo', name: 'Demo', nodes: { a: { type: 'code' } }, edges: [], variables: {} },
            branchId: 'base',
        });
        const dataflow = { nodes: { a: { incoming_state: [{ path: 'content' }] } } };
        bus.dispatch('flows/editor/dataflow_set', { dataflow });
        bus.dispatch('flows/editor/dataflow_observation_recorded', {
            nodeId: 'a',
            observation: { diff: [], output_state: { content: 'x' } },
        });

        bus.dispatch('flows/editor/branch_data_updated', {
            data: {
                nodes: { a: { type: 'code', input_mapping: { content: '@state:content' } } },
                edges: [],
                variables: {},
            },
        });

        const s = getState().flowsEditor;
        expect(s.dataflow).toEqual(dataflow);
        expect(dig(s, 'dataflowObservations', 'a', 'output_state', 'content')).toBe('x');
    });

    it('flow_loaded: авто-раскладка нод 0,0 (>=2) ставит isDirty', () => {
        const { bus, getState } = build();
        bus.dispatch('flows/editor/flow_loaded', {
            flow: {
                flow_id: 'lay',
                name: 'Lay',
                nodes: { a: { type: 'code' }, b: { type: 'code' } },
                edges: [{ from_node: 'a', to_node: 'b' }],
                entry: 'a',
                variables: {},
            },
            branchId: 'base',
        });
        const s = getState().flowsEditor;
        expect(s.isDirty).toBe(true);
        expect(dig(s, 'branchData', 'nodes', 'b', 'pos_x')).toBeGreaterThan(0);
    });

    it('node_selected открывает panel и сбрасывает resource', () => {
        const { bus, getState } = build();
        bus.dispatch('flows/editor/node_selected', { nodeId: 'a' });
        const s = getState().flowsEditor;
        expect(s.selectedNodeId).toBe('a');
        expect(s.selectedResourceId).toBeNull();
        expect(s.panelOpen).toBe(true);
    });

    it('history_pushed/undone/redone', () => {
        const { bus, getState } = build();
        bus.dispatch('flows/editor/history_pushed', { snapshot: { v: 1 } });
        bus.dispatch('flows/editor/history_pushed', { snapshot: { v: 2 } });
        let s = getState().flowsEditor;
        expect(dig(s, 'historyStack', 'length')).toBe(2);
        expect(s.historyPosition).toBe(1);
        expect(s.canUndo).toBe(true);
        expect(s.canRedo).toBe(false);

        bus.dispatch('flows/editor/history_undone', null);
        s = getState().flowsEditor;
        expect(s.historyPosition).toBe(0);
        expect(s.canRedo).toBe(true);

        bus.dispatch('flows/editor/history_redone', null);
        s = getState().flowsEditor;
        expect(s.historyPosition).toBe(1);
        expect(s.canRedo).toBe(false);
    });

    it('history_cleared чистит весь стек', () => {
        const { bus, getState } = build();
        bus.dispatch('flows/editor/history_pushed', { snapshot: { v: 1 } });
        bus.dispatch('flows/editor/history_cleared', null);
        const s = getState().flowsEditor;
        expect(s.historyStack).toEqual([]);
        expect(s.historyPosition).toBe(-1);
        expect(s.canUndo).toBe(false);
    });

    it('dirty_set / saving_set', () => {
        const { bus, getState } = build();
        bus.dispatch('flows/editor/dirty_set', { dirty: true });
        bus.dispatch('flows/editor/saving_set', { saving: true });
        const s = getState().flowsEditor;
        expect(s.isDirty).toBe(true);
        expect(s.isSaving).toBe(true);
    });

    it('flows/run/* мутируют running/completed/errored', () => {
        const { bus, getState } = build();
        bus.dispatch('flows/run/flow_started', { task_id: 't1' });
        bus.dispatch('flows/run/node_started', { node_id: 'a', task_id: 't1' });
        bus.dispatch('flows/run/node_started', { node_id: 'b', task_id: 't1' });
        let s = getState().flowsEditor;
        expect(s.runningNodeIds).toEqual(['a', 'b']);
        expect(s.agentExecutionRunning).toBe(true);

        bus.dispatch('flows/run/node_completed', { node_id: 'a', task_id: 't1' });
        s = getState().flowsEditor;
        expect(s.runningNodeIds).toEqual(['b']);
        expect(s.completedNodeIds).toEqual(['a']);

        bus.dispatch('flows/run/node_failed', { node_id: 'b', task_id: 't1', error: 'boom' });
        s = getState().flowsEditor;
        expect(s.runningNodeIds).toEqual([]);
        expect(s.erroredNodes).toEqual({ b: 'boom' });

        bus.dispatch('flows/run/flow_done', { task_id: 't1', state: 'completed' });
        expect(getState().flowsEditor.agentExecutionRunning).toBe(false);
    });

    it('flows/run/node_completed сохраняет nodeRunResults', () => {
        const { bus, getState } = build();
        bus.dispatch('flows/run/flow_started', { task_id: 't1' });
        bus.dispatch('flows/run/node_completed', {
            node_id: 'a',
            node_type: 'code',
            run_index: 0,
            duration_ms: 42,
            result_preview: 'done',
            primary_field: 'response',
            diff: [
                { path: 'response', old_value: null, new_value: 'done', change_type: 'added' },
            ],
        });
        const s = getState().flowsEditor;
        expect(dig(s, 'nodeRunResults', 'a')).toHaveLength(1);
        expect(dig(s, 'nodeRunResults', 'a', '0', 'kind')).toBe('ok');
        expect(dig(s, 'nodeRunResults', 'a', '0', 'duration_ms')).toBe(42);
        expect(dig(s, 'nodeRunResults', 'a', '0', 'result_preview')).toBe('done');
        expect(dig(s, 'nodeRunResults', 'a', '0', 'diff')).toEqual([
            { path: 'response', old_value: null, new_value: 'done', change_type: 'added' },
        ]);
    });

    it('node_completed хранит полный diff и все run_index без обрезки', () => {
        const { bus, getState } = build();
        const longText = 'X'.repeat(400);
        const firstDiff = Array.from({ length: 12 }, (_, index) => ({
            path: `field_${index}`,
            old_value: null,
            new_value: index === 0 ? longText : index,
            change_type: 'added',
        }));
        bus.dispatch('flows/run/node_completed', {
            node_id: 'loop_node',
            node_type: 'code',
            run_index: 0,
            result_preview: 'first',
            diff: firstDiff,
        });
        bus.dispatch('flows/run/node_completed', {
            node_id: 'loop_node',
            node_type: 'code',
            run_index: 1,
            result_preview: 'second',
            diff: [{ path: 'result', old_value: 1, new_value: 2, change_type: 'changed' }],
        });
        const runs = dig(getState().flowsEditor, 'nodeRunResults', 'loop_node');
        expect(runs).toHaveLength(2);
        expect(dig(runs, '0', 'run_index')).toBe(0);
        expect(dig(runs, '1', 'run_index')).toBe(1);
        expect(dig(runs, '0', 'diff')).toHaveLength(12);
        expect(dig(runs, '0', 'diff', '0', 'new_value')).toBe(longText);
        expect(dig(runs, '0', 'diff', '11', 'path')).toBe('field_11');
        expect(dig(runs, '1', 'diff', '0')).toEqual({
            path: 'result',
            old_value: 1,
            new_value: 2,
            change_type: 'changed',
        });
    });

    it('flows/editor/canvas_run_results_toggled переключает showCanvasRunResults', () => {
        const { bus, getState } = build();
        expect(getState().flowsEditor.showCanvasRunResults).toBe(true);
        bus.dispatch('flows/editor/canvas_run_results_toggled', { value: false });
        expect(getState().flowsEditor.showCanvasRunResults).toBe(false);
    });

    it('node_started entry ставит startWire running, sink complete ставит START/END completed', () => {
        const { bus, getState } = build();
        bus.dispatch('flows/editor/flow_loaded', {
            flow: {
                flow_id: 'w1',
                name: 'W1',
                nodes: { main: { type: 'llm_node' } },
                edges: [],
                entry: 'main',
                variables: {},
            },
            branchId: 'base',
        });
        bus.dispatch('flows/run/flow_started', { context_id: 'ctx-1', task_id: 't1' });
        bus.dispatch('flows/run/node_started', { node_id: 'main', task_id: 't1' });
        let s = getState().flowsEditor;
        expect(s.startWireRunState).toBe('running');
        expect(s.endWireRunStateByNodeId).toEqual({});

        bus.dispatch('flows/run/node_completed', { node_id: 'main', task_id: 't1', result_preview: 'ok' });
        s = getState().flowsEditor;
        expect(s.startWireRunState).toBe('completed');
        expect(dig(s, 'endWireRunStateByNodeId', 'main')).toBe('completed');
    });

    it('node_failed entry ставит START и END failed', () => {
        const { bus, getState } = build();
        bus.dispatch('flows/editor/flow_loaded', {
            flow: {
                flow_id: 'w2',
                name: 'W2',
                nodes: { main: { type: 'llm_node' } },
                edges: [],
                entry: 'main',
                variables: {},
            },
            branchId: 'base',
        });
        bus.dispatch('flows/run/flow_started', { context_id: 'ctx-2' });
        bus.dispatch('flows/run/node_started', { node_id: 'main' });
        bus.dispatch('flows/run/node_failed', { node_id: 'main', error: 'boom' });
        const s = getState().flowsEditor;
        expect(s.startWireRunState).toBe('failed');
        expect(dig(s, 'endWireRunStateByNodeId', 'main')).toBe('failed');
        expect(dig(s, 'nodeRunResults', 'main', '0', 'kind')).toBe('error');
    });

    it('flows/run/a2a_mapped применяет runEvents, runTrace и terminal', () => {
        const { bus, getState } = build();
        bus.dispatch('flows/editor/flow_loaded', {
            flow: {
                flow_id: 'w3',
                name: 'W3',
                nodes: { main: { type: 'llm_node' } },
                edges: [],
                entry: 'main',
                variables: {},
            },
            branchId: 'base',
        });
        bus.dispatch('flows/run/flow_started', { context_id: 'ctx-3' });
        bus.dispatch('flows/run/a2a_mapped', {
            context_id: 'ctx-3',
            runEvents: [{ type: 'flows/run/node_started', payload: { node_id: 'main' } }],
            traceEntries: [{
                id: 't1:node_start:main:0',
                kind: 'node_start',
                node_id: 'main',
                context_id: 'ctx-3',
                task_id: 't1',
            }],
            terminal: false,
            nextTaskId: 't1',
            taskPrimed: true,
        });
        let s = getState().flowsEditor;
        expect(s.runningNodeIds).toEqual(['main']);
        expect(s.startWireRunState).toBe('running');
        expect(s.runTrace).toHaveLength(1);
        expect(dig(s, 'runTrace', '0', 'kind')).toBe('node_start');
        expect(dig(s, 'runSession', 'taskId')).toBe('t1');
        expect(dig(s, 'runSession', 'taskPrimed')).toBe(true);
        expect(s.agentExecutionRunning).toBe(true);

        bus.dispatch('flows/run/a2a_mapped', {
            context_id: 'ctx-3',
            runEvents: [{
                type: 'flows/run/node_failed',
                payload: { node_id: 'main', error: 'empty response' },
            }],
            traceEntries: [{
                id: 't1:node_error:main:1',
                kind: 'node_error',
                node_id: 'main',
                error: 'empty response',
                context_id: 'ctx-3',
                task_id: 't1',
            }],
            terminal: false,
            nextTaskId: 't1',
            taskPrimed: true,
        });
        bus.dispatch('flows/run/a2a_mapped', {
            context_id: 'ctx-3',
            runEvents: [],
            traceEntries: [{
                id: 't1:status_terminal:2',
                kind: 'status_terminal',
                terminal_state: 'failed',
                context_id: 'ctx-3',
                task_id: 't1',
            }],
            terminal: true,
            nextTaskId: 't1',
            taskPrimed: true,
        });
        s = getState().flowsEditor;
        expect(s.agentExecutionRunning).toBe(false);
        expect(dig(s, 'erroredNodes', 'main')).toBe('empty response');
        expect(s.runTrace?.map((entry: unknown) => prop(entry, 'kind'))).toEqual([
            'node_start',
            'node_error',
            'status_terminal',
        ]);
    });

    it('flows/run/session_cleared сбрасывает run visualization', () => {
        const { bus, getState } = build();
        bus.dispatch('flows/run/flow_started', { context_id: 'ctx-4' });
        bus.dispatch('flows/run/node_started', { node_id: 'main' });
        bus.dispatch('flows/run/session_cleared', {});
        const s = getState().flowsEditor;
        expect(s.agentExecutionRunning).toBe(false);
        expect(s.runningNodeIds).toEqual([]);
        expect(s.runTrace).toEqual([]);
        expect(s.runSession).toEqual({ contextId: null, taskId: null, taskPrimed: false });
        expect(s.startWireRunState).toBeNull();
    });

    it('flows/run/edge_executed и node_started обновляют runningEdgeIndices / completedEdgeIndices', () => {
        const { bus, getState } = build();
        bus.dispatch('flows/editor/flow_loaded', {
            flow: {
                flow_id: 'e1',
                name: 'E',
                nodes: { a: { type: 'code' }, b: { type: 'code' } },
                edges: [{ from_node: 'a', to_node: 'b' }],
                variables: {},
            },
            branchId: 'base',
        });
        bus.dispatch('flows/run/flow_started', { task_id: 't1' });
        bus.dispatch('flows/run/edge_executed', { edge_index: 0, from_node: 'a', to_node: 'b' });
        let s = getState().flowsEditor;
        expect(s.runningEdgeIndices).toEqual([0]);
        expect(s.completedEdgeIndices).toEqual([]);

        bus.dispatch('flows/run/node_started', { node_id: 'b', task_id: 't1' });
        s = getState().flowsEditor;
        expect(s.runningEdgeIndices).toEqual([]);
        expect(s.completedEdgeIndices).toEqual([0]);
    });

    it('flows/run/edge_error помечает ребро в failedEdgeIndices', () => {
        const { bus, getState } = build();
        bus.dispatch('flows/editor/flow_loaded', {
            flow: {
                flow_id: 'e2',
                name: 'E2',
                nodes: { a: { type: 'code' }, b: { type: 'code' } },
                edges: [{ from_node: 'a', to_node: 'b' }],
                variables: {},
            },
            branchId: 'base',
        });
        bus.dispatch('flows/run/flow_started', { task_id: 't1' });
        bus.dispatch('flows/run/edge_error', {
            edge_index: 0,
            from_node: 'a',
            to_node: 'b',
            error: 'division by zero',
        });
        const s = getState().flowsEditor;
        expect(s.failedEdgeIndices).toEqual([0]);
        expect(s.runningEdgeIndices).toEqual([]);
        expect(s.completedEdgeIndices).toEqual([]);
    });

    it('flows/breakpoint/hit и breakpoint_toggled', () => {
        const { bus, getState } = build();
        bus.dispatch('flows/editor/breakpoint_toggled', { nodeId: 'a' });
        let s = getState().flowsEditor;
        expect(s.breakpointNodeIds).toEqual(['a']);

        bus.dispatch('flows/editor/breakpoint_toggled', { nodeId: 'b' });
        bus.dispatch('flows/editor/breakpoint_toggled', { nodeId: 'a' });
        s = getState().flowsEditor;
        expect(s.breakpointNodeIds).toEqual(['b']);

        bus.dispatch('flows/breakpoint/hit', { node_id: 'b', task_id: 't1' });
        expect(getState().flowsEditor.breakpointHitNodeId).toBe('b');

        bus.dispatch('flows/breakpoint/clear', {});
        expect(getState().flowsEditor.breakpointHitNodeId).toBe(null);
    });

    it('multi_selection_changed синхронизирует selectedNodeId', () => {
        const { bus, getState } = build();
        bus.dispatch('flows/editor/multi_selection_changed', { nodeIds: ['a'] });
        let s = getState().flowsEditor;
        expect(s.multiSelection).toEqual(['a']);
        expect(s.selectedNodeId).toBe('a');
        expect(s.panelOpen).toBe(true);

        bus.dispatch('flows/editor/multi_selection_changed', { nodeIds: ['a', 'b'] });
        s = getState().flowsEditor;
        expect(s.multiSelection).toEqual(['a', 'b']);
        expect(s.selectedNodeId).toBeNull();
        expect(s.panelOpen).toBe(false);
    });

    it('viewbox_changed обновляет viewBox', () => {
        const { bus, getState } = build();
        bus.dispatch('flows/editor/viewbox_changed', { viewBox: { x: 10, y: 20, w: 800, h: 600 } });
        const s = getState().flowsEditor;
        expect(s.viewBox).toEqual({ x: 10, y: 20, w: 800, h: 600 });
    });

    it('smart_guides_updated и smart_guides_toggled', () => {
        const { bus, getState } = build();
        bus.dispatch('flows/editor/smart_guides_updated', { guides: [{ axis: 'v', at: 100 }] });
        expect(dig(getState().flowsEditor, 'smartGuides', 'length')).toBe(1);

        bus.dispatch('flows/editor/smart_guides_toggled', null);
        expect(getState().flowsEditor.smartGuidesEnabled).toBe(false);
    });

    it('sticky_note_added/updated/removed', () => {
        const { bus, getState } = build();
        bus.dispatch('flows/editor/sticky_note_added', { note: { id: 's1', x: 0, y: 0, width: 200, height: 140, text: 'hello' } });
        expect(dig(getState().flowsEditor, 'stickyNotes', 'length')).toBe(1);

        bus.dispatch('flows/editor/sticky_note_updated', { note: { id: 's1', text: 'updated' } });
        expect(dig(getState().flowsEditor, 'stickyNotes', '0', 'text')).toBe('updated');

        bus.dispatch('flows/editor/sticky_note_removed', { id: 's1' });
        expect(dig(getState().flowsEditor, 'stickyNotes', 'length')).toBe(0);
    });

    it('context_menu_opened/closed', () => {
        const { bus, getState } = build();
        bus.dispatch('flows/editor/context_menu_opened', { menu: { x: 100, y: 200, target: 'node', targetId: 'a' } });
        expect(getState().flowsEditor.contextMenu).toEqual({ x: 100, y: 200, target: 'node', targetId: 'a' });

        bus.dispatch('flows/editor/context_menu_closed', null);
        expect(getState().flowsEditor.contextMenu).toBeNull();
    });

    it('node_deleted удаляет ноду + edges + чистит selection/breakpoints', () => {
        const { bus, getState } = build();
        bus.dispatch('flows/editor/flow_loaded', {
            flow: {
                flow_id: 'demo', name: 'Demo',
                nodes: { a: { type: 'code' }, b: { type: 'code' } },
                edges: [
                    { from_node: 'a', to_node: 'b' },
                    { from_node: 'b', to_node: 'a' },
                ],
                entry: 'a',
            },
            branchId: 'base',
        });
        bus.dispatch('flows/editor/node_selected', { nodeId: 'a' });
        bus.dispatch('flows/editor/breakpoint_toggled', { nodeId: 'a' });
        bus.dispatch('flows/run/node_started', { node_id: 'a', task_id: 't1' });
        bus.dispatch('flows/run/node_failed', { node_id: 'a', task_id: 't1', error: 'x' });
        bus.dispatch('flows/editor/node_deleted', { nodeId: 'a' });
        const s = getState().flowsEditor;
        expect(digOr(s, 'branchData', 'nodes', 'a')).toBeUndefined();
        expect(dig(s, 'branchData', 'nodes', 'b')).toBeDefined();
        expect(dig(s, 'branchData', 'edges')).toEqual([]);
        expect(dig(s, 'branchData', 'entry')).toBeNull();
        expect(s.entryNodeId).toBeNull();
        expect(s.selectedNodeId).toBeNull();
        expect(s.panelOpen).toBe(false);
        expect(s.breakpointNodeIds).toEqual([]);
        expect(s.runningNodeIds).toEqual([]);
        expect(s.erroredNodes).toEqual({});
        expect(s.isDirty).toBe(true);
    });

    it('flow_loaded подхватывает sticky_notes из flow.config.metadata', () => {
        const { bus, getState } = build();
        bus.dispatch('flows/editor/flow_loaded', {
            flow: {
                flow_id: 'demo',
                name: 'Demo',
                nodes: { a: { type: 'code' } },
                edges: [],
                entry: 'a',
                metadata: { sticky_notes: [{ id: 'n1', x: 10, y: 10, width: 100, height: 80, text: 'hi' }] },
            },
            branchId: 'base',
        });
        const s = getState().flowsEditor;
        expect(s.stickyNotes).toEqual([{ id: 'n1', x: 10, y: 10, width: 100, height: 80, text: 'hi' }]);
        expect(s.entryNodeId).toBe('a');
    });

    it('data_wires_toggled переключает showDataWires', () => {
        const { bus, getState } = build();
        expect(getState().flowsEditor.showDataWires).toBe(false);
        bus.dispatch('flows/editor/data_wires_toggled', {});
        expect(getState().flowsEditor.showDataWires).toBe(true);
        bus.dispatch('flows/editor/data_wires_toggled', {});
        expect(getState().flowsEditor.showDataWires).toBe(false);
    });

    it('dataflow_set принимает payload dataflow', () => {
        const { bus, getState } = build();
        bus.dispatch('flows/editor/dataflow_set', { dataflow: { nodes: { a: { issues: [] } } } });
        expect(dig(getState().flowsEditor, 'dataflow', 'nodes', 'a', 'issues')).toEqual([]);
    });

    it('workspace_set run открывает execution panel', () => {
        const { bus, getState } = build();
        expect(getState().flowsEditor.workspace).toBe('logic');
        expect(getState().flowsEditor.executionPanelOpen).toBe(false);
        bus.dispatch('flows/editor/workspace_set', { workspace: 'run' });
        const runState = getState().flowsEditor;
        expect(runState.workspace).toBe('run');
        expect(runState.executionPanelOpen).toBe(true);
        bus.dispatch('flows/editor/workspace_set', { workspace: 'logic' });
        const logicState = getState().flowsEditor;
        expect(logicState.workspace).toBe('logic');
        expect(logicState.executionPanelOpen).toBe(true);
    });
});
