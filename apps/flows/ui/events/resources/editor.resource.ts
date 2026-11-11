/**
 * Редактор flow — единый slice состояния редактора.
 *
 * Содержит:
 *   - доменное состояние flow и черновик ветки (`branchData`);
 *   - выбор ноды/ресурса/ветки и состояние панелей;
 *   - undo/redo стэк;
 *   - execution state каждой ноды (`runningNodeIds`, `completedNodeIds`,
 *     `erroredNodes`) — обновляется push-событиями `flows/run/*`;
 *   - breakpoints (`breakpointNodeIds`);
 *   - локальный canvas-state (`viewBox`, `panTool`, `multiSelection`,
 *     `smartGuides`, `contextMenu`, `stickyNotes`);
 *   - `editorLayout` (`agent` | `canvas`) — Agent Focus Mode для single llm_node.
 *
 * `silent: true` — UI-only фабрика, .run() запрещён.
 */

import { createAsyncOp } from '@platform/lib/events/index.js';
import { applyAutoLayoutToBranchData, canvasNeedsAutoLayout } from '../../_helpers/flow-graph-auto-layout.js';
import {
    applyEditorLayoutToState,
    EDITOR_LAYOUT_AGENT,
    EDITOR_LAYOUT_CANVAS,
    isAgentFocusEligible,
    resolveEditorLayout,
} from '../../_helpers/flow-editor-layout.js';
import type { FlowEditorSlice } from '../editor.types.js';
const HISTORY_LIMIT = 50;
const DEFAULT_VIEWBOX = Object.freeze({ x: 0, y: 0, w: 1600, h: 1000 });

interface EditorRunSession {
    contextId: string | null;
    taskId: string | null;
    taskPrimed: boolean;
    [key: string]: unknown;
}

interface StickyNote {
    id: string;
    [key: string]: unknown;
}

function requireStickyNotes(state: FlowEditorSlice): StickyNote[] {
    const notes = state.stickyNotes;
    if (!Array.isArray(notes)) throw new Error('flows/editor: stickyNotes required');
    const rows: StickyNote[] = [];
    for (const note of notes) {
        if (!_isPlainObject(note) || typeof note.id !== 'string') {
            throw new Error('flows/editor: sticky note id required');
        }
        rows.push({ ...note, id: note.id });
    }
    return rows;
}

function _withoutId(list: readonly string[] | undefined, id: string): string[] {
    if (list === undefined) throw new Error('flows/editor: id list required');
    return list.filter((existing) => existing !== id);
}

function _withId(list: readonly string[] | undefined, id: string): string[] {
    if (list === undefined) throw new Error('flows/editor: id list required');
    if (list.includes(id)) return [...list];
    return [...list, id];
}

function _normalizeDiffItem(entry: unknown) {
    if (!_isPlainObject(entry)) {
        throw new Error('flows/editor: diff entry must be an object');
    }
    const path = entry.path;
    const changeType = entry.change_type;
    if (typeof path !== 'string') {
        throw new Error('flows/editor: diff entry.path must be a string');
    }
    if (typeof changeType !== 'string') {
        throw new Error('flows/editor: diff entry.change_type must be a string');
    }
    if (!('old_value' in entry)) {
        throw new Error('flows/editor: diff entry.old_value is required');
    }
    if (!('new_value' in entry)) {
        throw new Error('flows/editor: diff entry.new_value is required');
    }
    return Object.freeze({
        path,
        old_value: entry.old_value,
        new_value: entry.new_value,
        change_type: changeType,
    });
}

function _normalizeDiffList(raw: unknown) {
    if (!Array.isArray(raw)) {
        throw new Error('flows/editor: diff must be an array');
    }
    const out = [];
    for (let i = 0; i < raw.length; i += 1) {
        out.push(_normalizeDiffItem(raw[i]));
    }
    return Object.freeze(out);
}

function _appendNodeRunResult(
    nodeRunResults: unknown,
    nodeId: string,
    result: unknown,
): Record<string, readonly unknown[]> {
    const base = _isPlainObject(nodeRunResults) ? nodeRunResults : {};
    const next: Record<string, readonly unknown[]> = {};
    for (const [key, value] of Object.entries(base)) {
        if (!Array.isArray(value)) throw new Error('flows/editor: node run list required');
        next[key] = value;
    }
    const existing = next[nodeId];
    const nextList = existing === undefined ? [] : [...existing];
    nextList.push(result);
    next[nodeId] = nextList;
    return next;
}

function _nodeRunResultKey(nodeId: string, runIndex: unknown) {
    return `${nodeId}:${String(runIndex)}`;
}

function _toggleExpandedNodeRunKey(expandedKeys: unknown, nodeId: string, runIndex: unknown) {
    const key = _nodeRunResultKey(nodeId, runIndex);
    const base = Array.isArray(expandedKeys) ? expandedKeys : [];
    if (base.includes(key)) {
        return base.filter((item) => item !== key);
    }
    return [...base, key];
}

const _DEEP_MERGE_EXCLUDE = new Set(['node_id', 'tool_id', 'flow_id']);

function _isPlainObject(value: unknown): value is Record<string, unknown> {
    return value !== null && typeof value === 'object' && !Array.isArray(value);
}

function _deepClone(value: unknown): unknown {
    if (value === null || typeof value !== 'object') return value;
    if (Array.isArray(value)) return value.map(_deepClone);
    if (!_isPlainObject(value)) return value;
    const out: Record<string, unknown> = {};
    for (const [k, v] of Object.entries(value)) out[k] = _deepClone(v);
    return out;
}

function _deepMerge(base: unknown, override: unknown): unknown {
    if (!_isPlainObject(base)) return _deepClone(override);
    if (!_isPlainObject(override)) return _deepClone(base);
    const cloned = _deepClone(base);
    if (!_isPlainObject(cloned)) {
        throw new Error('flows/editor: merged object required');
    }
    const result: Record<string, unknown> = cloned;
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

function _resolveFlowMetadata(flow: Record<string, unknown>) {
    const config = flow.config;
    if (_isPlainObject(config) && _isPlainObject(config.metadata)) return config.metadata;
    if (_isPlainObject(flow.metadata)) return flow.metadata;
    return {};
}

function _edgeNodeId(edge: Record<string, unknown>, primary: string, alt: string) {
    if (typeof edge[primary] === 'string' && edge[primary].length > 0) return edge[primary];
    if (typeof edge[alt] === 'string' && edge[alt].length > 0) return edge[alt];
    return '';
}

function _edgeKey(edge: unknown) {
    if (!_isPlainObject(edge)) return '';
    const from = _edgeNodeId(edge, 'from_node', 'from');
    const to = _edgeNodeId(edge, 'to_node', 'to');
    return `${from}->${to}`;
}

function _modeOf(branchCfgSlice: unknown, field: string, defaultMode: 'merge' | 'replace') {
    if (!_isPlainObject(branchCfgSlice)) return defaultMode;
    const raw = branchCfgSlice[field];
    if (raw === 'merge' || raw === 'replace') return raw;
    return defaultMode;
}

function _buildEffectiveBranchData(flow: Record<string, unknown>, branchId: string | null) {
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

    let effectiveNodes: Record<string, unknown>;
    let inheritedNodeIds: string[];
    if (cfgNodes === null) {
        const clonedNodes = _deepClone(baseNodes);
        if (!_isPlainObject(clonedNodes)) throw new Error('flows/editor: nodes clone required');
        effectiveNodes = clonedNodes;
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
        const replacedNodes = _deepClone(cfgNodes);
        if (!_isPlainObject(replacedNodes)) throw new Error('flows/editor: nodes clone required');
        effectiveNodes = replacedNodes;
        inheritedNodeIds = [];
    }

    let effectiveEdges: unknown[];
    let inheritedEdgeKeys: string[];
    if (cfgEdges === null) {
        effectiveEdges = baseEdges.map(_deepClone);
        inheritedEdgeKeys = baseEdges.map(_edgeKey);
    } else if (edgesMode === 'merge') {
        const cfgEdgePairs = new Set(cfgEdges.map(_edgeKey));
        const inheritedBase = baseEdges.filter((edge) => !cfgEdgePairs.has(_edgeKey(edge)));
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
        const clonedBaseVars = _deepClone(baseVars);
        const clonedCfgVars = _deepClone(cfgVars);
        if (!_isPlainObject(clonedBaseVars) || !_isPlainObject(clonedCfgVars)) {
            throw new Error('flows/editor: variables clone required');
        }
        effectiveVars = { ...clonedBaseVars, ...clonedCfgVars };
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

function _stableStringify(value: unknown): string {
    if (Array.isArray(value)) return `[${value.map(_stableStringify).join(',')}]`;
    if (!_isPlainObject(value)) return JSON.stringify(value);
    const keys = Object.keys(value).sort();
    return `{${keys.map((k) => `${JSON.stringify(k)}:${_stableStringify(value[k])}`).join(',')}}`;
}

const _INHERIT_NODE_COMPARE_OMIT = new Set(['pos_x', 'pos_y']);

function _nodeSnapshotForInheritCompare(node: unknown) {
    if (!_isPlainObject(node)) return node;
    const out: Record<string, unknown> = {};
    for (const [k, v] of Object.entries(node)) {
        if (_INHERIT_NODE_COMPARE_OMIT.has(k)) continue;
        out[k] = v;
    }
    return out;
}

function _incomingEdgeIndicesToNode(edges: unknown, nodeId: string) {
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

const IDLE_RUN_SESSION = Object.freeze({
    contextId: null,
    taskId: null,
    taskPrimed: false,
});

const EMPTY_RUN_TRACE = Object.freeze([]);
const EMPTY_END_WIRE_STATE = Object.freeze({});
const EMPTY_NODE_RUN_RESULTS = Object.freeze({});
const EMPTY_EXPANDED_NODE_RUN_KEYS = Object.freeze([]);

function _optionalRunId(value: unknown) {
    if (value === null || value === undefined) {
        return null;
    }
    if (typeof value !== 'string' || value.length === 0) {
        throw new Error('flows/editor: run id must be a non-empty string or null');
    }
    return value;
}

function _graphEntryId(state: FlowEditorSlice) {
    if (typeof state.entryNodeId === 'string' && state.entryNodeId.length > 0) {
        return state.entryNodeId;
    }
    const entry = state.branchData && typeof state.branchData.entry === 'string'
        ? state.branchData.entry
        : '';
    return entry.length > 0 ? entry : null;
}

function _isSinkNode(state: FlowEditorSlice, nodeId: string) {
    const edges = state.branchData && Array.isArray(state.branchData.edges)
        ? state.branchData.edges
        : [];
    for (let i = 0; i < edges.length; i += 1) {
        const edge = edges[i];
        if (!_isPlainObject(edge)) {
            continue;
        }
        const from = edge.from_node != null && edge.from_node !== '' ? edge.from_node : edge.from;
        if (from === nodeId) {
            return false;
        }
    }
    return true;
}

function _applyTerminalWires(state: FlowEditorSlice, nodeId: string, phase: unknown) {
    if (typeof nodeId !== 'string' || nodeId.length === 0) {
        throw new Error('flows/editor: terminal wire node_id required');
    }
    if (phase !== 'started' && phase !== 'completed' && phase !== 'failed') {
        throw new Error(`flows/editor: unsupported terminal wire phase ${String(phase)}`);
    }
    const entryId = _graphEntryId(state);
    let startWireRunState = state.startWireRunState === undefined ? null : state.startWireRunState;
    const prevEnds = _isPlainObject(state.endWireRunStateByNodeId)
        ? state.endWireRunStateByNodeId
        : EMPTY_END_WIRE_STATE;
    let endWireRunStateByNodeId = prevEnds;
    if (entryId === nodeId) {
        if (phase === 'started') {
            startWireRunState = 'running';
        } else if (phase === 'completed') {
            startWireRunState = 'completed';
        } else {
            startWireRunState = 'failed';
        }
    }
    if (phase !== 'started' && _isSinkNode(state, nodeId)) {
        endWireRunStateByNodeId = Object.freeze({
            ...prevEnds,
            [nodeId]: phase === 'completed' ? 'completed' : 'failed',
        });
    }
    return {
        ...state,
        startWireRunState,
        endWireRunStateByNodeId,
    };
}

function _clearedRunVisualization(
    state: FlowEditorSlice,
    extras: { runSession: EditorRunSession; agentExecutionRunning: boolean },
): FlowEditorSlice {
    return {
        ...state,
        runningNodeIds: [],
        completedNodeIds: [],
        runningEdgeIndices: [],
        completedEdgeIndices: [],
        failedEdgeIndices: [],
        erroredNodes: {},
        nodeRunResults: EMPTY_NODE_RUN_RESULTS,
        expandedNodeRunKeys: EMPTY_EXPANDED_NODE_RUN_KEYS,
        breakpointHitNodeId: null,
        runTrace: EMPTY_RUN_TRACE,
        startWireRunState: null,
        endWireRunStateByNodeId: EMPTY_END_WIRE_STATE,
        runSession: extras.runSession,
        agentExecutionRunning: extras.agentExecutionRunning,
    };
}

function _applyFlowStarted(state: FlowEditorSlice, payload: unknown) {
    if (!_isPlainObject(payload)) throw new Error('flows/editor: payload must be an object');
    const contextId = _optionalRunId(payload.context_id);
    const taskId = _optionalRunId(payload.task_id);
    return _clearedRunVisualization(state, {
        agentExecutionRunning: true,
        runSession: Object.freeze({
            contextId,
            taskId,
            taskPrimed: false,
        }),
    });
}

function _applyFlowDone(state: FlowEditorSlice) {
    return { ...state, agentExecutionRunning: false };
}

function _applySessionCleared(state: FlowEditorSlice) {
    return _clearedRunVisualization(state, {
        agentExecutionRunning: false,
        runSession: IDLE_RUN_SESSION,
    });
}

function _applyEdgeExecuted(state: FlowEditorSlice, payload: unknown) {
    if (!_isPlainObject(payload)) throw new Error('flows/editor: payload must be an object');
    const idx = typeof payload.edge_index === 'number' && Number.isFinite(payload.edge_index)
        ? Math.floor(payload.edge_index)
        : -1;
    if (idx < 0) return state;
    const completedSet = new Set(Array.isArray(state.completedEdgeIndices) ? state.completedEdgeIndices : []);
    if (completedSet.has(idx)) return state;
    const runningSet = new Set(Array.isArray(state.runningEdgeIndices) ? state.runningEdgeIndices : []);
    runningSet.add(idx);
    return { ...state, runningEdgeIndices: Array.from(runningSet) };
}

function _applyEdgeError(state: FlowEditorSlice, payload: unknown) {
    if (!_isPlainObject(payload)) throw new Error('flows/editor: payload must be an object');
    const idx = typeof payload.edge_index === 'number' && Number.isFinite(payload.edge_index)
        ? Math.floor(payload.edge_index)
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

function _applyNodeStarted(state: FlowEditorSlice, payload: unknown) {
    if (!_isPlainObject(payload)) throw new Error('flows/editor: payload must be an object');
    const nodeId = payload.node_id;
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
        if (ei === undefined) throw new Error('flows/editor: edge index required');
        if (runSet.has(ei)) {
            runSet.delete(ei);
            compSet.add(ei);
        }
    }
    return _applyTerminalWires({
        ...state,
        runningNodeIds: _withId(state.runningNodeIds, nodeId),
        completedNodeIds: _withoutId(state.completedNodeIds, nodeId),
        erroredNodes: erroredCopy,
        runningEdgeIndices: Array.from(runSet),
        completedEdgeIndices: Array.from(compSet),
    }, nodeId, 'started');
}

function _applyNodeCompleted(state: FlowEditorSlice, payload: unknown) {
    if (!_isPlainObject(payload)) throw new Error('flows/editor: payload must be an object');
    const nodeId = payload.node_id;
    if (typeof nodeId !== 'string' || nodeId.length === 0) return state;
    const existing = state.nodeRunResults && typeof state.nodeRunResults === 'object'
        ? state.nodeRunResults[nodeId]
        : null;
    const runIndex = typeof payload.run_index === 'number' && Number.isFinite(payload.run_index)
        ? Math.floor(payload.run_index)
        : (Array.isArray(existing) ? existing.length : 0);
    const nodeType = typeof payload.node_type === 'string' ? payload.node_type : '';
    const resultPreview = typeof payload.result_preview === 'string' ? payload.result_preview : '';
    const primaryField = typeof payload.primary_field === 'string' ? payload.primary_field : '';
    let durationMs = null;
    if (typeof payload.duration_ms === 'number' && Number.isFinite(payload.duration_ms)) {
        durationMs = Math.round(payload.duration_ms);
    }
    const diff = Array.isArray(payload.diff) ? _normalizeDiffList(payload.diff) : Object.freeze([]);
    const result = Object.freeze({
        kind: 'ok',
        node_id: nodeId,
        node_type: nodeType,
        run_index: runIndex,
        result_preview: resultPreview,
        primary_field: primaryField,
        duration_ms: durationMs,
        diff,
    });
    return _applyTerminalWires({
        ...state,
        runningNodeIds: _withoutId(state.runningNodeIds, nodeId),
        completedNodeIds: _withId(state.completedNodeIds, nodeId),
        nodeRunResults: _appendNodeRunResult(state.nodeRunResults, nodeId, result),
    }, nodeId, 'completed');
}

function _applyNodeFailed(state: FlowEditorSlice, payload: unknown) {
    if (!_isPlainObject(payload)) throw new Error('flows/editor: payload must be an object');
    const nodeId = payload.node_id;
    if (typeof nodeId !== 'string' || nodeId.length === 0) return state;
    const existing = state.nodeRunResults && typeof state.nodeRunResults === 'object'
        ? state.nodeRunResults[nodeId]
        : null;
    const runIndex = typeof payload.run_index === 'number' && Number.isFinite(payload.run_index)
        ? Math.floor(payload.run_index)
        : (Array.isArray(existing) ? existing.length : 0);
    const nodeType = typeof payload.node_type === 'string' ? payload.node_type : '';
    let durationMs = null;
    if (typeof payload.duration_ms === 'number' && Number.isFinite(payload.duration_ms)) {
        durationMs = Math.round(payload.duration_ms);
    }
    const errorText = typeof payload.error === 'string' ? payload.error : '';
    const result = Object.freeze({
        kind: 'error',
        node_id: nodeId,
        node_type: nodeType,
        run_index: runIndex,
        error: errorText,
        duration_ms: durationMs,
        diff: Object.freeze([]),
    });
    const erroredCopy = { ...state.erroredNodes, [nodeId]: errorText };
    const edges = state.branchData && Array.isArray(state.branchData.edges)
        ? state.branchData.edges
        : [];
    const incomingIdx = _incomingEdgeIndicesToNode(edges, nodeId);
    const runSet = new Set(Array.isArray(state.runningEdgeIndices) ? state.runningEdgeIndices : []);
    const failSet = new Set(Array.isArray(state.failedEdgeIndices) ? state.failedEdgeIndices : []);
    for (let i = 0; i < incomingIdx.length; i += 1) {
        const ei = incomingIdx[i];
        if (ei === undefined) throw new Error('flows/editor: edge index required');
        if (runSet.has(ei)) runSet.delete(ei);
        failSet.add(ei);
    }
    return _applyTerminalWires({
        ...state,
        runningNodeIds: _withoutId(state.runningNodeIds, nodeId),
        erroredNodes: erroredCopy,
        runningEdgeIndices: Array.from(runSet),
        failedEdgeIndices: Array.from(failSet),
        nodeRunResults: _appendNodeRunResult(state.nodeRunResults, nodeId, result),
    }, nodeId, 'failed');
}

function _applyRunEvent(state: FlowEditorSlice, type: string, payload: unknown) {
    if (!_isPlainObject(payload)) throw new Error('flows/editor: payload must be an object');
    if (type === 'flows/run/node_started') {
        return _applyNodeStarted(state, payload);
    }
    if (type === 'flows/run/node_completed') {
        return _applyNodeCompleted(state, payload);
    }
    if (type === 'flows/run/node_failed') {
        return _applyNodeFailed(state, payload);
    }
    if (type === 'flows/run/edge_executed') {
        return _applyEdgeExecuted(state, payload);
    }
    if (type === 'flows/run/edge_error') {
        return _applyEdgeError(state, payload);
    }
    throw new Error(`flows/editor: unsupported mapped run event ${type}`);
}

function _applyA2aMapped(state: FlowEditorSlice, payload: unknown) {
    if (!_isPlainObject(payload)) throw new Error('flows/editor: payload must be an object');
    const contextId = payload.context_id;
    if (typeof contextId !== 'string' || contextId.length === 0) {
        throw new Error('flows/editor: a2a_mapped context_id required');
    }
    if (!Array.isArray(payload.runEvents)) {
        throw new Error('flows/editor: a2a_mapped runEvents array required');
    }
    if (!Array.isArray(payload.traceEntries)) {
        throw new Error('flows/editor: a2a_mapped traceEntries array required');
    }
    if (typeof payload.terminal !== 'boolean') {
        throw new Error('flows/editor: a2a_mapped terminal must be boolean');
    }
    if (typeof payload.taskPrimed !== 'boolean') {
        throw new Error('flows/editor: a2a_mapped taskPrimed must be boolean');
    }
    const nextTaskId = _optionalRunId(payload.nextTaskId);
    let next = state;
    let hasNodeStarted = false;
    for (let i = 0; i < payload.runEvents.length; i += 1) {
        const runEvent = payload.runEvents[i];
        if (!_isPlainObject(runEvent) || typeof runEvent.type !== 'string' || runEvent.type.length === 0) {
            throw new Error('flows/editor: a2a_mapped run event type required');
        }
        if (runEvent.type === 'flows/run/node_started') {
            hasNodeStarted = true;
        }
    }
    if (!state.agentExecutionRunning && hasNodeStarted) {
        next = _applyFlowStarted(next, { context_id: contextId, task_id: nextTaskId });
    }
    for (let i = 0; i < payload.runEvents.length; i += 1) {
        const runEvent = payload.runEvents[i];
        if (!_isPlainObject(runEvent) || typeof runEvent.type !== 'string') {
            throw new Error('flows/editor: a2a_mapped run event type required');
        }
        const eventPayload = runEvent.payload;
        if (!_isPlainObject(eventPayload)) {
            throw new Error('flows/editor: a2a_mapped run event payload object required');
        }
        next = _applyRunEvent(next, runEvent.type, eventPayload);
    }
    const prevTrace = Array.isArray(next.runTrace) ? next.runTrace : EMPTY_RUN_TRACE;
    const runTrace = payload.traceEntries.length === 0
        ? prevTrace
        : Object.freeze([...prevTrace, ...payload.traceEntries]);
    let breakpointHitNodeId = next.breakpointHitNodeId;
    for (let i = 0; i < payload.traceEntries.length; i += 1) {
        const entry = payload.traceEntries[i];
        if (!_isPlainObject(entry)) {
            throw new Error('flows/editor: a2a_mapped trace entry must be an object');
        }
        if (entry.kind === 'breakpoint' && typeof entry.node_id === 'string' && entry.node_id.length > 0) {
            breakpointHitNodeId = entry.node_id;
        }
    }
    const session = _isPlainObject(next.runSession) ? next.runSession : IDLE_RUN_SESSION;
    return {
        ...next,
        runTrace,
        breakpointHitNodeId,
        runSession: Object.freeze({
            contextId,
            taskId: nextTaskId !== null ? nextTaskId : session.taskId,
            taskPrimed: payload.taskPrimed,
        }),
        agentExecutionRunning: payload.terminal ? false : next.agentExecutionRunning,
    };
}

export const editorResource = createAsyncOp({
    name: 'flows/editor',
    silent: true,
    transport: 'http',
    // UI-only фабрика: удерживаемое состояние редактора flows, без реальных HTTP-вызовов
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
        openNodePanelIds: [],
        propertyPanelLayouts: {},
        panelOpen: false,
        executionPanelOpen: false,
        agentExecutionRunning: false,
        activeTool: 'select',
        previewExecutionState: null,
        dataflow: null,
        dataflowObservations: {},
        workspace: 'logic',
        editorLayout: EDITOR_LAYOUT_CANVAS,
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
        nodeRunResults: EMPTY_NODE_RUN_RESULTS,
        expandedNodeRunKeys: EMPTY_EXPANDED_NODE_RUN_KEYS,
        breakpointNodeIds: [],
        breakpointHitNodeId: null,
        showCanvasRunResults: true,
        runSession: IDLE_RUN_SESSION,
        runTrace: EMPTY_RUN_TRACE,
        startWireRunState: null,
        endWireRunStateByNodeId: EMPTY_END_WIRE_STATE,
        entryNodeId: null,
        inheritedNodeIds: [],
        inheritedEdgeKeys: [],
        multiSelection: [],
        viewBox: { ...DEFAULT_VIEWBOX },
        smartGuides: [],
        smartGuidesEnabled: true,
        showDataWires: false,
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
        PROPERTY_PANEL_LAYOUT_SET: 'property_panel_layout_set',
        EXECUTION_PANEL_SET: 'execution_panel_set',
        AGENT_EXECUTION_SET: 'agent_execution_set',
        ACTIVE_TOOL_SET: 'active_tool_set',
        WORKSPACE_SET: 'workspace_set',
        EDITOR_LAYOUT_SET: 'editor_layout_set',
        NAME_SET: 'name_set',
        FLOW_CONFIG_PATCHED: 'flow_config_patched',
        PUBLISHED_AT_SET: 'published_at_set',
        DIRTY_SET: 'dirty_set',
        SAVING_SET: 'saving_set',
        PREVIEW_STATE_SET: 'preview_state_set',
        DATAFLOW_SET: 'dataflow_set',
        DATAFLOW_OBSERVATION_RECORDED: 'dataflow_observation_recorded',
        HISTORY_PUSHED: 'history_pushed',
        HISTORY_UNDONE: 'history_undone',
        HISTORY_REDONE: 'history_redone',
        HISTORY_CLEARED: 'history_cleared',
        VIEWBOX_CHANGED: 'viewbox_changed',
        TOOL_CHANGED: 'tool_changed',
        MULTI_SELECTION_CHANGED: 'multi_selection_changed',
        SMART_GUIDES_UPDATED: 'smart_guides_updated',
        SMART_GUIDES_TOGGLED: 'smart_guides_toggled',
        DATA_WIRES_TOGGLED: 'data_wires_toggled',
        CONTEXT_MENU_OPENED: 'context_menu_opened',
        CONTEXT_MENU_CLOSED: 'context_menu_closed',
        STICKY_NOTE_ADDED: 'sticky_note_added',
        STICKY_NOTE_UPDATED: 'sticky_note_updated',
        STICKY_NOTE_REMOVED: 'sticky_note_removed',
        BREAKPOINT_TOGGLED: 'breakpoint_toggled',
        NODE_DELETED: 'node_deleted',
        PENDING_NODE_TOOL_CLEARED: 'pending_node_tool_cleared',
        NODE_RUN_RESULT_EXPAND_TOGGLED: 'node_run_result_expand_toggled',
        CANVAS_RUN_RESULTS_TOGGLED: 'canvas_run_results_toggled',
    },
    actions: {
        setFlow: 'flow_loaded',
        setBranch: 'branch_set',
        updateBranchData: 'branch_data_updated',
        selectNode: 'node_selected',
        selectResource: 'resource_selected',
        closePanel: 'panel_closed',
        setPropertyPanelLayout: 'property_panel_layout_set',
        setExecutionPanelOpen: 'execution_panel_set',
        setAgentExecutionRunning: 'agent_execution_set',
        setActiveTool: 'active_tool_set',
        setWorkspace: 'workspace_set',
        setEditorLayout: 'editor_layout_set',
        setName: 'name_set',
        patchFlowConfig: 'flow_config_patched',
        setPublishedAt: 'published_at_set',
        setDirty: 'dirty_set',
        setSaving: 'saving_set',
        setPreviewExecutionState: 'preview_state_set',
        setDataflow: 'dataflow_set',
        recordDataflowObservation: 'dataflow_observation_recorded',
        pushHistory: 'history_pushed',
        undo: 'history_undone',
        redo: 'history_redone',
        clearHistory: 'history_cleared',
        setViewBox: 'viewbox_changed',
        changeTool: 'tool_changed',
        setMultiSelection: 'multi_selection_changed',
        setSmartGuides: 'smart_guides_updated',
        toggleSmartGuides: 'smart_guides_toggled',
        toggleDataWires: 'data_wires_toggled',
        openContextMenu: 'context_menu_opened',
        closeContextMenu: 'context_menu_closed',
        addStickyNote: 'sticky_note_added',
        updateStickyNote: 'sticky_note_updated',
        removeStickyNote: 'sticky_note_removed',
        toggleBreakpoint: 'breakpoint_toggled',
        removeNode: 'node_deleted',
        clearPendingNodeTool: 'pending_node_tool_cleared',
        toggleNodeRunResultExpand: 'node_run_result_expand_toggled',
        toggleCanvasRunResults: 'canvas_run_results_toggled',
    },
    extraReducer: (state: FlowEditorSlice, event) => {
        const t = event.type;
        const p: Record<string, unknown> = {};
        if (_isPlainObject(event.payload)) {
            for (const [key, field] of Object.entries(event.payload)) p[key] = field;
        }
        const s = state;

        if (t === 'flows/editor/flow_loaded') {
            const flow = p.flow;
            if (!_isPlainObject(flow)) return state;
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
            const loadedFlowId = typeof flow.flow_id === 'string' ? flow.flow_id : s.flowId;
            if (typeof loadedFlowId !== 'string' || loadedFlowId.length === 0) {
                throw new Error('flows/editor: flow_id required');
            }
            const nextFlowId = loadedFlowId;
            const resolvedLayout = resolveEditorLayout(nextBranchData, nextFlowId, null);
            // Повторная загрузка того же flow (дублирующийся item_loaded,
            // refresh после save) не должна сбрасывать открытые панели и выбор.
            const isSameFlow = s.flowId === nextFlowId;
            const nextNodes = _isPlainObject(nextBranchData) && _isPlainObject(nextBranchData.nodes)
                ? nextBranchData.nodes
                : {};
            const nextResources = _isPlainObject(nextBranchData) && _isPlainObject(nextBranchData.resources)
                ? nextBranchData.resources
                : {};
            const keptOpenIds = isSameFlow
                ? (Array.isArray(s.openNodePanelIds) ? s.openNodePanelIds : []).filter((id) => id in nextNodes)
                : [];
            const keptSelectedNodeId = isSameFlow && typeof s.selectedNodeId === 'string' && s.selectedNodeId in nextNodes
                ? s.selectedNodeId
                : null;
            const keptResourceId = isSameFlow && typeof s.selectedResourceId === 'string' && s.selectedResourceId in nextResources
                ? s.selectedResourceId
                : null;
            const keptMultiSelection = isSameFlow && Array.isArray(s.multiSelection)
                ? s.multiSelection.filter((id) => id in nextNodes)
                : [];
            const loaded = {
                ...state,
                flowId: nextFlowId,
                flowConfig: flow,
                branchData: nextBranchData,
                currentBranchId: requestedBranchId,
                inheritedNodeIds: effective.inheritedNodeIds,
                inheritedEdgeKeys: effective.inheritedEdgeKeys,
                previewExecutionState: p.previewExecutionState && typeof p.previewExecutionState === 'object' ? p.previewExecutionState : null,
                dataflow: null,
                dataflowObservations: {},
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
                nodeRunResults: EMPTY_NODE_RUN_RESULTS,
                expandedNodeRunKeys: EMPTY_EXPANDED_NODE_RUN_KEYS,
                breakpointHitNodeId: null,
                runSession: IDLE_RUN_SESSION,
                runTrace: EMPTY_RUN_TRACE,
                startWireRunState: null,
                endWireRunStateByNodeId: EMPTY_END_WIRE_STATE,
                entryNodeId: effective.entryNodeId,
                multiSelection: keptMultiSelection,
                stickyNotes,
                pendingNodeToolId: isSameFlow && keptSelectedNodeId ? s.pendingNodeToolId : null,
                selectedNodeId: keptSelectedNodeId,
                selectedResourceId: keptResourceId,
                openNodePanelIds: keptOpenIds,
                propertyPanelLayouts: isSameFlow && _isPlainObject(s.propertyPanelLayouts) ? s.propertyPanelLayouts : {},
                panelOpen: isSameFlow && (keptOpenIds.length > 0 || keptResourceId !== null),
                editorLayout: isSameFlow && s.editorLayout === EDITOR_LAYOUT_AGENT && isAgentFocusEligible(nextBranchData)
                    ? EDITOR_LAYOUT_AGENT
                    : EDITOR_LAYOUT_CANVAS,
            };
            return applyEditorLayoutToState(loaded, resolvedLayout, nextBranchData);
        }

        if (t === 'flows/editor/branch_set') {
            return { ...state, currentBranchId: typeof p.branchId === 'string' ? p.branchId : null };
        }

        if (t === 'flows/editor/branch_data_updated') {
            const data = p.data;
            if (!_isPlainObject(data)) return state;
            const prev = _isPlainObject(s.branchData) ? s.branchData : { nodes: {}, edges: [] };
            const prevNodes = _isPlainObject(prev.nodes) ? prev.nodes : {};
            const nextNodes = _isPlainObject(data.nodes) ? data.nodes : {};
            const inheritedNodeIds = (Array.isArray(s.inheritedNodeIds) ? s.inheritedNodeIds : []).filter((id) => {
                if (!(id in nextNodes)) return false;
                const a = _nodeSnapshotForInheritCompare(prevNodes[id]);
                const b = _nodeSnapshotForInheritCompare(nextNodes[id]);
                return _stableStringify(a) === _stableStringify(b);
            });
            const prevEdges = Array.isArray(prev.edges) ? prev.edges : [];
            const nextEdges = Array.isArray(data.edges) ? data.edges : [];
            const prevEdgeByKey = new Map(prevEdges.map((edge) => [_edgeKey(edge), edge]));
            const nextEdgeByKey = new Map(nextEdges.map((edge) => [_edgeKey(edge), edge]));
            const inheritedEdgeKeys = (Array.isArray(s.inheritedEdgeKeys) ? s.inheritedEdgeKeys : []).filter((key) => {
                if (!nextEdgeByKey.has(key)) return false;
                return _stableStringify(prevEdgeByKey.get(key)) === _stableStringify(nextEdgeByKey.get(key));
            });
            const nextEntry = typeof data.entry === 'string' && data.entry.length > 0
                ? data.entry
                : null;
            const nextState = {
                ...state,
                branchData: data,
                entryNodeId: nextEntry,
                inheritedNodeIds,
                inheritedEdgeKeys,
            };
            if (!isAgentFocusEligible(data) && s.editorLayout !== EDITOR_LAYOUT_CANVAS) {
                return { ...nextState, editorLayout: EDITOR_LAYOUT_CANVAS };
            }
            return nextState;
        }

        if (t === 'flows/editor/editor_layout_set') {
            const layout = p.layout;
            if (layout !== 'agent' && layout !== 'canvas') {
                return state;
            }
            const branchData = s.branchData && typeof s.branchData === 'object'
                ? s.branchData
                : { nodes: {}, edges: [] };
            if (layout === 'agent' && !isAgentFocusEligible(branchData)) {
                return state;
            }
            return applyEditorLayoutToState(state, layout, branchData);
        }

        if (t === 'flows/editor/node_selected') {
            const nodeId = typeof p.nodeId === 'string' && p.nodeId.length > 0 ? p.nodeId : null;
            const openToolId = typeof p.openToolId === 'string' && p.openToolId.length > 0 ? p.openToolId : null;
            const prevNodeId = typeof s.selectedNodeId === 'string' ? s.selectedNodeId : null;
            let openNodePanelIds = Array.isArray(s.openNodePanelIds) ? [...s.openNodePanelIds] : [];
            let propertyPanelLayouts = _isPlainObject(s.propertyPanelLayouts)
                ? { ...s.propertyPanelLayouts }
                : {};
            if (prevNodeId && prevNodeId !== nodeId && openNodePanelIds.includes(prevNodeId)) {
                const prevLayout = _isPlainObject(propertyPanelLayouts[prevNodeId])
                    ? propertyPanelLayouts[prevNodeId]
                    : {};
                propertyPanelLayouts[prevNodeId] = { ...prevLayout, collapsed: true };
            }
            if (nodeId) {
                if (!openNodePanelIds.includes(nodeId)) {
                    openNodePanelIds.push(nodeId);
                }
                const nextLayout = _isPlainObject(propertyPanelLayouts[nodeId])
                    ? propertyPanelLayouts[nodeId]
                    : {};
                propertyPanelLayouts[nodeId] = { ...nextLayout, collapsed: false };
            }
            return {
                ...state,
                selectedNodeId: nodeId,
                selectedResourceId: null,
                openNodePanelIds,
                propertyPanelLayouts,
                panelOpen: nodeId !== null || openNodePanelIds.length > 0,
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
                panelOpen: rid !== null || (Array.isArray(s.openNodePanelIds) && s.openNodePanelIds.length > 0),
                multiSelection: [],
                pendingNodeToolId: null,
            };
        }

        if (t === 'flows/editor/panel_closed') {
            const targetNodeId = typeof p.nodeId === 'string' && p.nodeId.length > 0 ? p.nodeId : null;
            if (targetNodeId) {
                const openNodePanelIds = (Array.isArray(s.openNodePanelIds) ? s.openNodePanelIds : [])
                    .filter((id) => id !== targetNodeId);
                const propertyPanelLayouts = _isPlainObject(s.propertyPanelLayouts)
                    ? { ...s.propertyPanelLayouts }
                    : {};
                delete propertyPanelLayouts[targetNodeId];
                const nextSelectedNodeId = s.selectedNodeId === targetNodeId
                    ? (openNodePanelIds.length > 0 ? openNodePanelIds[openNodePanelIds.length - 1] : null)
                    : s.selectedNodeId;
                return {
                    ...state,
                    openNodePanelIds,
                    propertyPanelLayouts,
                    selectedNodeId: nextSelectedNodeId,
                    panelOpen: openNodePanelIds.length > 0 || Boolean(s.selectedResourceId),
                    multiSelection: nextSelectedNodeId ? [nextSelectedNodeId] : [],
                    pendingNodeToolId: nextSelectedNodeId ? s.pendingNodeToolId : null,
                };
            }
            return {
                ...state,
                panelOpen: false,
                selectedNodeId: null,
                selectedResourceId: null,
                openNodePanelIds: [],
                propertyPanelLayouts: {},
                multiSelection: [],
                pendingNodeToolId: null,
            };
        }

        if (t === 'flows/editor/property_panel_layout_set') {
            const nodeId = typeof p.nodeId === 'string' && p.nodeId.length > 0 ? p.nodeId : null;
            const layout = p.layout;
            if (!nodeId || !layout || typeof layout !== 'object') {
                return state;
            }
            const propertyPanelLayouts = _isPlainObject(s.propertyPanelLayouts)
                ? { ...s.propertyPanelLayouts }
                : {};
            propertyPanelLayouts[nodeId] = { ...layout };
            return { ...state, propertyPanelLayouts };
        }

        if (t === 'flows/editor/pending_node_tool_cleared') {
            return { ...state, pendingNodeToolId: null };
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

        if (t === 'flows/editor/workspace_set') {
            const workspace = p.workspace;
            if (workspace !== 'logic' && workspace !== 'interface' && workspace !== 'run') {
                throw new Error(`flows/editor: unsupported workspace ${String(workspace)}`);
            }
            if (workspace === 'run') {
                return { ...state, workspace, executionPanelOpen: true };
            }
            return { ...state, workspace };
        }

        if (t === 'flows/editor/name_set') {
            const name = typeof p.name === 'string' ? p.name : '';
            if (!s.flowConfig) return state;
            return {
                ...state,
                flowConfig: { ...s.flowConfig, name },
                isDirty: true,
            };
        }

        if (t === 'flows/editor/flow_config_patched') {
            const patch = p.patch;
            if (!s.flowConfig || !patch || typeof patch !== 'object') return state;
            return {
                ...state,
                flowConfig: { ...s.flowConfig, ...patch },
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

        if (t === 'flows/editor/dataflow_set') {
            return { ...state, dataflow: p.dataflow && typeof p.dataflow === 'object' ? p.dataflow : null };
        }

        if (t === 'flows/editor/dataflow_observation_recorded') {
            const nodeId = typeof p.nodeId === 'string' && p.nodeId.length > 0 ? p.nodeId : null;
            const observation = p.observation && typeof p.observation === 'object' ? p.observation : null;
            if (!nodeId || !observation) return state;
            return {
                ...state,
                dataflowObservations: {
                    ...(_isPlainObject(s.dataflowObservations) ? s.dataflowObservations : {}),
                    [nodeId]: observation,
                },
            };
        }

        if (t === 'flows/editor/history_pushed') {
            const snapshot = p.snapshot;
            if (!snapshot) return state;
            const historyStack = state.historyStack;
            const historyPosition = state.historyPosition;
            if (!Array.isArray(historyStack) || typeof historyPosition !== 'number') {
                throw new Error('flows/editor: history required');
            }
            const stack = historyStack.slice(0, historyPosition + 1);
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
            const historyPosition = state.historyPosition;
            if (typeof historyPosition !== 'number') throw new Error('flows/editor: historyPosition required');
            if (historyPosition < 0) return state;
            const newPos = historyPosition - 1;
            return {
                ...state,
                historyPosition: newPos,
                canUndo: newPos >= 0,
                canRedo: true,
            };
        }

        if (t === 'flows/editor/history_redone') {
            const historyStack = state.historyStack;
            const historyPosition = state.historyPosition;
            if (!Array.isArray(historyStack) || typeof historyPosition !== 'number') {
                throw new Error('flows/editor: history required');
            }
            const max = historyStack.length - 1;
            if (historyPosition >= max) return state;
            const newPos = historyPosition + 1;
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
            if (!_isPlainObject(v)) return state;
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
                selectedNodeId: ids.length === 1 ? ids[0] : (ids.length > 1 ? null : s.selectedNodeId),
                panelOpen: ids.length === 1,
            };
        }

        if (t === 'flows/editor/smart_guides_updated') {
            const guides = Array.isArray(p.guides) ? p.guides : [];
            return { ...state, smartGuides: guides };
        }

        if (t === 'flows/editor/smart_guides_toggled') {
            return { ...state, smartGuidesEnabled: !s.smartGuidesEnabled };
        }

        if (t === 'flows/editor/data_wires_toggled') {
            return { ...state, showDataWires: !s.showDataWires };
        }

        if (t === 'flows/editor/context_menu_opened') {
            const menu = p.menu;
            if (!_isPlainObject(menu)) return state;
            return { ...state, contextMenu: { x: menu.x, y: menu.y, target: menu.target, targetId: typeof menu.targetId === 'string' ? menu.targetId : null } };
        }

        if (t === 'flows/editor/context_menu_closed') {
            return { ...state, contextMenu: null };
        }

        if (t === 'flows/editor/breakpoint_toggled') {
            const nodeId = p.nodeId;
            if (typeof nodeId !== 'string' || nodeId.length === 0) return state;
            if (state.breakpointNodeIds === undefined) throw new Error('flows/editor: breakpointNodeIds required');
            const exists = state.breakpointNodeIds.includes(nodeId);
            return {
                ...state,
                breakpointNodeIds: exists ? _withoutId(s.breakpointNodeIds, nodeId) : _withId(s.breakpointNodeIds, nodeId),
            };
        }

        if (t === 'flows/editor/sticky_note_added') {
            const note = p.note;
            if (!_isPlainObject(note) || typeof note.id !== 'string') return state;
            return { ...state, stickyNotes: [...requireStickyNotes(s), note] };
        }

        if (t === 'flows/editor/sticky_note_updated') {
            const note = p.note;
            if (!_isPlainObject(note) || typeof note.id !== 'string') return state;
            return {
                ...state,
                stickyNotes: requireStickyNotes(s).map((n) => (n.id === note.id ? { ...n, ...note } : n)),
            };
        }

        if (t === 'flows/editor/sticky_note_removed') {
            const id = p.id;
            if (typeof id !== 'string') return state;
            return { ...state, stickyNotes: requireStickyNotes(s).filter((n) => n.id !== id) };
        }

        if (t === 'flows/run/flow_started') {
            return _applyFlowStarted(state, p);
        }

        if (t === 'flows/run/flow_done') {
            return _applyFlowDone(state);
        }

        if (t === 'flows/run/session_cleared') {
            return _applySessionCleared(state);
        }

        if (t === 'flows/run/a2a_mapped') {
            return _applyA2aMapped(state, p);
        }

        if (t === 'flows/run/edge_executed') {
            return _applyEdgeExecuted(state, p);
        }

        if (t === 'flows/run/edge_error') {
            return _applyEdgeError(state, p);
        }

        if (t === 'flows/run/node_started') {
            return _applyNodeStarted(state, p);
        }

        if (t === 'flows/run/node_completed') {
            return _applyNodeCompleted(state, p);
        }

        if (t === 'flows/run/node_failed') {
            return _applyNodeFailed(state, p);
        }

        if (t === 'flows/editor/node_run_result_expand_toggled') {
            const nodeId = p.nodeId;
            const runIndex = p.runIndex;
            if (typeof nodeId !== 'string' || nodeId.length === 0) return state;
            if (typeof runIndex !== 'number' || !Number.isFinite(runIndex)) return state;
            return {
                ...state,
                expandedNodeRunKeys: Object.freeze(
                    _toggleExpandedNodeRunKey(s.expandedNodeRunKeys, nodeId, Math.floor(runIndex)),
                ),
            };
        }

        if (t === 'flows/editor/canvas_run_results_toggled') {
            if (typeof p.value !== 'boolean') return state;
            return { ...state, showCanvasRunResults: p.value };
        }

        if (t === 'flows/breakpoint/hit') {
            const nodeId = p.node_id;
            if (typeof nodeId !== 'string' || nodeId.length === 0) return state;
            return { ...state, breakpointHitNodeId: nodeId };
        }

        if (t === 'flows/breakpoint/clear') {
            if (s.breakpointHitNodeId === null) return state;
            return { ...state, breakpointHitNodeId: null };
        }

        if (t === 'flows/editor/node_deleted') {
            const nodeId = p.nodeId;
            if (typeof nodeId !== 'string' || nodeId.length === 0) return state;
            if ((Array.isArray(s.inheritedNodeIds) ? s.inheritedNodeIds : []).includes(nodeId)) return state;
            const data = s.branchData;
            if (!data || typeof data !== 'object') return state;
            const nodes = data.nodes && typeof data.nodes === 'object' ? data.nodes : {};
            if (!(nodeId in nodes)) return state;
            const nextNodes: Record<string, unknown> = {};
            for (const [id, node] of Object.entries(nodes)) {
                if (id !== nodeId) nextNodes[id] = node;
            }
            const edges = Array.isArray(data.edges) ? data.edges : [];
            const nextEdges = edges.filter((edge) => _isPlainObject(edge) && edge.from_node !== nodeId && edge.to_node !== nodeId);
            const erroredCopy = { ...s.erroredNodes };
            delete erroredCopy[nodeId];
            return {
                ...state,
                branchData: { ...data, nodes: nextNodes, edges: nextEdges, entry: data.entry === nodeId ? null : data.entry },
                selectedNodeId: s.selectedNodeId === nodeId ? null : s.selectedNodeId,
                openNodePanelIds: (Array.isArray(s.openNodePanelIds) ? s.openNodePanelIds : [])
                    .filter((id) => id !== nodeId),
                propertyPanelLayouts: (() => {
                    const layouts = _isPlainObject(s.propertyPanelLayouts)
                        ? { ...s.propertyPanelLayouts }
                        : {};
                    delete layouts[nodeId];
                    return layouts;
                })(),
                panelOpen: (Array.isArray(s.openNodePanelIds) ? s.openNodePanelIds : [])
                    .filter((id) => id !== nodeId).length > 0
                    || (s.selectedNodeId !== null && s.selectedNodeId !== nodeId),
                multiSelection: _withoutId(state.multiSelection, nodeId),
                breakpointNodeIds: _withoutId(s.breakpointNodeIds, nodeId),
                runningNodeIds: _withoutId(s.runningNodeIds, nodeId),
                completedNodeIds: _withoutId(s.completedNodeIds, nodeId),
                erroredNodes: erroredCopy,
                entryNodeId: s.entryNodeId === nodeId ? null : s.entryNodeId,
                isDirty: true,
            };
        }

        return state;
    },
});

/**
 * Массовое удаление нод и связанных рёбер.
 *
 * REST-зеркало: POST /flows/api/v1/flows/{flow_id}/nodes/bulk_delete
 * Транспорт ws; success триггерит reducer для очистки multiSelection и
 * перезагружает flow через `flows/flows`.
 */
export const editorBulkDeleteOp = createAsyncOp({
    name: 'flows/editor_bulk_delete',
    transport: 'ws',
    wsTimeoutMs: 15_000,
    successToastKey: 'flows:canvas.toast.bulk_delete_success',
    errorToastKey: 'flows:canvas.toast.bulk_delete_error',
    commandType: 'flows/flows/nodes_bulk_delete_requested',
    restMirror: { method: 'POST', path: '/flows/api/v1/flows/{flow_id}/nodes/bulk_delete' },
});

/**
 * Сохранение стикеров — PATCH metadata flow.config.metadata.sticky_notes.
 */
export const stickyNoteUpsertOp = createAsyncOp({
    name: 'flows/sticky_note_upsert',
    transport: 'ws',
    wsTimeoutMs: 15_000,
    silent: true,
    commandType: 'flows/flows/metadata_update_requested',
    restMirror: { method: 'PATCH', path: '/flows/api/v1/flows/{flow_id}/metadata' },
});

declare module '@platform/lib/events/factory-registry.js' {
    interface PlatformFactoryRegistry {
        'flows/editor': typeof editorResource;
        'flows/editor_bulk_delete': typeof editorBulkDeleteOp;
        'flows/sticky_note_upsert': typeof stickyNoteUpsertOp;
    }
}
