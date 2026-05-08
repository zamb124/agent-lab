/**
 * Flow editor — единый slice состояния редактора.
 *
 * Содержит:
 *   - доменное состояние flow и черновик ветки (`branchData`);
 *   - выбор ноды/ресурса/ветки и состояние панелей;
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
import { applyAutoLayoutToBranchData, canvasNeedsAutoLayout } from '../../_helpers/flow-graph-auto-layout.js';

const HISTORY_LIMIT = 50;
const DEFAULT_VIEWBOX = Object.freeze({ x: 0, y: 0, w: 1600, h: 1000 });

function _withoutId(list, id) {
    return list.filter((existing) => existing !== id);
}

function _withId(list, id) {
    if (list.includes(id)) return list;
    return [...list, id];
}

const _DEEP_MERGE_EXCLUDE = new Set(['node_id', 'tool_id', 'flow_id']);

function _isPlainObject(value) {
    return value !== null && typeof value === 'object' && !Array.isArray(value);
}

function _deepClone(value) {
    if (value === null || typeof value !== 'object') return value;
    if (Array.isArray(value)) return value.map(_deepClone);
    const out = {};
    for (const [k, v] of Object.entries(value)) out[k] = _deepClone(v);
    return out;
}

function _deepMerge(base, override) {
    if (!_isPlainObject(base)) return _deepClone(override);
    if (!_isPlainObject(override)) return _deepClone(base);
    const result = _deepClone(base);
    for (const [key, value] of Object.entries(override)) {
        if (_DEEP_MERGE_EXCLUDE.has(key)) continue;
        if (value === null || value === undefined) continue;
        if (_isPlainObject(result[key]) && _isPlainObject(value)) {
            result[key] = _deepMerge(result[key], value);
        } else {
            result[key] = _deepClone(value);
        }
    }
    return result;
}

function _resolveFlowMetadata(flow) {
    if (flow.config && typeof flow.config === 'object'
            && flow.config.metadata && typeof flow.config.metadata === 'object') {
        return flow.config.metadata;
    }
    if (flow.metadata && typeof flow.metadata === 'object') {
        return flow.metadata;
    }
    return {};
}

function _edgeNodeId(edge, primary, alt) {
    if (typeof edge[primary] === 'string' && edge[primary].length > 0) return edge[primary];
    if (typeof edge[alt] === 'string' && edge[alt].length > 0) return edge[alt];
    return '';
}

function _edgeKey(edge) {
    if (!edge || typeof edge !== 'object') return '';
    const from = _edgeNodeId(edge, 'from_node', 'from');
    const to = _edgeNodeId(edge, 'to_node', 'to');
    return `${from}->${to}`;
}

function _modeOf(branchCfgSlice, field, defaultMode) {
    if (!branchCfgSlice || typeof branchCfgSlice !== 'object') return defaultMode;
    const raw = branchCfgSlice[field];
    if (raw === 'merge' || raw === 'replace') return raw;
    return defaultMode;
}

function _buildEffectiveBranchData(flow, branchId) {
    const baseNodes = _isPlainObject(flow.nodes) ? flow.nodes : {};
    const baseEdges = Array.isArray(flow.edges) ? flow.edges : [];
    const baseVars = _isPlainObject(flow.variables) ? flow.variables : {};
    const baseEntry = typeof flow.entry === 'string' ? flow.entry : null;
    const resources = _isPlainObject(flow.resources) ? flow.resources : {};

    const isBase = !branchId || branchId === 'base';
    const branchCfg = !isBase && _isPlainObject(flow.branches) && _isPlainObject(flow.branches[branchId])
        ? flow.branches[branchId]
        : null;

    if (!branchCfg) {
        return {
            branchData: {
                nodes: _deepClone(baseNodes),
                edges: baseEdges.map(_deepClone),
                entry: baseEntry,
                variables: _deepClone(baseVars),
                resources: _deepClone(resources),
            },
            inheritedNodeIds: [],
            inheritedEdgeKeys: [],
            entryNodeId: baseEntry,
        };
    }

    const nodesMode = _modeOf(branchCfg, 'nodes_mode', 'replace');
    const edgesMode = _modeOf(branchCfg, 'edges_mode', 'replace');
    const variablesMode = _modeOf(branchCfg, 'variables_mode', 'merge');

    const cfgNodes = _isPlainObject(branchCfg.nodes) ? branchCfg.nodes : null;
    const cfgEdges = Array.isArray(branchCfg.edges) ? branchCfg.edges : null;
    const cfgVars = _isPlainObject(branchCfg.variables) ? branchCfg.variables : null;

    let effectiveNodes;
    let inheritedNodeIds;
    if (cfgNodes === null) {
        effectiveNodes = _deepClone(baseNodes);
        inheritedNodeIds = Object.keys(baseNodes);
    } else if (nodesMode === 'merge') {
        effectiveNodes = {};
        for (const [id, node] of Object.entries(baseNodes)) {
            effectiveNodes[id] = _isPlainObject(cfgNodes[id])
                ? _deepMerge(node, cfgNodes[id])
                : _deepClone(node);
        }
        for (const [id, node] of Object.entries(cfgNodes)) {
            if (!(id in effectiveNodes)) effectiveNodes[id] = _deepClone(node);
        }
        inheritedNodeIds = Object.keys(baseNodes).filter((id) => !(id in cfgNodes));
    } else {
        effectiveNodes = _deepClone(cfgNodes);
        inheritedNodeIds = [];
    }

    let effectiveEdges;
    let inheritedEdgeKeys;
    if (cfgEdges === null) {
        effectiveEdges = baseEdges.map(_deepClone);
        inheritedEdgeKeys = baseEdges.map(_edgeKey);
    } else if (edgesMode === 'merge') {
        const cfgEdgePairs = new Set(cfgEdges.map(_edgeKey));
        const inheritedBase = baseEdges.filter((e) => !cfgEdgePairs.has(_edgeKey(e)));
        effectiveEdges = [...inheritedBase.map(_deepClone), ...cfgEdges.map(_deepClone)];
        inheritedEdgeKeys = inheritedBase.map(_edgeKey);
    } else {
        effectiveEdges = cfgEdges.map(_deepClone);
        inheritedEdgeKeys = [];
    }

    let effectiveVars;
    if (cfgVars === null) {
        effectiveVars = _deepClone(baseVars);
    } else if (variablesMode === 'merge') {
        effectiveVars = { ..._deepClone(baseVars), ..._deepClone(cfgVars) };
    } else {
        effectiveVars = _deepClone(cfgVars);
    }

    const effectiveEntry = typeof branchCfg.entry === 'string' && branchCfg.entry.length > 0
        ? branchCfg.entry
        : baseEntry;

    return {
        branchData: {
            nodes: effectiveNodes,
            edges: effectiveEdges,
            entry: effectiveEntry,
            variables: effectiveVars,
            resources: _deepClone(resources),
        },
        inheritedNodeIds,
        inheritedEdgeKeys,
        entryNodeId: effectiveEntry,
    };
}

function _stableStringify(value) {
    if (value === null || typeof value !== 'object') return JSON.stringify(value);
    if (Array.isArray(value)) return `[${value.map(_stableStringify).join(',')}]`;
    const keys = Object.keys(value).sort();
    return `{${keys.map((k) => `${JSON.stringify(k)}:${_stableStringify(value[k])}`).join(',')}}`;
}

const _INHERIT_NODE_COMPARE_OMIT = new Set(['pos_x', 'pos_y']);

function _nodeSnapshotForInheritCompare(node) {
    if (!_isPlainObject(node)) return node;
    const out = {};
    for (const [k, v] of Object.entries(node)) {
        if (_INHERIT_NODE_COMPARE_OMIT.has(k)) continue;
        out[k] = v;
    }
    return out;
}

function _incomingEdgeIndicesToNode(edges, nodeId) {
    if (!Array.isArray(edges) || typeof nodeId !== 'string' || nodeId.length === 0) return [];
    const out = [];
    for (let i = 0; i < edges.length; i += 1) {
        const e = edges[i];
        if (!_isPlainObject(e)) continue;
        const to = e.to_node != null && e.to_node !== '' ? e.to_node : e.to;
        if (to === nodeId) out.push(i);
    }
    return out;
}

export const editorResource = createAsyncOp({
    name: 'flows/editor',
    silent: true,
    transport: 'http',
    // UI-only фабрика: held state редактора flows, без реальных HTTP-вызовов
    // (см. ниже extraInitial и расширенный extraReducer). `.run()` запрещён;
    // данные мутируются через actions (loadFlow / setBranch / setActiveTool / ...).
    // restMirror с `service: 'ui-only'` явно декларирует отсутствие REST-зеркала
    // — CI пропускает проверку и не даёт WARN в strict.
    restMirror: { method: 'GET', path: '/__ui_only__/flows/editor', service: 'ui-only' },
    request: async () => {
        throw new Error('flows/editor: UI-only factory; .run() is not supported');
    },
    extraInitial: {
        flowId: null,
        flowConfig: null,
        branchData: { nodes: {}, edges: [], entry: null, variables: {}, resources: {} },
        currentBranchId: null,
        selectedNodeId: null,
        selectedResourceId: null,
        panelOpen: false,
        panelExpanded: false,
        executionPanelOpen: false,
        agentExecutionRunning: false,
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
        runningEdgeIndices: [],
        completedEdgeIndices: [],
        failedEdgeIndices: [],
        erroredNodes: {},
        breakpointNodeIds: [],
        breakpointHitNodeId: null,
        entryNodeId: null,
        inheritedNodeIds: [],
        inheritedEdgeKeys: [],
        multiSelection: [],
        viewBox: { ...DEFAULT_VIEWBOX },
        smartGuides: [],
        smartGuidesEnabled: true,
        contextMenu: null,
        stickyNotes: [],
        pendingNodeToolId: null,
    },
    extraEvents: {
        FLOW_LOADED: 'flow_loaded',
        BRANCH_SET: 'branch_set',
        BRANCH_DATA_UPDATED: 'branch_data_updated',
        NODE_SELECTED: 'node_selected',
        RESOURCE_SELECTED: 'resource_selected',
        PANEL_CLOSED: 'panel_closed',
        PANEL_EXPANDED: 'panel_expanded',
        EXECUTION_PANEL_SET: 'execution_panel_set',
        AGENT_EXECUTION_SET: 'agent_execution_set',
        ACTIVE_TOOL_SET: 'active_tool_set',
        MODE_SET: 'mode_set',
        NAME_SET: 'name_set',
        FLOW_CONFIG_PATCHED: 'flow_config_patched',
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
        PENDING_NODE_TOOL_CLEARED: 'pending_node_tool_cleared',
    },
    actions: {
        setFlow: 'flow_loaded',
        setBranch: 'branch_set',
        updateBranchData: 'branch_data_updated',
        selectNode: 'node_selected',
        selectResource: 'resource_selected',
        closePanel: 'panel_closed',
        togglePanelExpanded: 'panel_expanded',
        setExecutionPanelOpen: 'execution_panel_set',
        setAgentExecutionRunning: 'agent_execution_set',
        setActiveTool: 'active_tool_set',
        setMode: 'mode_set',
        setName: 'name_set',
        patchFlowConfig: 'flow_config_patched',
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
        clearPendingNodeTool: 'pending_node_tool_cleared',
    },
    extraReducer: (state, event) => {
        const t = event.type;
        const p = event.payload && typeof event.payload === 'object' ? event.payload : {};

        if (t === 'flows/editor/flow_loaded') {
            const flow = p.flow;
            if (!flow || typeof flow !== 'object') return state;
            const requestedBranchId = typeof p.branchId === 'string' ? p.branchId : null;
            const effective = _buildEffectiveBranchData(flow, requestedBranchId);
            const meta = _resolveFlowMetadata(flow);
            const stickyNotes = Array.isArray(meta.sticky_notes) ? meta.sticky_notes : [];
            let nextBranchData = effective.branchData;
            let loadLayoutDirty = false;
            if (canvasNeedsAutoLayout(nextBranchData)) {
                const laid = applyAutoLayoutToBranchData(nextBranchData);
                if (laid !== nextBranchData) {
                    nextBranchData = laid;
                    loadLayoutDirty = true;
                }
            }
            return {
                ...state,
                flowId: typeof flow.flow_id === 'string' ? flow.flow_id : state.flowId,
                flowConfig: flow,
                branchData: nextBranchData,
                currentBranchId: requestedBranchId,
                inheritedNodeIds: effective.inheritedNodeIds,
                inheritedEdgeKeys: effective.inheritedEdgeKeys,
                previewExecutionState: p.previewExecutionState && typeof p.previewExecutionState === 'object' ? p.previewExecutionState : null,
                agentExecutionRunning: false,
                isDirty: loadLayoutDirty,
                historyStack: [],
                historyPosition: -1,
                canUndo: false,
                canRedo: false,
                runningNodeIds: [],
                completedNodeIds: [],
                runningEdgeIndices: [],
                completedEdgeIndices: [],
                failedEdgeIndices: [],
                erroredNodes: {},
                breakpointHitNodeId: null,
                entryNodeId: effective.entryNodeId,
                multiSelection: [],
                stickyNotes,
                pendingNodeToolId: null,
            };
        }

        if (t === 'flows/editor/branch_set') {
            return { ...state, currentBranchId: typeof p.branchId === 'string' ? p.branchId : null };
        }

        if (t === 'flows/editor/branch_data_updated') {
            const data = p.data;
            if (!data || typeof data !== 'object') return state;
            const prev = state.branchData && typeof state.branchData === 'object' ? state.branchData : { nodes: {}, edges: [] };
            const prevNodes = _isPlainObject(prev.nodes) ? prev.nodes : {};
            const nextNodes = _isPlainObject(data.nodes) ? data.nodes : {};
            const inheritedNodeIds = (Array.isArray(state.inheritedNodeIds) ? state.inheritedNodeIds : []).filter((id) => {
                if (!(id in nextNodes)) return false;
                const a = _nodeSnapshotForInheritCompare(prevNodes[id]);
                const b = _nodeSnapshotForInheritCompare(nextNodes[id]);
                return _stableStringify(a) === _stableStringify(b);
            });
            const prevEdges = Array.isArray(prev.edges) ? prev.edges : [];
            const nextEdges = Array.isArray(data.edges) ? data.edges : [];
            const prevEdgeByKey = new Map(prevEdges.map((e) => [_edgeKey(e), e]));
            const nextEdgeByKey = new Map(nextEdges.map((e) => [_edgeKey(e), e]));
            const inheritedEdgeKeys = (Array.isArray(state.inheritedEdgeKeys) ? state.inheritedEdgeKeys : []).filter((key) => {
                if (!nextEdgeByKey.has(key)) return false;
                return _stableStringify(prevEdgeByKey.get(key)) === _stableStringify(nextEdgeByKey.get(key));
            });
            const nextEntry = typeof data.entry === 'string' && data.entry.length > 0
                ? data.entry
                : null;
            return {
                ...state,
                branchData: data,
                entryNodeId: nextEntry,
                inheritedNodeIds,
                inheritedEdgeKeys,
            };
        }

        if (t === 'flows/editor/node_selected') {
            const nodeId = typeof p.nodeId === 'string' && p.nodeId.length > 0 ? p.nodeId : null;
            const openToolId = typeof p.openToolId === 'string' && p.openToolId.length > 0 ? p.openToolId : null;
            return {
                ...state,
                selectedNodeId: nodeId,
                selectedResourceId: null,
                panelOpen: nodeId !== null,
                multiSelection: nodeId ? [nodeId] : [],
                pendingNodeToolId: nodeId ? openToolId : null,
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
                pendingNodeToolId: null,
            };
        }

        if (t === 'flows/editor/panel_closed') {
            return {
                ...state,
                panelOpen: false,
                selectedNodeId: null,
                selectedResourceId: null,
                multiSelection: [],
                pendingNodeToolId: null,
            };
        }

        if (t === 'flows/editor/pending_node_tool_cleared') {
            return { ...state, pendingNodeToolId: null };
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

        if (t === 'flows/editor/flow_config_patched') {
            const patch = p.patch;
            if (!state.flowConfig || !patch || typeof patch !== 'object') return state;
            return {
                ...state,
                flowConfig: { ...state.flowConfig, ...patch },
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
            return { ...state, previewExecutionState: p.snapshot && typeof p.snapshot === 'object' ? p.snapshot : null };
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
            return { ...state, contextMenu: { x: menu.x, y: menu.y, target: menu.target, targetId: typeof menu.targetId === 'string' ? menu.targetId : null } };
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
                runningEdgeIndices: [],
                completedEdgeIndices: [],
                failedEdgeIndices: [],
                erroredNodes: {},
                breakpointHitNodeId: null,
                agentExecutionRunning: true,
            };
        }

        if (t === 'flows/run/flow_done') {
            return { ...state, agentExecutionRunning: false };
        }

        if (t === 'flows/run/edge_executed') {
            const idx = typeof p.edge_index === 'number' && Number.isFinite(p.edge_index)
                ? Math.floor(p.edge_index)
                : -1;
            if (idx < 0) return state;
            const completedSet = new Set(Array.isArray(state.completedEdgeIndices) ? state.completedEdgeIndices : []);
            if (completedSet.has(idx)) return state;
            const runningSet = new Set(Array.isArray(state.runningEdgeIndices) ? state.runningEdgeIndices : []);
            runningSet.add(idx);
            return { ...state, runningEdgeIndices: Array.from(runningSet) };
        }

        if (t === 'flows/run/edge_error') {
            const idx = typeof p.edge_index === 'number' && Number.isFinite(p.edge_index)
                ? Math.floor(p.edge_index)
                : -1;
            if (idx < 0) return state;
            const runSet = new Set(Array.isArray(state.runningEdgeIndices) ? state.runningEdgeIndices : []);
            const compSet = new Set(Array.isArray(state.completedEdgeIndices) ? state.completedEdgeIndices : []);
            const failSet = new Set(Array.isArray(state.failedEdgeIndices) ? state.failedEdgeIndices : []);
            runSet.delete(idx);
            compSet.delete(idx);
            failSet.add(idx);
            return {
                ...state,
                runningEdgeIndices: Array.from(runSet),
                completedEdgeIndices: Array.from(compSet),
                failedEdgeIndices: Array.from(failSet),
            };
        }

        if (t === 'flows/run/node_started') {
            const nodeId = p.node_id;
            if (typeof nodeId !== 'string' || nodeId.length === 0) return state;
            const erroredCopy = { ...state.erroredNodes };
            delete erroredCopy[nodeId];
            const edges = state.branchData && Array.isArray(state.branchData.edges)
                ? state.branchData.edges
                : [];
            const incomingIdx = _incomingEdgeIndicesToNode(edges, nodeId);
            const runSet = new Set(Array.isArray(state.runningEdgeIndices) ? state.runningEdgeIndices : []);
            const compSet = new Set(Array.isArray(state.completedEdgeIndices) ? state.completedEdgeIndices : []);
            for (let i = 0; i < incomingIdx.length; i += 1) {
                const ei = incomingIdx[i];
                if (runSet.has(ei)) {
                    runSet.delete(ei);
                    compSet.add(ei);
                }
            }
            return {
                ...state,
                runningNodeIds: _withId(state.runningNodeIds, nodeId),
                completedNodeIds: _withoutId(state.completedNodeIds, nodeId),
                erroredNodes: erroredCopy,
                runningEdgeIndices: Array.from(runSet),
                completedEdgeIndices: Array.from(compSet),
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
            const edges = state.branchData && Array.isArray(state.branchData.edges)
                ? state.branchData.edges
                : [];
            const incomingIdx = _incomingEdgeIndicesToNode(edges, nodeId);
            const runSet = new Set(Array.isArray(state.runningEdgeIndices) ? state.runningEdgeIndices : []);
            const failSet = new Set(Array.isArray(state.failedEdgeIndices) ? state.failedEdgeIndices : []);
            for (let i = 0; i < incomingIdx.length; i += 1) {
                const ei = incomingIdx[i];
                if (runSet.has(ei)) runSet.delete(ei);
                failSet.add(ei);
            }
            return {
                ...state,
                runningNodeIds: _withoutId(state.runningNodeIds, nodeId),
                erroredNodes: erroredCopy,
                runningEdgeIndices: Array.from(runSet),
                failedEdgeIndices: Array.from(failSet),
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
            const data = state.branchData;
            if (!data || typeof data !== 'object') return state;
            const nodes = data.nodes && typeof data.nodes === 'object' ? data.nodes : {};
            if (!(oldId in nodes)) return state;
            if (newId in nodes) return state;
            const nextNodes = {};
            for (const [id, node] of Object.entries(nodes)) {
                const targetId = id === oldId ? newId : id;
                if (id !== oldId || !node || typeof node !== 'object') {
                    nextNodes[targetId] = node && typeof node === 'object' ? { ...node, node_id: targetId } : node;
                    continue;
                }
                const prevName = typeof node.name === 'string' ? node.name : '';
                const syncNameToId = prevName === '' || prevName === oldId;
                nextNodes[targetId] = syncNameToId
                    ? { ...node, node_id: targetId, name: newId }
                    : { ...node, node_id: targetId };
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
                branchData: { ...data, nodes: nextNodes, edges: nextEdges, entry },
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
            if ((Array.isArray(state.inheritedNodeIds) ? state.inheritedNodeIds : []).includes(nodeId)) return state;
            const data = state.branchData;
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
                branchData: { ...data, nodes: nextNodes, edges: nextEdges, entry: data.entry === nodeId ? null : data.entry },
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
