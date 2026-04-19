/**
 * flows/editor — UI-only фабрика состояния редактора.
 *
 * extraReducer: flow_loaded / node_selected / panel_closed / panel_expanded /
 * variables_panel_toggled / execution_panel_set / agent_execution_set /
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

    it('flow_loaded заполняет flowConfig и skillsData', () => {
        const { bus, getState } = build();
        bus.dispatch('flows/editor/flow_loaded', {
            flow: { flow_id: 'demo', name: 'Demo', nodes: { a: { type: 'code' } }, edges: [], variables: {} },
            skillId: 'base',
        });
        const s = getState().flowsEditor;
        expect(s.flowId).toBe('demo');
        expect(s.flowConfig.name).toBe('Demo');
        expect(s.skillsData.nodes.a.type).toBe('code');
        expect(s.isDirty).toBe(false);
        expect(s.historyStack).toEqual([]);
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

    it('dirty_set / saving_set', () => {
        const { bus, getState } = build();
        bus.dispatch('flows/editor/dirty_set', { dirty: true });
        bus.dispatch('flows/editor/saving_set', { saving: true });
        const s = getState().flowsEditor;
        expect(s.isDirty).toBe(true);
        expect(s.isSaving).toBe(true);
    });
});
