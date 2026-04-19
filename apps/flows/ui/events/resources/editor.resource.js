/**
 * Flow editor — единый slice состояния редактора.
 *
 * Содержит:
 *   - доменное состояние flow и skills (`skillsData`);
 *   - выбор ноды/ресурса/skill и состояние панелей;
 *   - undo/redo стэк;
 *   - execution state каждой ноды (`runningNodeIds`, `completedNodeIds`,
 *     `erroredNodes`) — обновляется push-событиями `flows/run/*`;
 *   - breakpoints (`breakpointNodeIds`);
 *   - локальный canvas-state (`viewBox`, `panTool`, `multiSelection`,
 *     `smartGuides`, `contextMenu`, `stickyNotes`).
 *
 * `silent: true` — UI-only фабрика, .run() запрещён.
 */

import { createAsyncOp } from '@platform/lib/events/index.js';
import { httpRequest } from '@platform/lib/events/http.js';

const HISTORY_LIMIT = 50;
const DEFAULT_VIEWBOX = Object.freeze({ x: 0, y: 0, w: 1600, h: 1000 });

function _withoutId(list, id) {
    return list.filter((existing) => existing !== id);
}

function _withId(list, id) {
    if (list.includes(id)) return list;
    return [...list, id];
}

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
        runningNodeIds: [],
        completedNodeIds: [],
        erroredNodes: {},
        breakpointNodeIds: [],
        breakpointHitNodeId: null,
        entryNodeId: null,
        inheritedNodeIds: [],
        multiSelection: [],
        viewBox: { ...DEFAULT_VIEWBOX },
        smartGuides: [],
        smartGuidesEnabled: true,
        contextMenu: null,
        stickyNotes: [],
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
        VIEWBOX_CHANGED: 'viewbox_changed',
        TOOL_CHANGED: 'tool_changed',
        MULTI_SELECTION_CHANGED: 'multi_selection_changed',
        SMART_GUIDES_UPDATED: 'smart_guides_updated',
        SMART_GUIDES_TOGGLED: 'smart_guides_toggled',
        CONTEXT_MENU_OPENED: 'context_menu_opened',
        CONTEXT_MENU_CLOSED: 'context_menu_closed',
        STICKY_NOTE_ADDED: 'sticky_note_added',
        STICKY_NOTE_UPDATED: 'sticky_note_updated',
        STICKY_NOTE_REMOVED: 'sticky_note_removed',
        BREAKPOINT_TOGGLED: 'breakpoint_toggled',
        NODE_ID_CHANGED: 'node_id_changed',
        NODE_DELETED: 'node_deleted',
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
        setViewBox: 'viewbox_changed',
        changeTool: 'tool_changed',
        setMultiSelection: 'multi_selection_changed',
        setSmartGuides: 'smart_guides_updated',
        toggleSmartGuides: 'smart_guides_toggled',
        openContextMenu: 'context_menu_opened',
        closeContextMenu: 'context_menu_closed',
        addStickyNote: 'sticky_note_added',
        updateStickyNote: 'sticky_note_updated',
        removeStickyNote: 'sticky_note_removed',
        toggleBreakpoint: 'breakpoint_toggled',
        renameNodeId: 'node_id_changed',
        removeNode: 'node_deleted',
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
            const meta = (flow.config && flow.config.metadata) || flow.metadata || {};
            const stickyNotes = Array.isArray(meta.sticky_notes) ? meta.sticky_notes : [];
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
                runningNodeIds: [],
                completedNodeIds: [],
                erroredNodes: {},
                breakpointHitNodeId: null,
                entryNodeId: typeof flow.entry === 'string' ? flow.entry : null,
                multiSelection: [],
                stickyNotes,
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
                multiSelection: nodeId ? [nodeId] : [],
            };
        }

        if (t === 'flows/editor/resource_selected') {
            const rid = typeof p.resourceId === 'string' && p.resourceId.length > 0 ? p.resourceId : null;
            return {
                ...state,
                selectedResourceId: rid,
                selectedNodeId: null,
                panelOpen: rid !== null,
                multiSelection: [],
            };
        }

        if (t === 'flows/editor/panel_closed') {
            return { ...state, panelOpen: false, selectedNodeId: null, selectedResourceId: null, multiSelection: [] };
        }

        if (t === 'flows/editor/panel_expanded') {
            if (typeof p.expanded === 'boolean') {
                return { ...state, panelExpanded: p.expanded };
            }
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

        if (t === 'flows/editor/viewbox_changed') {
            const v = p.viewBox;
            if (!v || typeof v !== 'object') return state;
            return { ...state, viewBox: { x: v.x, y: v.y, w: v.w, h: v.h } };
        }

        if (t === 'flows/editor/tool_changed') {
            return { ...state, activeTool: typeof p.tool === 'string' ? p.tool : 'select' };
        }

        if (t === 'flows/editor/multi_selection_changed') {
            const ids = Array.isArray(p.nodeIds) ? p.nodeIds : [];
            return {
                ...state,
                multiSelection: ids,
                selectedNodeId: ids.length === 1 ? ids[0] : (ids.length > 1 ? null : state.selectedNodeId),
                panelOpen: ids.length === 1,
            };
        }

        if (t === 'flows/editor/smart_guides_updated') {
            const guides = Array.isArray(p.guides) ? p.guides : [];
            return { ...state, smartGuides: guides };
        }

        if (t === 'flows/editor/smart_guides_toggled') {
            return { ...state, smartGuidesEnabled: !state.smartGuidesEnabled };
        }

        if (t === 'flows/editor/context_menu_opened') {
            const menu = p.menu;
            if (!menu || typeof menu !== 'object') return state;
            return { ...state, contextMenu: { x: menu.x, y: menu.y, target: menu.target, targetId: menu.targetId || null } };
        }

        if (t === 'flows/editor/context_menu_closed') {
            return { ...state, contextMenu: null };
        }

        if (t === 'flows/editor/breakpoint_toggled') {
            const nodeId = p.nodeId;
            if (typeof nodeId !== 'string' || nodeId.length === 0) return state;
            const exists = state.breakpointNodeIds.includes(nodeId);
            return {
                ...state,
                breakpointNodeIds: exists ? _withoutId(state.breakpointNodeIds, nodeId) : _withId(state.breakpointNodeIds, nodeId),
            };
        }

        if (t === 'flows/editor/sticky_note_added') {
            const note = p.note;
            if (!note || typeof note !== 'object' || typeof note.id !== 'string') return state;
            return { ...state, stickyNotes: [...state.stickyNotes, note] };
        }

        if (t === 'flows/editor/sticky_note_updated') {
            const note = p.note;
            if (!note || typeof note !== 'object' || typeof note.id !== 'string') return state;
            return {
                ...state,
                stickyNotes: state.stickyNotes.map((n) => (n.id === note.id ? { ...n, ...note } : n)),
            };
        }

        if (t === 'flows/editor/sticky_note_removed') {
            const id = p.id;
            if (typeof id !== 'string') return state;
            return { ...state, stickyNotes: state.stickyNotes.filter((n) => n.id !== id) };
        }

        if (t === 'flows/run/flow_started') {
            return {
                ...state,
                runningNodeIds: [],
                completedNodeIds: [],
                erroredNodes: {},
                breakpointHitNodeId: null,
                agentExecutionRunning: true,
            };
        }

        if (t === 'flows/run/flow_done') {
            return { ...state, agentExecutionRunning: false };
        }

        if (t === 'flows/run/node_started') {
            const nodeId = p.node_id;
            if (typeof nodeId !== 'string' || nodeId.length === 0) return state;
            const erroredCopy = { ...state.erroredNodes };
            delete erroredCopy[nodeId];
            return {
                ...state,
                runningNodeIds: _withId(state.runningNodeIds, nodeId),
                completedNodeIds: _withoutId(state.completedNodeIds, nodeId),
                erroredNodes: erroredCopy,
            };
        }

        if (t === 'flows/run/node_completed') {
            const nodeId = p.node_id;
            if (typeof nodeId !== 'string' || nodeId.length === 0) return state;
            return {
                ...state,
                runningNodeIds: _withoutId(state.runningNodeIds, nodeId),
                completedNodeIds: _withId(state.completedNodeIds, nodeId),
            };
        }

        if (t === 'flows/run/node_failed') {
            const nodeId = p.node_id;
            if (typeof nodeId !== 'string' || nodeId.length === 0) return state;
            const erroredCopy = { ...state.erroredNodes, [nodeId]: typeof p.error === 'string' ? p.error : '' };
            return {
                ...state,
                runningNodeIds: _withoutId(state.runningNodeIds, nodeId),
                erroredNodes: erroredCopy,
            };
        }

        if (t === 'flows/breakpoint/hit') {
            const nodeId = p.node_id;
            if (typeof nodeId !== 'string' || nodeId.length === 0) return state;
            return { ...state, breakpointHitNodeId: nodeId };
        }

        if (t === 'flows/editor/node_id_changed') {
            const oldId = p.oldId;
            const newId = p.newId;
            if (typeof oldId !== 'string' || oldId.length === 0) return state;
            if (typeof newId !== 'string' || newId.length === 0) return state;
            if (oldId === newId) return state;
            const data = state.skillsData;
            if (!data || typeof data !== 'object') return state;
            const nodes = data.nodes && typeof data.nodes === 'object' ? data.nodes : {};
            if (!(oldId in nodes)) return state;
            if (newId in nodes) return state;
            const nextNodes = {};
            for (const [id, node] of Object.entries(nodes)) {
                const targetId = id === oldId ? newId : id;
                const nodeCopy = node && typeof node === 'object' ? { ...node, node_id: targetId } : node;
                nextNodes[targetId] = nodeCopy;
            }
            const edges = Array.isArray(data.edges) ? data.edges : [];
            const nextEdges = edges.map((edge) => {
                if (!edge || typeof edge !== 'object') return edge;
                const fromNode = edge.from_node === oldId ? newId : edge.from_node;
                const toNode = edge.to_node === oldId ? newId : edge.to_node;
                if (fromNode === edge.from_node && toNode === edge.to_node) return edge;
                return { ...edge, from_node: fromNode, to_node: toNode };
            });
            const entry = data.entry === oldId ? newId : data.entry;
            return {
                ...state,
                skillsData: { ...data, nodes: nextNodes, edges: nextEdges, entry },
                selectedNodeId: state.selectedNodeId === oldId ? newId : state.selectedNodeId,
                multiSelection: state.multiSelection.map((id) => (id === oldId ? newId : id)),
                entryNodeId: state.entryNodeId === oldId ? newId : state.entryNodeId,
                breakpointNodeIds: state.breakpointNodeIds.map((id) => (id === oldId ? newId : id)),
                runningNodeIds: state.runningNodeIds.map((id) => (id === oldId ? newId : id)),
                completedNodeIds: state.completedNodeIds.map((id) => (id === oldId ? newId : id)),
                isDirty: true,
            };
        }

        if (t === 'flows/editor/node_deleted') {
            const nodeId = p.nodeId;
            if (typeof nodeId !== 'string' || nodeId.length === 0) return state;
            const data = state.skillsData;
            if (!data || typeof data !== 'object') return state;
            const nodes = data.nodes && typeof data.nodes === 'object' ? data.nodes : {};
            if (!(nodeId in nodes)) return state;
            const nextNodes = {};
            for (const [id, node] of Object.entries(nodes)) {
                if (id !== nodeId) nextNodes[id] = node;
            }
            const edges = Array.isArray(data.edges) ? data.edges : [];
            const nextEdges = edges.filter((edge) => edge && edge.from_node !== nodeId && edge.to_node !== nodeId);
            const erroredCopy = { ...state.erroredNodes };
            delete erroredCopy[nodeId];
            return {
                ...state,
                skillsData: { ...data, nodes: nextNodes, edges: nextEdges, entry: data.entry === nodeId ? null : data.entry },
                selectedNodeId: state.selectedNodeId === nodeId ? null : state.selectedNodeId,
                panelOpen: state.selectedNodeId === nodeId ? false : state.panelOpen,
                multiSelection: state.multiSelection.filter((id) => id !== nodeId),
                breakpointNodeIds: _withoutId(state.breakpointNodeIds, nodeId),
                runningNodeIds: _withoutId(state.runningNodeIds, nodeId),
                completedNodeIds: _withoutId(state.completedNodeIds, nodeId),
                erroredNodes: erroredCopy,
                entryNodeId: state.entryNodeId === nodeId ? null : state.entryNodeId,
                isDirty: true,
            };
        }

        return state;
    },
});

/**
 * Bulk delete нод и связанных рёбер.
 *
 * REST-зеркало: POST /flows/api/v1/flows/{flow_id}/nodes/bulk_delete
 * Транспорт http; success триггерит reducer для очистки multiSelection и
 * перезагружает flow через `flows/flows`.
 */
export const editorBulkDeleteOp = createAsyncOp({
    name: 'flows/editor_bulk_delete',
    transport: 'http',
    successToastKey: 'flows:canvas.toast.bulk_delete_success',
    errorToastKey: 'flows:canvas.toast.bulk_delete_error',
    restMirror: { method: 'POST', path: '/flows/api/v1/flows/{flow_id}/nodes/bulk_delete' },
    request: async ({ payload }) => {
        const flowId = payload.flow_id;
        const nodeIds = payload.node_ids;
        if (typeof flowId !== 'string' || flowId.length === 0) {
            throw new Error('flow_id is required');
        }
        if (!Array.isArray(nodeIds) || nodeIds.length === 0) {
            throw new Error('node_ids is required');
        }
        return await httpRequest({
            method: 'POST',
            url: `/flows/api/v1/flows/${encodeURIComponent(flowId)}/nodes/bulk_delete`,
            body: { node_ids: nodeIds },
        });
    },
});

/**
 * Persist sticky notes — PATCH metadata flow.config.metadata.sticky_notes.
 */
export const stickyNoteUpsertOp = createAsyncOp({
    name: 'flows/sticky_note_upsert',
    transport: 'http',
    silent: true,
    restMirror: { method: 'PATCH', path: '/flows/api/v1/flows/{flow_id}/metadata' },
    request: async ({ payload }) => {
        const flowId = payload.flow_id;
        const stickyNotes = payload.sticky_notes;
        if (typeof flowId !== 'string' || flowId.length === 0) {
            throw new Error('flow_id is required');
        }
        if (!Array.isArray(stickyNotes)) {
            throw new Error('sticky_notes is required');
        }
        return await httpRequest({
            method: 'PATCH',
            url: `/flows/api/v1/flows/${encodeURIComponent(flowId)}/metadata`,
            body: { sticky_notes: stickyNotes },
        });
    },
});
