/**
 * Flow editor UI-state — выбор ноды/ресурса, состояние панелей, undo/redo,
 * preview executionState, dirty/saving флаги.
 *
 * Это чисто UI-фабрика: нет HTTP, есть только actions и extraReducer.
 * `silent: true` обязательно — фабрика не делает запросов и тостов.
 */

import { createAsyncOp } from '@platform/lib/events/index.js';

const HISTORY_LIMIT = 50;

export const editorResource = createAsyncOp({
    name: 'flows/editor',
    silent: true,
    transport: 'http',
    request: async () => {
        throw new Error('flows/editor — UI-only фабрика; .run() не вызывается');
    },
    extraInitial: {
        flowId: null,
        flowConfig: null,
        skillsData: { nodes: {}, edges: [], entry: null, variables: {}, resources: {} },
        currentSkillId: null,
        selectedNodeId: null,
        selectedResourceId: null,
        panelOpen: false,
        panelExpanded: false,
        executionPanelOpen: false,
        agentExecutionRunning: false,
        variablesPanelOpen: false,
        activeTool: 'select',
        previewExecutionState: null,
        mode: 'edit',
        isDirty: false,
        isSaving: false,
        publishedAt: null,
        historyStack: [],
        historyPosition: -1,
        canUndo: false,
        canRedo: false,
    },
    extraEvents: {
        FLOW_LOADED: 'flow_loaded',
        SKILL_SET: 'skill_set',
        SKILLS_DATA_UPDATED: 'skills_data_updated',
        NODE_SELECTED: 'node_selected',
        RESOURCE_SELECTED: 'resource_selected',
        PANEL_CLOSED: 'panel_closed',
        PANEL_EXPANDED: 'panel_expanded',
        EXECUTION_PANEL_SET: 'execution_panel_set',
        VARIABLES_PANEL_TOGGLED: 'variables_panel_toggled',
        AGENT_EXECUTION_SET: 'agent_execution_set',
        ACTIVE_TOOL_SET: 'active_tool_set',
        MODE_SET: 'mode_set',
        NAME_SET: 'name_set',
        PUBLISHED_AT_SET: 'published_at_set',
        DIRTY_SET: 'dirty_set',
        SAVING_SET: 'saving_set',
        PREVIEW_STATE_SET: 'preview_state_set',
        HISTORY_PUSHED: 'history_pushed',
        HISTORY_UNDONE: 'history_undone',
        HISTORY_REDONE: 'history_redone',
        HISTORY_CLEARED: 'history_cleared',
    },
    actions: {
        setFlow: 'flow_loaded',
        setSkill: 'skill_set',
        updateSkillsData: 'skills_data_updated',
        selectNode: 'node_selected',
        selectResource: 'resource_selected',
        closePanel: 'panel_closed',
        togglePanelExpanded: 'panel_expanded',
        setExecutionPanelOpen: 'execution_panel_set',
        toggleVariablesPanel: 'variables_panel_toggled',
        setAgentExecutionRunning: 'agent_execution_set',
        setActiveTool: 'active_tool_set',
        setMode: 'mode_set',
        setName: 'name_set',
        setPublishedAt: 'published_at_set',
        setDirty: 'dirty_set',
        setSaving: 'saving_set',
        setPreviewExecutionState: 'preview_state_set',
        pushHistory: 'history_pushed',
        undo: 'history_undone',
        redo: 'history_redone',
        clearHistory: 'history_cleared',
    },
    extraReducer: (state, event) => {
        const t = event.type;
        const p = event.payload || {};

        if (t === 'flows/editor/flow_loaded') {
            const flow = p.flow;
            if (!flow || typeof flow !== 'object') return state;
            const skillsData = {
                nodes: flow.nodes || {},
                edges: flow.edges || [],
                entry: flow.entry || null,
                variables: flow.variables || {},
                resources: flow.resources || {},
            };
            return {
                ...state,
                flowId: typeof flow.flow_id === 'string' ? flow.flow_id : state.flowId,
                flowConfig: flow,
                skillsData,
                currentSkillId: typeof p.skillId === 'string' ? p.skillId : null,
                previewExecutionState: p.previewExecutionState || null,
                agentExecutionRunning: false,
                isDirty: false,
                historyStack: [],
                historyPosition: -1,
                canUndo: false,
                canRedo: false,
            };
        }

        if (t === 'flows/editor/skill_set') {
            return { ...state, currentSkillId: typeof p.skillId === 'string' ? p.skillId : null };
        }

        if (t === 'flows/editor/skills_data_updated') {
            const data = p.data;
            if (!data || typeof data !== 'object') return state;
            return { ...state, skillsData: data };
        }

        if (t === 'flows/editor/node_selected') {
            const nodeId = typeof p.nodeId === 'string' && p.nodeId.length > 0 ? p.nodeId : null;
            return {
                ...state,
                selectedNodeId: nodeId,
                selectedResourceId: null,
                panelOpen: nodeId !== null,
            };
        }

        if (t === 'flows/editor/resource_selected') {
            const rid = typeof p.resourceId === 'string' && p.resourceId.length > 0 ? p.resourceId : null;
            return {
                ...state,
                selectedResourceId: rid,
                selectedNodeId: null,
                panelOpen: rid !== null,
            };
        }

        if (t === 'flows/editor/panel_closed') {
            return { ...state, panelOpen: false, selectedNodeId: null, selectedResourceId: null };
        }

        if (t === 'flows/editor/panel_expanded') {
            return { ...state, panelExpanded: !state.panelExpanded };
        }

        if (t === 'flows/editor/execution_panel_set') {
            return { ...state, executionPanelOpen: Boolean(p.open) };
        }

        if (t === 'flows/editor/variables_panel_toggled') {
            return { ...state, variablesPanelOpen: !state.variablesPanelOpen };
        }

        if (t === 'flows/editor/agent_execution_set') {
            return { ...state, agentExecutionRunning: Boolean(p.running) };
        }

        if (t === 'flows/editor/active_tool_set') {
            return { ...state, activeTool: typeof p.tool === 'string' ? p.tool : 'select' };
        }

        if (t === 'flows/editor/mode_set') {
            const mode = p.mode === 'run' ? 'run' : 'edit';
            return { ...state, mode };
        }

        if (t === 'flows/editor/name_set') {
            const name = typeof p.name === 'string' ? p.name : '';
            if (!state.flowConfig) return state;
            return {
                ...state,
                flowConfig: { ...state.flowConfig, name },
                isDirty: true,
            };
        }

        if (t === 'flows/editor/published_at_set') {
            const publishedAt = typeof p.publishedAt === 'string' ? p.publishedAt : null;
            return { ...state, publishedAt };
        }

        if (t === 'flows/editor/dirty_set') {
            return { ...state, isDirty: Boolean(p.dirty) };
        }

        if (t === 'flows/editor/saving_set') {
            return { ...state, isSaving: Boolean(p.saving) };
        }

        // Реакция на успешный publish — отметить publishedAt и снять dirty.
        if (t === 'flows/flow_update/succeeded') {
            return {
                ...state,
                isDirty: false,
                isSaving: false,
                publishedAt: new Date().toISOString(),
            };
        }

        if (t === 'flows/editor/preview_state_set') {
            return { ...state, previewExecutionState: p.snapshot || null };
        }

        if (t === 'flows/editor/history_pushed') {
            const snapshot = p.snapshot;
            if (!snapshot) return state;
            const stack = state.historyStack.slice(0, state.historyPosition + 1);
            stack.push(snapshot);
            while (stack.length > HISTORY_LIMIT) stack.shift();
            return {
                ...state,
                historyStack: stack,
                historyPosition: stack.length - 1,
                canUndo: stack.length > 0,
                canRedo: false,
            };
        }

        if (t === 'flows/editor/history_undone') {
            if (state.historyPosition < 0) return state;
            const newPos = state.historyPosition - 1;
            return {
                ...state,
                historyPosition: newPos,
                canUndo: newPos >= 0,
                canRedo: true,
            };
        }

        if (t === 'flows/editor/history_redone') {
            const max = state.historyStack.length - 1;
            if (state.historyPosition >= max) return state;
            const newPos = state.historyPosition + 1;
            return {
                ...state,
                historyPosition: newPos,
                canUndo: true,
                canRedo: newPos < max,
            };
        }

        if (t === 'flows/editor/history_cleared') {
            return {
                ...state,
                historyStack: [],
                historyPosition: -1,
                canUndo: false,
                canRedo: false,
            };
        }

        return state;
    },
});
