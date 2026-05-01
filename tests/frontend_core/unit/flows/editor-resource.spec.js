/**
 * flows/editor — UI-only фабрика состояния редактора.
 *
 * extraReducer: flow_loaded / node_selected / panel_closed / panel_expanded /
 * execution_panel_set / agent_execution_set /
 * active_tool_set / dirty_set / saving_set / preview_state_set /
 * history_pushed / history_undone / history_redone / history_cleared.
 */

import { describe, it, expect, beforeEach, afterEach } from 'vitest';
import { collectFactories } from '@platform/lib/events/factories/register.js';
import { editorResource } from '../../../../apps/flows/ui/events/resources/editor.resource.js';
import { resetFactories } from '../../helpers/factory-fixtures.js';
import { buildBus } from '../../helpers/bus-fixtures.js';
import { registerFactory } from '@platform/lib/events/factory-registry.js';

beforeEach(() => resetFactories());
afterEach(() => resetFactories());

function build() {
    registerFactory(editorResource);
    const collected = collectFactories([editorResource]);
    return buildBus({ slices: collected.slices });
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
        expect(s.flowConfig.name).toBe('Demo');
        expect(s.branchData.nodes.a.type).toBe('code');
        expect(s.isDirty).toBe(false);
        expect(s.historyStack).toEqual([]);
    });

    it('flow_loaded: авто-раскладка нод 0,0 (>=2) ставит isDirty', () => {
        const { bus, getState } = build();
        bus.dispatch('flows/editor/flow_loaded', {
            flow: {
                flow_id: 'lay',
                name: 'Lay',
                nodes: { a: { type: 'code' }, b: { type: 'code' } },
                edges: [{ from: 'a', to: 'b' }],
                entry: 'a',
                variables: {},
            },
            branchId: 'base',
        });
        const s = getState().flowsEditor;
        expect(s.isDirty).toBe(true);
        expect(s.branchData.nodes.b.pos_x).toBeGreaterThan(0);
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
        expect(s.historyStack.length).toBe(2);
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

    it('panel_expanded toggles', () => {
        const { bus, getState } = build();
        expect(getState().flowsEditor.panelExpanded).toBe(false);
        bus.dispatch('flows/editor/panel_expanded', null);
        expect(getState().flowsEditor.panelExpanded).toBe(true);
        bus.dispatch('flows/editor/panel_expanded', null);
        expect(getState().flowsEditor.panelExpanded).toBe(false);
    });

    it('panel_expanded принимает явный expanded', () => {
        const { bus, getState } = build();
        bus.dispatch('flows/editor/panel_expanded', { expanded: true });
        expect(getState().flowsEditor.panelExpanded).toBe(true);
        bus.dispatch('flows/editor/panel_expanded', { expanded: false });
        expect(getState().flowsEditor.panelExpanded).toBe(false);
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

    it('flows/run/edge_executed и node_started обновляют runningEdgeIndices / completedEdgeIndices', () => {
        const { bus, getState } = build();
        bus.dispatch('flows/editor/flow_loaded', {
            flow: {
                flow_id: 'e1',
                name: 'E',
                nodes: { a: { type: 'code' }, b: { type: 'code' } },
                edges: [{ from: 'a', to: 'b' }],
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
                edges: [{ from: 'a', to: 'b' }],
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
        expect(getState().flowsEditor.smartGuides.length).toBe(1);

        bus.dispatch('flows/editor/smart_guides_toggled', null);
        expect(getState().flowsEditor.smartGuidesEnabled).toBe(false);
    });

    it('sticky_note_added/updated/removed', () => {
        const { bus, getState } = build();
        bus.dispatch('flows/editor/sticky_note_added', { note: { id: 's1', x: 0, y: 0, width: 200, height: 140, text: 'hello' } });
        expect(getState().flowsEditor.stickyNotes.length).toBe(1);

        bus.dispatch('flows/editor/sticky_note_updated', { note: { id: 's1', text: 'updated' } });
        expect(getState().flowsEditor.stickyNotes[0].text).toBe('updated');

        bus.dispatch('flows/editor/sticky_note_removed', { id: 's1' });
        expect(getState().flowsEditor.stickyNotes.length).toBe(0);
    });

    it('context_menu_opened/closed', () => {
        const { bus, getState } = build();
        bus.dispatch('flows/editor/context_menu_opened', { menu: { x: 100, y: 200, target: 'node', targetId: 'a' } });
        expect(getState().flowsEditor.contextMenu).toEqual({ x: 100, y: 200, target: 'node', targetId: 'a' });

        bus.dispatch('flows/editor/context_menu_closed', null);
        expect(getState().flowsEditor.contextMenu).toBeNull();
    });

    it('node_id_changed переименовывает ноду + обновляет edges/entry/selection', () => {
        const { bus, getState } = build();
        bus.dispatch('flows/editor/flow_loaded', {
            flow: {
                flow_id: 'demo',
                name: 'Demo',
                nodes: { old: { type: 'code', name: 'A' }, b: { type: 'code', name: 'B' } },
                edges: [
                    { from_node: 'old', to_node: 'b' },
                    { from_node: 'b', to_node: 'old' },
                ],
                entry: 'old',
            },
            branchId: 'base',
        });
        bus.dispatch('flows/editor/node_selected', { nodeId: 'old' });
        bus.dispatch('flows/editor/breakpoint_toggled', { nodeId: 'old' });
        bus.dispatch('flows/editor/node_id_changed', { oldId: 'old', newId: 'fresh' });
        const s = getState().flowsEditor;
        expect(s.branchData.nodes.fresh).toBeDefined();
        expect(s.branchData.nodes.fresh.node_id).toBe('fresh');
        expect(s.branchData.nodes.old).toBeUndefined();
        expect(s.branchData.edges).toEqual([
            { from_node: 'fresh', to_node: 'b' },
            { from_node: 'b', to_node: 'fresh' },
        ]);
        expect(s.branchData.entry).toBe('fresh');
        expect(s.entryNodeId).toBe('fresh');
        expect(s.selectedNodeId).toBe('fresh');
        expect(s.multiSelection).toEqual(['fresh']);
        expect(s.breakpointNodeIds).toEqual(['fresh']);
        expect(s.isDirty).toBe(true);
    });

    it('node_id_changed игнорирует коллизию имён', () => {
        const { bus, getState } = build();
        bus.dispatch('flows/editor/flow_loaded', {
            flow: {
                flow_id: 'demo', name: 'Demo',
                nodes: { a: { type: 'code' }, b: { type: 'code' } },
                edges: [],
            },
            branchId: 'base',
        });
        bus.dispatch('flows/editor/node_id_changed', { oldId: 'a', newId: 'b' });
        const s = getState().flowsEditor;
        expect(s.branchData.nodes.a).toBeDefined();
        expect(s.branchData.nodes.b).toBeDefined();
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
        expect(s.branchData.nodes.a).toBeUndefined();
        expect(s.branchData.nodes.b).toBeDefined();
        expect(s.branchData.edges).toEqual([]);
        expect(s.branchData.entry).toBeNull();
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
});
