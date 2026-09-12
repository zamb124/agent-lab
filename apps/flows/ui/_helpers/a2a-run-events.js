/**
 * Проекция A2A-кадра в события выполнения редактора: подсветка нод/рёбер холста
 * (``flows/run/*``) и записи трассировки панели выполнения. Данные — платформенные
 * data-артефакты emitter'а (``node_start_*``, ``node_complete_*``, ``edge_*``, ``tool_call:*``)
 * и статусы Task (breakpoint, input_required, терминальные).
 */

import {
    isTerminalTaskState,
    resolveA2aContextId,
    resolveA2aTaskId,
    unwrapA2aStreamResult,
} from '@platform/lib/flow-ui/protocol/a2a-stream.js';
import { decodePart, textFromParts } from '@platform/lib/flow-ui/protocol/parts.js';

function finiteInt(value) {
    return typeof value === 'number' && Number.isFinite(value) ? Math.floor(value) : null;
}

function nodePayload(data, extra = {}) {
    const payload = { node_id: data.node_id, ...extra };
    if (typeof data.node_type === 'string') payload.node_type = data.node_type;
    if (typeof data.result_preview === 'string') payload.result_preview = data.result_preview;
    const duration = finiteInt(data.duration_ms);
    if (duration !== null) payload.duration_ms = Math.round(data.duration_ms);
    const runIndex = finiteInt(data.run_index);
    if (runIndex !== null) payload.run_index = runIndex;
    if (typeof data.primary_field === 'string') payload.primary_field = data.primary_field;
    if (Array.isArray(data.diff)) payload.diff = data.diff;
    if (Array.isArray(data.steps)) payload.steps = data.steps;
    return payload;
}

function edgePayload(data) {
    const edgeIndex = finiteInt(data.edge_index);
    if (edgeIndex === null || edgeIndex < 0 || typeof data.from_node !== 'string' || typeof data.to_node !== 'string') return null;
    return { edge_index: edgeIndex, from_node: data.from_node, to_node: data.to_node };
}

function artifactEvents(out, artifact, contextId, taskId) {
    const trace = (fields) => out.traceEntries.push({ context_id: contextId, task_id: taskId, fields });
    for (const part of artifact.parts) {
        const decoded = decodePart(part);
        if (decoded.kind !== 'data') continue;
        const data = decoded.value;
        if (!data || typeof data !== 'object') continue;
        if (typeof data.tool === 'string' && typeof data.tool_call_id === 'string') {
            const isResult = Object.prototype.hasOwnProperty.call(data, 'result');
            trace({ kind: isResult ? 'tool_result' : 'tool_call', tool: data.tool, tool_call_id: data.tool_call_id });
            continue;
        }
        if (data.event === 'edge_executed' || data.event === 'edge_error') {
            const payload = edgePayload(data);
            if (payload === null) continue;
            if (data.event === 'edge_error') payload.error = typeof data.error === 'string' ? data.error : '';
            out.runEvents.push({ type: `flows/run/${data.event}`, payload });
            trace({ kind: data.event, ...payload });
            continue;
        }
        if (typeof data.node_id !== 'string' || data.node_id === '') continue;
        if (data.event === 'node_start') {
            out.runEvents.push({ type: 'flows/run/node_started', payload: { node_id: data.node_id } });
            trace({ kind: 'node_start', node_id: data.node_id, node_type: typeof data.node_type === 'string' ? data.node_type : '' });
        } else if (data.event === 'node_complete') {
            const payload = nodePayload(data);
            out.runEvents.push({ type: 'flows/run/node_completed', payload });
            trace({ kind: 'node_complete', ...payload });
        } else if (data.event === 'node_error') {
            const error = typeof data.error === 'string' && data.error !== '' ? data.error : 'error';
            const payload = nodePayload(data, { error });
            delete payload.result_preview;
            out.runEvents.push({ type: 'flows/run/node_failed', payload });
            trace({ kind: 'node_error', ...payload });
        }
    }
}

function statusEvents(out, event, contextId, taskId) {
    const state = event.status?.state;
    const metadata = event.metadata && typeof event.metadata === 'object' ? event.metadata : {};
    const trace = (fields) => out.traceEntries.push({ context_id: contextId, task_id: taskId, fields });
    if (state === 'TASK_STATE_INPUT_REQUIRED') {
        if (metadata.breakpoint === true) {
            trace({ kind: 'breakpoint', node_id: typeof metadata.node_id === 'string' ? metadata.node_id : '' });
        } else {
            trace({ kind: 'input_required' });
        }
        return;
    }
    if (isTerminalTaskState(state)) {
        out.terminal = true;
        const text = textFromParts(event.status?.message?.parts);
        trace({ kind: 'status_terminal', terminal_state: state.replace('TASK_STATE_', '').toLowerCase(), message_preview: text.slice(0, 160) });
    }
}

/**
 * @param {object} result JSON-RPC ``result`` кадра SendStreamingMessage / SubscribeToTask
 * @param {{ contextId: string | null, currentTaskId: string | null, taskPrimed: boolean }} session
 */
export function mapA2aResultToRunEvents(result, session) {
    const out = {
        runEvents: [],
        traceEntries: [],
        nextTaskId: session.currentTaskId,
        taskPrimed: session.taskPrimed,
        terminal: false,
    };
    const unwrapped = unwrapA2aStreamResult(result);
    if (unwrapped === null) return out;
    const taskId = resolveA2aTaskId(result, session.currentTaskId);
    const contextId = session.contextId ?? resolveA2aContextId(result, null);
    if (taskId) {
        out.nextTaskId = taskId;
        if (contextId) out.taskPrimed = true;
    }
    if (unwrapped.frameKind === 'artifactUpdate' && unwrapped.event.artifact) {
        artifactEvents(out, unwrapped.event.artifact, contextId, taskId);
    } else if (unwrapped.frameKind === 'statusUpdate') {
        statusEvents(out, unwrapped.event, contextId, taskId);
    } else if (unwrapped.frameKind === 'task') {
        for (const artifact of unwrapped.event.artifacts ?? []) artifactEvents(out, artifact, contextId, taskId);
        if (isTerminalTaskState(unwrapped.event.status?.state)) out.terminal = true;
    }
    return out;
}
