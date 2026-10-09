import { INTERRUPTED_TASK_STATES, TERMINAL_TASK_STATES } from './constants.js';

export type A2aJsonObject = Record<string, unknown>;

export interface A2aAccumulatedTask extends A2aJsonObject {
    id: string;
    contextId: string | null;
    status: unknown;
    history: unknown[];
    artifacts: A2aJsonObject[];
    artifactsById: Record<string, A2aJsonObject>;
    closedArtifactIds: Set<string>;
    metadata: A2aJsonObject;
}

export interface A2aTaskAccumulator {
    tasksById: Record<string, A2aAccumulatedTask>;
    taskOrder: string[];
    eventFingerprints: Map<string, string>;
}

export interface A2aFrameResult {
    accumulator: A2aTaskAccumulator;
    changedTaskId: string | null;
    frameKind: string | null;
    message?: A2aJsonObject;
}

type A2aWrappedKind = 'statusUpdate' | 'artifactUpdate' | 'task' | 'message';

/** Глубокая копия JSON-значений протокола: аккумулятор не делит объекты с входящими кадрами. */
function clone<T>(value: T): T {
    if (value === null || typeof value !== 'object') return value;
    return globalThis.structuredClone(value);
}

function eventIdentity(event: A2aJsonObject | null | undefined): unknown {
    const metadata = event?.metadata as A2aJsonObject | undefined;
    return metadata?.platformEventId || metadata?.platform_event_id || null;
}

function unwrap(result: unknown): { kind: A2aWrappedKind; value: A2aJsonObject } | null {
    if (!result || typeof result !== 'object') return null;
    const record = result as A2aJsonObject;
    for (const kind of ['statusUpdate', 'artifactUpdate', 'task', 'message'] as const) {
        const value = record[kind];
        if (value && typeof value === 'object') return { kind, value: value as A2aJsonObject };
    }
    if (typeof record.id === 'string' && record.status && typeof record.status === 'object') {
        return { kind: 'task', value: record };
    }
    return null;
}

function taskIdOf(kind: A2aWrappedKind, value: A2aJsonObject): string | null {
    if (kind === 'task') return typeof value.id === 'string' ? value.id : null;
    const id = value.taskId || value.task_id || value.id;
    return typeof id === 'string' ? id : null;
}

function contextIdOf(value: A2aJsonObject): string | null {
    const id = value.contextId || value.context_id;
    return typeof id === 'string' ? id : null;
}

function mergeMetadata(current: unknown, update: unknown): A2aJsonObject {
    if (!current || typeof current !== 'object') return clone(update || {}) as A2aJsonObject;
    if (!update || typeof update !== 'object') return clone(current) as A2aJsonObject;
    const merged = { ...clone(current) } as A2aJsonObject;
    for (const [key, value] of Object.entries(update as A2aJsonObject)) {
        const existing = merged[key];
        merged[key] = (
            value && typeof value === 'object' && !Array.isArray(value)
            && existing && typeof existing === 'object' && !Array.isArray(existing)
        ) ? mergeMetadata(existing, value) : clone(value);
    }
    return merged;
}

function mergeArtifact(existing: A2aJsonObject | undefined, incoming: A2aJsonObject, append: boolean): A2aJsonObject {
    if (!existing || !append) return clone(incoming);
    if (existing.artifactId !== incoming.artifactId) {
        throw new Error('flow-ui: artifact identity changed while appending');
    }
    const existingParts = Array.isArray(existing.parts) ? existing.parts : [];
    const incomingParts = Array.isArray(incoming.parts) ? incoming.parts : [];
    return {
        ...clone(existing),
        parts: [...existingParts.map(clone), ...incomingParts.map(clone)],
        metadata: mergeMetadata(existing.metadata, incoming.metadata),
    };
}

export function createA2ATaskAccumulator(): A2aTaskAccumulator {
    return {
        tasksById: {},
        taskOrder: [],
        eventFingerprints: new Map(),
    };
}

function ensureTask(accumulator: A2aTaskAccumulator, taskId: string, contextId: string | null): A2aAccumulatedTask {
    const existing = accumulator.tasksById[taskId];
    if (existing) {
        if (contextId && existing.contextId && existing.contextId !== contextId) {
            throw new Error('flow-ui: A2A event context identity changed');
        }
        return existing;
    }
    const task: A2aAccumulatedTask = {
        id: taskId,
        contextId,
        status: null,
        history: [],
        artifacts: [],
        artifactsById: {},
        closedArtifactIds: new Set(),
        metadata: {},
    };
    accumulator.tasksById[taskId] = task;
    accumulator.taskOrder.push(taskId);
    return task;
}

function rememberEvent(accumulator: A2aTaskAccumulator, event: A2aJsonObject, identity: unknown): boolean {
    if (!identity) return false;
    const fingerprint = JSON.stringify(event);
    const previous = accumulator.eventFingerprints.get(String(identity));
    if (previous !== undefined) {
        if (previous !== fingerprint) throw new Error(`flow-ui: A2A event collision ${String(identity)}`);
        return true;
    }
    accumulator.eventFingerprints.set(String(identity), fingerprint);
    return false;
}

export function applyA2AFrame(accumulator: A2aTaskAccumulator, frame: A2aJsonObject | null | undefined): A2aFrameResult {
    if (frame?.error) throw new Error((frame.error as A2aJsonObject).message as string || 'A2A stream error');
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
        target.history = (Array.isArray(value.history) ? value.history : []).map(clone);
        target.metadata = clone((value.metadata || {}) as A2aJsonObject);
        target.artifacts = [];
        target.artifactsById = {};
        for (const artifact of Array.isArray(value.artifacts) ? value.artifacts : []) {
            if (!artifact || typeof artifact !== 'object') continue;
            const record = artifact as A2aJsonObject;
            const id = record.artifactId || record.artifact_id;
            if (typeof id !== 'string' || !id) continue;
            const snapshot = clone(record);
            target.artifacts.push(snapshot);
            target.artifactsById[id] = snapshot;
        }
        return { accumulator, changedTaskId: taskId, frameKind: kind };
    }

    const taskId = taskIdOf(kind, value);
    const contextId = contextIdOf(value);
    if (!taskId || !contextId) throw new Error(`flow-ui: ${kind} scope is incomplete`);
    const task = ensureTask(accumulator, taskId, contextId);
    if (kind === 'statusUpdate') {
        task.status = clone(value.status || null);
        if (value.metadata && typeof value.metadata === 'object') {
            task.metadata = mergeMetadata(task.metadata, value.metadata);
        }
    } else {
        const artifact = (value.artifact && typeof value.artifact === 'object') ? value.artifact as A2aJsonObject : null;
        const id = artifact?.artifactId || artifact?.artifact_id;
        if (typeof id !== 'string' || !id || !artifact) throw new Error('flow-ui: artifact update has no artifactId');
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

export function taskBoundary(task: { status?: unknown } | null | undefined): 'terminal' | 'interrupted' | null {
    const state = (task?.status as A2aJsonObject | undefined)?.state;
    if (typeof state === 'string' && TERMINAL_TASK_STATES.has(state)) return 'terminal';
    if (typeof state === 'string' && INTERRUPTED_TASK_STATES.has(state)) return 'interrupted';
    return null;
}

export function serializableTask(task: A2aAccumulatedTask | null | undefined): A2aJsonObject | null {
    if (!task) return null;
    const copy = clone(task) as A2aJsonObject;
    copy.closedArtifactIds = [...task.closedArtifactIds];
    return copy;
}
