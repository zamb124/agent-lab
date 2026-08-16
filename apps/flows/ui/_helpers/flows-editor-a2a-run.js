/**
 * Граница Test Run: JSON-RPC A2A кадр → editor domain `flows/run/*` + flattened run-trace.
 *
 * Core Flow UI не знает про канвас редактора. Хост панели вызывает этот хелпер
 * на каждом `flow-ui-a2a-frame`.
 */

import { mapA2aResultToChatRuntimeEvents } from '@platform/lib/flow-ui/protocol/a2a-result-helpers.js';

function _isPlainObject(value) {
    return value !== null && typeof value === 'object' && !Array.isArray(value);
}

function _optionalId(value, field) {
    if (value === null) {
        return null;
    }
    if (typeof value !== 'string' || value.length === 0) {
        throw new Error(`mapEditorA2aFrame: session.${field} must be null or non-empty string`);
    }
    return value;
}

function _optionalTraceId(value, field) {
    if (value === null || value === undefined) {
        return null;
    }
    if (typeof value !== 'string' || value.length === 0) {
        throw new Error(`mapEditorA2aFrame: ${field} must be a non-empty string or null`);
    }
    return value;
}

function _flattenTraceEntry(raw, index) {
    if (!_isPlainObject(raw)) {
        throw new Error('mapEditorA2aFrame: trace entry must be an object');
    }
    if (!_isPlainObject(raw.fields)) {
        throw new Error('mapEditorA2aFrame: trace entry.fields must be an object');
    }
    const kind = raw.fields.kind;
    if (typeof kind !== 'string' || kind.length === 0) {
        throw new Error('mapEditorA2aFrame: trace entry.fields.kind must be a non-empty string');
    }
    const taskId = _optionalTraceId(raw.task_id, 'task_id');
    const contextId = _optionalTraceId(raw.context_id, 'context_id');
    const nodeId = _optionalTraceId(raw.fields.node_id, 'node_id');
    const idParts = [taskId, kind, nodeId, String(index)].filter((part) => typeof part === 'string' && part.length > 0);
    if (idParts.length === 0) {
        throw new Error('mapEditorA2aFrame: cannot build trace entry id');
    }
    return Object.freeze({
        ...raw.fields,
        id: idParts.join(':'),
        context_id: contextId,
        task_id: taskId,
    });
}

/**
 * @param {object} frame JSON-RPC SSE envelope `{ jsonrpc, id, result }`
 * @param {{
 *   contextId: string | null,
 *   currentTaskId: string | null,
 *   taskPrimed: boolean,
 *   traceIndexBase: number,
 * }} session
 */
export function mapEditorA2aFrame(frame, session) {
    if (!_isPlainObject(frame)) {
        throw new Error('mapEditorA2aFrame: JSON-RPC frame object required');
    }
    if (!_isPlainObject(frame.result)) {
        throw new Error('mapEditorA2aFrame: frame.result object required');
    }
    if (!_isPlainObject(session)) {
        throw new Error('mapEditorA2aFrame: session object required');
    }
    if (typeof session.taskPrimed !== 'boolean') {
        throw new Error('mapEditorA2aFrame: session.taskPrimed must be boolean');
    }
    if (typeof session.traceIndexBase !== 'number' || !Number.isFinite(session.traceIndexBase) || session.traceIndexBase < 0) {
        throw new Error('mapEditorA2aFrame: session.traceIndexBase must be a non-negative number');
    }
    const contextId = _optionalId(session.contextId, 'contextId');
    const currentTaskId = _optionalId(session.currentTaskId, 'currentTaskId');
    const mapped = mapA2aResultToChatRuntimeEvents(frame.result, {
        contextId,
        currentTaskId,
        taskPrimed: session.taskPrimed,
    });
    const runEvents = Array.isArray(mapped.runEvents) ? mapped.runEvents : null;
    if (runEvents === null) {
        throw new Error('mapEditorA2aFrame: mapped.runEvents must be an array');
    }
    const rawTrace = Array.isArray(mapped.traceEntries) ? mapped.traceEntries : null;
    if (rawTrace === null) {
        throw new Error('mapEditorA2aFrame: mapped.traceEntries must be an array');
    }
    const traceIndexBase = Math.floor(session.traceIndexBase);
    return Object.freeze({
        runEvents: Object.freeze(runEvents.slice()),
        terminal: mapped.terminal === true,
        nextTaskId: typeof mapped.nextTaskId === 'string' && mapped.nextTaskId.length > 0
            ? mapped.nextTaskId
            : null,
        taskPrimed: mapped.taskPrimed === true,
        traceEntries: Object.freeze(rawTrace.map((entry, offset) => _flattenTraceEntry(entry, traceIndexBase + offset))),
    });
}
