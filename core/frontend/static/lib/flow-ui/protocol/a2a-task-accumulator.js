import { INTERRUPTED_TASK_STATES, TERMINAL_TASK_STATES } from './constants.js';
import { cloneSerializable } from '../utils/clone.js';

function clone(value) {
    return cloneSerializable(value);
}

function eventIdentity(event) {
    return event?.metadata?.platformEventId || event?.metadata?.platform_event_id || null;
}

function unwrap(result) {
    if (!result || typeof result !== 'object') return null;
    for (const kind of ['statusUpdate', 'artifactUpdate', 'task', 'message']) {
        if (result[kind] && typeof result[kind] === 'object') return { kind, value: result[kind] };
    }
    if (typeof result.id === 'string' && result.status && typeof result.status === 'object') {
        return { kind: 'task', value: result };
    }
    return null;
}

function taskIdOf(kind, value) {
    if (kind === 'task') return value.id;
    return value.taskId || value.task_id || value.id || null;
}

function contextIdOf(value) {
    return value.contextId || value.context_id || null;
}

function mergeMetadata(current, update) {
    if (!current || typeof current !== 'object') return clone(update || {});
    if (!update || typeof update !== 'object') return clone(current);
    const merged = { ...clone(current) };
    for (const [key, value] of Object.entries(update)) {
        merged[key] = (
            value && typeof value === 'object' && !Array.isArray(value)
            && merged[key] && typeof merged[key] === 'object' && !Array.isArray(merged[key])
        ) ? mergeMetadata(merged[key], value) : clone(value);
    }
    return merged;
}

function mergeArtifact(existing, incoming, append) {
    if (!existing || !append) return clone(incoming);
    if (existing.artifactId !== incoming.artifactId) {
        throw new Error('flow-ui: artifact identity changed while appending');
    }
    return {
        ...clone(existing),
        parts: [...(existing.parts || []).map(clone), ...(incoming.parts || []).map(clone)],
        metadata: mergeMetadata(existing.metadata, incoming.metadata),
    };
}

export function createA2ATaskAccumulator() {
    return {
        tasksById: {},
        taskOrder: [],
        eventFingerprints: new Map(),
    };
}

function ensureTask(accumulator, taskId, contextId) {
    const existing = accumulator.tasksById[taskId];
    if (existing) {
        if (contextId && existing.contextId && existing.contextId !== contextId) {
            throw new Error('flow-ui: A2A event context identity changed');
        }
        return existing;
    }
    const task = {
        id: taskId,
        contextId,
        status: null,
        history: [],
        artifacts: [],
        artifactsById: {},
        closedArtifactIds: new Set(),
        metadata: {},
        latestSequence: 0,
    };
    accumulator.tasksById[taskId] = task;
    accumulator.taskOrder.push(taskId);
    return task;
}

function rememberEvent(accumulator, event, identity) {
    if (!identity) return false;
    const fingerprint = JSON.stringify(event);
    const previous = accumulator.eventFingerprints.get(identity);
    if (previous !== undefined) {
        if (previous !== fingerprint) throw new Error(`flow-ui: A2A event collision ${identity}`);
        return true;
    }
    accumulator.eventFingerprints.set(identity, fingerprint);
    return false;
}

export function applyA2AFrame(accumulator, frame) {
    if (frame?.error) throw new Error(frame.error.message || 'A2A stream error');
    const wrapped = unwrap(frame?.result || frame);
    if (!wrapped) return { accumulator, changedTaskId: null, frameKind: null };
    const { kind, value } = wrapped;
    const identity = eventIdentity(value);
    if (rememberEvent(accumulator, value, identity)) {
        return { accumulator, changedTaskId: taskIdOf(kind, value), frameKind: kind };
    }

    if (kind === 'message') {
        return { accumulator, changedTaskId: null, frameKind: kind, message: clone(value) };
    }
    if (kind === 'task') {
        const taskId = taskIdOf(kind, value);
        if (!taskId) throw new Error('flow-ui: Task snapshot has no id');
        const target = ensureTask(accumulator, taskId, contextIdOf(value));
        target.contextId = contextIdOf(value) || target.contextId;
        target.status = clone(value.status || null);
        target.history = (value.history || []).map(clone);
        target.metadata = clone(value.metadata || {});
        target.artifacts = [];
        target.artifactsById = {};
        for (const artifact of value.artifacts || []) {
            const id = artifact.artifactId || artifact.artifact_id;
            if (!id) continue;
            const snapshot = clone(artifact);
            target.artifacts.push(snapshot);
            target.artifactsById[id] = snapshot;
        }
        return { accumulator, changedTaskId: taskId, frameKind: kind };
    }

    const taskId = taskIdOf(kind, value);
    const contextId = contextIdOf(value);
    if (!taskId || !contextId) throw new Error(`flow-ui: ${kind} scope is incomplete`);
    const task = ensureTask(accumulator, taskId, contextId);
    const sequence = Number(value?.metadata?.platformSequence || 0);
    if (Number.isFinite(sequence)) task.latestSequence = Math.max(task.latestSequence, sequence);
    if (kind === 'statusUpdate') {
        task.status = clone(value.status || null);
        if (value.metadata && typeof value.metadata === 'object') {
            task.metadata = mergeMetadata(task.metadata, value.metadata);
        }
    } else {
        const artifact = value.artifact;
        const id = artifact?.artifactId || artifact?.artifact_id;
        if (!id) throw new Error('flow-ui: artifact update has no artifactId');
        if (task.closedArtifactIds.has(id)) throw new Error(`flow-ui: artifact ${id} is closed`);
        const merged = mergeArtifact(task.artifactsById[id], artifact, value.append === true);
        if (!task.artifactsById[id]) task.artifacts.push(merged);
        else task.artifacts = task.artifacts.map((item) => (
            (item.artifactId || item.artifact_id) === id ? merged : item
        ));
        task.artifactsById[id] = merged;
        if (value.lastChunk === true || value.last_chunk === true) task.closedArtifactIds.add(id);
    }
    return { accumulator, changedTaskId: taskId, frameKind: kind };
}

export function taskBoundary(task) {
    const state = task?.status?.state;
    if (TERMINAL_TASK_STATES.has(state)) return 'terminal';
    if (INTERRUPTED_TASK_STATES.has(state)) return 'interrupted';
    return null;
}

export function serializableTask(task) {
    if (!task) return null;
    const copy = clone(task);
    copy.closedArtifactIds = [...task.closedArtifactIds];
    return copy;
}
